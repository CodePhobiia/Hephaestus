"""Integration scorer — evaluates cross-domain synthesis quality.

Computes six-dimension IntegrationScoreBreakdown:
1. Structural alignment — do mapped components play comparable roles?
2. Constraint fidelity — did the transfer preserve critical limits?
3. Source grounding — can the system point to vault knowledge supporting the bridge?
4. Counterfactual dependence — does the invention collapse without the bridge?
5. Bidirectional explainability — can we explain why the mapping works AND why alternatives fail?
6. Non-ornamental use — is the bridge doing functional work, not decorating narrative?

Uses heuristic scoring by default; accepts an optional LLM backend for
counterfactual and non-ornamental evaluation (Phase 4+).
"""

from __future__ import annotations

import logging
from typing import Protocol

from hephaestus.transliminality.domain.enums import AnalogicalVerdict
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    IntegrationScoreBreakdown,
    TransferOpportunity,
    TransliminalityPack,
)

logger = logging.getLogger(__name__)


class LLMEvaluator(Protocol):
    """Optional LLM backend for deep integration evaluation."""

    async def evaluate_counterfactual(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
    ) -> float: ...

    async def evaluate_non_ornamental(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
    ) -> float: ...


def _structural_alignment(maps: list[AnalogicalMap]) -> float:
    """Average structural alignment across valid maps.

    Uses map-level structural_alignment_score, weighted by confidence.
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0
    total_weight = sum(m.confidence for m in valid)
    if total_weight == 0:
        return 0.0
    return sum(m.structural_alignment_score * m.confidence for m in valid) / total_weight


def _constraint_fidelity(maps: list[AnalogicalMap]) -> float:
    """Score how well constraints survived transfer.

    High score = most constraints preserved. Zero broken constraints = 1.0.
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0
    scores = []
    for m in valid:
        total = len(m.preserved_constraints) + len(m.broken_constraints)
        if total == 0:
            scores.append(0.5)  # no constraint data → neutral
        else:
            scores.append(len(m.preserved_constraints) / total)
    return sum(scores) / len(scores)


def _source_grounding(maps: list[AnalogicalMap]) -> float:
    """Score how well maps are grounded in vault knowledge.

    Higher = more provenance references backing the bridge.
    Capped at 1.0 (4+ refs = fully grounded).
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0
    scores = [min(len(m.provenance_refs) / 4.0, 1.0) for m in valid]
    return sum(scores) / len(scores)


def _counterfactual_dependence_heuristic(
    maps: list[AnalogicalMap],
    opportunities: list[TransferOpportunity],
) -> float:
    """Heuristic counterfactual dependence score.

    Higher if:
    - Transfer opportunities exist and are specific (have transformations/caveats)
    - Maps have high confidence (suggesting genuine structural dependency)
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0

    # Opportunity specificity: do opportunities have concrete transformations?
    if opportunities:
        specificity = sum(
            1 for o in opportunities if o.required_transformations or o.caveats
        ) / len(opportunities)
    else:
        specificity = 0.0

    # Bridge strength: average confidence of valid maps
    strength = sum(m.confidence for m in valid) / len(valid)

    # Combine: strong bridge + specific opportunities = high counterfactual
    return (specificity * 0.5 + strength * 0.5)


def _bidirectional_explainability(maps: list[AnalogicalMap]) -> float:
    """Score whether maps explain both what works AND what doesn't.

    Higher if maps have:
    - Rationale (explains why mapping works)
    - Analogy breaks (explains where it fails)
    Both are needed for bidirectional explanation.
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0
    scores = []
    for m in valid:
        has_positive = 0.5 if m.rationale else 0.0
        has_negative = 0.5 if m.analogy_breaks else 0.0
        scores.append(has_positive + has_negative)
    return sum(scores) / len(scores)


def _non_ornamental_use_heuristic(maps: list[AnalogicalMap]) -> float:
    """Heuristic non-ornamental score.

    Higher if maps have concrete component mappings (not just abstract prose).
    A map with zero mapped_components is likely ornamental.
    """
    valid = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid:
        return 0.0
    scores = []
    for m in valid:
        if m.mapped_components:
            # More concrete mappings = more functional use
            scores.append(min(len(m.mapped_components) / 3.0, 1.0))
        else:
            scores.append(0.0)
    return sum(scores) / len(scores)


class HeuristicIntegrationScorer:
    """Integration scorer using heuristic dimension estimation.

    Optionally accepts an LLM evaluator for counterfactual and
    non-ornamental dimensions (Phase 4+).
    """

    def __init__(self, llm_evaluator: LLMEvaluator | None = None) -> None:
        self._llm = llm_evaluator

    async def score_pack(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
    ) -> IntegrationScoreBreakdown:
        """Score integration quality across six dimensions."""
        structural = _structural_alignment(maps)
        fidelity = _constraint_fidelity(maps)
        grounding = _source_grounding(maps)

        # Use LLM evaluator if available, otherwise heuristic
        if self._llm is not None:
            counterfactual = await self._llm.evaluate_counterfactual(pack, maps)
            non_ornamental = await self._llm.evaluate_non_ornamental(pack, maps)
        else:
            counterfactual = _counterfactual_dependence_heuristic(maps, opportunities)
            non_ornamental = _non_ornamental_use_heuristic(maps)

        bidirectional = _bidirectional_explainability(maps)

        breakdown = IntegrationScoreBreakdown(
            structural_alignment=structural,
            constraint_fidelity=fidelity,
            source_grounding=grounding,
            counterfactual_dependence=counterfactual,
            bidirectional_explainability=bidirectional,
            non_ornamental_use=non_ornamental,
        )

        from hephaestus.transliminality.domain.scoring import compute_integration_score

        logger.info(
            "integration_score  "
            "structural=%.3f  fidelity=%.3f  grounding=%.3f  "
            "counterfactual=%.3f  bidirectional=%.3f  non_ornamental=%.3f  "
            "aggregate=%.3f",
            structural, fidelity, grounding,
            counterfactual, bidirectional, non_ornamental,
            compute_integration_score(breakdown),
        )

        return breakdown
