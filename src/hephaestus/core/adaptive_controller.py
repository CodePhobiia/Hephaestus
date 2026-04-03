"""Adaptive exploration controller — mid-run adjustments to exploration parameters."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExplorationState:
    """Tracks exploration health metrics during a run."""

    search_diversity_scores: list[float] = field(default_factory=list)
    parse_failure_count: int = 0
    total_parse_attempts: int = 0
    cost_usd_so_far: float = 0.0
    cost_ceiling_usd: float = 5.0
    current_candidates: int = 0

    @property
    def parse_failure_rate(self) -> float:
        if self.total_parse_attempts == 0:
            return 0.0
        return self.parse_failure_count / self.total_parse_attempts

    @property
    def avg_diversity(self) -> float:
        if not self.search_diversity_scores:
            return 0.0
        return sum(self.search_diversity_scores) / len(self.search_diversity_scores)

    @property
    def cost_ratio(self) -> float:
        if self.cost_ceiling_usd <= 0:
            return 1.0
        return self.cost_usd_so_far / self.cost_ceiling_usd


@dataclass
class AdaptiveAdjustment:
    """A recommended adjustment to exploration parameters."""

    action: str  # widen_lenses, stop_early, reduce_pressure, degrade_graceful
    reason: str
    parameter: str = ""
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "parameter": self.parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


class AdaptiveExplorationController:
    """Mid-run controller that adjusts exploration parameters based on health signals.

    Rules:
    1. If search diversity collapses (< diversity_floor), widen lens set
    2. If diversity already high (> diversity_ceiling), stop early (save tokens)
    3. If parse failure rate rises mid-run, reduce pressure rounds
    4. If cost ceiling approaching, degrade gracefully instead of hard-fail
    """

    def __init__(
        self,
        *,
        diversity_floor: float = 0.3,
        diversity_ceiling: float = 0.8,
        parse_failure_threshold: float = 0.4,
        cost_warning_ratio: float = 0.7,
        cost_critical_ratio: float = 0.9,
    ) -> None:
        self._diversity_floor = diversity_floor
        self._diversity_ceiling = diversity_ceiling
        self._parse_threshold = parse_failure_threshold
        self._cost_warning = cost_warning_ratio
        self._cost_critical = cost_critical_ratio

    def evaluate(self, state: ExplorationState) -> list[AdaptiveAdjustment]:
        """Evaluate exploration state and return recommended adjustments."""
        adjustments: list[AdaptiveAdjustment] = []

        # Rule 1: Diversity collapse
        if state.search_diversity_scores and state.avg_diversity < self._diversity_floor:
            adjustments.append(AdaptiveAdjustment(
                action="widen_lenses",
                reason=f"Search diversity collapsed ({state.avg_diversity:.2f} < {self._diversity_floor:.2f})",
                parameter="num_search_lenses",
                old_value=state.current_candidates,
                new_value=min(state.current_candidates + 4, 20),
            ))
            logger.info(
                "Adaptive: diversity collapse detected (%.2f), recommending lens widening",
                state.avg_diversity,
            )

        # Rule 2: Early stop on high diversity
        if len(state.search_diversity_scores) >= 3 and state.avg_diversity > self._diversity_ceiling:
            adjustments.append(AdaptiveAdjustment(
                action="stop_early",
                reason=f"Search diversity already high ({state.avg_diversity:.2f} > {self._diversity_ceiling:.2f})",
            ))
            logger.info(
                "Adaptive: high diversity (%.2f), recommending early stop",
                state.avg_diversity,
            )

        # Rule 3: Parse failure rate
        if state.total_parse_attempts >= 3 and state.parse_failure_rate > self._parse_threshold:
            adjustments.append(AdaptiveAdjustment(
                action="reduce_pressure",
                reason=f"Parse failure rate high ({state.parse_failure_rate:.2f} > {self._parse_threshold:.2f})",
                parameter="pressure_max_rounds",
                old_value=None,
                new_value=1,  # Reduce to minimum
            ))
            logger.warning(
                "Adaptive: parse failure rate %.2f, recommending pressure reduction",
                state.parse_failure_rate,
            )

        # Rule 4: Cost governance
        if state.cost_ratio >= self._cost_critical:
            adjustments.append(AdaptiveAdjustment(
                action="degrade_graceful",
                reason=f"Cost ceiling critical ({state.cost_ratio:.0%} of ${state.cost_ceiling_usd:.2f})",
                parameter="execution_mode",
                old_value="full",
                new_value="minimal",
            ))
            logger.warning(
                "Adaptive: cost at %.0f%% of ceiling, recommending graceful degradation",
                state.cost_ratio * 100,
            )
        elif state.cost_ratio >= self._cost_warning:
            adjustments.append(AdaptiveAdjustment(
                action="reduce_pressure",
                reason=f"Cost ceiling approaching ({state.cost_ratio:.0%} of ${state.cost_ceiling_usd:.2f})",
                parameter="translate_permutations",
                old_value=None,
                new_value=1,
            ))
            logger.info(
                "Adaptive: cost at %.0f%% of ceiling, recommending scope reduction",
                state.cost_ratio * 100,
            )

        return adjustments

    def should_stop_search(self, state: ExplorationState) -> bool:
        """Quick check: should the search loop terminate early?"""
        if state.cost_ratio >= self._cost_critical:
            return True
        if len(state.search_diversity_scores) >= 3 and state.avg_diversity > self._diversity_ceiling:
            return True
        return False

    def should_reduce_pressure(self, state: ExplorationState) -> bool:
        """Quick check: should pressure rounds be reduced?"""
        if state.parse_failure_rate > self._parse_threshold:
            return True
        if state.cost_ratio >= self._cost_warning:
            return True
        return False


__all__ = [
    "AdaptiveAdjustment",
    "AdaptiveExplorationController",
    "ExplorationState",
]
