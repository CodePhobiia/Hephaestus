"""Tests for transliminality domain models."""

from dataclasses import FrozenInstanceError

import pytest

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    BridgeEntityKind,
    ConstraintTag,
    ControlPatternTag,
    EpistemicState,
    FailureModeTag,
    PackOriginKind,
    RetrievalReason,
    RoleTag,
    SignatureSubjectKind,
    TimeScaleTag,
    TopologyTag,
    TransliminalityMode,
    TrustTier,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogyBreak,
    BridgeCandidate,
    ComponentMapping,
    EntityRef,
    IntegrationScoreBreakdown,
    KnowledgePackEntry,
    ResourceTag,
    RoleSignature,
    SignalTag,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityConfig,
    TransliminalityPack,
    TransliminalityRequest,
    TransliminalityRunManifest,
)


def _id(prefix: str = "test") -> EntityId:
    return DeterministicIdGenerator(seed=0).generate(prefix)


def _ref(prefix: str = "test", kind: str = "test") -> EntityRef:
    return EntityRef(entity_id=_id(prefix), entity_kind=kind)


class TestEntityRef:
    def test_str_without_vault(self) -> None:
        ref = _ref("page", "page")
        assert "page:" in str(ref)

    def test_str_with_vault(self) -> None:
        vault_id = _id("vault")
        ref = EntityRef(entity_id=_id("page"), entity_kind="page", vault_id=vault_id)
        assert str(ref).startswith(str(vault_id))

    def test_frozen(self) -> None:
        ref = _ref()
        with pytest.raises(FrozenInstanceError):
            ref.entity_kind = "other"  # type: ignore[misc]


class TestTransliminalityConfig:
    def test_defaults(self) -> None:
        cfg = TransliminalityConfig()
        assert cfg.enabled is True
        assert cfg.mode == TransliminalityMode.BALANCED
        assert cfg.max_remote_vaults == 3
        assert cfg.strict_channel_min_confidence == 0.80
        assert cfg.soft_channel_min_confidence == 0.50

    def test_conservative_mode(self) -> None:
        cfg = TransliminalityConfig(mode=TransliminalityMode.CONSERVATIVE)
        assert cfg.mode == TransliminalityMode.CONSERVATIVE

    def test_frozen(self) -> None:
        cfg = TransliminalityConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.enabled = False  # type: ignore[misc]


class TestTransliminalityRequest:
    def test_construction(self) -> None:
        run_id = _id("run")
        req = TransliminalityRequest(
            run_id=run_id,
            problem="How can we filter contaminants at nanoscale?",
            home_vault_ids=[_id("vault")],
            config=TransliminalityConfig(),
        )
        assert req.run_id == run_id
        assert req.branch_id is None
        assert req.remote_vault_ids is None


class TestRoleSignature:
    def test_minimal(self) -> None:
        sig = RoleSignature(
            signature_id=_id("sig"),
            subject_ref=_ref("prob", "problem"),
            subject_kind=SignatureSubjectKind.PROBLEM,
        )
        assert sig.functional_roles == []
        assert sig.confidence == 0.0

    def test_full_taxonomy(self) -> None:
        sig = RoleSignature(
            signature_id=_id("sig"),
            subject_ref=_ref("mech", "mechanism"),
            subject_kind=SignatureSubjectKind.MECHANISM,
            functional_roles=[RoleTag.FILTER, RoleTag.GATE],
            inputs=[SignalTag(name="flow", description="incoming fluid")],
            outputs=[SignalTag(name="filtered_flow")],
            constraints=[ConstraintTag.CAPACITY_LIMIT, ConstraintTag.PRECISION_REQUIREMENT],
            failure_modes=[FailureModeTag.OVERLOAD, FailureModeTag.LEAKAGE],
            control_patterns=[ControlPatternTag.THRESHOLDING],
            timescale=TimeScaleTag.MILLISECOND,
            resource_profile=[ResourceTag(name="energy", direction="consumed")],
            topology=[TopologyTag.LAYERED],
            confidence=0.85,
        )
        assert len(sig.functional_roles) == 2
        assert sig.timescale == TimeScaleTag.MILLISECOND


