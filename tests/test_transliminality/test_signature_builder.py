"""Tests for the LLM-backed ProblemRoleSignatureBuilder."""

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    ConstraintTag,
    RoleTag,
    SignatureSubjectKind,
)
from hephaestus.transliminality.domain.models import TransliminalityConfig
from hephaestus.transliminality.service.problem_signature_builder import (
    LLMProblemRoleSignatureBuilder,
    SignatureBuilderError,
)

_idgen = DeterministicIdGenerator(seed=700)


@dataclass
class _FakeForgeTrace:
    total_cost_usd: float = 0.001
    total_input_tokens: int = 500
    total_output_tokens: int = 200


@dataclass
class _FakeForgeResult:
    output: str
    trace: _FakeForgeTrace


def _mock_harness(output_json: dict) -> MagicMock:
    """Build a mock DeepForgeHarness that returns the given JSON."""
    harness = MagicMock()
    harness.forge = AsyncMock(
        return_value=_FakeForgeResult(output=json.dumps(output_json), trace=_FakeForgeTrace()),
    )
    return harness


class TestLLMProblemRoleSignatureBuilder:
    async def test_successful_extraction(self) -> None:
        harness = _mock_harness({
            "functional_roles": ["FILTER", "GATE"],
            "inputs": [{"name": "raw_signal", "description": "unfiltered input"}],
            "outputs": [{"name": "clean_signal"}],
            "constraints": ["LATENCY_BOUND"],
            "failure_modes": ["OVERLOAD"],
            "control_patterns": ["THRESHOLDING"],
            "timescale": "MILLISECOND",
            "resource_profile": [],
            "topology": ["LAYERED"],
            "confidence": 0.82,
            "rationale": "Filtering problem with latency constraints.",
        })

        builder = LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=_idgen,
        )

        sig = await builder.build(
            problem="How can we filter noise from sensor data in real-time?",
            home_vault_ids=[_idgen.generate("vault")],
            branch_id=None,
            config=TransliminalityConfig(),
        )

        assert sig.subject_kind == SignatureSubjectKind.PROBLEM
        assert RoleTag.FILTER in sig.functional_roles
        assert RoleTag.GATE in sig.functional_roles
        assert ConstraintTag.LATENCY_BOUND in sig.constraints
        assert sig.confidence == 0.82
        harness.forge.assert_awaited_once()

    async def test_retry_on_empty_roles(self) -> None:
        """Builder retries when LLM returns no functional roles."""
        call_count = 0

        async def _forge_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeForgeResult(
                    output=json.dumps({"functional_roles": [], "confidence": 0.5}),
                    trace=_FakeForgeTrace(),
                )
            return _FakeForgeResult(
                output=json.dumps({"functional_roles": ["DETECT"], "confidence": 0.7}),
                trace=_FakeForgeTrace(),
            )

        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=_forge_side_effect)

        builder = LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=_idgen,
            max_retries=3,
        )

        sig = await builder.build(
            problem="test", home_vault_ids=[], branch_id=None,
            config=TransliminalityConfig(),
        )
        assert call_count == 2
        assert RoleTag.DETECT in sig.functional_roles

    async def test_retry_on_unparseable_output(self) -> None:
        """Builder retries when LLM returns non-JSON."""
        call_count = 0

        async def _forge_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeForgeResult(output="not json at all", trace=_FakeForgeTrace())
            return _FakeForgeResult(
                output=json.dumps({"functional_roles": ["BUFFER"], "confidence": 0.6}),
                trace=_FakeForgeTrace(),
            )

        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=_forge_side_effect)

        builder = LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=_idgen,
            max_retries=3,
        )

        sig = await builder.build(
            problem="test", home_vault_ids=[], branch_id=None,
            config=TransliminalityConfig(),
        )
        assert call_count == 2
        assert RoleTag.BUFFER in sig.functional_roles

    async def test_fails_after_max_retries(self) -> None:
        """Builder raises after exhausting all retries."""
        harness = _mock_harness({"functional_roles": []})  # always empty roles

        builder = LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=_idgen,
            max_retries=2,
        )

        with pytest.raises(SignatureBuilderError, match="Failed to extract"):
            await builder.build(
                problem="test", home_vault_ids=[], branch_id=None,
                config=TransliminalityConfig(),
            )

    async def test_fails_on_exception(self) -> None:
        """Builder raises when harness throws."""
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=RuntimeError("API down"))

        builder = LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=_idgen,
            max_retries=2,
        )

        with pytest.raises(SignatureBuilderError):
            await builder.build(
                problem="test", home_vault_ids=[], branch_id=None,
                config=TransliminalityConfig(),
            )
