"""Tests for role signature prompt parsing."""

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    ConstraintTag,
    ControlPatternTag,
    FailureModeTag,
    RoleTag,
    SignatureSubjectKind,
    TimeScaleTag,
    TopologyTag,
)
from hephaestus.transliminality.prompts.role_signature import (
    ROLE_SIGNATURE_SYSTEM,
    ROLE_SIGNATURE_USER,
    parse_role_signature,
)

_idgen = DeterministicIdGenerator(seed=400)


class TestPromptTemplates:
    def test_system_prompt_mentions_all_role_tags(self) -> None:
        for tag in RoleTag:
            assert tag.name in ROLE_SIGNATURE_SYSTEM

    def test_system_prompt_mentions_all_constraint_tags(self) -> None:
        for tag in ConstraintTag:
            assert tag.name in ROLE_SIGNATURE_SYSTEM

    def test_user_prompt_has_placeholder(self) -> None:
        rendered = ROLE_SIGNATURE_USER.format(problem="test problem")
        assert "test problem" in rendered


class TestParseRoleSignature:
    def test_full_parse(self) -> None:
        raw = {
            "functional_roles": ["FILTER", "GATE", "DETECT"],
            "inputs": [{"name": "flow", "description": "incoming data stream"}],
            "outputs": [{"name": "filtered_flow"}, {"name": "alerts"}],
            "constraints": ["CAPACITY_LIMIT", "LATENCY_BOUND"],
            "failure_modes": ["OVERLOAD", "LEAKAGE"],
            "control_patterns": ["THRESHOLDING", "FEEDBACK"],
            "timescale": "MILLISECOND",
            "resource_profile": [
                {"name": "cpu", "direction": "consumed", "description": "processing"},
            ],
            "topology": ["LAYERED"],
            "confidence": 0.85,
            "rationale": "The problem requires selective filtering with latency constraints.",
        }
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)

        assert sig.subject_kind == SignatureSubjectKind.PROBLEM
        assert len(sig.functional_roles) == 3
        assert RoleTag.FILTER in sig.functional_roles
        assert RoleTag.GATE in sig.functional_roles
        assert len(sig.inputs) == 1
        assert sig.inputs[0].name == "flow"
        assert len(sig.outputs) == 2
        assert len(sig.constraints) == 2
        assert ConstraintTag.CAPACITY_LIMIT in sig.constraints
        assert len(sig.failure_modes) == 2
        assert FailureModeTag.OVERLOAD in sig.failure_modes
        assert len(sig.control_patterns) == 2
        assert ControlPatternTag.THRESHOLDING in sig.control_patterns
        assert sig.timescale == TimeScaleTag.MILLISECOND
        assert len(sig.resource_profile) == 1
        assert sig.resource_profile[0].name == "cpu"
        assert sig.topology == [TopologyTag.LAYERED]
        assert sig.confidence == 0.85

    def test_empty_parse(self) -> None:
        sig = parse_role_signature({}, problem="test", id_generator=_idgen)
        assert sig.functional_roles == []
        assert sig.inputs == []
        assert sig.constraints == []
        assert sig.timescale is None
        assert sig.confidence == 0.0

    def test_invalid_enum_values_skipped(self) -> None:
        raw = {
            "functional_roles": ["FILTER", "NONEXISTENT_ROLE", "GATE"],
            "constraints": ["CAPACITY_LIMIT", "BOGUS_CONSTRAINT"],
        }
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert len(sig.functional_roles) == 2  # NONEXISTENT skipped
        assert len(sig.constraints) == 1  # BOGUS skipped

    def test_lowercase_enum_values_accepted(self) -> None:
        raw = {
            "functional_roles": ["filter", "gate"],
            "timescale": "millisecond",
        }
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert RoleTag.FILTER in sig.functional_roles
        assert sig.timescale == TimeScaleTag.MILLISECOND

    def test_signals_from_strings(self) -> None:
        """LLMs sometimes return plain strings instead of dicts for inputs/outputs."""
        raw = {
            "inputs": ["raw_data", "config"],
            "outputs": ["processed_output"],
        }
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert len(sig.inputs) == 2
        assert sig.inputs[0].name == "raw_data"
        assert len(sig.outputs) == 1

    def test_null_timescale(self) -> None:
        raw = {"timescale": None}
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert sig.timescale is None

    def test_string_null_timescale(self) -> None:
        raw = {"timescale": "null"}
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert sig.timescale is None

    def test_signature_id_generated(self) -> None:
        raw = {"functional_roles": ["FILTER"]}
        sig = parse_role_signature(raw, problem="test", id_generator=_idgen)
        assert sig.signature_id.prefix == "sig"
        assert sig.subject_ref.entity_kind == "problem"