class TestBridgeCandidate:
    def test_construction(self) -> None:
        idgen = DeterministicIdGenerator(seed=10)
        bc = BridgeCandidate(
            candidate_id=idgen.generate("bc"),
            left_ref=_ref("page", "page"),
            right_ref=_ref("page", "page"),
            left_signature_ref=_ref("sig", "role_signature"),
            right_signature_ref=_ref("sig", "role_signature"),
            left_kind=BridgeEntityKind.MECHANISM,
            right_kind=BridgeEntityKind.CONCEPT,
            retrieval_reason=RetrievalReason.ROLE_MATCH,
            similarity_score=0.72,
        )
        assert bc.similarity_score == 0.72
        assert bc.epistemic_filter_passed is True


class TestAnalogicalMap:
    def test_defaults(self) -> None:
        am = AnalogicalMap(
            map_id=_id("map"),
            candidate_ref=_ref("bc", "bridge_candidate"),
            shared_role="selective filtering",
        )
        assert am.verdict == AnalogicalVerdict.INVALID
        assert am.mapped_components == []
        assert am.confidence == 0.0

    def test_with_breaks(self) -> None:
        brk = AnalogyBreak(
            category=AnalogyBreakCategory.SCALE_MISMATCH,
            description="Source operates at molecular scale, target at macro",
            severity=0.6,
        )
        am = AnalogicalMap(
            map_id=_id("map"),
            candidate_ref=_ref("bc", "bridge_candidate"),
            shared_role="redundancy under failure",
            analogy_breaks=[brk],
            verdict=AnalogicalVerdict.PARTIAL,
            confidence=0.65,
        )
        assert len(am.analogy_breaks) == 1
        assert am.analogy_breaks[0].severity == 0.6

    def test_component_mapping(self) -> None:
        cm = ComponentMapping(
            left_component_ref=_ref("comp", "component"),
            right_component_ref=_ref("comp", "component"),
            shared_role="gate",
            mapping_rationale="Both control flow admission under pressure",
        )
        assert cm.shared_role == "gate"


class TestTransferOpportunity:
    def test_construction(self) -> None:
        to = TransferOpportunity(
            opportunity_id=_id("top"),
            map_ref=_ref("map", "analogical_map"),
            title="Immune checkpoint → API rate limiter",
            transferred_mechanism="staged activation gating",
            target_problem_fit="Rate limiting needs selective, staged admission control",
            expected_benefit="Adaptive rate limiting that responds to threat signals",
            required_transformations=["Replace molecular signals with request metadata"],
            caveats=[TransferCaveat(category="scale", description="Timescale differs")],
            confidence=0.75,
            epistemic_state=EpistemicState.HYPOTHESIS,
        )
        assert to.confidence == 0.75
        assert len(to.caveats) == 1


class TestKnowledgePackEntry:
    def test_defaults(self) -> None:
        entry = KnowledgePackEntry(
            entry_id=_id("kpe"),
            text="Immune checkpoints use staged activation for selective gating",
            origin_kind=PackOriginKind.VAULT_CLAIM,
        )
        assert entry.epistemic_state == EpistemicState.VALIDATED
        assert entry.trust_tier == TrustTier.INTERNAL_VERIFIED
        assert entry.salience == 0.0


class TestIntegrationScoreBreakdown:
    def test_defaults_are_zero(self) -> None:
        isb = IntegrationScoreBreakdown()
        assert isb.structural_alignment == 0.0
        assert isb.non_ornamental_use == 0.0


class TestTransliminalityPack:
    def test_empty_pack(self) -> None:
        pack = TransliminalityPack(
            pack_id=_id("tpack"),
            run_id=_id("run"),
            problem_signature_ref=_ref("sig", "role_signature"),
        )
        assert pack.strict_baseline_entries == []
        assert pack.soft_context_entries == []
        assert pack.strict_constraint_entries == []
        assert pack.policy_version == "1.0"


class TestTransliminalityRunManifest:
    def test_construction(self) -> None:
        manifest = TransliminalityRunManifest(
            manifest_id=_id("tman"),
            run_id=_id("run"),
            candidate_count=40,
            analyzed_count=12,
            valid_map_count=4,
            rejected_map_count=8,
            transfer_opportunity_count=3,
        )
        assert manifest.candidate_count == 40
        assert manifest.valid_map_count == 4
