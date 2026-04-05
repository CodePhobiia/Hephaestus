"""
Tests for the Seed Data Generator.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from hephaestus.convergence.database import ConvergenceDatabase
from hephaestus.convergence.seed import (
    _SEED_DATA,
    SeedDataLoader,
    seed_database,
)

# ---------------------------------------------------------------------------
# _SEED_DATA structure
# ---------------------------------------------------------------------------


class TestSeedData:
    def test_minimum_pattern_count(self) -> None:
        assert len(_SEED_DATA) >= 50

    def test_minimum_classes(self) -> None:
        classes = {p.problem_class for p in _SEED_DATA}
        assert len(classes) >= 10

    def test_minimum_patterns_per_class(self) -> None:
        from collections import Counter

        counts = Counter(p.problem_class for p in _SEED_DATA)
        for cls, count in counts.items():
            assert count >= 5, f"Class {cls!r} has only {count} patterns (need ≥ 5)"

    def test_all_texts_nonempty(self) -> None:
        for p in _SEED_DATA:
            assert p.text.strip(), f"Empty text in class {p.problem_class!r}"

    def test_problem_class_nonempty(self) -> None:
        for p in _SEED_DATA:
            assert p.problem_class.strip()


class TestSeedDataLoaderStatic:
    def test_get_problem_classes(self) -> None:
        classes = SeedDataLoader.get_problem_classes()
        assert isinstance(classes, list)
        assert len(classes) >= 10
        # Should be sorted
        assert classes == sorted(classes)

    def test_get_patterns_for_class(self) -> None:
        classes = SeedDataLoader.get_problem_classes()
        first_cls = classes[0]
        patterns = SeedDataLoader.get_patterns_for_class(first_cls)
        assert len(patterns) >= 5
        assert all(isinstance(p, str) for p in patterns)

    def test_get_patterns_nonexistent_class(self) -> None:
        patterns = SeedDataLoader.get_patterns_for_class("nonexistent_xyz")
        assert patterns == []

    def test_pattern_count(self) -> None:
        count = SeedDataLoader.pattern_count()
        assert count >= 50


# ---------------------------------------------------------------------------
# SeedDataLoader.load()
# ---------------------------------------------------------------------------


def _make_mock_model(dim: int = 32) -> MagicMock:
    """Mock SentenceTransformer that returns random normalised embeddings."""
    mock = MagicMock()

    def encode_side_effect(texts: list[str], **kwargs: object) -> np.ndarray:
        n = len(texts) if isinstance(texts, list) else 1
        vecs = np.random.randn(n, dim).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    mock.encode.side_effect = encode_side_effect
    return mock


class TestSeedDataLoaderLoad:
    @pytest.fixture
    async def empty_db(self) -> ConvergenceDatabase:
        db = ConvergenceDatabase(":memory:")
        await db.connect()
        yield db
        await db.disconnect()

    async def test_load_inserts_all_patterns(self, empty_db: ConvergenceDatabase) -> None:
        mock_model = _make_mock_model()
        loader = SeedDataLoader(empty_db, embed_model=mock_model)
        inserted = await loader.load(skip_existing=False)
        assert inserted == len(_SEED_DATA)
        assert await empty_db.pattern_count() == len(_SEED_DATA)

    async def test_load_skip_existing(self, empty_db: ConvergenceDatabase) -> None:
        # Add one pattern to make DB non-empty
        await empty_db.add_pattern(
            problem_class="test",
            pattern_text="existing",
            embedding=np.zeros(32, dtype=np.float32),
        )
        mock_model = _make_mock_model()
        loader = SeedDataLoader(empty_db, embed_model=mock_model)
        inserted = await loader.load(skip_existing=True)
        assert inserted == 0  # skipped
        # Pattern count should still be 1
        assert await empty_db.pattern_count() == 1

    async def test_load_force_when_existing(self, empty_db: ConvergenceDatabase) -> None:
        # Add one pattern, then force reload
        await empty_db.add_pattern(
            problem_class="test",
            pattern_text="existing",
            embedding=np.zeros(32, dtype=np.float32),
        )
        mock_model = _make_mock_model()
        loader = SeedDataLoader(empty_db, embed_model=mock_model)
        inserted = await loader.load(skip_existing=False)
        # All seed patterns should be inserted alongside existing
        assert inserted == len(_SEED_DATA)

    async def test_load_patterns_are_correctly_classified(
        self, empty_db: ConvergenceDatabase
    ) -> None:
        mock_model = _make_mock_model()
        loader = SeedDataLoader(empty_db, embed_model=mock_model)
        await loader.load(skip_existing=False)

        classes = SeedDataLoader.get_problem_classes()
        for cls in classes:
            db_patterns = await empty_db.get_patterns_for_class(cls)
            seed_count = len(SeedDataLoader.get_patterns_for_class(cls))
            assert len(db_patterns) == seed_count, (
                f"Class {cls!r}: expected {seed_count} patterns, got {len(db_patterns)}"
            )

    async def test_load_model_called_once_for_all_texts(
        self, empty_db: ConvergenceDatabase
    ) -> None:
        mock_model = _make_mock_model()
        loader = SeedDataLoader(empty_db, embed_model=mock_model)
        await loader.load(skip_existing=False)
        # encode should be called exactly once (batch encoding)
        mock_model.encode.assert_called_once()


# ---------------------------------------------------------------------------
# seed_database convenience function
# ---------------------------------------------------------------------------


class TestSeedDatabaseFunction:
    async def test_seed_database_convenience(self, tmp_path: object) -> None:
        """seed_database should create a DB and seed it."""
        from unittest.mock import patch

        dim = 32
        mock_model = _make_mock_model(dim)

        with patch(
            "hephaestus.convergence.seed._lazy_st",
            return_value=mock_model,
        ):
            inserted = await seed_database(":memory:", skip_existing=False)

        assert inserted >= 50
