"""Tests for FusionRequest, FusionResult, PairFusionResult contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    AnalogyVerdict,
    BridgeCandidateKind,
    FusionMode,
)
from hephaestus.forgebase.domain.values import VaultRevisionId
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


class TestFusionEnums:
    def test_fusion_mode_values(self):
        assert FusionMode.STRICT.value == "strict"
        assert FusionMode.EXPLORATORY.value == "exploratory"
        assert len(FusionMode) == 2

    def test_bridge_candidate_kind_values(self):
        assert BridgeCandidateKind.CONCEPT.value == "concept"
        assert BridgeCandidateKind.MECHANISM.value == "mechanism"
        assert BridgeCandidateKind.CLAIM_CLUSTER.value == "claim_cluster"
        assert BridgeCandidateKind.PAGE_THEME.value == "page_theme"
        assert BridgeCandidateKind.EXPLORATORY.value == "exploratory"
        assert len(BridgeCandidateKind) == 5

    def test_analogy_verdict_values(self):
        assert AnalogyVerdict.STRONG_ANALOGY.value == "strong_analogy"
        assert AnalogyVerdict.WEAK_ANALOGY.value == "weak_analogy"
        assert AnalogyVerdict.NO_ANALOGY.value == "no_analogy"
        assert AnalogyVerdict.INVALID.value == "invalid"
        assert len(AnalogyVerdict) == 4


class TestFusionRequest:
    def test_construction_minimal(self, id_gen):
        from hephaestus.forgebase.contracts.fusion import FusionRequest

        vault_ids = [id_gen.vault_id(), id_gen.vault_id()]
        req = FusionRequest(vault_ids=vault_ids)

        assert req.vault_ids == vault_ids
        assert req.problem is None
        assert req.fusion_mode == FusionMode.STRICT
        assert req.policy is None
        assert req.max_candidates == 50
        assert req.max_bridges == 20
        assert req.max_transfers == 10

    def test_construction_with_problem(self, id_gen):
        from hephaestus.forgebase.contracts.fusion import FusionRequest

        req = FusionRequest(
            vault_ids=[id_gen.vault_id(), id_gen.vault_id()],
            problem="How to improve battery longevity?",
            fusion_mode=FusionMode.EXPLORATORY,
            max_candidates=100,
        )

        assert req.problem == "How to improve battery longevity?"
        assert req.fusion_mode == FusionMode.EXPLORATORY
        assert req.max_candidates == 100


class TestFusionResult:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.contracts.fusion import (
            FusionRequest,
            FusionResult,
        )
        from hephaestus.forgebase.fusion.models import FusionManifest

        vault_ids = [id_gen.vault_id(), id_gen.vault_id()]
        req = FusionRequest(vault_ids=vault_ids)

        # Create minimal packs
        rev_id = VaultRevisionId(f"rev_{1:026d}")
        baseline = PriorArtBaselinePack(
            entries=[],
            vault_id=vault_ids[0],
            vault_revision_id=rev_id,
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        context = DomainContextPack(
            concepts=[],
            mechanisms=[],
            open_questions=[],
            explored_directions=[],
            vault_id=vault_ids[0],
            vault_revision_id=rev_id,
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        dossier = ConstraintDossierPack(
            hard_constraints=[],
            known_failure_modes=[],
            validated_objections=[],
            unresolved_controversies=[],
            competitive_landscape=[],
            vault_id=vault_ids[0],
            vault_revision_id=rev_id,
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        manifest = FusionManifest(
            manifest_id=id_gen.generate("mfst"),
            vault_ids=vault_ids,
            problem=None,
            fusion_mode=FusionMode.STRICT,
            candidate_count=0,
            analyzed_count=0,
            bridge_count=0,
            transfer_count=0,
            policy_version="1.0.0",
            analyzer_version="mock_1.0",
            analyzer_calls=[],
            pair_manifests=[],
            created_at=_now(),
        )

        result = FusionResult(
            fusion_id=id_gen.generate("fuse"),
            request=req,
            bridge_concepts=[],
            transfer_opportunities=[],
            fused_baseline=baseline,
            fused_context=context,
            fused_dossier=dossier,
            pair_results=[],
            fusion_manifest=manifest,
            created_at=_now(),
        )

        assert result.fusion_id.prefix == "fuse"
        assert result.request == req
        assert result.bridge_concepts == []
        assert result.transfer_opportunities == []
        assert result.created_at == _now()


class TestPairFusionResult:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.contracts.fusion import PairFusionResult
        from hephaestus.forgebase.fusion.models import PairFusionManifest

        left = id_gen.vault_id()
        right = id_gen.vault_id()

        pair_manifest = PairFusionManifest(
            left_vault_id=left,
            right_vault_id=right,
            left_revision=VaultRevisionId(f"rev_{1:026d}"),
            right_revision=VaultRevisionId(f"rev_{2:026d}"),
            candidate_count=5,
            map_count=2,
            transfer_count=1,
            analyzer_calls=[],
        )

        pair_result = PairFusionResult(
            left_vault_id=left,
            right_vault_id=right,
            candidates_generated=5,
            maps_produced=[],
            transfers_produced=[],
            pair_manifest=pair_manifest,
        )

        assert pair_result.left_vault_id == left
        assert pair_result.right_vault_id == right
        assert pair_result.candidates_generated == 5
