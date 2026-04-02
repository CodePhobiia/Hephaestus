"""
Tests for the Convergence Detector.

The sentence-transformer model is mocked to avoid downloading weights in CI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from hephaestus.convergence.database import ConvergenceDatabase, PatternRecord
from hephaestus.convergence.detector import (
    BatchDetectionResult,
    BatchScore,
    ConvergenceDetector,
    DetectionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit(dim: int, idx: int) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def _rand_norm(dim: int = 32) -> np.ndarray:
    v = np.random.randn(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _make_record(
    idx: int,
    problem_class: str = "test",
    embedding: np.ndarray | None = None,
    dim: int = 32,
) -> PatternRecord:
    emb = embedding if embedding is not None else _unit(dim, idx)
    return PatternRecord(
        id=idx,
        problem_class=problem_class,
        pattern_text=f"pattern_{idx}",
        pattern_embedding=emb,
    )


def _make_mock_model(return_embedding: np.ndarray) -> MagicMock:
    """Build a mock SentenceTransformer that always returns the given embedding."""
    mock = MagicMock()
    mock.encode.return_value = return_embedding
    return mock


# ---------------------------------------------------------------------------
# No-database detector (in-memory patterns only)
# ---------------------------------------------------------------------------


class TestDetectorNoDb:
    def test_detect_no_patterns_returns_non_convergent(self) -> None:
        detector = ConvergenceDetector()
        result = detector.detect_sync("anything")
        assert not result.is_convergent
        assert result.similarity == 0.0

    def test_detect_high_similarity_convergent(self) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )
        record = _make_record(0, embedding=emb)
        detector.load_patterns_from_records([record])

        result = detector.detect_sync("some text that maps to index 0")
        assert result.is_convergent
        assert result.similarity >= 0.9
        assert result.matched_pattern is record
        assert result.novelty_vector.banality_similarity >= 0.9

    def test_detect_orthogonal_not_convergent(self) -> None:
        pattern_emb = _unit(32, 0)
        query_emb = _unit(32, 1)  # orthogonal
        mock_model = _make_mock_model(query_emb)
        detector = ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )
        detector.load_patterns_from_records([_make_record(0, embedding=pattern_emb)])

        result = detector.detect_sync("orthogonal text")
        assert not result.is_convergent
        assert result.similarity < 0.9

    def test_threshold_setter(self) -> None:
        detector = ConvergenceDetector(similarity_threshold=0.8)
        detector.threshold = 0.95
        assert detector.threshold == 0.95

    def test_threshold_setter_invalid(self) -> None:
        detector = ConvergenceDetector()
        with pytest.raises(ValueError, match="Threshold"):
            detector.threshold = 1.5

    def test_add_in_memory_pattern(self) -> None:
        emb = _unit(32, 5)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(embed_model=mock_model)
        assert detector.loaded_pattern_count == 0

        record = detector.add_in_memory_pattern("new pattern text")
        assert detector.loaded_pattern_count == 1
        assert record.id == -1

    def test_loaded_class_after_load_from_records(self) -> None:
        detector = ConvergenceDetector()
        detector.load_patterns_from_records([_make_record(0)])
        assert detector.loaded_class == "in_memory"

    def test_repr(self) -> None:
        detector = ConvergenceDetector()
        r = repr(detector)
        assert "ConvergenceDetector" in r

    def test_detect_returns_problem_class(self) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(embed_model=mock_model)
        records = [_make_record(0, problem_class="load_balancing")]
        detector.load_patterns_from_records(records)
        result = detector.detect_sync("text")
        assert result.problem_class == "in_memory"


# ---------------------------------------------------------------------------
# With-database detector (async)
# ---------------------------------------------------------------------------


class TestDetectorWithDb:
    @pytest.fixture
    async def db_with_patterns(self) -> ConvergenceDatabase:
        """Create an in-memory DB seeded with 3 test patterns."""
        db = ConvergenceDatabase(":memory:")
        await db.connect()

        for i in range(3):
            emb = _unit(32, i)
            await db.add_pattern(
                problem_class="auth",
                pattern_text=f"auth pattern {i}",
                embedding=emb,
            )
        yield db
        await db.disconnect()

    async def test_load_patterns_from_db(
        self, db_with_patterns: ConvergenceDatabase
    ) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(
            db=db_with_patterns, embed_model=mock_model
        )
        count = await detector.load_patterns("auth")
        assert count == 3
        assert detector.loaded_pattern_count == 3
        assert detector.loaded_class == "auth"

    async def test_auto_load_on_detect(
        self, db_with_patterns: ConvergenceDatabase
    ) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(
            db=db_with_patterns,
            similarity_threshold=0.9,
            embed_model=mock_model,
        )
        result = await detector.detect("text", problem_class="auth", auto_load=True)
        assert detector.loaded_class == "auth"
        # Pattern at idx=0 is identical to query → convergent
        assert result.is_convergent

    async def test_load_patterns_all(
        self, db_with_patterns: ConvergenceDatabase
    ) -> None:
        # Add pattern for a different class
        await db_with_patterns.add_pattern(
            problem_class="cache", pattern_text="cache p", embedding=_unit(32, 5)
        )
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(db=db_with_patterns, embed_model=mock_model)
        count = await detector.load_patterns(None)
        assert count == 4  # 3 auth + 1 cache

    async def test_no_db_raises_on_load(self) -> None:
        detector = ConvergenceDetector(db=None)
        with pytest.raises(RuntimeError, match="No database"):
            await detector.load_patterns("test")

    async def test_force_reload(
        self, db_with_patterns: ConvergenceDatabase
    ) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(db=db_with_patterns, embed_model=mock_model)
        await detector.load_patterns("auth")
        initial_count = detector.loaded_pattern_count

        # Add a new pattern, then force reload
        await db_with_patterns.add_pattern(
            problem_class="auth", pattern_text="new", embedding=_unit(32, 10)
        )
        await detector.load_patterns("auth", force_reload=True)
        assert detector.loaded_pattern_count == initial_count + 1

    async def test_no_reload_same_class(
        self, db_with_patterns: ConvergenceDatabase
    ) -> None:
        emb = _unit(32, 0)
        mock_model = _make_mock_model(emb)
        detector = ConvergenceDetector(db=db_with_patterns, embed_model=mock_model)
        count1 = await detector.load_patterns("auth")
        count2 = await detector.load_patterns("auth")
        # Second call should return same count without re-querying
        assert count1 == count2
        # encode should not have been called (no new embeddings computed)
        mock_model.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------


class TestBatchScoring:
    def _make_batch_detector(
        self, query_embeddings: np.ndarray
    ) -> ConvergenceDetector:
        """Create a detector whose model returns rows of *query_embeddings*."""
        call_count = [0]

        def encode_side_effect(texts: list[str], **kwargs: object) -> np.ndarray:
            # Handles both single and batch
            if isinstance(texts, list):
                n = len(texts)
                if query_embeddings.ndim == 1:
                    return np.tile(query_embeddings, (n, 1))
                return query_embeddings[:n]
            return query_embeddings

        mock_model = MagicMock()
        mock_model.encode.side_effect = encode_side_effect
        return ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )

    async def test_batch_empty_candidates(self) -> None:
        detector = ConvergenceDetector()
        result = await detector.score_batch([])
        assert result.candidates == []
        assert result.best is None
        assert result.worst is None

    async def test_batch_no_patterns(self) -> None:
        detector = ConvergenceDetector()
        result = await detector.score_batch(["a", "b", "c"])
        # No patterns → all novel
        assert len(result.candidates) == 3
        assert all(s.novelty_score == 1.0 for s in result.candidates)
        assert result.convergent_count == 0

    async def test_batch_all_convergent(self) -> None:
        emb = _unit(32, 0)
        mock_model = MagicMock()
        mock_model.encode.return_value = np.tile(emb, (3, 1))

        detector = ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )
        detector.load_patterns_from_records([_make_record(0, embedding=emb)])

        result = await detector.score_batch(["a", "b", "c"])
        assert result.convergent_count == 3

    async def test_batch_sorted_best_first(self) -> None:
        # Pattern at dim 0
        pattern_emb = _unit(32, 0)
        # Candidate embeddings: one identical (sim=1), one orthogonal (sim=0)
        cand_embs = np.stack([_unit(32, 1), _unit(32, 0)], axis=0)  # [orthogonal, identical]

        mock_model = MagicMock()
        mock_model.encode.return_value = cand_embs

        detector = ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )
        detector.load_patterns_from_records([_make_record(0, embedding=pattern_emb)])

        result = await detector.score_batch(["text_a", "text_b"])
        # First result should be most novel (orthogonal)
        assert result.best is not None
        assert result.best.novelty_score >= result.worst.novelty_score  # type: ignore[union-attr]

    async def test_batch_novel_candidates_filter(self) -> None:
        emb = _unit(32, 0)
        # Mix: one convergent (sim=1), one novel (sim=0)
        cand_embs = np.stack([emb, _unit(32, 1)], axis=0)

        mock_model = MagicMock()
        mock_model.encode.return_value = cand_embs

        detector = ConvergenceDetector(
            similarity_threshold=0.9, embed_model=mock_model
        )
        detector.load_patterns_from_records([_make_record(0, embedding=emb)])

        result = await detector.score_batch(["convergent", "novel"])
        # One novel, one convergent
        assert len(result.novel_candidates) == 1
        assert len(result.convergent_candidates) == 1
        assert result.candidates[0].novelty_vector.prior_art_similarity >= 0.0

    async def test_batch_sets_ranks(self) -> None:
        detector = ConvergenceDetector()
        result = await detector.score_batch(["a", "b", "c"])
        ranks = sorted(s.rank for s in result.candidates)
        assert ranks == [1, 2, 3]
