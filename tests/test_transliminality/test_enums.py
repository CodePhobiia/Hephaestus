"""Tests for transliminality domain enums."""

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
    TimeScaleTag,
    TopologyTag,
    TransliminalityEvent,
    TransliminalityMode,
    TransliminalObjectionType,
    TrustTier,
)


class TestTransliminalityMode:
    def test_members(self) -> None:
        assert TransliminalityMode.CONSERVATIVE
        assert TransliminalityMode.BALANCED
        assert TransliminalityMode.EXPLORATORY

    def test_string_value(self) -> None:
        assert str(TransliminalityMode.BALANCED) == "balanced"


class TestRoleTaxonomy:
    def test_role_tag_count(self) -> None:
        assert len(RoleTag) == 16

    def test_constraint_tag_count(self) -> None:
        assert len(ConstraintTag) == 10

    def test_failure_mode_tag_count(self) -> None:
        assert len(FailureModeTag) == 10

    def test_control_pattern_tag_count(self) -> None:
        assert len(ControlPatternTag) == 10

    def test_timescale_ordering(self) -> None:
        tags = list(TimeScaleTag)
        assert tags[0] == TimeScaleTag.NANOSECOND
        assert tags[-1] == TimeScaleTag.DECADE

    def test_topology_count(self) -> None:
        assert len(TopologyTag) == 10


class TestBridgeEnums:
    def test_bridge_entity_kinds(self) -> None:
        assert BridgeEntityKind.CONCEPT
        assert BridgeEntityKind.MECHANISM
        assert BridgeEntityKind.INVENTION

    def test_retrieval_reasons(self) -> None:
        assert RetrievalReason.ROLE_MATCH
        assert RetrievalReason.EMBEDDING_SIMILARITY
        assert RetrievalReason.PRIOR_BRIDGE_HISTORY


class TestAnalogyEnums:
    def test_verdicts(self) -> None:
        assert len(AnalogicalVerdict) == 4
        assert AnalogicalVerdict.VALID
        assert AnalogicalVerdict.INVALID

    def test_break_categories(self) -> None:
        assert AnalogyBreakCategory.SCALE_MISMATCH
        assert AnalogyBreakCategory.CONSTRAINT_VIOLATION


class TestEpistemicEnums:
    def test_epistemic_state_progression(self) -> None:
        states = list(EpistemicState)
        assert EpistemicState.VERIFIED in states
        assert EpistemicState.REJECTED in states

    def test_trust_tiers(self) -> None:
        assert TrustTier.AUTHORITATIVE
        assert TrustTier.LOW_TRUST

    def test_pack_origin_kinds(self) -> None:
        assert PackOriginKind.VAULT_CLAIM
        assert PackOriginKind.BRIDGE_SYNTHESIS


class TestPantheonObjections:
    def test_all_objection_types(self) -> None:
        assert len(TransliminalObjectionType) == 7
        assert TransliminalObjectionType.ORNAMENTAL_ANALOGY
        assert TransliminalObjectionType.LITERAL_TRANSPLANT
        assert TransliminalObjectionType.UNGROUNDED_BRIDGE


class TestDomainEvents:
    def test_event_values_are_dotted(self) -> None:
        for event in TransliminalityEvent:
            assert event.value.startswith("transliminality.")

    def test_event_count(self) -> None:
        assert len(TransliminalityEvent) == 10
