"""
Tests for the Convergence Pruner.

Embedding model is replaced with a lightweight mock to avoid downloading
sentence-transformer weights in CI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from hephaestus.deepforge.adapters.base import StreamChunk
from hephaestus.deepforge.exceptions import ConvergenceDetected, PrunerError
from hephaestus.deepforge.pruner import (
    ConvergencePattern,
    ConvergencePruner,
    PruneResult,
    PrunerSession,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vec(dim: int, idx: int) -> np.ndarray:
    """Create a unit vector in dimension *dim* with 1.0 at *idx*."""
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def make_mock_embed_model(
    fixed_embedding: np.ndarray | None = None,
) -> MagicMock:
    """
    Build a mock SentenceTransformer that returns *fixed_embedding* for any text.

    If *fixed_embedding* is None, returns a unique random unit vector each call.
    """
    mock = MagicMock()

    if fixed_embedding is not None:
        mock.encode.return_value = fixed_embedding
    else:
        # Return a different random normalised vector each time
        def _random_encode(text: Any, **kwargs: Any) -> np.ndarray:
            v = np.random.randn(128).astype(np.float32)
            return v / np.linalg.norm(v)

        mock.encode.side_effect = _random_encode

    return mock


async def _make_stream(texts: list[str]) -> AsyncIterator[StreamChunk]:
    """Build a simple async stream from a list of token strings."""
    accumulated = ""
    for text in texts:
        accumulated += text
        yield StreamChunk(delta=text, accumulated=accumulated)
    yield StreamChunk(
        delta="",
        accumulated=accumulated,
        is_final=True,
        input_tokens=20,
        output_tokens=len(texts),
        stop_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# ConvergencePattern
# ---------------------------------------------------------------------------


class TestConvergencePattern:
    def test_creation(self) -> None:
        emb = _unit_vec(128, 0)
        pattern = ConvergencePattern(text="Some text", embedding=emb, label="test")
        assert pattern.text == "Some text"
        assert pattern.block_count == 0

    def test_block_count_increments(self) -> None:
        emb = _unit_vec(128, 0)
        p = ConvergencePattern(text="t", embedding=emb)
        p.block_count += 1
        assert p.block_count == 1


# ---------------------------------------------------------------------------
# PrunerSession
# ---------------------------------------------------------------------------


class TestPrunerSession:
    def test_record_kill(self) -> None:
        session = PrunerSession()
        session.record_kill("partial output", "obvious_answer", tokens=50)
        assert session.kill_count == 1
        assert len(session.blocked_paths) == 1
        assert session.blocked_paths[0] == "partial output"
        assert session.tokens_wasted == 50
        assert session.pattern_hits.get("obvious_answer") == 1

    def test_multiple_kills(self) -> None:
        session = PrunerSession()
        session.record_kill("p1", "label_a")
        session.record_kill("p2", "label_b")
        session.record_kill("p3", "label_a")
        assert session.kill_count == 3
        assert session.pattern_hits["label_a"] == 2
        assert session.pattern_hits["label_b"] == 1


# ---------------------------------------------------------------------------
# ConvergencePruner — unit tests
# ---------------------------------------------------------------------------


class TestConvergencePruner:
    def test_no_patterns_never_converges(self) -> None:
        pruner = ConvergencePruner(patterns=[])
        is_conv, sim, pattern = pruner.check_convergence("Some random text here")
        assert not is_conv
        assert sim == 0.0
        assert pattern is None

    def test_short_text_skipped(self) -> None:
        embed_model = make_mock_embed_model(_unit_vec(128, 0))
        emb = _unit_vec(128, 0)
        pattern = ConvergencePattern(text="match", embedding=emb)
        pruner = ConvergencePruner(
            patterns=[pattern],
            embed_model=embed_model,
            min_chars_before_check=100,
        )
        is_conv, _, _ = pruner.check_convergence("short")
        assert not is_conv
        embed_model.encode.assert_not_called()

    def test_high_similarity_triggers_convergence(self) -> None:
        # Pattern and query are identical unit vectors → sim = 1.0
        emb = _unit_vec(128, 3)
        pattern = ConvergencePattern(text="The obvious answer is...", embedding=emb)
        embed_model = make_mock_embed_model(emb)  # always returns same vec
        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.90,
            embed_model=embed_model,
            min_chars_before_check=10,
        )
        is_conv, sim, matched = pruner.check_convergence("The obvious answer is yes." * 3)
        assert is_conv
        assert sim >= 0.90
        assert matched is pattern

    def test_low_similarity_no_convergence(self) -> None:
        pattern_emb = _unit_vec(128, 0)
        query_emb = _unit_vec(128, 1)  # orthogonal → sim = 0
        pattern = ConvergencePattern(text="pattern", embedding=pattern_emb)

        # Make encoder return orthogonal vector for query
        mock_model = MagicMock()
        mock_model.encode.return_value = query_emb

        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.8,
            embed_model=mock_model,
            min_chars_before_check=5,
        )
        is_conv, sim, matched = pruner.check_convergence("something completely different text here")
        assert not is_conv
        assert sim < 0.8

    def test_add_pattern_computes_embedding(self) -> None:
        embed_model = make_mock_embed_model(_unit_vec(128, 5))
        pruner = ConvergencePruner(patterns=[], embed_model=embed_model)
        p = pruner.add_pattern("New pattern text", label="test", source="organic")
        assert p.text == "New pattern text"
        assert p.label == "test"
        assert pruner.pattern_count == 1
        embed_model.encode.assert_called_once()

    def test_add_patterns_batch(self) -> None:
        dim = 32
        embeddings = np.random.randn(3, dim).astype(np.float32)
        # Normalise each row
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings /= norms

        mock_model = MagicMock()
        mock_model.encode.return_value = embeddings

        pruner = ConvergencePruner(patterns=[], embed_model=mock_model)
        patterns = pruner.add_patterns_from_texts(["A", "B", "C"], label="batch", source="seed")
        assert len(patterns) == 3
        assert pruner.pattern_count == 3

    def test_pattern_count(self) -> None:
        emb = _unit_vec(64, 0)
        patterns = [ConvergencePattern(text=f"p{i}", embedding=emb) for i in range(7)]
        pruner = ConvergencePruner(patterns=patterns)
        assert pruner.pattern_count == 7

    def test_reset_session(self) -> None:
        pruner = ConvergencePruner()
        pruner.session.record_kill("text", "label")
        assert pruner.session.kill_count == 1
        pruner.reset_session()
        assert pruner.session.kill_count == 0

    def test_export_patterns(self) -> None:
        emb = _unit_vec(64, 0)
        patterns = [
            ConvergencePattern(text=f"pattern{i}", embedding=emb, label="l", source="s")
            for i in range(3)
        ]
        pruner = ConvergencePruner(patterns=patterns)
        exported = pruner.export_patterns()
        assert len(exported) == 3
        assert exported[0]["text"] == "pattern0"
        assert "embedding" not in exported[0]


# ---------------------------------------------------------------------------
# ConvergencePruner.monitor_stream() tests
# ---------------------------------------------------------------------------


class TestMonitorStream:
    @pytest.mark.asyncio
    async def test_clean_stream_returns_result(self) -> None:
        """A stream with no convergence should complete normally."""
        # Always return orthogonal vector (no similarity to patterns)
        pattern_emb = _unit_vec(128, 0)
        query_emb = _unit_vec(128, 1)
        pattern = ConvergencePattern(text="pattern", embedding=pattern_emb)

        mock_model = MagicMock()
        mock_model.encode.return_value = query_emb

        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.9,
            embed_model=mock_model,
            check_interval=2,
            min_chars_before_check=5,
        )

        stream = _make_stream(["Hello ", "world ", "this ", "is ", "great!"])
        result = await pruner.monitor_stream(stream)
        assert isinstance(result, PruneResult)
        assert "great!" in result.text
        assert result.input_tokens == 20

    @pytest.mark.asyncio
    async def test_convergence_kills_stream(self) -> None:
        """Convergence detection should raise ConvergenceDetected."""
        convergence_emb = _unit_vec(128, 5)
        pattern = ConvergencePattern(
            text="The answer is obviously X",
            embedding=convergence_emb,
            label="obvious",
        )

        # Encode always returns the convergence embedding (sim = 1.0)
        mock_model = MagicMock()
        mock_model.encode.return_value = convergence_emb

        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.9,
            embed_model=mock_model,
            check_interval=1,  # check every chunk
            min_chars_before_check=5,
        )

        # Tokens that accumulate enough chars quickly
        tokens = ["The answer", " is obviously", " X and ", "everyone knows it"]
        stream = _make_stream(tokens)

        with pytest.raises(ConvergenceDetected) as exc_info:
            await pruner.monitor_stream(stream)

        exc = exc_info.value
        assert exc.pattern_similarity >= 0.9
        assert exc.matched_pattern == "The answer is obviously X"
        assert pruner.session.kill_count == 1

    @pytest.mark.asyncio
    async def test_cancel_on_convergence_calls_adapter(self) -> None:
        """On convergence, the adapter's cancel_stream() should be called."""
        emb = _unit_vec(64, 7)
        pattern = ConvergencePattern(text="p", embedding=emb)

        mock_model = MagicMock()
        mock_model.encode.return_value = emb

        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.9,
            embed_model=mock_model,
            check_interval=1,
            min_chars_before_check=5,
        )

        mock_adapter = MagicMock()
        mock_adapter.compute_cost.return_value = 0.001

        tokens = ["triggered convergence now yes indeed absolutely"]
        stream = _make_stream(tokens)

        with pytest.raises(ConvergenceDetected):
            await pruner.monitor_stream(stream, adapter=mock_adapter)

        mock_adapter.cancel_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_stream_raises(self) -> None:
        """A stream that yields no chunks should raise PrunerError."""
        pruner = ConvergencePruner()

        async def _empty() -> AsyncIterator[StreamChunk]:
            return
            yield  # type: ignore[misc]

        with pytest.raises(PrunerError, match="final chunk"):
            await pruner.monitor_stream(_empty())

    @pytest.mark.asyncio
    async def test_session_accumulates_multiple_kills(self) -> None:
        """Each convergence detection should increment kill count."""
        emb = _unit_vec(64, 2)
        pattern = ConvergencePattern(text="p", embedding=emb, label="cat1")

        mock_model = MagicMock()
        mock_model.encode.return_value = emb

        pruner = ConvergencePruner(
            patterns=[pattern],
            similarity_threshold=0.8,
            embed_model=mock_model,
            check_interval=1,
            min_chars_before_check=5,
        )

        for _ in range(3):
            stream = _make_stream(["trigger convergence now!"])
            with pytest.raises(ConvergenceDetected):
                await pruner.monitor_stream(stream)

        assert pruner.session.kill_count == 3
        assert len(pruner.session.blocked_paths) == 3
