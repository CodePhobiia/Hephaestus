"""
Tests for the Convergence Database.

All tests use an in-memory SQLite database to avoid filesystem side effects.
"""

from __future__ import annotations

import numpy as np
import pytest

from hephaestus.convergence.database import (
    ConvergenceDatabase,
    PatternRecord,
    SimilarityResult,
    open_database,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db() -> ConvergenceDatabase:
    """Return a fresh in-memory ConvergenceDatabase."""
    database = ConvergenceDatabase(":memory:")
    await database.connect()
    yield database
    await database.disconnect()


def _rand_emb(dim: int = 384) -> np.ndarray:
    """Create a random normalised embedding vector."""
    v = np.random.randn(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _unit_emb(dim: int, idx: int) -> np.ndarray:
    """Unit vector in dimension *dim* with 1.0 at *idx*."""
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


class TestConnection:
    async def test_connect_and_disconnect(self) -> None:
        db = ConvergenceDatabase(":memory:")
        assert db._conn is None
        await db.connect()
        assert db._conn is not None
        await db.disconnect()
        assert db._conn is None

    async def test_double_connect_is_safe(self) -> None:
        db = ConvergenceDatabase(":memory:")
        await db.connect()
        await db.connect()  # second connect should be no-op
        assert db._conn is not None
        await db.disconnect()

    async def test_context_manager(self) -> None:
        async with ConvergenceDatabase(":memory:") as db:
            count = await db.pattern_count()
            assert count == 0

    async def test_open_database_helper(self) -> None:
        async with open_database(":memory:") as db:
            assert db._conn is not None

    async def test_require_conn_raises_when_disconnected(self) -> None:
        db = ConvergenceDatabase(":memory:")
        with pytest.raises(RuntimeError, match="not connected"):
            db._require_conn()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestAddPattern:
    async def test_add_returns_positive_id(self, db: ConvergenceDatabase) -> None:
        pid = await db.add_pattern(
            problem_class="load_balancing",
            pattern_text="Round-robin load balancing",
            embedding=_rand_emb(),
        )
        assert isinstance(pid, int)
        assert pid > 0

    async def test_add_and_get(self, db: ConvergenceDatabase) -> None:
        emb = _rand_emb()
        pid = await db.add_pattern(
            problem_class="caching",
            pattern_text="Use Redis for caching",
            embedding=emb,
            frequency=3,
            source_model="gpt-5.4",
        )
        record = await db.get_pattern(pid)
        assert record is not None
        assert record.id == pid
        assert record.problem_class == "caching"
        assert record.pattern_text == "Use Redis for caching"
        assert record.frequency == 3
        assert record.source_model == "gpt-5.4"
        assert record.blocked_count == 0
        np.testing.assert_allclose(record.pattern_embedding, emb, atol=1e-5)

    async def test_get_nonexistent_returns_none(self, db: ConvergenceDatabase) -> None:
        result = await db.get_pattern(99999)
        assert result is None

    async def test_multiple_patterns_different_classes(self, db: ConvergenceDatabase) -> None:
        for i, cls in enumerate(["auth", "caching", "search"]):
            await db.add_pattern(
                problem_class=cls,
                pattern_text=f"pattern for {cls}",
                embedding=_unit_emb(384, i),
            )
        count = await db.pattern_count()
        assert count == 3


class TestGetPatternsForClass:
    async def test_empty_class_returns_empty(self, db: ConvergenceDatabase) -> None:
        results = await db.get_patterns_for_class("nonexistent")
        assert results == []

    async def test_returns_matching_class_only(self, db: ConvergenceDatabase) -> None:
        for i in range(3):
            await db.add_pattern(
                problem_class="auth",
                pattern_text=f"auth pattern {i}",
                embedding=_rand_emb(),
            )
        await db.add_pattern(
            problem_class="caching",
            pattern_text="cache pattern",
            embedding=_rand_emb(),
        )

        auth_patterns = await db.get_patterns_for_class("auth")
        assert len(auth_patterns) == 3
        for p in auth_patterns:
            assert p.problem_class == "auth"

        cache_patterns = await db.get_patterns_for_class("caching")
        assert len(cache_patterns) == 1

    async def test_ordered_by_blocked_count(self, db: ConvergenceDatabase) -> None:
        p1 = await db.add_pattern(
            problem_class="test", pattern_text="low", embedding=_rand_emb(), blocked_count=1
        )
        p2 = await db.add_pattern(
            problem_class="test", pattern_text="high", embedding=_rand_emb(), blocked_count=10
        )
        results = await db.get_patterns_for_class("test")
        assert results[0].blocked_count == 10
        assert results[1].blocked_count == 1

    async def test_limit_respected(self, db: ConvergenceDatabase) -> None:
        for i in range(10):
            await db.add_pattern(
                problem_class="bulk", pattern_text=f"p{i}", embedding=_rand_emb()
            )
        results = await db.get_patterns_for_class("bulk", limit=3)
        assert len(results) == 3


class TestIncrementBlocked:
    async def test_increment_blocked(self, db: ConvergenceDatabase) -> None:
        pid = await db.add_pattern(
            problem_class="test", pattern_text="p", embedding=_rand_emb()
        )
        await db.increment_blocked(pid)
        record = await db.get_pattern(pid)
        assert record is not None
        assert record.blocked_count == 1

    async def test_multiple_increments(self, db: ConvergenceDatabase) -> None:
        pid = await db.add_pattern(
            problem_class="test", pattern_text="p", embedding=_rand_emb()
        )
        for _ in range(5):
            await db.increment_blocked(pid)
        record = await db.get_pattern(pid)
        assert record is not None
        assert record.blocked_count == 5

    async def test_increment_by_custom_amount(self, db: ConvergenceDatabase) -> None:
        pid = await db.add_pattern(
            problem_class="test", pattern_text="p", embedding=_rand_emb()
        )
        await db.increment_blocked(pid, increment=10)
        record = await db.get_pattern(pid)
        assert record is not None
        assert record.blocked_count == 10


class TestDeletePattern:
    async def test_delete_existing(self, db: ConvergenceDatabase) -> None:
        pid = await db.add_pattern(
            problem_class="test", pattern_text="delete me", embedding=_rand_emb()
        )
        deleted = await db.delete_pattern(pid)
        assert deleted is True
        assert await db.get_pattern(pid) is None

    async def test_delete_nonexistent(self, db: ConvergenceDatabase) -> None:
        deleted = await db.delete_pattern(99999)
        assert deleted is False


class TestGetAllPatterns:
    async def test_get_all_returns_all(self, db: ConvergenceDatabase) -> None:
        for i in range(5):
            await db.add_pattern(
                problem_class=f"cls{i}", pattern_text=f"p{i}", embedding=_rand_emb()
            )
        all_patterns = await db.get_all_patterns()
        assert len(all_patterns) == 5

    async def test_get_all_empty_database(self, db: ConvergenceDatabase) -> None:
        all_patterns = await db.get_all_patterns()
        assert all_patterns == []


# ---------------------------------------------------------------------------
# Search similar
# ---------------------------------------------------------------------------


class TestSearchSimilar:
    async def test_search_empty_db(self, db: ConvergenceDatabase) -> None:
        results = await db.search_similar(_rand_emb())
        assert results == []

    async def test_finds_identical_embedding(self, db: ConvergenceDatabase) -> None:
        emb = _unit_emb(384, 0)
        pid = await db.add_pattern(
            problem_class="search", pattern_text="exact match", embedding=emb
        )
        results = await db.search_similar(emb, top_k=1)
        assert len(results) == 1
        assert results[0].record.id == pid
        assert results[0].similarity > 0.99

    async def test_top_k_limits_results(self, db: ConvergenceDatabase) -> None:
        for i in range(10):
            await db.add_pattern(
                problem_class="cls", pattern_text=f"p{i}", embedding=_unit_emb(384, i)
            )
        results = await db.search_similar(_unit_emb(384, 0), top_k=3)
        assert len(results) <= 3

    async def test_sorted_by_similarity_descending(self, db: ConvergenceDatabase) -> None:
        # Create patterns at known angles
        emb_a = _unit_emb(384, 0)  # very similar to query
        emb_b = _unit_emb(384, 1)  # orthogonal
        await db.add_pattern(problem_class="cls", pattern_text="similar", embedding=emb_a)
        await db.add_pattern(problem_class="cls", pattern_text="orthogonal", embedding=emb_b)

        query = _unit_emb(384, 0)
        results = await db.search_similar(query, top_k=2)
        assert len(results) == 2
        assert results[0].similarity > results[1].similarity

    async def test_filter_by_problem_class(self, db: ConvergenceDatabase) -> None:
        emb = _unit_emb(384, 0)
        await db.add_pattern(problem_class="auth", pattern_text="auth p", embedding=emb)
        await db.add_pattern(problem_class="cache", pattern_text="cache p", embedding=emb)

        # Search restricted to 'auth'
        results = await db.search_similar(emb, problem_class="auth")
        assert all(r.record.problem_class == "auth" for r in results)

    async def test_min_similarity_filter(self, db: ConvergenceDatabase) -> None:
        emb_a = _unit_emb(384, 0)
        emb_b = _unit_emb(384, 1)  # orthogonal → sim=0
        await db.add_pattern(problem_class="cls", pattern_text="high", embedding=emb_a)
        await db.add_pattern(problem_class="cls", pattern_text="zero", embedding=emb_b)

        results = await db.search_similar(_unit_emb(384, 0), min_similarity=0.5)
        # orthogonal pattern should be filtered out
        assert all(r.similarity >= 0.5 for r in results)


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


class TestCounters:
    async def test_pattern_count(self, db: ConvergenceDatabase) -> None:
        assert await db.pattern_count() == 0
        for i in range(3):
            await db.add_pattern(problem_class="cls", pattern_text=f"p{i}", embedding=_rand_emb())
        assert await db.pattern_count() == 3

    async def test_class_count(self, db: ConvergenceDatabase) -> None:
        assert await db.class_count() == 0
        await db.add_pattern(problem_class="a", pattern_text="p1", embedding=_rand_emb())
        await db.add_pattern(problem_class="a", pattern_text="p2", embedding=_rand_emb())
        await db.add_pattern(problem_class="b", pattern_text="p3", embedding=_rand_emb())
        assert await db.class_count() == 2


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------


class TestExportImport:
    async def test_export_to_json(self, db: ConvergenceDatabase, tmp_path: any) -> None:
        await db.add_pattern(
            problem_class="test", pattern_text="hello", embedding=_rand_emb()
        )
        out = tmp_path / "export.json"
        count = await db.export_to_json(out)
        assert count == 1
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert len(data) == 1
        assert data[0]["pattern_text"] == "hello"
        assert "pattern_embedding" not in data[0]

    async def test_import_from_json(self, db: ConvergenceDatabase, tmp_path: any) -> None:
        # First create and export
        await db.add_pattern(
            problem_class="import_test", pattern_text="import me", embedding=_rand_emb()
        )
        out = tmp_path / "import_test.json"
        await db.export_to_json(out)

        # Import into a fresh database
        async with ConvergenceDatabase(":memory:") as db2:
            count = await db2.import_from_json(out)
            assert count == 1
            patterns = await db2.get_patterns_for_class("import_test")
            assert len(patterns) == 1
            assert patterns[0].pattern_text == "import me"

    async def test_export_full_and_reimport(self, db: ConvergenceDatabase, tmp_path: any) -> None:
        emb = _rand_emb()
        await db.add_pattern(
            problem_class="full_test", pattern_text="full export", embedding=emb
        )
        out = tmp_path / "full.npz"
        count = await db.export_full(out)
        assert count == 1

        async with ConvergenceDatabase(":memory:") as db2:
            imported = await db2.import_full(out)
            assert imported == 1
            patterns = await db2.get_all_patterns()
            assert len(patterns) == 1
            np.testing.assert_allclose(patterns[0].pattern_embedding, emb, atol=1e-5)
