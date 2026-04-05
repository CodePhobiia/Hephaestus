"""Tests for fusion domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    AnalogyVerdict,
    BridgeCandidateKind,
    FusionMode,
)
from hephaestus.forgebase.domain.values import VaultRevisionId
from hephaestus.forgebase.fusion.models import (
    AnalogicalMap,
    AnalogyBreak,
    BridgeCandidate,
    ComponentMapping,
    ConstraintMapping,
    FusionManifest,
    PairFusionManifest,
    TransferOpportunity,
)
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


class TestComponentMapping:
    def test_construction(self):
        cm = ComponentMapping(
            left_component="cathode layer",
            right_component="routing layer",
            mapping_confidence=0.85,
        )
        assert cm.left_component == "cathode layer"
        assert cm.right_component == "routing layer"
        assert cm.left_ref is None
        assert cm.right_ref is None
        assert cm.mapping_confidence == 0.85

    def test_with_refs(self, id_gen):
        cm = ComponentMapping(
            left_component="anode",
            right_component="hub",
            left_ref=id_gen.page_id(),
            right_ref=id_gen.page_id(),
            mapping_confidence=0.7,
        )
        assert cm.left_ref is not None
        assert cm.right_ref is not None


class TestConstraintMapping:
    def test_construction_preserved(self):
        cm = ConstraintMapping(
            left_constraint="temperature < 300K",
            right_constraint="latency < 100ms",
            preserved=True,
        )
        assert cm.preserved is True

    def test_construction_not_preserved(self):
        cm = ConstraintMapping(
            left_constraint="pressure > 10 atm",
            right_constraint="throughput > 1000 req/s",
            preserved=False,
        )
        assert cm.preserved is False


class TestAnalogyBreak:
    def test_construction(self):
        ab = AnalogyBreak(
            description="Scale differs by 6 orders of magnitude",
            severity="high",
            category="scale_difference",
        )
        assert ab.description == "Scale differs by 6 orders of magnitude"
        assert ab.severity == "high"
        assert ab.category == "scale_difference"


class TestBridgeCandidate:
    def test_construction_minimal(self, id_gen):
        left_vault = id_gen.vault_id()
        right_vault = id_gen.vault_id()

        bc = BridgeCandidate(
            candidate_id=id_gen.generate("bcand"),
            left_vault_id=left_vault,
            right_vault_id=right_vault,
            left_entity_ref=id_gen.page_id(),
            right_entity_ref=id_gen.page_id(),
            left_kind=BridgeCandidateKind.CONCEPT,
            right_kind=BridgeCandidateKind.MECHANISM,
            similarity_score=0.78,
            retrieval_reason="cosine_similarity_top_band",
            left_text="Lithium-ion intercalation chemistry",
            right_text="Hub-and-spoke logistics routing",
        )

        assert bc.candidate_id.prefix == "bcand"
        assert bc.left_kind == BridgeCandidateKind.CONCEPT
        assert bc.right_kind == BridgeCandidateKind.MECHANISM
        assert bc.similarity_score == 0.78
        assert bc.epistemic_filter_passed is True
        assert bc.problem_relevance is None
        assert bc.left_claim_refs == []
        assert bc.right_source_refs == []

    def test_construction_full(self, id_gen):
        left_vault = id_gen.vault_id()
        right_vault = id_gen.vault_id()
        left_rev = VaultRevisionId(f"rev_{1:026d}")
        right_rev = VaultRevisionId(f"rev_{2:026d}")

        bc = BridgeCandidate(
            candidate_id=id_gen.generate("bcand"),
            left_vault_id=left_vault,
            right_vault_id=right_vault,
            left_entity_ref=id_gen.page_id(),
            right_entity_ref=id_gen.page_id(),
            left_kind=BridgeCandidateKind.CLAIM_CLUSTER,
            right_kind=BridgeCandidateKind.PAGE_THEME,
            similarity_score=0.62,
            retrieval_reason="diversified_mid_band",
            left_text="Battery cycling improves with thin films",
            right_text="Route optimization via graph reduction",
            left_claim_refs=[id_gen.claim_id(), id_gen.claim_id()],
            right_claim_refs=[id_gen.claim_id()],
            left_source_refs=[id_gen.source_id()],
            right_source_refs=[id_gen.source_id(), id_gen.source_id()],
            left_revision_ref=left_rev,
            right_revision_ref=right_rev,
            epistemic_filter_passed=True,
            problem_relevance=0.85,
        )

        assert len(bc.left_claim_refs) == 2
        assert len(bc.right_source_refs) == 2
        assert bc.problem_relevance == 0.85
        assert bc.left_revision_ref == left_rev


class TestAnalogicalMap:
    def test_construction_minimal(self, id_gen):
        am = AnalogicalMap(
            map_id=id_gen.generate("amap"),
            bridge_concept="layered transport",
            left_structure="Li-ion intercalation layers",
            right_structure="Multi-tier distribution network",
        )

        assert am.map_id.prefix == "amap"
        assert am.bridge_concept == "layered transport"
        assert am.confidence == 0.0
        assert am.verdict == AnalogyVerdict.NO_ANALOGY
        assert am.mapped_components == []
        assert am.mapped_constraints == []
        assert am.analogy_breaks == []

    def test_construction_strong_analogy(self, id_gen):
        components = [
            ComponentMapping("cathode", "distribution center", mapping_confidence=0.9),
            ComponentMapping("anode", "collection point", mapping_confidence=0.85),
        ]
        constraints = [
            ConstraintMapping("charge rate < 4C", "throughput < 10k/hr", preserved=True),
        ]
        breaks = [
            AnalogyBreak("Scale differs", "medium", "scale_difference"),
        ]

        am = AnalogicalMap(
            map_id=id_gen.generate("amap"),
            bridge_concept="directed flow in layered network",
            left_structure="Electrochemical cell architecture",
            right_structure="Supply chain network topology",
            mapped_components=components,
            mapped_constraints=constraints,
            analogy_breaks=breaks,
            confidence=0.82,
            verdict=AnalogyVerdict.STRONG_ANALOGY,
            problem_relevance=0.9,
            source_candidates=[id_gen.generate("bcand")],
            left_page_refs=[id_gen.page_id()],
            right_page_refs=[id_gen.page_id()],
            left_claim_refs=[id_gen.claim_id()],
            right_claim_refs=[id_gen.claim_id(), id_gen.claim_id()],
        )

        assert am.verdict == AnalogyVerdict.STRONG_ANALOGY
        assert am.confidence == 0.82
        assert len(am.mapped_components) == 2
        assert len(am.mapped_constraints) == 1
        assert len(am.analogy_breaks) == 1
        assert am.problem_relevance == 0.9


class TestTransferOpportunity:
    def test_construction_minimal(self, id_gen):
        t = TransferOpportunity(
            opportunity_id=id_gen.generate("txfr"),
            from_vault_id=id_gen.vault_id(),
            to_vault_id=id_gen.vault_id(),
            mechanism="Apply hub-spoke optimization to ion transport paths",
            rationale="Structural analogy between distribution networks and electrode layers",
        )

        assert t.opportunity_id.prefix == "txfr"
        assert t.confidence == 0.0
        assert t.caveats == []
        assert t.caveat_categories == []
        assert t.analogical_map_id is None

    def test_construction_full(self, id_gen):
        map_id = id_gen.generate("amap")
        t = TransferOpportunity(
            opportunity_id=id_gen.generate("txfr"),
            from_vault_id=id_gen.vault_id(),
            to_vault_id=id_gen.vault_id(),
            mechanism="Graph-theoretic routing optimization for ion transport",
            rationale="Both systems exhibit flow-through-layered-network structure",
            caveats=["Scale mismatch", "Domain assumption about reversibility"],
            caveat_categories=["scale", "domain_assumption"],
            analogical_map_id=map_id,
            confidence=0.75,
            problem_relevance=0.88,
            from_page_refs=[id_gen.page_id()],
            to_page_refs=[id_gen.page_id()],
            from_claim_refs=[id_gen.claim_id()],
        )

        assert t.confidence == 0.75
        assert len(t.caveats) == 2
        assert len(t.caveat_categories) == 2
        assert t.analogical_map_id == map_id


class TestPairFusionManifest:
    def test_construction(self, id_gen):
        left = id_gen.vault_id()
        right = id_gen.vault_id()

        pm = PairFusionManifest(
            left_vault_id=left,
            right_vault_id=right,
            left_revision=VaultRevisionId(f"rev_{1:026d}"),
            right_revision=VaultRevisionId(f"rev_{2:026d}"),
            candidate_count=25,
            map_count=8,
            transfer_count=3,
        )

        assert pm.left_vault_id == left
        assert pm.candidate_count == 25
        assert pm.analyzer_calls == []


class TestFusionManifest:
    def test_construction(self, id_gen):
        vault_ids = [id_gen.vault_id(), id_gen.vault_id()]

        fm = FusionManifest(
            manifest_id=id_gen.generate("mfst"),
            vault_ids=vault_ids,
            problem="Improve battery longevity",
            fusion_mode=FusionMode.STRICT,
            candidate_count=50,
            analyzed_count=50,
            bridge_count=12,
            transfer_count=5,
            policy_version="1.0.0",
            analyzer_version="anthropic_v1",
            created_at=_now(),
        )

        assert fm.manifest_id.prefix == "mfst"
        assert fm.problem == "Improve battery longevity"
        assert fm.fusion_mode == FusionMode.STRICT
        assert fm.bridge_count == 12
        assert fm.pair_manifests == []
        assert fm.analyzer_calls == []

    def test_construction_with_pair_manifests(self, id_gen):
        v1 = id_gen.vault_id()
        v2 = id_gen.vault_id()
        v3 = id_gen.vault_id()

        pair1 = PairFusionManifest(
            left_vault_id=v1,
            right_vault_id=v2,
            left_revision=VaultRevisionId(f"rev_{1:026d}"),
            right_revision=VaultRevisionId(f"rev_{2:026d}"),
            candidate_count=20,
            map_count=5,
            transfer_count=2,
        )
        pair2 = PairFusionManifest(
            left_vault_id=v1,
            right_vault_id=v3,
            left_revision=VaultRevisionId(f"rev_{1:026d}"),
            right_revision=VaultRevisionId(f"rev_{3:026d}"),
            candidate_count=15,
            map_count=3,
            transfer_count=1,
        )

        fm = FusionManifest(
            manifest_id=id_gen.generate("mfst"),
            vault_ids=[v1, v2, v3],
            problem=None,
            fusion_mode=FusionMode.EXPLORATORY,
            candidate_count=35,
            analyzed_count=35,
            bridge_count=8,
            transfer_count=3,
            policy_version="1.0.0",
            analyzer_version="mock_v1",
            pair_manifests=[pair1, pair2],
            created_at=_now(),
        )

        assert len(fm.pair_manifests) == 2
        assert fm.fusion_mode == FusionMode.EXPLORATORY
