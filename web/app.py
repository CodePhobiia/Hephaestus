"""
Hephaestus Web Interface — FastAPI Server.

Provides a streaming SSE interface to the Hephaestus invention pipeline,
a static web UI, and REST endpoints for lens browsing.

Environment Variables
---------------------
ANTHROPIC_API_KEY:  Anthropic API key (required unless using gpt5 model).
OPENAI_API_KEY:     OpenAI API key (required unless using opus model).
HEPH_HOST:          Bind host (default: 0.0.0.0).
HEPH_PORT:          Bind port (default: 8000).
HEPH_LOG_LEVEL:     Log level (default: info).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hephaestus.execution.models import RunRecord, RunStatus
from hephaestus.execution.orchestrator import OrchestratorConfig, RunOrchestrator
from hephaestus.execution.run_store import create_run_store
from web.forgebase_api import forgebase_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auth / rate-limit / concurrency primitives
# ---------------------------------------------------------------------------

_HEPH_API_KEY = os.environ.get("HEPH_API_KEY", "")
_RATE_LIMIT_RPM = int(os.environ.get("HEPH_RATE_LIMIT_RPM", "10"))
_MAX_CONCURRENT = int(os.environ.get("HEPH_MAX_CONCURRENT", "2"))
_invention_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# Simple in-memory token bucket for rate limiting
_rate_bucket: list[float] = []

# Global spend guardrails (reset manually or per restart)
_SPEND_LIMIT_USD = float(os.environ.get("HEPH_SPEND_LIMIT_USD", "20.0"))
_global_spend_usd = 0.0

def _check_spend_limit() -> bool:
    """Return True if within the global spend boundary."""
    return _global_spend_usd < _SPEND_LIMIT_USD


def _check_rate_limit() -> bool:
    """Return True if the request is within rate limits."""
    now = time.time()
    window = 60.0
    # Prune expired entries
    while _rate_bucket and _rate_bucket[0] < now - window:
        _rate_bucket.pop(0)
    if len(_rate_bucket) >= _RATE_LIMIT_RPM:
        return False
    _rate_bucket.append(now)
    return True


def _check_auth(request: Request) -> bool:
    """Validate API key if HEPH_API_KEY is configured."""
    if not _HEPH_API_KEY:
        return True  # No key configured — open access
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() == _HEPH_API_KEY
    return False


def _codex_auth_available() -> bool:
    auth_path = Path.home() / ".codex" / "auth.json"
    return auth_path.is_file() and shutil.which("node") is not None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"

# ---------------------------------------------------------------------------
# App factory / Orchestrator Initialization
# ---------------------------------------------------------------------------

_pubsub: dict[str, list[asyncio.Queue]] = {}
_RUN_ARTIFACT_DIR = Path(
    os.environ.get(
        "HEPH_RUN_ARTIFACT_DIR",
        str(Path.home() / ".hephaestus" / "run_artifacts"),
    )
)

# Production DB toggle based on env
if "HEPHAESTUS_DATABASE_URL" in os.environ:
    _store = create_run_store(backend="postgres", dsn=os.environ["HEPHAESTUS_DATABASE_URL"])
else:
    _store = create_run_store(backend="sqlite", db_path="hephaestus_dev.db")

_orchestrator = RunOrchestrator(_store, OrchestratorConfig())


def _artifact_path(run_id: str) -> Path:
    return _RUN_ARTIFACT_DIR / f"{run_id}.json"


def _persist_run_artifact(run_id: str, report: Any) -> str:
    """Persist a replayable terminal artifact for a completed run."""
    _RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "saved_at": datetime.now(UTC).isoformat(),
        "report": json.loads(json.dumps(report.to_dict(), default=str)),
        "web_result": _format_report(report),
        "summary": getattr(report, "summary", lambda: "")(),
    }
    path = _artifact_path(run_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _load_run_artifact(result_ref: str | None) -> dict[str, Any] | None:
    if not result_ref:
        return None
    path = Path(result_ref)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

async def _pipeline_fn(record: RunRecord, cancel_event: asyncio.Event) -> str | None:
    """Background worker logic for runs."""
    try:
        from hephaestus.core.cross_model import get_model_preset
        from hephaestus.core.genesis import Genesis, GenesisConfig

        cfg_dict = dict(record.config_snapshot)
        model_req = str(cfg_dict.pop("model", "both") or "both").lower()
        preset_key = {"opus": "opus", "gpt5": "gpt", "codex": "codex"}.get(model_req, "both")
        models = get_model_preset(preset_key)

        cfg = GenesisConfig(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            use_codex_cli=(model_req == "codex"),
            num_candidates=cfg_dict.get("candidates", 8),
            num_translations=min(3, cfg_dict.get("candidates", 8)),
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            domain_hint=cfg_dict.get("domain_hint"),
            depth=cfg_dict.get("depth", 3),
            exploration_mode=cfg_dict.get("exploration_mode", "standard").lower(),
            pressure_translate_enabled=cfg_dict.get("pressure_translate_enabled", True),
            pressure_search_mode=cfg_dict.get("pressure_search_mode", "adaptive").lower(),
        )

        genesis = Genesis(cfg)
        result_ref = None

        async for update in genesis.invent_stream(record.problem):
            if cancel_event.is_set():
                break

            await _store.update_stage(record.run_id, update.stage.name)

            queues = _pubsub.get(record.run_id, [])
            for q in queues:
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(update)

            if update.stage.name == "COMPLETE" and update.data:
                result_ref = _persist_run_artifact(record.run_id, update.data)

        for q in _pubsub.get(record.run_id, []):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait("EOF")

        return result_ref
    except Exception as exc:
        logger.exception("Pipeline unhandled error")
        for q in _pubsub.get(record.run_id, []):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(exc)
        raise exc

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _HEPH_API_KEY:
        logger.warning(
            "HEPH_API_KEY is not set — API is unauthenticated. "
            "Set HEPH_API_KEY to require Bearer token auth."
        )
    await _orchestrator.start()
    await _orchestrator.start_dispatcher(_pipeline_fn)
    yield
    await _orchestrator.stop()
    # Shutdown ForgeBase if it was initialized
    from web.forgebase_deps import shutdown_forgebase
    await shutdown_forgebase()

app = FastAPI(
    title="Hephaestus Invention Engine",
    description="The AI that invents things that don't exist yet.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS: Restrict to explicitly configured origins (never use wildcard with credentials)
_HEPH_ALLOWED_ORIGINS = os.environ.get("HEPH_ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_HEPH_ALLOWED_ORIGINS,
    allow_credentials=False,  # Only enable if auth cookies/tokens in use; currently session-based
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Serve static files if directory exists
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

app.include_router(forgebase_router)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class InventRequest(BaseModel):
    """Request body for the /api/invent endpoint."""

    problem: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Problem to invent a solution for",
    )
    model: str = Field(default="both", description="Model selection: both | opus | gpt5 | codex")
    candidates: int = Field(default=8, ge=2, le=20, description="Number of search candidates")
    domain_hint: str | None = Field(default=None, description="Soft domain bias constraint")
    depth: int = Field(default=3, ge=1, le=10, description="Exploration bounds and scale")
    exploration_mode: str = Field(default="standard", description="standard or forge modes")
    pressure_translate_enabled: bool = Field(default=True, description="Applies rigorous deepforge mechanics")
    pressure_search_mode: str = Field(default="adaptive", description="off, adaptive, or always")


class HealthResponse(BaseModel):
    status: str
    version: str
    anthropic_configured: bool
    openai_configured: bool


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: Any) -> str:
    """Format a server-sent event."""
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def _sse_error(message: str, stage: str = "error") -> str:
    return _sse_event("error", {"stage": stage, "message": message})


# ---------------------------------------------------------------------------
# Stage display config
# ---------------------------------------------------------------------------

_STAGE_CONFIG: dict[str, dict[str, str]] = {
    "STARTING": {"label": "Initializing forge...", "icon": "⚒️"},
    "DECOMPOSING": {"label": "Extracting structural form...", "icon": "🔬"},
    "DECOMPOSED": {"label": "Structure extracted", "icon": "✓"},
    "SEARCHING": {"label": "Scanning cross-domain space...", "icon": "🔭"},
    "SEARCHED": {"label": "Candidates discovered", "icon": "✓"},
    "SCORING": {"label": "Scoring structural fidelity...", "icon": "⚖️"},
    "SCORED": {"label": "Candidates ranked", "icon": "✓"},
    "TRANSLATING": {"label": "Translating with interference active...", "icon": "🔀"},
    "TRANSLATED": {"label": "Translations complete", "icon": "✓"},
    "VERIFYING": {"label": "Adversarial verification...", "icon": "🛡️"},
    "VERIFIED": {"label": "Inventions verified", "icon": "✓"},
    "COMPLETE": {"label": "Forge complete", "icon": "🔥"},
    "FAILED": {"label": "Pipeline failed", "icon": "✗"},
}


def _format_stage_event(stage_name: str, message: str, elapsed: float) -> dict[str, Any]:
    config = _STAGE_CONFIG.get(stage_name, {"label": stage_name, "icon": "◦"})
    return {
        "stage": stage_name,
        "label": config["label"],
        "icon": config["icon"],
        "message": message,
        "elapsed_seconds": round(elapsed, 1),
    }


def _format_report(report: Any) -> dict[str, Any]:
    """Serialize an InventionReport to a JSON-safe dict for the web UI."""
    top = report.top_invention
    if top is None:
        return {"error": "No inventions produced"}

    # Build mapping table
    mapping_rows = []
    if hasattr(top, "translation") and hasattr(top.translation, "mapping"):
        for elem in top.translation.mapping:
            mapping_rows.append({
                "source": getattr(elem, "source_element", ""),
                "target": getattr(elem, "target_element", ""),
                "mechanism": getattr(elem, "mechanism", ""),
            })

    # Alternatives
    alternatives = []
    for inv in report.alternative_inventions[:3]:
        novelty_score = getattr(inv, "novelty_score", None)
        alternatives.append({
            "name": getattr(inv, "invention_name", ""),
            "source_domain": getattr(inv, "source_domain", ""),
            "novelty_score": round(float(novelty_score or 0.0), 3),
            "feasibility": getattr(inv, "feasibility_rating", ""),
        })

    # Prior art
    prior_art = None
    if hasattr(top, "prior_art_status"):
        prior_art = {
            "status": top.prior_art_status,
            "notes": getattr(top, "verification_notes", ""),
        }

    # Novelty proof
    novelty_proof = None
    if hasattr(top, "translation") and hasattr(top.translation, "mathematical_proof"):
        novelty_proof = top.translation.mathematical_proof

    novelty_score = getattr(top, "novelty_score", None)
    structural_validity = getattr(top, "structural_validity", None)
    return {
        "invention_name": getattr(top, "invention_name", "Unknown"),
        "source_domain": getattr(top, "source_domain", ""),
        "novelty_score": round(float(novelty_score or 0.0), 3),
        "structural_validity": round(float(structural_validity or 0.0), 3),
        "feasibility_rating": getattr(top, "feasibility_rating", ""),
        "verdict": getattr(getattr(top, "adversarial_result", None), "verdict", ""),
        "key_insight": getattr(getattr(top, "translation", None), "key_insight", ""),
        "architecture": getattr(getattr(top, "translation", None), "architecture", ""),
        "limitations": getattr(getattr(top, "translation", None), "limitations", []),
        "implementation_notes": getattr(
            getattr(top, "translation", None), "implementation_notes", ""
        ),
        "mapping": mapping_rows,
        "alternatives": alternatives,
        "prior_art": prior_art,
        "novelty_proof": novelty_proof,
        "adversarial_notes": getattr(
            getattr(top, "adversarial_result", None), "strongest_objection", ""
        ),
        "cost_usd": round(report.total_cost_usd, 4),
        "cost_breakdown": (
            report.cost_breakdown.to_dict() if hasattr(report.cost_breakdown, "to_dict") else {}
        ),
        "duration_seconds": round(getattr(report, "total_duration_seconds", 0.0), 1),
        "models": getattr(report, "model_config", {}),
        "native_domain": getattr(getattr(report, "structure", None), "native_domain", ""),
        "mathematical_shape": getattr(getattr(report, "structure", None), "mathematical_shape", ""),
    }


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness check — returns 200 if the process is up."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        anthropic_configured=bool(os.environ.get("ANTHROPIC_API_KEY")),
        openai_configured=bool(os.environ.get("OPENAI_API_KEY")),
    )


@app.get("/api/ready", tags=["meta"])
async def readiness() -> JSONResponse:
    """Readiness check — verifies lens loading and basic configuration."""
    checks: dict[str, bool] = {
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "codex_auth": _codex_auth_available(),
    }
    try:
        from hephaestus.lenses.loader import LensLoader
        loader = LensLoader()
        lens_list = loader.list_available(skip_errors=True)
        checks["lenses_loaded"] = len(lens_list) > 0
        checks["lens_count"] = len(lens_list)
    except Exception:
        checks["lenses_loaded"] = False

    ready = checks.get("lenses_loaded", False) and (
        checks.get("anthropic_key", False)
        or checks.get("openai_key", False)
        or checks.get("codex_auth", False)
    )
    return JSONResponse(
        content={"ready": ready, "checks": checks},
        status_code=200 if ready else 503,
    )


@app.get("/api/lenses", tags=["lenses"])
async def list_lenses() -> JSONResponse:
    """List all available cognitive lenses in the library."""
    try:
        from hephaestus.lenses.loader import LensLoader
        loader = LensLoader()
        lenses = loader.list_available(skip_errors=True)
        return JSONResponse(content={"lenses": lenses, "count": len(lenses)})
    except Exception as exc:
        logger.exception("Failed to list lenses")
        raise HTTPException(status_code=500, detail=f"Failed to load lenses: {exc}") from exc


@app.post("/api/runs", tags=["invention"])
async def create_run(request_body: InventRequest, request: Request) -> JSONResponse:
    """Submit a new Hephaestus invention pipeline run to the durable orchestrator."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not _check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    if not _check_spend_limit():
        raise HTTPException(status_code=402, detail="Global spend limit reached.")

    try:
        record = await _orchestrator.submit(
            problem=request_body.problem,
            config=request_body.model_dump(),
        )
        return JSONResponse(
            content={"run_id": record.run_id, "status": record.status.value},
            status_code=202,
        )
    except ValueError as e:
        if "Queue full" in str(e):
            raise HTTPException(status_code=429, detail=str(e)) from e
        return JSONResponse(content={"detail": str(e)}, status_code=400)


