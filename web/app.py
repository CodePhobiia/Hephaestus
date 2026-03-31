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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    depth: int = Field(default=3, ge=1, le=10, description="Anti-training pressure depth")
    model: str = Field(default="both", description="Model selection: both | opus | gpt5")
    candidates: int = Field(default=8, ge=2, le=20, description="Number of search candidates")


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
            "novelty_score": round(getattr(inv, "novelty_score", 0.0), 3),
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
        "novelty_score": round(getattr(top, "novelty_score", 0.0), 3),
        "structural_validity": round(getattr(top, "structural_validity", 0.0), 3),
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
    """Health check — always returns 200 if the server is running."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        anthropic_configured=bool(os.environ.get("ANTHROPIC_API_KEY")),
        openai_configured=bool(os.environ.get("OPENAI_API_KEY")),
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
async def invent_stream_endpoint(request_body: InventRequest) -> StreamingResponse:
    """
    Run the Hephaestus invention pipeline and stream SSE progress events.

    Returns a ``text/event-stream`` response. Events:
    - ``stage``  — pipeline stage updates (one per stage)
    - ``result`` — final invention result (JSON)
    - ``error``  — pipeline error
    """
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
            from hephaestus.core.genesis import Genesis, GenesisConfig, PipelineStage

            # Build config from request
            cfg = GenesisConfig(
                anthropic_api_key=anthropic_key,
                openai_api_key=openai_key,
                num_candidates=request_body.candidates,
                num_translations=min(3, request_body.candidates),
            )
            genesis = Genesis(cfg)

            async for update in genesis.invent_stream(request_body.problem):
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
