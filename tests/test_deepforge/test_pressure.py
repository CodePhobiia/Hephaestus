"""
Tests for the Anti-Training Pressure engine.

The adapter and embedding model are fully mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from hephaestus.deepforge.adapters.base import GenerationResult
from hephaestus.deepforge.exceptions import ConfigurationError
from hephaestus.deepforge.pressure import AntiTrainingPressure, BlockedPath, PressureTrace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vec(dim: int, idx: int) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def _make_result(text: str, in_tok: int = 100, out_tok: int = 50) -> GenerationResult:
    return GenerationResult(
        text=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=(in_tok * 3.0 + out_tok * 15.0) / 1_000_000,
        model="test-model",
        stop_reason="end_turn",
    )


def _make_adapter(responses: list[str]) -> MagicMock:
    """Return a mock adapter that delivers *responses* in sequence."""
    adapter = MagicMock()
    adapter.config = MagicMock()
    adapter.config.input_cost_per_million = 3.0
    adapter.config.output_cost_per_million = 15.0
    adapter.generate = AsyncMock(side_effect=[_make_result(r) for r in responses])
    return adapter


def _make_embed_model(embeddings: list[np.ndarray]) -> MagicMock:
    """
    Return a mock SentenceTransformer whose encode() returns *embeddings* in sequence.

    If only one embedding is provided, it is returned for every call.
    """
    mock = MagicMock()
    if len(embeddings) == 1:
        mock.encode.return_value = embeddings[0]
    else:
        mock.encode.side_effect = embeddings
    return mock


# ---------------------------------------------------------------------------
# BlockedPath
# ---------------------------------------------------------------------------


class TestBlockedPath:
    def test_creation(self) -> None:
        emb = _unit_vec(64, 0)
        bp = BlockedPath(round_index=0, text="default", embedding=emb, reason="mirror")
        assert bp.round_index == 0
        assert bp.text == "default"


# ---------------------------------------------------------------------------
# PressureTrace
# ---------------------------------------------------------------------------


class TestPressureTrace:
    def test_add_result_accumulates(self) -> None:
        trace = PressureTrace()
        r1 = _make_result("text1", 100, 50)
        r2 = _make_result("text2", 200, 80)
        trace.add_result(r1)
        trace.add_result(r2)
        assert trace.total_input_tokens == 300
        assert trace.total_output_tokens == 130
        assert trace.rounds_completed == 2
        assert trace.total_cost_usd > 0


# ---------------------------------------------------------------------------
# AntiTrainingPressure
# ---------------------------------------------------------------------------


class TestAntiTrainingPressure:
    def test_bad_max_rounds_raises(self) -> None:
        adapter = MagicMock()
        with pytest.raises(ConfigurationError, match="max_rounds"):
            AntiTrainingPressure(adapter, max_rounds=0)

    @pytest.mark.asyncio
    async def test_single_round_returns_default(self) -> None:
        """With max_rounds=1 only the mirror step runs."""
        responses = ["The default predictable answer."]
        adapter = _make_adapter(responses)

        # Embeddings: default answer gets emb_0; the check is between it and itself
        emb_0 = _unit_vec(64, 0)
        embed_model = _make_embed_model([emb_0])

        pressure = AntiTrainingPressure(
            adapter,
            max_rounds=1,
            embed_model=embed_model,
        )
        trace = await pressure.apply("What is the answer?")

        # With max_rounds=1 there is only the mirror round (round 0);
        # no pressure rounds run, so final_output is empty and success=False.
        assert trace.rounds_completed >= 1
        assert len(trace.blocked_paths) >= 1
        assert trace.blocked_paths[0].text == "The default predictable answer."
        adapter.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_novel_output_at_round_1(self) -> None:
        """
        Round 0 = default (blocked).
        Round 1 = novel (orthogonal embedding → high distance).
        """
        default_text = "The obvious standard answer everyone gives."
        novel_text = "A totally different approach from a foreign domain."

        responses = [default_text, novel_text]
        adapter = _make_adapter(responses)

        emb_default = _unit_vec(64, 0)
        emb_novel = _unit_vec(64, 1)  # orthogonal to default → distance 1.0

        # encode is called:
        #   1. embed default text (round 0)
        #   2. embed novel text (round 1 verification)
        embed_model = _make_embed_model([emb_default, emb_novel])

        pressure = AntiTrainingPressure(
            adapter,
            max_rounds=3,
            structural_distance_threshold=0.5,  # distance must be >= 0.5
            embed_model=embed_model,
        )
        trace = await pressure.apply("Give me a creative solution.")

        assert trace.success is True
        assert trace.final_output == novel_text
        assert trace.rounds_completed == 2
        assert len(trace.blocked_paths) == 1  # only default blocked
        assert trace.blocked_paths[0].text == default_text

    @pytest.mark.asyncio
    async def test_rephrasing_is_blocked(self) -> None:
        """
        Round 0 = default.
        Round 1 = rephrasing (high similarity → blocked).
        Round 2 = genuinely novel.
        """
        default_text = "Standard answer A."
        rephrase_text = "Standard answer A, rephrased slightly."
        novel_text = "Completely different structural approach B."

        responses = [default_text, rephrase_text, novel_text]
        adapter = _make_adapter(responses)

        emb_default = _unit_vec(64, 0)
        emb_similar = _unit_vec(64, 0)  # identical → distance 0 → blocked
        emb_novel = _unit_vec(64, 1)  # orthogonal → distance 1

        embed_model = _make_embed_model([emb_default, emb_similar, emb_novel])

        pressure = AntiTrainingPressure(
            adapter,
            max_rounds=4,
            structural_distance_threshold=0.5,
            embed_model=embed_model,
        )
        trace = await pressure.apply("Problem statement.")

        assert trace.success is True
        assert trace.final_output == novel_text
        # Default and rephrase should both be blocked
        assert any(bp.text == default_text for bp in trace.blocked_paths)
        assert any(bp.text == rephrase_text for bp in trace.blocked_paths)

    @pytest.mark.asyncio
    async def test_exhausted_rounds_returns_success_false(self) -> None:
        """When all rounds are exhausted without finding novel output, success=False."""
        responses = ["Same answer.", "Same answer again.", "Same answer once more."]
        adapter = _make_adapter(responses)

        emb_same = _unit_vec(64, 3)  # always same embedding
        embed_model = _make_embed_model([emb_same])

        pressure = AntiTrainingPressure(
            adapter,
            max_rounds=3,
            structural_distance_threshold=0.5,
            embed_model=embed_model,
        )
        trace = await pressure.apply("Problem.")

        assert trace.success is False
        assert trace.rounds_completed == 3

    @pytest.mark.asyncio
    async def test_pre_seeded_blocked_paths(self) -> None:
        """Extra blocked paths from pruner session should be fed into prohibition."""
        responses = ["Default answer."]
        adapter = _make_adapter(responses)

        emb = _unit_vec(64, 0)
        # encode is called 3 times:
        # 1. "Previous blocked output 1" (pre-seed)
        # 2. "Previous blocked output 2" (pre-seed)
        # 3. "Default answer." (round 0 mirror)
        embed_model = _make_embed_model([emb, emb, emb])

        pressure = AntiTrainingPressure(
            adapter,
            max_rounds=1,
            embed_model=embed_model,
        )
        trace = await pressure.apply(
            "Problem.",
            extra_blocked_paths=["Previous blocked output 1", "Previous blocked output 2"],
        )

        # Pre-seeded paths should appear in blocked_paths with round_index=-1
        pre_seeded = [bp for bp in trace.blocked_paths if bp.round_index == -1]
        assert len(pre_seeded) == 2

    def test_verify_structural_incompatibility_orthogonal(self) -> None:
        adapter = MagicMock()
        emb_a = _unit_vec(64, 0)
        emb_b = _unit_vec(64, 1)

        mock_model = MagicMock()
        mock_model.encode.side_effect = [emb_a, emb_b]

        pressure = AntiTrainingPressure(
            adapter,
            structural_distance_threshold=0.5,
            embed_model=mock_model,
        )
        is_incompatible, dist = pressure.verify_structural_incompatibility("text_a", "text_b")
        assert is_incompatible
        assert dist == pytest.approx(1.0, abs=1e-5)

    def test_verify_structural_incompatibility_identical(self) -> None:
        adapter = MagicMock()
        emb = _unit_vec(64, 0)

        mock_model = MagicMock()
        mock_model.encode.return_value = emb

        pressure = AntiTrainingPressure(
            adapter,
            structural_distance_threshold=0.5,
            embed_model=mock_model,
        )
        is_incompatible, dist = pressure.verify_structural_incompatibility("same", "same")
        assert not is_incompatible
        assert dist == pytest.approx(0.0, abs=1e-5)

    def test_build_prohibition_system_includes_blocked_texts(self) -> None:
        emb = _unit_vec(64, 0)
        blocked = [
            BlockedPath(round_index=0, text="The default answer.", embedding=emb, reason="mirror"),
            BlockedPath(round_index=1, text="Second answer.", embedding=emb, reason="rephrase"),
        ]
        result = AntiTrainingPressure._build_prohibition_system(
            base_system="Be creative.",
            blocked=blocked,
        )
        assert "Be creative." in result
        assert "BLOCKED PATH" in result
        assert "The default answer." in result
        assert "Second answer." in result
        assert "FUNDAMENTALLY DIFFERENT" in result

    def test_build_prohibition_system_no_base(self) -> None:
        emb = _unit_vec(64, 0)
        blocked = [BlockedPath(0, "Default.", emb, "mirror")]
        result = AntiTrainingPressure._build_prohibition_system(None, blocked)
        assert "BLOCKED PATH" in result

    @pytest.mark.asyncio
    async def test_cost_accumulates_across_rounds(self) -> None:
        responses = ["Default.", "Novel completely different answer here."]
        adapter = _make_adapter(responses)

        emb_0 = _unit_vec(64, 0)
        emb_1 = _unit_vec(64, 1)
        embed_model = _make_embed_model([emb_0, emb_1])

        pressure = AntiTrainingPressure(adapter, max_rounds=3, embed_model=embed_model)
        trace = await pressure.apply("Q")

        assert trace.total_cost_usd > 0
        assert trace.total_input_tokens > 0
        assert trace.total_output_tokens > 0
