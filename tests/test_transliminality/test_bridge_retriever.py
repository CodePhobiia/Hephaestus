"""Tests for fusion adapter and bridge retriever."""

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.adapters.fusion import (
    _map_kind,
    _map_reason,
    convert_bridge_candidate,
)
from hephaestus.transliminality.domain.enums import (
    BridgeEntityKind,
    RetrievalReason,
    RoleTag,
    SignatureSubjectKind,
)
from hephaestus.transliminality.domain.models import (
    EntityRef,
    RoleSignature,
)
from hephaestus.transliminality.service.bridge_retriever import (
    _build_problem_text,
)

_idgen = DeterministicIdGenerator(seed=600)


# ---------------------------------------------------------------------------
# Fusion adapter tests
# ---------------------------------------------------------------------------

class TestKindMapping:
    def test_concept(self) -> None:
        assert _map_kind("concept") == BridgeEntityKind.CONCEPT

    def test_mechanism(self) -> None:
        assert _map_kind("mechanism") == BridgeEntityKind.MECHANISM

    def test_claim_cluster(self) -> None:
        assert _map_kind("claim_cluster") == BridgeEntityKind.CLAIM_CLUSTER

    def test_page_theme_maps_to_page_family(self) -> None:
        assert _map_kind("page_theme") == BridgeEntityKind.PAGE_FAMILY

    def test_exploratory_falls_back_to_concept(self) -> None:
        assert _map_kind("exploratory") == BridgeEntityKind.CONCEPT

    def test_unknown_falls_back_to_concept(self) -> None:
        assert _map_kind("unknown_type") == BridgeEntityKind.CONCEPT


class TestReasonMapping:
    def test_cosine_similarity(self) -> None:
        assert _map_reason("cosine_similarity") == RetrievalReason.EMBEDDING_SIMILARITY

    def test_role_match(self) -> None:
        assert _map_reason("role_match") == RetrievalReason.ROLE_MATCH

    def test_unknown_falls_back(self) -> None:
        assert _map_reason("something_new") == RetrievalReason.EMBEDDING_SIMILARITY


class TestConvertBridgeCandidate:
    def test_conversion(self) -> None:
        """Test conversion from a mock ForgeBase BridgeCandidate-like object."""

        class _FakeFBCandidate:
            candidate_id = _idgen.generate("bcand")
            left_vault_id = _idgen.generate("vault")
            right_vault_id = _idgen.generate("vault")
            left_entity_ref = _idgen.generate("page")
            right_entity_ref = _idgen.generate("page")
            left_kind = "mechanism"
            right_kind = "concept"
            retrieval_reason = "cosine_similarity"
            similarity_score = 0.78
            left_claim_refs: list[EntityId] = []
            right_claim_refs: list[EntityId] = []
            left_source_refs: list[EntityId] = []
            right_source_refs: list[EntityId] = []
            left_revision_ref = None
            right_revision_ref = None
            epistemic_filter_passed = True

        fb = _FakeFBCandidate()
        tlim = convert_bridge_candidate(fb)

        assert tlim.candidate_id == fb.candidate_id
        assert tlim.left_kind == BridgeEntityKind.MECHANISM
        assert tlim.right_kind == BridgeEntityKind.CONCEPT
        assert tlim.retrieval_reason == RetrievalReason.EMBEDDING_SIMILARITY
        assert tlim.similarity_score == 0.78
        assert tlim.left_ref.vault_id == fb.left_vault_id
        assert tlim.right_ref.vault_id == fb.right_vault_id
        assert tlim.epistemic_filter_passed is True


# ---------------------------------------------------------------------------
# Bridge retriever tests
# ---------------------------------------------------------------------------

class TestBuildProblemText:
    def test_includes_roles(self) -> None:
        sig = RoleSignature(
            signature_id=_idgen.generate("sig"),
            subject_ref=EntityRef(entity_id=_idgen.generate("sig"), entity_kind="problem"),
            subject_kind=SignatureSubjectKind.PROBLEM,
            functional_roles=[RoleTag.FILTER, RoleTag.GATE],
        )
        text = _build_problem_text(sig)
        assert "filter" in text
        assert "gate" in text

    def test_includes_constraints_and_failure_modes(self) -> None:
        from hephaestus.transliminality.domain.enums import (
            ConstraintTag,
            FailureModeTag,
        )

        sig = RoleSignature(
            signature_id=_idgen.generate("sig"),
            subject_ref=EntityRef(entity_id=_idgen.generate("sig"), entity_kind="problem"),
            subject_kind=SignatureSubjectKind.PROBLEM,
            constraints=[ConstraintTag.LATENCY_BOUND],
            failure_modes=[FailureModeTag.OVERLOAD],
        )
        text = _build_problem_text(sig)
        assert "latency_bound" in text
        assert "overload" in text

    def test_empty_signature_returns_empty(self) -> None:
        sig = RoleSignature(
            signature_id=_idgen.generate("sig"),
            subject_ref=EntityRef(entity_id=_idgen.generate("sig"), entity_kind="problem"),
            subject_kind=SignatureSubjectKind.PROBLEM,
        )
        text = _build_problem_text(sig)
        assert text == ""
