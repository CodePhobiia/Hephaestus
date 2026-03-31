"""
Tests for the DeepForge Harness orchestrator.

All sub-engines and adapters are mocked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from hephaestus.deepforge.adapters.base import GenerationResult, StreamChunk
from hephaestus.deepforge.exceptions import ConvergenceDetected, GenerationKilled
from hephaestus.deepforge.harness import (
    DeepForgeHarness,
    ForgeResult,
    ForgeTrace,
    HarnessConfig,
)
from hephaestus.deepforge.interference import InjectionStrategy, Lens
from hephaestus.deepforge.pressure import PressureTrace
from hephaestus.deepforge.pruner import ConvergencePattern, ConvergencePruner, PruneResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vec(dim: int, idx: int) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def _make_result(text: str = "output", in_tok: int = 100, out_tok: int = 50) -> GenerationResult:
    return GenerationResult(
        text=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=0.001,
        model="mock-model",
        stop_reason="end_turn",
    )


def _make_adapter(responses: list[str] | None = None) -> MagicMock:
    adapter = MagicMock()
    adapter.model_name = "mock-model"
    adapter.config.provider = "mock"
    adapter.is_cancelled = False

    results = [_make_result(r) for r in (responses or ["Default output."])]
    adapter.generate = AsyncMock(side_effect=results)
    adapter.cancel_stream = MagicMock()
    adapter.compute_cost = MagicMock(return_value=0.001)
    return adapter


def _make_lens(name: str = "Biology", axioms: list[str] | None = None) -> Lens:
    return Lens(
        name=name,
        domain="biology",
        axioms=axioms or ["Axiom 1", "Axiom 2"],
    )


async def _successful_stream(text: str) -> AsyncIterator[StreamChunk]:
    """Yield a simple successful stream for a given text."""
    words = text.split()
    accumulated = ""
    for word in words:
        accumulated += word + " "
        yield StreamChunk(delta=word + " ", accumulated=accumulated)
    yield StreamChunk(
        delta="",
        accumulated=accumulated.strip(),
        is_final=True,
        input_tokens=20,
        output_tokens=len(words),
        stop_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# HarnessConfig
# ---------------------------------------------------------------------------


class TestHarnessConfig:
    def test_defaults(self) -> None:
        cfg = HarnessConfig()
        assert cfg.use_interference is True
        assert cfg.use_pruner is True
        assert cfg.use_pressure is True
        assert cfg.max_pressure_rounds == 3
        assert cfg.max_tokens == 4096

    def test_custom_values(self) -> None:
        cfg = HarnessConfig(
            use_interference=False,
            max_pressure_rounds=5,
            temperature=0.5,
        )
        assert not cfg.use_interference
        assert cfg.max_pressure_rounds == 5
        assert cfg.temperature == 0.5


# ---------------------------------------------------------------------------
# DeepForgeHarness initialisation
# ---------------------------------------------------------------------------


class TestHarnessInit:
    def test_all_engines_disabled_by_default_no_lenses(self) -> None:
        adapter = _make_adapter()
        cfg = HarnessConfig(use_interference=True, lenses=[])  # no lenses → no engine
        harness = DeepForgeHarness(adapter, cfg)
        assert harness.interference_engine is None

    def test_engines_created_when_enabled(self) -> None:
        adapter = _make_adapter()
        lens = _make_lens()
        cfg = HarnessConfig(
            lenses=[lens],
            use_interference=True,
            use_pruner=True,
            use_pressure=True,
        )
        harness = DeepForgeHarness(adapter, cfg)
        assert harness.interference_engine is not None
        assert harness.pruner is not None
        assert harness.pressure_engine is not None

    def test_engines_disabled(self) -> None:
        adapter = _make_adapter()
        cfg = HarnessConfig(
            use_interference=False,
            use_pruner=False,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)
        assert harness.interference_engine is None
        assert harness.pruner is None
        assert harness.pressure_engine is None


# ---------------------------------------------------------------------------
# Pressure-pipeline mode (all three mechanisms)
# ---------------------------------------------------------------------------


class TestHarnessWithPressure:
    @pytest.mark.asyncio
    async def test_forge_with_pressure_returns_result(self) -> None:
        adapter = _make_adapter(["Default.", "Novel answer."])
        lens = _make_lens()

        # Mock the pressure engine's apply() to return a success trace
        pressure_trace = PressureTrace(
            final_output="Novel answer.",
            success=True,
            rounds_completed=2,
            total_cost_usd=0.002,
            total_input_tokens=200,
            total_output_tokens=100,
        )

        cfg = HarnessConfig(
            lenses=[lens],
            use_interference=True,
            use_pruner=True,
            use_pressure=True,
        )
        harness = DeepForgeHarness(adapter, cfg)

        with patch.object(
            harness._pressure, "apply", new=AsyncMock(return_value=pressure_trace)
        ):
            result = await harness.forge("Design a trustless system.")

        assert isinstance(result, ForgeResult)
        assert result.output == "Novel answer."
        assert result.success is True
        assert result.trace.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_forge_with_pressure_unsuccessful_returns_last_output(self) -> None:
        adapter = _make_adapter(["Default."])
        emb = _unit_vec(64, 0)
        blocked_path = MagicMock()
        blocked_path.text = "Fallback text from blocked path."

        pressure_trace = PressureTrace(
            final_output="",  # empty — no novel found
            success=False,
            rounds_completed=3,
            total_cost_usd=0.003,
            total_input_tokens=300,
            total_output_tokens=150,
            blocked_paths=[blocked_path],
        )

        cfg = HarnessConfig(lenses=[_make_lens()], use_pressure=True)
        harness = DeepForgeHarness(adapter, cfg)

        with patch.object(
            harness._pressure, "apply", new=AsyncMock(return_value=pressure_trace)
        ):
            result = await harness.forge("Hard problem.")

        assert result.output == "Fallback text from blocked path."
        assert result.success is False


# ---------------------------------------------------------------------------
# Pruner-only mode
# ---------------------------------------------------------------------------


class TestHarnessWithPruner:
    @pytest.mark.asyncio
    async def test_forge_pruner_only_success(self) -> None:
        adapter = _make_adapter()
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=True,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)

        # Mock the pruner's monitor_stream to return success immediately
        prune_result = PruneResult(
            text="Clean novel output.",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
            stop_reason="end_turn",
        )

        # generate_stream must return an async iterator
        async def _mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(delta="Clean novel output.", accumulated="Clean novel output.")
            yield StreamChunk(
                delta="", accumulated="Clean novel output.",
                is_final=True, input_tokens=100, output_tokens=20, stop_reason="end_turn"
            )

        adapter.generate_stream = _mock_stream

        with patch.object(
            harness._pruner, "monitor_stream", new=AsyncMock(return_value=prune_result)
        ):
            result = await harness.forge("What is the solution?")

        assert result.output == "Clean novel output."
        assert result.success is True

    @pytest.mark.asyncio
    async def test_forge_retries_on_convergence(self) -> None:
        """Convergence kills should trigger retries up to max_pruner_retries."""
        adapter = _make_adapter()
        cfg = HarnessConfig(
            lenses=[_make_lens()],
            use_interference=True,
            use_pruner=True,
            use_pressure=False,
            max_pruner_retries=3,
        )
        harness = DeepForgeHarness(adapter, cfg)

        kill_count = 0

        async def _mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(delta="tok", accumulated="tok")

        adapter.generate_stream = _mock_stream

        async def _monitor_stream_side_effect(*args: Any, **kwargs: Any) -> PruneResult:
            nonlocal kill_count
            kill_count += 1
            if kill_count < 3:
                raise ConvergenceDetected(
                    partial_output="partial...",
                    pattern_similarity=0.95,
                    matched_pattern="The obvious answer.",
                )
            return PruneResult(
                text="Finally novel!",
                input_tokens=100,
                output_tokens=20,
                cost_usd=0.001,
                stop_reason="end_turn",
            )

        with patch.object(
            harness._pruner,
            "monitor_stream",
            side_effect=_monitor_stream_side_effect,
        ):
            result = await harness.forge("Solve this.")

        assert result.output == "Finally novel!"
        assert result.trace.pruner_kills == 2  # 2 kills before success

    @pytest.mark.asyncio
    async def test_forge_exhausts_retries_returns_partial(self) -> None:
        """When all retries are exhausted, harness returns the last partial output."""
        adapter = _make_adapter()
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=True,
            use_pressure=False,
            max_pruner_retries=2,
        )
        harness = DeepForgeHarness(adapter, cfg)

        async def _mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(delta="tok", accumulated="tok")

        adapter.generate_stream = _mock_stream

        call_count = 0

        async def _always_kill(*args: Any, **kwargs: Any) -> PruneResult:
            nonlocal call_count
            call_count += 1
            raise ConvergenceDetected("partial", 0.95, "pattern")

        with patch.object(harness._pruner, "monitor_stream", side_effect=_always_kill):
            result = await harness.forge("Impossible problem.")

        assert result.success is False
        assert result.stop_reason == "max_retries_exhausted"


# ---------------------------------------------------------------------------
# No mechanisms (bare adapter)
# ---------------------------------------------------------------------------


class TestHarnessNoMechanisms:
    @pytest.mark.asyncio
    async def test_forge_bare_calls_adapter_directly(self) -> None:
        adapter = _make_adapter(["Direct output."])
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=False,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)
        result = await harness.forge("Simple question.")

        assert result.output == "Direct output."
        assert result.success is True
        adapter.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_forge_system_prompt_override(self) -> None:
        adapter = _make_adapter(["Answer."])
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=False,
            use_pressure=False,
            system_prompt="Default system",
        )
        harness = DeepForgeHarness(adapter, cfg)
        await harness.forge("Question.", system="Override system")

        call_kwargs = adapter.generate.call_args
        assert call_kwargs.kwargs.get("system") == "Override system"


# ---------------------------------------------------------------------------
# Trace content
# ---------------------------------------------------------------------------


class TestForgeTrace:
    @pytest.mark.asyncio
    async def test_trace_records_mechanisms(self) -> None:
        adapter = _make_adapter(["Output."])
        cfg = HarnessConfig(
            lenses=[_make_lens()],
            use_interference=True,
            use_pruner=False,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)
        result = await harness.forge("Question.")

        assert "cognitive_interference" in result.trace.mechanisms_used

    @pytest.mark.asyncio
    async def test_trace_wall_time_positive(self) -> None:
        adapter = _make_adapter(["Out."])
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=False,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)
        result = await harness.forge("Q.")
        assert result.trace.wall_time_seconds >= 0

    @pytest.mark.asyncio
    async def test_trace_accumulates_tokens(self) -> None:
        adapter = _make_adapter(["Output with tokens."])
        cfg = HarnessConfig(
            lenses=[],
            use_interference=False,
            use_pruner=False,
            use_pressure=False,
        )
        harness = DeepForgeHarness(adapter, cfg)
        result = await harness.forge("Q.")
        assert result.trace.total_input_tokens == 100
        assert result.trace.total_output_tokens == 50


# ---------------------------------------------------------------------------
# Helpers test
# ---------------------------------------------------------------------------


class TestBuildInterferenceSystem:
    def test_merges_base_and_injection(self) -> None:
        result = DeepForgeHarness._build_interference_system(
            base_system="Base instruction.",
            injection_text="Lens frame here.",
        )
        assert "Base instruction." in result
        assert "Lens frame here." in result
        assert "COGNITIVE INTERFERENCE" in result

    def test_no_base_system(self) -> None:
        result = DeepForgeHarness._build_interference_system(
            base_system=None,
            injection_text="Lens frame.",
        )
        assert "COGNITIVE INTERFERENCE" in result
        assert "Lens frame." in result
