"""Error recovery — graceful partial results and resume support."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineCheckpoint:
    """Checkpoint of pipeline state for resume."""

    problem: str
    stage_completed: int  # 0-5 (0 = not started)
    stage_name: str
    timestamp: str = ""
    structure: Any = None
    candidates: list[Any] = field(default_factory=list)
    scored: list[Any] = field(default_factory=list)
    translations: list[Any] = field(default_factory=list)
    verified: list[Any] = field(default_factory=list)
    error: str = ""
    cost_so_far: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    @property
    def is_complete(self) -> bool:
        return self.stage_completed >= 5

    @property
    def has_partial_results(self) -> bool:
        return self.stage_completed >= 3  # at least scored


@dataclass
class PartialResult:
    """Best available result from a partially completed pipeline."""

    problem: str
    stage_reached: str
    best_candidate: Any | None
    reason: str
    cost_usd: float


def extract_partial_result(checkpoint: PipelineCheckpoint) -> PartialResult | None:
    """Extract the best available result from a failed/interrupted pipeline run.

    If the pipeline got past scoring, we can return the top scored candidate
    even without full translation/verification.
    """
    if checkpoint.stage_completed < 2:
        return None  # Need at least candidates

    best = None
    reason = f"Pipeline stopped at stage {checkpoint.stage_name}"

    if checkpoint.verified:
        best = checkpoint.verified[0]
        reason = f"Verification completed but pipeline interrupted: {checkpoint.error}"
    elif checkpoint.translations:
        best = checkpoint.translations[0]
        reason = f"Translation completed but verification failed: {checkpoint.error}"
    elif checkpoint.scored:
        best = checkpoint.scored[0]
        reason = f"Scoring completed but translation failed: {checkpoint.error}"
    elif checkpoint.candidates:
        best = checkpoint.candidates[0]
        reason = f"Search completed but scoring failed: {checkpoint.error}"

    if best is None:
        return None

    return PartialResult(
        problem=checkpoint.problem,
        stage_reached=checkpoint.stage_name,
        best_candidate=best,
        reason=reason,
        cost_usd=checkpoint.cost_so_far,
    )


def save_checkpoint(checkpoint: PipelineCheckpoint, path: Path) -> None:
    """Save a checkpoint to disk for later resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "problem": checkpoint.problem,
        "stage_completed": checkpoint.stage_completed,
        "stage_name": checkpoint.stage_name,
        "timestamp": checkpoint.timestamp,
        "error": checkpoint.error,
        "cost_so_far": checkpoint.cost_so_far,
    }
    path.write_text(json.dumps(data, indent=2))


def load_checkpoint(path: Path) -> PipelineCheckpoint | None:
    """Load a checkpoint from disk."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return PipelineCheckpoint(
            problem=data["problem"],
            stage_completed=data["stage_completed"],
            stage_name=data["stage_name"],
            timestamp=data.get("timestamp", ""),
            error=data.get("error", ""),
            cost_so_far=data.get("cost_so_far", 0.0),
        )
    except Exception as exc:
        logger.warning("Failed to load checkpoint: %s", exc)
        return None


def format_error_hint(error_msg: str, stage: str = "") -> str:
    """Generate an actionable hint from an error message and stage."""
    msg = error_msg.lower()

    if "rate limit" in msg or "429" in msg:
        return "API rate limit hit. Wait 30-60 seconds and retry, or use a different model."
    if "timeout" in msg or "timed out" in msg:
        return f"Stage '{stage}' timed out. Try reducing --candidates or --depth."
    if "api key" in msg or "auth" in msg:
        return "Check your API keys: ANTHROPIC_API_KEY and/or OPENAI_API_KEY."
    if "connection" in msg:
        return "Network error. Check your internet connection and try again."
    if "no candidates" in msg:
        return "No cross-domain candidates found. Try --domain <hint> or rephrase the problem."
    if "all filtered" in msg:
        return "All candidates were filtered. Try --depth 1 for less aggressive filtering."
    if "decomposition" in msg or "structure" in msg:
        return "Could not extract problem structure. Try rephrasing more concretely."
    if "translation" in msg:
        return "Structural translation failed. Try --intensity AGGRESSIVE for broader search."

    return f"Pipeline failed at {stage}: {error_msg[:100]}"


__all__ = [
    "PipelineCheckpoint",
    "PartialResult",
    "extract_partial_result",
    "save_checkpoint",
    "load_checkpoint",
    "format_error_hint",
]
