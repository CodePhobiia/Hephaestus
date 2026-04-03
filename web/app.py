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
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Hephaestus Invention Engine",
    description="The AI that invents things that don't exist yet.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

import os  # noqa: E402 — used above and here

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


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class InventRequest(BaseModel):
    """Request body for the /api/invent endpoint."""

    problem: str = Field(..., min_length=5, max_length=4000, description="Problem to invent a solution for")
    model: str = Field(default="both", description="Model selection: both | opus | gpt5")
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
        alternatives.append({
            "name": getattr(inv, "invention_name", ""),
            "source_domain": getattr(inv, "source_domain", ""),
            "novelty_score": round(getattr(inv, "novelty_score", 3) if getattr(inv, "novelty_score", None) is not None else 0.0, 3),
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

    return {
        "invention_name": getattr(top, "invention_name", "Unknown"),
        "source_domain": getattr(top, "source_domain", ""),
        "novelty_score": round(getattr(top, "novelty_score", 3) if getattr(top, "novelty_score", None) is not None else 0.0, 3),
        "structural_validity": round(getattr(top, "structural_validity", 3) if getattr(top, "structural_validity", None) is not None else 0.0, 3),
        "feasibility_rating": getattr(top, "feasibility_rating", ""),
        "verdict": getattr(getattr(top, "adversarial_result", None), "verdict", ""),
        "key_insight": getattr(getattr(top, "translation", None), "key_insight", ""),
        "architecture": getattr(getattr(top, "translation", None), "architecture", ""),
        "limitations": getattr(getattr(top, "translation", None), "limitations", []),
        "implementation_notes": getattr(getattr(top, "translation", None), "implementation_notes", ""),
        "mapping": mapping_rows,
        "alternatives": alternatives,
        "prior_art": prior_art,
        "novelty_proof": novelty_proof,
        "adversarial_notes": getattr(getattr(top, "adversarial_result", None), "strongest_objection", ""),
        "cost_usd": round(report.total_cost_usd, 4),
        "cost_breakdown": report.cost_breakdown.to_dict() if hasattr(report.cost_breakdown, "to_dict") else {},
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
        checks.get("anthropic_key", False) or checks.get("openai_key", False)
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


@app.post("/api/invent", tags=["invention"])
async def invent_stream_endpoint(request_body: InventRequest, request: Request) -> StreamingResponse:
    """
    Run the Hephaestus invention pipeline and stream SSE progress events.

    Requires ``Authorization: Bearer <key>`` if ``HEPH_API_KEY`` is set.

    Returns a ``text/event-stream`` response. Events:
    - ``stage``  — pipeline stage updates (one per stage)
    - ``result`` — final invention result (JSON)
    - ``error``  — pipeline error
    """
    # Auth check
    if not _check_auth(request):
        async def _auth_error():
            yield _sse_error("Unauthorized. Provide a valid API key via Authorization: Bearer <key>.", stage="auth")
        return StreamingResponse(_auth_error(), media_type="text/event-stream", status_code=401)

    # Rate limit check
    if not _check_rate_limit():
        async def _rate_error():
            yield _sse_error(f"Rate limit exceeded ({_RATE_LIMIT_RPM} requests/min). Try again later.", stage="rate_limit")
        return StreamingResponse(_rate_error(), media_type="text/event-stream", status_code=429)

    # Spend guardrail check
    if not _check_spend_limit():
        async def _spend_error():
            yield _sse_error(f"Global spend limit reached (${_SPEND_LIMIT_USD:.2f}). Contact admin.", stage="spend_limit")
        return StreamingResponse(_spend_error(), media_type="text/event-stream", status_code=402)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    # Validate keys for requested model
    model = request_body.model.lower()
    if model in ("opus", "both") and not anthropic_key:
        async def _key_error():
            yield _sse_error("ANTHROPIC_API_KEY is not configured on the server.", stage="config")
        return StreamingResponse(_key_error(), media_type="text/event-stream")

    if model in ("gpt5", "both") and not openai_key:
        async def _key_error2():
            yield _sse_error("OPENAI_API_KEY is not configured on the server.", stage="config")
        return StreamingResponse(_key_error2(), media_type="text/event-stream")

    async def event_generator():
        try:
            # Acquire concurrency semaphore
            async with _invention_semaphore:
                from hephaestus.core.genesis import Genesis, GenesisConfig, PipelineStage
                from hephaestus.core.cross_model import get_model_preset
                
                preset_key = {"opus": "opus", "gpt5": "gpt"}.get(model, "both")
                models = get_model_preset(preset_key)

                # Build config from request
                cfg = GenesisConfig(
                    anthropic_api_key=anthropic_key,
                    openai_api_key=openai_key,
                    num_candidates=request_body.candidates,
                    num_translations=min(3, request_body.candidates),
                    decompose_model=models["decompose"],
                    search_model=models["search"],
                    score_model=models["score"],
                    translate_model=models["translate"],
                    attack_model=models["attack"],
                    defend_model=models["defend"],
                    domain_hint=request_body.domain_hint,
                    depth=request_body.depth,
                    exploration_mode=request_body.exploration_mode.lower(),
                    pressure_translate_enabled=request_body.pressure_translate_enabled,
                    pressure_search_mode=request_body.pressure_search_mode.lower(),
                )
                genesis = Genesis(cfg)

                async for update in genesis.invent_stream(request_body.problem):
                    # Disconnect-aware: stop if the client hung up
                    if await request.is_disconnected():
                        logger.info("Client disconnected — cancelling invention pipeline")
                        return

                    stage_name = update.stage.name
                    event_data = _format_stage_event(
                        stage_name=stage_name,
                        message=update.message,
                        elapsed=update.elapsed_seconds,
                    )

                    if stage_name == "COMPLETE":
                        # Emit the stage update first
                        yield _sse_event("stage", event_data)
                        # Then emit the full result
                        try:
                            result_data = _format_report(update.data)
                            yield _sse_event("result", result_data)
                        except Exception as fmt_exc:
                            logger.exception("Failed to format report")
                            yield _sse_error(f"Result formatting error: {fmt_exc}")
                        return

                    elif stage_name == "FAILED":
                        yield _sse_event("stage", event_data)
                        yield _sse_error(update.message, stage=stage_name)
                        return

                    else:
                        yield _sse_event("stage", event_data)
                        
                    # Update global spend per cycle to prevent infinite spins if metrics exposed
                    if update.data and hasattr(update.data, "total_cost_usd"):
                        global _global_spend_usd
                        _global_spend_usd += getattr(update.data, "total_cost_usd", 0.0)
                        if not _check_spend_limit():
                            yield _sse_error(f"Spend boundary exceeded mid-flight (${_SPEND_LIMIT_USD:.2f}). Aborting.", stage="spend_limit")
                            return

                    # Small yield to flush
                    await asyncio.sleep(0)

        except Exception as exc:
            logger.exception("Unexpected error in invention stream")
            yield _sse_error(f"Server error: {exc}")

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
    from hephaestus.providers.diagnostics import provider_health_summary
    from hephaestus.providers import build_default_registry

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

    from hephaestus.execution.run_store import SQLiteRunStore
    from hephaestus.execution.models import RunStatus

    store = SQLiteRunStore()
    await store.initialize()
    try:
        status_filter = RunStatus(status) if status else None
        runs = await store.list_runs(status=status_filter, limit=limit, offset=offset)
        return JSONResponse(content={
            "runs": [r.to_dict() for r in runs],
            "count": len(runs),
        })
    finally:
        await store.close()


@app.get("/api/runs/{run_id}", tags=["runs"])
async def get_run(run_id: str, request: Request) -> JSONResponse:
    """Get a single run's details."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from hephaestus.execution.run_store import SQLiteRunStore

    store = SQLiteRunStore()
    await store.initialize()
    try:
        record = await store.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return JSONResponse(content=record.to_dict())
    finally:
        await store.close()


@app.post("/api/runs/{run_id}/cancel", tags=["runs"])
async def cancel_run(run_id: str, request: Request) -> JSONResponse:
    """Cancel a queued or running pipeline run."""
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from hephaestus.execution.run_store import SQLiteRunStore

    store = SQLiteRunStore()
    await store.initialize()
    try:
        cancelled = await store.cancel(run_id)
        return JSONResponse(content={"cancelled": cancelled, "run_id": run_id})
    finally:
        await store.close()


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
