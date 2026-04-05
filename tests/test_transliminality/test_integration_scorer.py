"""Tests for the heuristic integration scorer."""

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogyBreak,
    ComponentMapping,
    EntityRef,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityPack,
)
from hephaestus.transliminality.domain.scoring import compute_integration_score
from hephaestus.transliminality.service.integration_scorer import (
    HeuristicIntegrationScorer,
    _bidirectional_explainability,
    _constraint_fidelity,
    _counterfactual_dependence_heuristic,
    _non_ornamental_use_heuristic,
    _source_grounding,
    _structural_alignment,
)

_idgen = DeterministicIdGenerator(seed=1100)


def _ref(prefix: str = "t", kind: str = "test") -> EntityRef:
    return EntityRef(entity_id=_idgen.generate(prefix), entity_kind=kind)


def _map(
    *,
    verdict: AnalogicalVerdict = AnalogicalVerdict.VALID,
    confidence: float = 0.8,
    alignment: float = 0.8,
    preserved: int = 3,
    broken: int = 0,
    provenance: int = 2,
    components: int = 1,
    has_rationale: bool = True,
    has_breaks: bool = False,
) -> AnalogicalMap:
    return AnalogicalMap(
        map_id=_idgen.generate("map"),
        candidate_ref=_ref("bc", "bridge"),
        shared_role="gating",
        mapped_components=[
            ComponentMapping(None, None, "gate", "admission control")
            for _ in range(components)
        ],
        preserved_constraints=[f"c{i}" for i in range(preserved)],
        broken_constraints=[f"b{i}" for i in range(broken)],
        analogy_breaks=[
            AnalogyBreak(AnalogyBreakCategory.SCALE_MISMATCH, "scale issue", severity=0.5)
        ] if has_breaks else [],
        structural_alignment_score=alignment,
        constraint_carryover_score=1.0 - (broken / max(preserved + broken, 1)),
        grounding_score=min(provenance / 4.0, 1.0),
        confidence=confidence,
        verdict=verdict,
        rationale="Strong match" if has_rationale else "",
        provenance_refs=[_ref("src", "source") for _ in range(provenance)],
    )


def _opp(*, transformations: int = 1, caveats: int = 1) -> TransferOpportunity:
    return TransferOpportunity(
        opportunity_id=_idgen.generate("opp"),
        map_ref=_ref("map", "analogical_map"),
        title="test transfer",
        transferred_mechanism="gating",
        target_problem_fit="good fit",
        expected_benefit="better selectivity",
        required_transformations=[f"t{i}" for i in range(transformations)],
        caveats=[
            TransferCaveat(category="scale", description="scale differs", severity=0.5)
            for _ in range(caveats)
        ],
        confidence=0.7,
    )


class TestStructuralAlignment:
    def test_no_maps(self) -> None:
        assert _structural_alignment([]) == 0.0

    def test_single_valid_map(self) -> None:
        result = _structural_alignment([_map(alignment=0.9, confidence=1.0)])
        assert result == pytest.approx(0.9)

    def test_weighted_by_confidence(self) -> None:
        maps = [
            _map(alignment=1.0, confidence=0.9),
            _map(alignment=0.5, confidence=0.1),
        ]
        result = _structural_alignment(maps)
        # Heavily weighted toward the high-confidence map
        assert result > 0.8

    def test_ignores_invalid_maps(self) -> None:
        result = _structural_alignment([_map(verdict=AnalogicalVerdict.INVALID)])
        assert result == 0.0


class TestConstraintFidelity:
    def test_all_preserved(self) -> None:
        result = _constraint_fidelity([_map(preserved=5, broken=0)])
        assert result == pytest.approx(1.0)

    def test_all_broken(self) -> None:
        result = _constraint_fidelity([_map(preserved=0, broken=5)])
        assert result == pytest.approx(0.0)

    def test_mixed(self) -> None:
        result = _constraint_fidelity([_map(preserved=3, broken=1)])
        assert result == pytest.approx(0.75)


class TestSourceGrounding:
    def test_no_provenance(self) -> None:
        result = _source_grounding([_map(provenance=0)])
        assert result == pytest.approx(0.0)

    def test_full_provenance(self) -> None:
        result = _source_grounding([_map(provenance=4)])
        assert result == pytest.approx(1.0)

    def test_capped_at_one(self) -> None:
        result = _source_grounding([_map(provenance=10)])
        assert result == pytest.approx(1.0)


class TestCounterfactualHeuristic:
    def test_no_maps(self) -> None:
        assert _counterfactual_dependence_heuristic([], []) == 0.0

    def test_with_specific_opportunities(self) -> None:
        result = _counterfactual_dependence_heuristic(
            [_map()], [_opp(transformations=2, caveats=1)],
        )
        assert result > 0.3

    def test_no_opportunities_halves_score(self) -> None:
        with_opps = _counterfactual_dependence_heuristic([_map()], [_opp()])
        without_opps = _counterfactual_dependence_heuristic([_map()], [])
        assert with_opps > without_opps


class TestBidirectionalExplainability:
    def test_both_present(self) -> None:
        result = _bidirectional_explainability([_map(has_rationale=True, has_breaks=True)])
        assert result == pytest.approx(1.0)

    def test_rationale_only(self) -> None:
        result = _bidirectional_explainability([_map(has_rationale=True, has_breaks=False)])
        assert result == pytest.approx(0.5)

    def test_neither(self) -> None:
        result = _bidirectional_explainability([_map(has_rationale=False, has_breaks=False)])
        assert result == pytest.approx(0.0)


class TestNonOrnamentalHeuristic:
    def test_with_components(self) -> None:
        result = _non_ornamental_use_heuristic([_map(components=3)])
        assert result == pytest.approx(1.0)

    def test_no_components(self) -> None:
        result = _non_ornamental_use_heuristic([_map(components=0)])
        assert result == pytest.approx(0.0)


class TestHeuristicScorer:
    async def test_score_valid_maps(self) -> None:
        scorer = HeuristicIntegrationScorer()
        breakdown = await scorer.score_pack(
            pack=TransliminalityPack(
                pack_id=_idgen.generate("tpack"),
                run_id=_idgen.generate("run"),
                problem_signature_ref=_ref("sig", "role_signature"),
            ),
            maps=[_map(has_rationale=True, has_breaks=True, components=2)],
            opportunities=[_opp()],
        )
        assert breakdown.structural_alignment > 0
        assert breakdown.constraint_fidelity > 0
        assert breakdown.source_grounding > 0
        assert breakdown.bidirectional_explainability > 0
        assert breakdown.non_ornamental_use > 0
        # Aggregate should be positive
        assert compute_integration_score(breakdown) > 0

    async def test_score_empty(self) -> None:
        scorer = HeuristicIntegrationScorer()
        breakdown = await scorer.score_pack(
            pack=TransliminalityPack(
                pack_id=_idgen.generate("tpack"),
                run_id=_idgen.generate("run"),
                problem_signature_ref=_ref("sig", "role_signature"),
            ),
            maps=[],
            opportunities=[],
        )
        assert compute_integration_score(breakdown) == 0.0