@app.get("/api/runs/{run_id}/events", tags=["invention"])
async def stream_run_events(run_id: str, request: Request) -> StreamingResponse:
    """Stream events for an active pipeline run."""
    if not _check_auth(request):
        async def _auth_error():
            yield _sse_error("Unauthorized", stage="auth")
        return StreamingResponse(_auth_error(), media_type="text/event-stream", status_code=401)

    record = await _orchestrator.get_run(run_id)
    if not record:
        async def _not_found():
            yield _sse_error("Run not found", stage="error")
        return StreamingResponse(_not_found(), media_type="text/event-stream", status_code=404)
    artifact_payload = _load_run_artifact(record.result_ref)

    # Terminal runs can be replayed entirely from durable state without waiting
    # on the in-memory pubsub fanout.
    if record.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
        async def _replay_terminal():
            for item in record.stage_history:
                stage_name = str(item.get("stage", "UNKNOWN") or "UNKNOWN")
                yield _sse_event(
                    "stage",
                    _format_stage_event(
                        stage_name,
                        f"Replayed stage transition: {stage_name}",
                        0.0,
                    ),
                )
            if record.status == RunStatus.COMPLETED:
                yield _sse_event(
                    "stage",
                    _format_stage_event("COMPLETE", "Replayed completed run", 0.0),
                )
                if artifact_payload is not None:
                    yield _sse_event("result", artifact_payload.get("web_result", {}))
            elif record.status == RunStatus.FAILED:
                yield _sse_event(
                    "stage",
                    _format_stage_event("FAILED", record.error or "Run failed", 0.0),
                )
                yield _sse_error(record.error or "Run failed", stage=record.error_stage or "FAILED")
            else:
                yield _sse_event(
                    "stage",
                    _format_stage_event("FAILED", "Run cancelled", 0.0),
                )
                yield _sse_error("Run cancelled", stage="CANCELLED")
        return StreamingResponse(
            _replay_terminal(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    q = asyncio.Queue(maxsize=100)
    if run_id not in _pubsub:
        _pubsub[run_id] = []
    _pubsub[run_id].append(q)

    async def event_generator():
        try:
            for item in record.stage_history:
                stage_name = str(item.get("stage", "UNKNOWN") or "UNKNOWN")
                yield _sse_event(
                    "stage",
                    _format_stage_event(
                        stage_name,
                        f"Replayed stage transition: {stage_name}",
                        0.0,
                    ),
                )
            while True:
                if await request.is_disconnected():
                    break

                try:
                    update = await asyncio.wait_for(q.get(), timeout=2.0)
                    if update == "EOF":
                        break
                    if isinstance(update, Exception):
                        yield _sse_error(str(update), stage="FAILED")
                        break

                    stage_name = update.stage.name
                    event_data = _format_stage_event(
                        stage_name, update.message, update.elapsed_seconds
                    )

                    if stage_name == "COMPLETE":
                        yield _sse_event("stage", event_data)
                        try:
                            result_data = _format_report(update.data)
                            yield _sse_event("result", result_data)
                        except Exception as fmt_exc:
                            yield _sse_error(f"Result formatting error: {fmt_exc}")
                    elif stage_name == "FAILED":
                        yield _sse_event("stage", event_data)
                        yield _sse_error(update.message, stage=stage_name)
                    else:
                        yield _sse_event("stage", event_data)

                except TimeoutError:
                    yield ": keepalive\\n\\n"
        finally:
            if run_id in _pubsub:
                try:
                    _pubsub[run_id].remove(q)
                    if not _pubsub[run_id]:
                        del _pubsub[run_id]
                except ValueError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Static / UI routes
# ---------------------------------------------------------------------------
# Production API endpoints — metrics, providers, runs
# ---------------------------------------------------------------------------


@app.get("/api/metrics", tags=["observability"])
async def prometheus_metrics() -> StreamingResponse:
    """Prometheus-compatible metrics endpoint."""
    from hephaestus.telemetry.metrics import get_metrics

    content = get_metrics().export_prometheus()
    return StreamingResponse(
        iter([content]),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/providers", tags=["observability"])
async def provider_health(request: Request) -> JSONResponse:
    """Return provider availability summary."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    from hephaestus.providers import build_default_registry
    from hephaestus.providers.diagnostics import provider_health_summary

    registry = build_default_registry()
    return JSONResponse(content=provider_health_summary(registry))


@app.get("/api/runs", tags=["runs"])
async def list_runs(
    request: Request,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """List pipeline runs with optional status filter."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    status_filter = RunStatus(status) if status else None
    runs = await _orchestrator.list_runs(status=status_filter, limit=limit, offset=offset)
    return JSONResponse(content={
        "runs": [r.to_dict() for r in runs],
        "count": len(runs),
    })

@app.get("/api/runs/{run_id}", tags=["runs"])
async def get_run(run_id: str, request: Request) -> JSONResponse:
    """Get a single run's details."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    record = await _orchestrator.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return JSONResponse(content=record.to_dict())

@app.post("/api/runs/{run_id}/cancel", tags=["runs"])
async def cancel_run(run_id: str, request: Request) -> JSONResponse:
    """Cancel a queued or running pipeline run."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    cancelled = await _orchestrator.cancel_run(run_id)
    return JSONResponse(content={"cancelled": cancelled, "run_id": run_id})


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    """Serve the main web UI."""
    index_path = _TEMPLATES / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Web UI not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str) -> HTMLResponse:
    """SPA catch-all — always serve index.html for unknown paths."""
    index_path = _TEMPLATES / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "web.app:app",
        host=os.environ.get("HEPH_HOST", "0.0.0.0"),
        port=int(os.environ.get("HEPH_PORT", "8000")),
        log_level=os.environ.get("HEPH_LOG_LEVEL", "info"),
        reload=False,
    )
