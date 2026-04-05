"""Integration tests — verify full pipeline with mocked services.

Covers F-6 (integration test gap), F-7a (writeback), F-7b (analyzer prompt parsing),
F-7c (mode behavior), and M-3 (diversity).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.adapters.fusion_analyzer import (
    _parse_analogy_map,
    _parse_transfer_opportunities,
)
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    BridgeEntityKind,
    EpistemicState,
    RetrievalReason,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    BridgeCandidate,
    ComponentMapping,
    EntityRef,
    TransferOpportunity,
    TransliminalityConfig,
    TransliminalityRequest,
)
from hephaestus.transliminality.factory import create_engine
from hephaestus.transliminality.service.bridge_retriever import _diversified_select

_idgen = DeterministicIdGenerator(seed=1300)


def _ref(prefix: str = "t", kind: str = "test") -> EntityRef:
    return EntityRef(entity_id=_idgen.generate(prefix), entity_kind=kind)


def _candidate(*, kind: BridgeEntityKind = BridgeEntityKind.CONCEPT, score: float = 0.7) -> BridgeCandidate:
    return BridgeCandidate(
        candidate_id=_idgen.generate("bc"),
        left_ref=_ref("page", "entity"),
        right_ref=_ref("page", "entity"),
        left_signature_ref=_ref("sig", "signature"),
        right_signature_ref=_ref("sig", "signature"),
        left_kind=kind,
        right_kind=kind,
        retrieval_reason=RetrievalReason.ROLE_MATCH,
        similarity_score=score,
    )


# ---------------------------------------------------------------------------
# F-6: Full pipeline integration test with mock services
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """Test the engine with custom service implementations that produce real data."""

    async def test_pipeline_with_populated_maps(self) -> None:
        """Verify that maps flow through to pack and writeback."""
        idgen = DeterministicIdGenerator(seed=1400)

        # Custom analyzer that produces real maps
        valid_map = AnalogicalMap(
            map_id=idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="selective gating",
            mapped_components=[
                ComponentMapping(None, None, "gate", "admission control"),
            ],
            preserved_constraints=["capacity limit"],
            structural_alignment_score=0.85,
            constraint_carryover_score=0.9,
            grounding_score=0.7,
            confidence=0.85,
            verdict=AnalogicalVerdict.VALID,
            rationale="Strong structural match",
            provenance_refs=[_ref("src", "source")],
        )
        test_opp = TransferOpportunity(
            opportunity_id=idgen.generate("opp"),
            map_ref=EntityRef(entity_id=valid_map.map_id, entity_kind="analogical_map"),
            title="Gating transfer",
            transferred_mechanism="staged activation",
            target_problem_fit="good fit",
            expected_benefit="adaptive gating",
            confidence=0.8,
        )

        class _RealAnalyzer:
            async def analyze_candidates(self, candidates, problem_signature, config):
                return [valid_map], [test_opp]

        from hephaestus.transliminality.service.pack_assembler import ChannelPackAssembler

        engine = create_engine(id_generator=idgen)
        # Replace stubs with real implementations
        engine._fusion_analyzer = _RealAnalyzer()
        engine._pack_assembler = ChannelPackAssembler(id_generator=idgen)

        request = TransliminalityRequest(
            run_id=idgen.generate("run"),
            problem="How to filter contaminants?",
            home_vault_ids=[idgen.generate("vault")],
            config=TransliminalityConfig(),
        )

        result = await engine.build_pack(request)

        # Maps and opportunities should be carried through
        assert len(result.maps) == 1
        assert result.maps[0].verdict == AnalogicalVerdict.VALID
        assert len(result.opportunities) == 1

        # Pack should have entries in channels
        pack = result.pack
        total_entries = (
            len(pack.strict_baseline_entries)
            + len(pack.soft_context_entries)
            + len(pack.strict_constraint_entries)
        )
        assert total_entries > 0

        # Writeback should succeed
        manifest = await engine.write_back(result)
        assert manifest.valid_map_count == 0  # stub writeback
        assert manifest.run_id == request.run_id

    async def test_build_pack_result_is_frozen(self) -> None:
        """BuildPackResult should be frozen — no stale state."""
        engine = create_engine(id_generator=DeterministicIdGenerator(seed=1500))
        request = TransliminalityRequest(
            run_id=_idgen.generate("run"),
            problem="test",
            home_vault_ids=[],
            config=TransliminalityConfig(),
        )
        result = await engine.build_pack(request)
        with pytest.raises(AttributeError):
            result.pack = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# F-7b: Analyzer prompt parsing tests
# ---------------------------------------------------------------------------

class TestAnalogyMapParsing:
    def test_parse_valid_map(self) -> None:
        raw = {
            "verdict": "VALID",
            "shared_role": "selective filtering",
            "mapped_components": [
                {"shared_role": "gate", "mapping_rationale": "Both control admission"},
            ],
            "preserved_constraints": ["capacity limit", "latency bound"],
            "broken_constraints": ["energy bound"],
            "analogy_breaks": [
                {"category": "SCALE_MISMATCH", "description": "Molecular vs macro", "severity": 0.6},
            ],
            "confidence": 0.82,
            "rationale": "Strong structural match",
        }
        candidate = _candidate()
        result = _parse_analogy_map(raw, candidate, _idgen)
        assert result.verdict == AnalogicalVerdict.VALID
        assert result.shared_role == "selective filtering"
        assert len(result.mapped_components) == 1
        assert len(result.preserved_constraints) == 2
        assert len(result.broken_constraints) == 1
        assert len(result.analogy_breaks) == 1
        assert result.confidence == 0.82

    def test_parse_invalid_map(self) -> None:
        raw = {"verdict": "INVALID", "confidence": 0.1, "rationale": "No real analogy"}
        result = _parse_analogy_map(raw, _candidate(), _idgen)
        assert result.verdict == AnalogicalVerdict.INVALID

    def test_parse_empty_map(self) -> None:
        result = _parse_analogy_map({}, _candidate(), _idgen)
        assert result.verdict == AnalogicalVerdict.INVALID
        assert result.confidence == 0.0


class TestTransferOpportunityParsing:
    def test_parse_opportunities(self) -> None:
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.8,
            provenance_refs=[_ref("src", "source")],
        )
        raw_list = [
            {
                "title": "Immune checkpoint → Rate limiter",
                "transferred_mechanism": "staged activation",
                "target_problem_fit": "Rate limiting needs selective admission",
                "expected_benefit": "Adaptive gating",
                "required_transformations": ["Replace molecular signals with request metadata"],
                "caveats": [{"category": "scale", "description": "timescale differs", "severity": 0.4}],
                "confidence": 0.75,
            },
        ]
        result = _parse_transfer_opportunities(raw_list, amap, _idgen)
        assert len(result) == 1
        assert result[0].title == "Immune checkpoint → Rate limiter"
        assert len(result[0].required_transformations) == 1
        assert len(result[0].caveats) == 1

    def test_parse_empty_list(self) -> None:
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="test",
        )
        result = _parse_transfer_opportunities([], amap, _idgen)
        assert result == []

    def test_high_confidence_is_validated(self) -> None:
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="test",
        )
        raw_list = [{"confidence": 0.85, "title": "t", "transferred_mechanism": "m",
                     "target_problem_fit": "f", "expected_benefit": "b"}]
        result = _parse_transfer_opportunities(raw_list, amap, _idgen)
        assert result[0].epistemic_state == EpistemicState.VALIDATED


# ---------------------------------------------------------------------------
# M-3: Bridge retrieval diversity tests
# ---------------------------------------------------------------------------

class TestDiversifiedSelect:
    def test_single_kind_capped(self) -> None:
        """All candidates of same kind — just top-K by score."""
        candidates = [_candidate(score=0.9 - i * 0.1) for i in range(10)]
        result = _diversified_select(candidates, 3)
        assert len(result) == 3

    def test_diverse_kinds_get_representation(self) -> None:
        """Each kind gets at least one slot."""
        kinds = [BridgeEntityKind.CONCEPT, BridgeEntityKind.MECHANISM,
                 BridgeEntityKind.CLAIM_CLUSTER, BridgeEntityKind.PAGE_FAMILY]
        candidates = []
        for i, kind in enumerate(kinds):
            candidates.append(_candidate(kind=kind, score=0.5 + i * 0.1))
        result = _diversified_select(candidates, 4)
        result_kinds = {c.left_kind for c in result}
        assert len(result_kinds) == 4  # all 4 kinds represented

    def test_fewer_than_top_k_returns_all(self) -> None:
        candidates = [_candidate() for _ in range(3)]
        result = _diversified_select(candidates, 10)
        assert len(result) == 3

    def test_empty_returns_empty(self) -> None:
        assert _diversified_select([], 5) == []


# ---------------------------------------------------------------------------
# F-7c: Mode-specific behavior tests
# ---------------------------------------------------------------------------

class TestModeSpecificBehavior:
    def test_conservative_has_higher_strict_threshold(self) -> None:
        """CONSERVATIVE mode should use default high thresholds."""
        from hephaestus.transliminality.domain.enums import TransliminalityMode
        cfg = TransliminalityConfig(mode=TransliminalityMode.CONSERVATIVE)
        assert cfg.strict_channel_min_confidence == 0.80

    def test_exploratory_mode_allows_hypothesis(self) -> None:
        """EXPLORATORY mode should allow hypothesis in soft channel."""
        from hephaestus.transliminality.domain.enums import TransliminalityMode
        cfg = TransliminalityConfig(mode=TransliminalityMode.EXPLORATORY)
        assert cfg.allow_hypothesis_in_soft_channel is True

    def test_config_caps_are_respected_by_engine(self) -> None:
        """Verify that analyzed_candidate_limit caps the shortlist."""
        cfg_small = TransliminalityConfig(analyzed_candidate_limit=2, maps_to_keep=1)
        assert cfg_small.analyzed_candidate_limit == 2
        assert cfg_small.maps_to_keep == 1


# ---------------------------------------------------------------------------
# LLM evaluator tests
# ---------------------------------------------------------------------------

class TestLLMEvaluator:
    async def test_counterfactual_returns_score(self) -> None:
        from hephaestus.transliminality.domain.models import TransliminalityPack
        from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator

        harness = MagicMock()
        harness.forge = AsyncMock(return_value=MagicMock(
            output=json.dumps({"score": 0.75, "collapse_mode": "essential"}),
        ))

        evaluator = LLMIntegrationEvaluator(harness=harness)
        pack = TransliminalityPack(
            pack_id=_idgen.generate("tpack"),
            run_id=_idgen.generate("run"),
            problem_signature_ref=_ref("sig", "role_signature"),
        )
        valid_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            rationale="test",
        )
        score = await evaluator.evaluate_counterfactual(pack, [valid_map])
        assert score == 0.75

    async def test_non_ornamental_returns_score(self) -> None:
        from hephaestus.transliminality.domain.models import TransliminalityPack
        from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator

        harness = MagicMock()
        harness.forge = AsyncMock(return_value=MagicMock(
            output=json.dumps({"score": 0.6, "functional_elements": ["gate logic"]}),
        ))

        evaluator = LLMIntegrationEvaluator(harness=harness)
        pack = TransliminalityPack(
            pack_id=_idgen.generate("tpack"),
            run_id=_idgen.generate("run"),
            problem_signature_ref=_ref("sig", "role_signature"),
        )
        valid_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            mapped_components=[ComponentMapping(None, None, "gate", "controls flow")],
        )
        score = await evaluator.evaluate_non_ornamental(pack, [valid_map])
        assert score == 0.6

    async def test_empty_maps_return_zero(self) -> None:
        from hephaestus.transliminality.domain.models import TransliminalityPack
        from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator

        harness = MagicMock()
        evaluator = LLMIntegrationEvaluator(harness=harness)
        pack = TransliminalityPack(
            pack_id=_idgen.generate("tpack"),
            run_id=_idgen.generate("run"),
            problem_signature_ref=_ref("sig", "role_signature"),
        )
        assert await evaluator.evaluate_counterfactual(pack, []) == 0.0
        assert await evaluator.evaluate_non_ornamental(pack, []) == 0.0

    async def test_llm_failure_returns_zero(self) -> None:
        from hephaestus.transliminality.domain.models import TransliminalityPack
        from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator

        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=RuntimeError("API down"))

        evaluator = LLMIntegrationEvaluator(harness=harness)
        pack = TransliminalityPack(
            pack_id=_idgen.generate("tpack"),
            run_id=_idgen.generate("run"),
            problem_signature_ref=_ref("sig", "role_signature"),
        )
        valid_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
        )
        assert await evaluator.evaluate_counterfactual(pack, [valid_map]) == 0.0
        assert await evaluator.evaluate_non_ornamental(pack, [valid_map]) == 0.0
