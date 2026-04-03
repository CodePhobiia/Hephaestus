"""Codified depth policy table — maps (depth, mode) to per-stage operational budgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageBudget:
    """Per-stage operational budget derived from depth and mode."""

    search_candidates: int
    search_branching_loops: int
    translate_pressure_rounds: int
    translate_permutations: int
    recomposition_ceiling: int
    fallback_retries: int

    def to_dict(self) -> dict[str, int]:
        return {
            "search_candidates": self.search_candidates,
            "search_branching_loops": self.search_branching_loops,
            "translate_pressure_rounds": self.translate_pressure_rounds,
            "translate_permutations": self.translate_permutations,
            "recomposition_ceiling": self.recomposition_ceiling,
            "fallback_retries": self.fallback_retries,
        }


# ---------------------------------------------------------------------------
# Standard mode policy table (depth 1–10)
# ---------------------------------------------------------------------------
_STANDARD_TABLE: dict[int, StageBudget] = {
    1:  StageBudget(search_candidates=5,  search_branching_loops=1, translate_pressure_rounds=0, translate_permutations=1, recomposition_ceiling=1, fallback_retries=0),
    2:  StageBudget(search_candidates=6,  search_branching_loops=1, translate_pressure_rounds=0, translate_permutations=1, recomposition_ceiling=1, fallback_retries=1),
    3:  StageBudget(search_candidates=7,  search_branching_loops=1, translate_pressure_rounds=0, translate_permutations=2, recomposition_ceiling=2, fallback_retries=1),
    4:  StageBudget(search_candidates=8,  search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=2, recomposition_ceiling=2, fallback_retries=1),
    5:  StageBudget(search_candidates=9,  search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=1),
    6:  StageBudget(search_candidates=10, search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    7:  StageBudget(search_candidates=11, search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    8:  StageBudget(search_candidates=12, search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    9:  StageBudget(search_candidates=14, search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    10: StageBudget(search_candidates=16, search_branching_loops=2, translate_pressure_rounds=0, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
}

# ---------------------------------------------------------------------------
# Forge mode policy table (depth 1–10)
# Forge mode enables pressure rounds on Translate, adaptive search loops,
# but pressure is OFF for Decompose, Score, and Verify (Phase 1 doctrine).
# ---------------------------------------------------------------------------
_FORGE_TABLE: dict[int, StageBudget] = {
    1:  StageBudget(search_candidates=5,  search_branching_loops=1, translate_pressure_rounds=1, translate_permutations=1, recomposition_ceiling=1, fallback_retries=1),
    2:  StageBudget(search_candidates=6,  search_branching_loops=1, translate_pressure_rounds=2, translate_permutations=2, recomposition_ceiling=2, fallback_retries=1),
    3:  StageBudget(search_candidates=8,  search_branching_loops=1, translate_pressure_rounds=3, translate_permutations=2, recomposition_ceiling=2, fallback_retries=1),
    4:  StageBudget(search_candidates=9,  search_branching_loops=2, translate_pressure_rounds=3, translate_permutations=2, recomposition_ceiling=2, fallback_retries=1),
    5:  StageBudget(search_candidates=10, search_branching_loops=2, translate_pressure_rounds=4, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    6:  StageBudget(search_candidates=11, search_branching_loops=2, translate_pressure_rounds=5, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    7:  StageBudget(search_candidates=12, search_branching_loops=2, translate_pressure_rounds=5, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    8:  StageBudget(search_candidates=14, search_branching_loops=2, translate_pressure_rounds=6, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    9:  StageBudget(search_candidates=15, search_branching_loops=2, translate_pressure_rounds=7, translate_permutations=3, recomposition_ceiling=3, fallback_retries=2),
    10: StageBudget(search_candidates=16, search_branching_loops=2, translate_pressure_rounds=8, translate_permutations=3, recomposition_ceiling=3, fallback_retries=3),
}


class DepthPolicyTable:
    """Codified mapping of (depth, mode) to per-stage budgets.

    This replaces the old GenesisConfig.exploration_budget property
    with a strict, non-prose mapping table.
    """

    def __init__(self) -> None:
        self._tables: dict[str, dict[int, StageBudget]] = {
            "standard": _STANDARD_TABLE,
            "forge": _FORGE_TABLE,
        }

    def policy_for(self, depth: int, mode: str = "standard") -> StageBudget:
        """Look up the stage budget for a given depth and mode.

        Args:
            depth: Exploration depth (1–10). Clamped to valid range.
            mode: Exploration mode ('standard' or 'forge').

        Returns:
            StageBudget with all per-stage limits.
        """
        depth = max(1, min(10, depth))
        mode = mode.lower()

        table = self._tables.get(mode, self._tables["standard"])
        return table[depth]

    def all_policies(self, mode: str = "standard") -> dict[int, dict[str, int]]:
        """Return the full table for a mode (for debugging/docs)."""
        table = self._tables.get(mode, self._tables["standard"])
        return {depth: budget.to_dict() for depth, budget in sorted(table.items())}

    def modes(self) -> list[str]:
        """Return all registered modes."""
        return list(self._tables.keys())

    def register_mode(self, mode: str, table: dict[int, StageBudget]) -> None:
        """Register a custom mode table."""
        self._tables[mode] = table


# Module-level singleton
_default_table: DepthPolicyTable | None = None


def get_depth_policy() -> DepthPolicyTable:
    """Return the default depth policy table."""
    global _default_table
    if _default_table is None:
        _default_table = DepthPolicyTable()
    return _default_table


__all__ = [
    "DepthPolicyTable",
    "StageBudget",
    "get_depth_policy",
]
