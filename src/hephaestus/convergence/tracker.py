"""Convergence tracking — detects when repeated runs converge on similar solutions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hephaestus.core.diversity import compute_text_similarity

logger = logging.getLogger(__name__)


@dataclass
class ConvergenceSignal:
    """Result of checking for convergence."""
    is_converging: bool
    similarity_to_prior: float
    converged_count: int  # how many recent runs are similar
    ceiling_domain: str  # domain that keeps appearing
    recommendation: str


@dataclass
class ConvergenceTracker:
    """Tracks invention outputs across runs to detect convergence.

    When the same structural solutions keep appearing, the tracker
    warns the user to change parameters (increase depth, try different
    domain, adjust intensity).
    """

    window_size: int = 5
    similarity_threshold: float = 0.5
    _history: list[dict[str, Any]] = field(default_factory=list)

    def add(self, invention_name: str, source_domain: str, key_insight: str, architecture: str) -> None:
        """Record an invention for convergence tracking."""
        self._history.append({
            "invention_name": invention_name,
            "source_domain": source_domain,
            "key_insight": key_insight,
            "architecture": architecture,
            "text": f"{invention_name} {source_domain} {key_insight} {architecture}",
        })

    def check(self) -> ConvergenceSignal:
        """Check if recent inventions are converging."""
        if len(self._history) < 2:
            return ConvergenceSignal(
                is_converging=False,
                similarity_to_prior=0.0,
                converged_count=0,
                ceiling_domain="",
                recommendation="",
            )

        window = self._history[-self.window_size:]
        latest = window[-1]

        # Compare latest to all prior in window
        similarities = []
        domains: list[str] = []
        for prior in window[:-1]:
            sim = compute_text_similarity(latest["text"], prior["text"])
            similarities.append(sim)
            domains.append(prior["source_domain"])

        max_sim = max(similarities) if similarities else 0.0
        converged = sum(1 for s in similarities if s > self.similarity_threshold)

        # Most common domain in window
        domain_counts: dict[str, int] = {}
        for d in domains + [latest["source_domain"]]:
            domain_counts[d] = domain_counts.get(d, 0) + 1
        ceiling_domain = max(domain_counts, key=domain_counts.get) if domain_counts else ""

        is_converging = converged >= 2 or max_sim > 0.7

        recommendation = ""
        if is_converging:
            if max_sim > 0.7:
                recommendation = (
                    f"Recent inventions are very similar (similarity: {max_sim:.2f}). "
                    "Try: --intensity AGGRESSIVE, --depth 5+, or --domain <new_domain>"
                )
            else:
                recommendation = (
                    f"Solutions converging on {ceiling_domain}. "
                    "Try a different source domain or higher divergence intensity."
                )

        return ConvergenceSignal(
            is_converging=is_converging,
            similarity_to_prior=max_sim,
            converged_count=converged,
            ceiling_domain=ceiling_domain,
            recommendation=recommendation,
        )

    def clear(self) -> None:
        self._history.clear()

    @property
    def count(self) -> int:
        return len(self._history)


__all__ = ["ConvergenceSignal", "ConvergenceTracker"]
