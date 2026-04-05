"""Async SDK client for programmatic access to Hephaestus."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InventionResult:
    """Simplified result from a pipeline run."""

    invention_name: str
    source_domain: str
    domain_distance: float
    structural_fidelity: float
    novelty_score: float
    key_insight: str
    architecture: str
    limitations: list[str]
    verdict: str
    feasibility: str
    cost_usd: float
    duration_seconds: float
    raw_report: Any = None


@dataclass
class HephaestusClient:
    """Async client for running inventions programmatically.

    Usage::

        client = HephaestusClient(anthropic_key="sk-...", openai_key="sk-...")
        result = await client.invent("I need a load balancer")
        print(result.invention_name)
    """

    anthropic_key: str | None = None
    openai_key: str | None = None
    model: str = "both"
    depth: int = 3
    candidates: int = 8
    intensity: str = "STANDARD"
    output_mode: str = "MECHANISM"
    exploration_mode: str = "standard"
    pressure_translate_enabled: bool = True
    pressure_search_mode: str = "adaptive"

    async def invent(self, problem: str, **overrides: Any) -> InventionResult:
        """Run the full genesis pipeline and return a simplified result."""
        from hephaestus.cli.main import _build_genesis_config
        from hephaestus.core.genesis import Genesis

        config = _build_genesis_config(
            model=overrides.get("model", self.model),
            depth=overrides.get("depth", self.depth),
            candidates=overrides.get("candidates", self.candidates),
            domain=overrides.get("domain"),
            anthropic_key=self.anthropic_key,
            openai_key=self.openai_key,
            divergence_intensity=overrides.get("intensity", self.intensity),
            output_mode=overrides.get("output_mode", self.output_mode),
            exploration_mode=overrides.get("exploration_mode", self.exploration_mode),
            pressure_translate=overrides.get("pressure_translate", self.pressure_translate_enabled),
            pressure_search_mode=overrides.get("pressure_search_mode", self.pressure_search_mode),
        )

        genesis = Genesis(config)
        report = await genesis.invent(problem)
        return self._extract_result(report)

    async def invent_stream(self, problem: str, **overrides: Any) -> AsyncIterator[dict[str, Any]]:
        """Stream pipeline updates as dicts."""
        from hephaestus.cli.main import _build_genesis_config
        from hephaestus.core.genesis import Genesis

        config = _build_genesis_config(
            model=overrides.get("model", self.model),
            depth=overrides.get("depth", self.depth),
            candidates=overrides.get("candidates", self.candidates),
            domain=overrides.get("domain"),
            anthropic_key=self.anthropic_key,
            openai_key=self.openai_key,
            divergence_intensity=overrides.get("intensity", self.intensity),
            output_mode=overrides.get("output_mode", self.output_mode),
            exploration_mode=overrides.get("exploration_mode", self.exploration_mode),
            pressure_translate=overrides.get("pressure_translate", self.pressure_translate_enabled),
            pressure_search_mode=overrides.get("pressure_search_mode", self.pressure_search_mode),
        )

        genesis = Genesis(config)
        async for update in genesis.invent_stream(problem):
            yield {
                "stage": update.stage.name,
                "message": update.message,
                "data": update.data,
            }

    def _extract_result(self, report: Any) -> InventionResult:
        """Extract a simplified result from a full genesis report."""
        top = report.top_invention
        if not top:
            return InventionResult(
                invention_name="No invention produced",
                source_domain="N/A",
                domain_distance=0.0,
                structural_fidelity=0.0,
                novelty_score=0.0,
                key_insight="",
                architecture="",
                limitations=[],
                verdict="FAILED",
                feasibility="N/A",
                cost_usd=report.total_cost_usd,
                duration_seconds=report.total_duration_seconds,
                raw_report=report,
            )

        trans = top.translation
        return InventionResult(
            invention_name=top.invention_name,
            source_domain=top.source_domain,
            domain_distance=getattr(trans.source_candidate, "domain_distance", 0.0),
            structural_fidelity=getattr(trans.source_candidate, "structural_fidelity", 0.0),
            novelty_score=top.novelty_score,
            key_insight=getattr(trans, "key_insight", ""),
            architecture=getattr(trans, "architecture", ""),
            limitations=getattr(trans, "limitations", []),
            verdict=top.verdict,
            feasibility=top.feasibility_rating,
            cost_usd=report.total_cost_usd,
            duration_seconds=report.total_duration_seconds,
            raw_report=report,
        )


__all__ = ["HephaestusClient", "InventionResult"]
