"""Tests for MockFusionAnalyzer -- deterministic analogy analysis."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import AnalogyVerdict
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.analyzers.mock_analyzer import MockFusionAnalyzer
from tests.test_forgebase.test_fusion.conftest import make_bridge_candidate


class TestMockFusionAnalyzerContract:
    """Verify MockFusionAnalyzer satisfies the FusionAnalyzer ABC."""

    def test_is_subclass_of_abc(self):
        assert issubclass(MockFusionAnalyzer, FusionAnalyzer)

    def test_is_instance_of_abc(self, mock_fusion_analyzer):
        assert isinstance(mock_fusion_analyzer, FusionAnalyzer)


class TestStrongAnalogy:
    """Candidates with similarity_score >= 0.5 -> STRONG_ANALOGY."""

    async def test_strong_analogy_above_threshold(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.75,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.STRONG_ANALOGY
        assert maps[0].confidence == 0.75
        assert len(maps[0].mapped_components) == 1
        assert maps[0].mapped_components[0].left_component == "Component A"
        assert maps[0].mapped_components[0].right_component == "Component B"
        assert maps[0].mapped_components[0].mapping_confidence == 0.75

    async def test_strong_analogy_at_boundary(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.5,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.STRONG_ANALOGY

    async def test_strong_analogy_preserves_provenance(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.8,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        amap = maps[0]
        assert candidate.candidate_id in amap.source_candidates
        assert candidate.left_entity_ref in amap.left_page_refs
        assert candidate.right_entity_ref in amap.right_page_refs
        assert amap.left_claim_refs == candidate.left_claim_refs
        assert amap.right_claim_refs == candidate.right_claim_refs


class TestWeakAnalogy:
    """Candidates with 0.3 <= similarity_score < 0.5 -> WEAK_ANALOGY."""

    async def test_weak_analogy_in_middle(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.4,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.WEAK_ANALOGY
        assert maps[0].confidence == 0.4
        assert maps[0].mapped_components == []
        # WEAK_ANALOGY should NOT generate transfers
        assert len(transfers) == 0

    async def test_weak_analogy_at_lower_boundary(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.3,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.WEAK_ANALOGY

    async def test_weak_analogy_at_upper_boundary_exclusive(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        """0.5 is STRONG, not WEAK (boundary belongs to STRONG)."""
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.49,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert maps[0].verdict == AnalogyVerdict.WEAK_ANALOGY


class TestNoAnalogy:
    """Candidates with similarity_score < 0.3 -> NO_ANALOGY."""

    async def test_no_analogy_below_threshold(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.15,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY
        assert maps[0].confidence == 0.15
        assert maps[0].mapped_components == []
        assert len(transfers) == 0

    async def test_no_analogy_at_zero(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.0,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY

    async def test_no_analogy_at_upper_boundary_exclusive(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        """0.3 is WEAK, not NO_ANALOGY (boundary belongs to WEAK)."""
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.29,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY


class TestTransferGeneration:
    """Transfer opportunities are generated only for STRONG analogies."""

    async def test_generates_transfer_for_strong(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.7,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(transfers) == 1
        t = transfers[0]
        assert t.from_vault_id == left_vault_id
        assert t.to_vault_id == right_vault_id
        assert t.analogical_map_id == maps[0].map_id
        assert t.confidence == 0.7
        assert "0.70" in t.rationale
        assert t.caveats == ["Mock caveat"]
        assert t.caveat_categories == ["feasibility"]
        assert t.from_page_refs == [candidate.left_entity_ref]
        assert t.to_page_refs == [candidate.right_entity_ref]
        assert t.from_claim_refs == candidate.left_claim_refs

    async def test_no_transfer_for_weak(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.4,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(transfers) == 0

    async def test_no_transfer_for_no_analogy(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.1,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(transfers) == 0

    async def test_multiple_strong_generate_multiple_transfers(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidates = [
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.6,
            ),
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.8,
            ),
        ]

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            candidates,
            left_context,
            right_context,
        )

        assert len(maps) == 2
        assert all(m.verdict == AnalogyVerdict.STRONG_ANALOGY for m in maps)
        assert len(transfers) == 2


class TestEmptyCandidates:
    """Empty input should produce empty output."""

    async def test_empty_candidates_returns_empty(
        self,
        mock_fusion_analyzer,
        left_context,
        right_context,
    ):
        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [],
            left_context,
            right_context,
        )

        assert maps == []
        assert transfers == []
        assert record.model_name == "mock"
        assert record.backend_kind == "mock"
        assert record.prompt_id == "fusion_analysis"
        assert record.repair_invoked is False


class TestProblemRelevance:
    """Problem relevance is passed through from candidates to maps/transfers."""

    async def test_problem_relevance_passed_through(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.7,
            problem_relevance=0.92,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
            problem="Improve battery life",
        )

        assert maps[0].problem_relevance == 0.92
        assert transfers[0].problem_relevance == 0.92

    async def test_none_problem_relevance_passed_through(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.6,
            problem_relevance=None,
        )

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert maps[0].problem_relevance is None
        assert transfers[0].problem_relevance is None


class TestMixedCandidates:
    """A mix of STRONG, WEAK, and NO_ANALOGY candidates."""

    async def test_mixed_verdicts(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidates = [
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.8,
            ),
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.4,
            ),
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.1,
            ),
        ]

        maps, transfers, record = await mock_fusion_analyzer.analyze_candidates(
            candidates,
            left_context,
            right_context,
        )

        assert len(maps) == 3
        assert maps[0].verdict == AnalogyVerdict.STRONG_ANALOGY
        assert maps[1].verdict == AnalogyVerdict.WEAK_ANALOGY
        assert maps[2].verdict == AnalogyVerdict.NO_ANALOGY
        # Only 1 transfer (from STRONG)
        assert len(transfers) == 1

    async def test_call_record_always_present(
        self,
        mock_fusion_analyzer,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        candidates = [
            make_bridge_candidate(
                id_gen,
                left_vault_id,
                right_vault_id,
                similarity_score=0.6,
            ),
        ]

        _, _, record = await mock_fusion_analyzer.analyze_candidates(
            candidates,
            left_context,
            right_context,
        )

        assert record.model_name == "mock"
        assert record.backend_kind == "mock"
        assert record.prompt_id == "fusion_analysis"
        assert record.prompt_version == "1.0.0"
        assert record.schema_version == 1
        assert record.input_tokens == 0
        assert record.output_tokens == 0
        assert record.duration_ms == 0
