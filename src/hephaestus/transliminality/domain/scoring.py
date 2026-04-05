"""Integration scoring for transliminality — geometric mean across six dimensions.

Geometric mean is used because a near-zero failure in one dimension should
not be hidden by strong performance in another.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hephaestus.transliminality.domain.models import IntegrationScoreBreakdown

# Minimum value to prevent log-domain explosions; scores below this floor
# are treated as effectively zero for ranking purposes.
_FLOOR = 1e-6


def _geometric_mean(values: list[float]) -> float:
    """Compute the geometric mean of positive values.

    Uses log-space arithmetic to avoid overflow on large products.
    Any value at or below zero collapses the entire mean to zero.
    """
    if not values:
        return 0.0
    for v in values:
        if v <= 0.0:
            return 0.0
    log_sum = sum(math.log(max(v, _FLOOR)) for v in values)
    return math.exp(log_sum / len(values))


def compute_integration_score(breakdown: IntegrationScoreBreakdown) -> float:
    """Compute the aggregate integration score from a breakdown.

    Returns:
        Geometric mean of the six dimensions, in [0, 1].
    """
    dimensions = [
        breakdown.structural_alignment,
        breakdown.constraint_fidelity,
        breakdown.source_grounding,
        breakdown.counterfactual_dependence,
        breakdown.bidirectional_explainability,
        breakdown.non_ornamental_use,
    ]
    return _geometric_mean(dimensions)


@dataclass(frozen=True)
class FinalScoreBreakdown:
    """Combined final invention score across all axes."""

    novelty: float = 0.0
    integration: float = 0.0
    feasibility: float = 0.0
    verifiability: float = 0.0


def compute_final_score(breakdown: FinalScoreBreakdown) -> float:
    """Compute the final invention ranking score.

    Combines novelty, integration, feasibility, and verifiability via
    geometric mean.  Prevents highly novel nonsense, highly grounded
    conventionality, and flashy but unverifiable analogies.
    """
    dimensions = [
        breakdown.novelty,
        breakdown.integration,
        breakdown.feasibility,
        breakdown.verifiability,
    ]
    return _geometric_mean(dimensions)
