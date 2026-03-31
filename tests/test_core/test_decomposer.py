"""
Tests for Stage 1: Problem Decomposer.

All LLM calls are mocked — no API keys required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.core.decomposer import (
    DecompositionError,
    ProblemDecomposer,
    ProblemStructure,
)
from hephaestus.deepforge.adapters.base import GenerationResult
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_forge_result(text: str, cost: float = 0.01) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


def _make_harness(output: str) -> MagicMock:
    harness = MagicMock()
    harness.forge = AsyncMock(return_value=_make_forge_result(output))
    return harness


def _valid_decompose_json(**overrides) -> str:
    data = {
        "structure": "A system for distributing computation across unreliable nodes",
        "constraints": ["must tolerate node failures", "low latency required"],
        "mathematical_shape": "robust resource allocation in a graph with Byzantine fault tolerance",
        "native_domain": "distributed_systems",
        "problem_maps_to": ["routing", "allocation", "fault_tolerance"],
        "confidence": 0.9,
    }
    data.update(overrides)
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Tests: ProblemStructure
# ---------------------------------------------------------------------------


class TestProblemStructure:
    def test_basic_creation(self):
        ps = ProblemStructure(
            original_problem="Test problem",
            structure="Abstract form",
            constraints=["constraint 1"],
            mathematical_shape="graph optimization",
            native_domain="cs",
        )
        assert ps.original_problem == "Test problem"
        assert ps.native_domain == "cs"
        assert isinstance(ps.problem_maps_to, set)

    def test_problem_maps_to_normalised_to_set(self):
        ps = ProblemStructure(
            original_problem="test",
            structure="s",
            constraints=[],
            mathematical_shape="m",
            native_domain="cs",
            problem_maps_to=["routing", "allocation"],
        )
        assert isinstance(ps.problem_maps_to, set)
        assert "routing" in ps.problem_maps_to

    def test_to_search_description(self):
        ps = ProblemStructure(
            original_problem="test",
            structure="robust signal propagation",
            constraints=[],
            mathematical_shape="graph with Byzantine fault tolerance",
            native_domain="cs",
        )
        desc = ps.to_search_description()
        assert "robust signal propagation" in desc
        assert "Byzantine" in desc

    def test_summary(self):
        ps = ProblemStructure(
            original_problem="test",
            structure="s",
            constraints=["c1", "c2"],
            mathematical_shape="graph theory",
            native_domain="cs",
            confidence=0.85,
        )
        summary = ps.summary()
        assert "cs" in summary
        assert "0.85" in summary
        assert "constraints=2" in summary


# ---------------------------------------------------------------------------
# Tests: ProblemDecomposer
# ---------------------------------------------------------------------------


class TestProblemDecomposer:
    @pytest.mark.asyncio
    async def test_successful_decomposition(self):
        harness = _make_harness(_valid_decompose_json())
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose(
            "I need a fault-tolerant distributed task scheduler"
        )

        assert isinstance(result, ProblemStructure)
        assert result.structure
        assert result.mathematical_shape
        assert result.native_domain == "distributed_systems"
        assert len(result.constraints) == 2
        assert "routing" in result.problem_maps_to
        assert result.confidence == 0.9
        assert result.cost_usd > 0

    @pytest.mark.asyncio
    async def test_decomposition_with_markdown_fences(self):
        """Model wraps JSON in markdown fences — should still parse."""
        json_text = _valid_decompose_json()
        wrapped = f"```json\n{json_text}\n```"
        harness = _make_harness(wrapped)
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test problem")
        assert result.structure is not None

    @pytest.mark.asyncio
    async def test_decomposition_with_preamble(self):
        """Model adds preamble before JSON — should extract JSON object."""
        json_text = _valid_decompose_json()
        with_preamble = f"Here is the decomposition:\n\n{json_text}\n\nDone."
        harness = _make_harness(with_preamble)
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test problem")
        assert result.structure is not None

    @pytest.mark.asyncio
    async def test_empty_problem_raises(self):
        harness = MagicMock()
        decomposer = ProblemDecomposer(harness)

        with pytest.raises(DecompositionError, match="Empty problem"):
            await decomposer.decompose("")

    @pytest.mark.asyncio
    async def test_whitespace_only_problem_raises(self):
        harness = MagicMock()
        decomposer = ProblemDecomposer(harness)

        with pytest.raises(DecompositionError, match="Empty problem"):
            await decomposer.decompose("   \n  ")

    @pytest.mark.asyncio
    async def test_retries_on_bad_json(self):
        """Should retry if model returns non-JSON, succeed on second attempt."""
        good = _valid_decompose_json()
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            _make_forge_result("not json at all"),
            _make_forge_result(good),
        ])
        decomposer = ProblemDecomposer(harness, max_retries=3)

        result = await decomposer.decompose("test problem")
        assert result.structure is not None
        assert harness.forge.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        """All attempts return bad JSON — should raise DecompositionError."""
        harness = _make_harness("this is not json")
        harness.forge = AsyncMock(return_value=_make_forge_result("bad output"))
        decomposer = ProblemDecomposer(harness, max_retries=2)

        with pytest.raises(DecompositionError):
            await decomposer.decompose("test problem")

        assert harness.forge.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_required_field_triggers_retry(self):
        """JSON missing 'mathematical_shape' should trigger retry."""
        bad_json = json.dumps({"structure": "something"})  # missing mathematical_shape
        good_json = _valid_decompose_json()
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            _make_forge_result(bad_json),
            _make_forge_result(good_json),
        ])
        decomposer = ProblemDecomposer(harness, max_retries=3)

        result = await decomposer.decompose("test problem")
        assert result.mathematical_shape is not None

    @pytest.mark.asyncio
    async def test_missing_constraints_defaults_to_empty_list(self):
        """If constraints are missing from JSON, defaults to []."""
        json_text = json.dumps({
            "structure": "abstract form",
            "mathematical_shape": "graph flow",
            "native_domain": "cs",
            "confidence": 0.8,
        })
        harness = _make_harness(json_text)
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test")
        assert result.constraints == []

    @pytest.mark.asyncio
    async def test_missing_native_domain_defaults(self):
        """If native_domain missing, defaults to 'general'."""
        json_text = json.dumps({
            "structure": "abstract form",
            "mathematical_shape": "graph flow",
        })
        harness = _make_harness(json_text)
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test")
        assert result.native_domain == "general"

    @pytest.mark.asyncio
    async def test_cost_tracked(self):
        harness = _make_harness(_valid_decompose_json())
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_decompose_json(), cost=0.025))
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test")
        assert result.cost_usd == 0.025

    @pytest.mark.asyncio
    async def test_duration_tracked(self):
        harness = _make_harness(_valid_decompose_json())
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test")
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_trace_attached(self):
        harness = _make_harness(_valid_decompose_json())
        decomposer = ProblemDecomposer(harness)

        result = await decomposer.decompose("test")
        assert result.trace is not None
