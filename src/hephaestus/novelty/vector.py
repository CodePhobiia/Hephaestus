"""Shared novelty-vector surfaces used across search, branching, and evaluation."""

from __future__ import annotations

from dataclasses import dataclass


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class NoveltyVector:
    """Visible novelty dimensions used instead of a single opaque scalar."""

    banality_similarity: float = 0.0
    prior_art_similarity: float = 0.0
    branch_family_distance: float = 0.0
    source_domain_distance: float = 0.0
    mechanism_distance: float = 0.0
    evaluator_gain: float = 0.0
    subtraction_delta: float = 0.0
    critic_disagreement: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "banality_similarity": self.banality_similarity,
            "prior_art_similarity": self.prior_art_similarity,
            "branch_family_distance": self.branch_family_distance,
            "source_domain_distance": self.source_domain_distance,
            "mechanism_distance": self.mechanism_distance,
            "evaluator_gain": self.evaluator_gain,
            "subtraction_delta": self.subtraction_delta,
            "critic_disagreement": self.critic_disagreement,
        }

    def creativity_score(self) -> float:
        """Return a bounded creativity score that rewards distance plus viability."""
        return _clamp01(
            0.16 * (1.0 - self.banality_similarity)
            + 0.12 * (1.0 - self.prior_art_similarity)
            + 0.12 * self.branch_family_distance
            + 0.14 * self.source_domain_distance
            + 0.16 * self.mechanism_distance
            + 0.12 * self.evaluator_gain
            + 0.10 * self.subtraction_delta
            + 0.08 * self.critic_disagreement
        )

    def load_bearing_score(self) -> float:
        """Return the novelty score with extra weight on viability-bearing terms."""
        return _clamp01(
            0.20 * (1.0 - self.banality_similarity)
            + 0.12 * (1.0 - self.prior_art_similarity)
            + 0.12 * self.mechanism_distance
            + 0.22 * self.evaluator_gain
            + 0.22 * self.subtraction_delta
            + 0.12 * self.critic_disagreement
        )


__all__ = ["NoveltyVector"]
