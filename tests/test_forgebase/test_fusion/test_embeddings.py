"""Tests for EmbeddingIndex — persistent, version-pinned embedding cache."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deterministic_embedding(text: str) -> bytes:
    """Produce a deterministic 384-dim normalised float32 embedding from *text*."""
    h = hashlib.sha256(text.encode()).digest()
    rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
    vec = rng.randn(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tobytes()


def _make_entity_id(prefix: str = "pg", seq: int = 1) -> EntityId:
    ulid = str(seq).zfill(26)
    return EntityId(f"{prefix}_{ulid}")


def _make_version(n: int = 1) -> Version:
    return Version(n)


# ---------------------------------------------------------------------------
# In-memory embedding cache repository (test double)
# ---------------------------------------------------------------------------


class InMemoryEmbeddingCacheRepo:
    """Minimal in-memory implementation of EmbeddingCacheRepository for tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, int], tuple[bytes, str]] = {}

    async def get(self, entity_id: str, version: int) -> bytes | None:
        entry = self._store.get((entity_id, version))
        return entry[0] if entry is not None else None

    async def put(
        self,
        entity_id: str,
        version: int,
        embedding_blob: bytes,
        computed_at: str,
    ) -> None:
        self._store[(entity_id, version)] = (embedding_blob, computed_at)

    async def invalidate(self, entity_id: str) -> None:
        keys_to_remove = [k for k in self._store if k[0] == entity_id]
        for k in keys_to_remove:
            del self._store[k]

    async def batch_get(
        self,
        items: list[tuple[str, int]],
    ) -> dict[tuple[str, int], bytes]:
        results: dict[tuple[str, int], bytes] = {}
        for entity_id, version in items:
            entry = self._store.get((entity_id, version))
            if entry is not None:
                results[(entity_id, version)] = entry[0]
        return results


# ---------------------------------------------------------------------------
# Fake UoW
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    """Minimal UoW test double exposing only embedding_cache."""

    def __init__(self, cache_repo: InMemoryEmbeddingCacheRepo) -> None:
        self.embedding_cache = cache_repo
        self._committed = False
        self._rolled_back = False

    async def begin(self) -> None:
        pass

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._rolled_back = True

    async def __aenter__(self) -> FakeUnitOfWork:
        await self.begin()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_repo() -> InMemoryEmbeddingCacheRepo:
    return InMemoryEmbeddingCacheRepo()


@pytest.fixture
def uow_factory(cache_repo: InMemoryEmbeddingCacheRepo):
    """Factory that always returns a fresh FakeUnitOfWork backed by the same cache."""

    def _factory():
        return FakeUnitOfWork(cache_repo)

    return _factory


@pytest.fixture
def embedding_index(uow_factory) -> EmbeddingIndex:
    """EmbeddingIndex with _compute_embedding monkey-patched to avoid real model."""
    idx = EmbeddingIndex(uow_factory=uow_factory, model_name="test-model")
    idx._compute_embedding = _deterministic_embedding  # type: ignore[assignment]
    return idx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheMissComputesAndStores:
    """test_cache_miss_computes_and_stores — first call computes, second returns cached."""

    async def test_first_call_computes_and_caches(
        self,
        embedding_index: EmbeddingIndex,
        cache_repo: InMemoryEmbeddingCacheRepo,
    ):
        eid = _make_entity_id("pg", 1)
        ver = _make_version(1)
        text = "Lithium-ion intercalation chemistry"

        # Cache is empty initially
        assert await cache_repo.get(str(eid), ver.number) is None

        result = await embedding_index.get_or_compute(eid, ver, text)

        # Should have stored in cache
        cached = await cache_repo.get(str(eid), ver.number)
        assert cached is not None
        assert result == cached

        # Result should be valid float32 bytes for 384-dim vector
        arr = np.frombuffer(result, dtype=np.float32)
        assert arr.shape == (384,)

    async def test_second_call_returns_cached(
        self,
        embedding_index: EmbeddingIndex,
    ):
        eid = _make_entity_id("pg", 2)
        ver = _make_version(1)
        text = "Hub-and-spoke logistics"

        first = await embedding_index.get_or_compute(eid, ver, text)
        second = await embedding_index.get_or_compute(eid, ver, text)

        assert first == second


class TestCacheHitReturnsStored:
    """test_cache_hit_returns_stored — preload cache, verify no recompute."""

    async def test_preloaded_cache_skips_compute(
        self,
        uow_factory,
        cache_repo: InMemoryEmbeddingCacheRepo,
    ):
        eid = _make_entity_id("pg", 3)
        ver = _make_version(1)
        preloaded_blob = _deterministic_embedding("preloaded content")

        # Pre-populate cache
        await cache_repo.put(str(eid), ver.number, preloaded_blob, "2026-04-03T12:00:00Z")

        # Create index with a compute that would return different bytes
        idx = EmbeddingIndex(uow_factory=uow_factory, model_name="test-model")
        compute_called = False

        def _tracking_compute(text: str) -> bytes:
            nonlocal compute_called
            compute_called = True
            return _deterministic_embedding(text)

        idx._compute_embedding = _tracking_compute  # type: ignore[assignment]

        result = await idx.get_or_compute(eid, ver, "different text entirely")

        # Should return the preloaded blob, NOT compute a new one
        assert result == preloaded_blob
        assert not compute_called


class TestVersionChangeRecomputes:
    """test_version_change_recomputes — different version triggers new embedding."""

    async def test_new_version_triggers_compute(
        self,
        embedding_index: EmbeddingIndex,
        cache_repo: InMemoryEmbeddingCacheRepo,
    ):
        eid = _make_entity_id("pg", 4)
        ver1 = _make_version(1)
        ver2 = _make_version(2)
        text_v1 = "Original battery chemistry text"
        text_v2 = "Updated battery chemistry with new findings"

        result_v1 = await embedding_index.get_or_compute(eid, ver1, text_v1)
        result_v2 = await embedding_index.get_or_compute(eid, ver2, text_v2)

        # Different versions with different text should produce different embeddings
        assert result_v1 != result_v2

        # Both should be cached
        cached_v1 = await cache_repo.get(str(eid), ver1.number)
        cached_v2 = await cache_repo.get(str(eid), ver2.number)
        assert cached_v1 == result_v1
        assert cached_v2 == result_v2


class TestInvalidateRemovesCache:
    """test_invalidate_removes_cache — invalidate then next call recomputes."""

    async def test_invalidate_clears_all_versions(
        self,
        embedding_index: EmbeddingIndex,
        cache_repo: InMemoryEmbeddingCacheRepo,
    ):
        eid = _make_entity_id("pg", 5)
        ver1 = _make_version(1)
        ver2 = _make_version(2)

        await embedding_index.get_or_compute(eid, ver1, "text v1")
        await embedding_index.get_or_compute(eid, ver2, "text v2")

        # Both cached
        assert await cache_repo.get(str(eid), ver1.number) is not None
        assert await cache_repo.get(str(eid), ver2.number) is not None

        # Invalidate
        await embedding_index.invalidate(eid)

        # Both gone
        assert await cache_repo.get(str(eid), ver1.number) is None
        assert await cache_repo.get(str(eid), ver2.number) is None

    async def test_recomputes_after_invalidation(
        self,
        embedding_index: EmbeddingIndex,
    ):
        eid = _make_entity_id("pg", 6)
        ver = _make_version(1)
        text = "Some entity text"

        first = await embedding_index.get_or_compute(eid, ver, text)
        await embedding_index.invalidate(eid)
        second = await embedding_index.get_or_compute(eid, ver, text)

        # Same text/version => deterministic => same result
        assert first == second


class TestBatchGetOrCompute:
    """test_batch_get_or_compute — batch of items, mix of cached and new."""

    async def test_batch_mixed_cached_and_new(
        self,
        embedding_index: EmbeddingIndex,
        cache_repo: InMemoryEmbeddingCacheRepo,
    ):
        eid1 = _make_entity_id("pg", 10)
        eid2 = _make_entity_id("pg", 11)
        eid3 = _make_entity_id("pg", 12)
        ver = _make_version(1)

        # Pre-cache eid1
        precomputed = _deterministic_embedding("text for item 1")
        await cache_repo.put(str(eid1), ver.number, precomputed, "2026-04-03T12:00:00Z")

        items = [
            (eid1, ver, "text for item 1"),
            (eid2, ver, "text for item 2"),
            (eid3, ver, "text for item 3"),
        ]

        results = await embedding_index.batch_get_or_compute(items)

        assert len(results) == 3
        # eid1 should return the preloaded blob
        assert results[0] == precomputed
        # All results should be valid 384-dim float32 embeddings
        for blob in results:
            arr = np.frombuffer(blob, dtype=np.float32)
            assert arr.shape == (384,)

    async def test_batch_empty(self, embedding_index: EmbeddingIndex):
        results = await embedding_index.batch_get_or_compute([])
        assert results == []


class TestDeterministicEmbeddings:
    """test_deterministic_embeddings — same text produces same embedding bytes."""

    async def test_same_text_same_bytes(self, embedding_index: EmbeddingIndex):
        eid1 = _make_entity_id("pg", 20)
        eid2 = _make_entity_id("pg", 21)
        ver = _make_version(1)
        text = "Exact same text for both entities"

        result1 = await embedding_index.get_or_compute(eid1, ver, text)
        result2 = await embedding_index.get_or_compute(eid2, ver, text)

        assert result1 == result2

    async def test_embedding_is_normalised(self, embedding_index: EmbeddingIndex):
        eid = _make_entity_id("pg", 22)
        ver = _make_version(1)
        text = "Check normalisation"

        result = await embedding_index.get_or_compute(eid, ver, text)
        arr = np.frombuffer(result, dtype=np.float32)
        norm = np.linalg.norm(arr)
        assert abs(norm - 1.0) < 1e-5


class TestDifferentTextDifferentEmbeddings:
    """test_different_text_different_embeddings — different text yields different bytes."""

    async def test_different_text_produces_different_embeddings(
        self,
        embedding_index: EmbeddingIndex,
    ):
        eid1 = _make_entity_id("pg", 30)
        eid2 = _make_entity_id("pg", 31)
        ver = _make_version(1)

        result1 = await embedding_index.get_or_compute(
            eid1,
            ver,
            "Lithium-ion battery chemistry",
        )
        result2 = await embedding_index.get_or_compute(
            eid2,
            ver,
            "Hub-and-spoke logistics network",
        )

        assert result1 != result2

    async def test_different_text_cosine_distance_nonzero(
        self,
        embedding_index: EmbeddingIndex,
    ):
        eid1 = _make_entity_id("pg", 32)
        eid2 = _make_entity_id("pg", 33)
        ver = _make_version(1)

        r1 = await embedding_index.get_or_compute(eid1, ver, "Alpha beta gamma")
        r2 = await embedding_index.get_or_compute(eid2, ver, "Delta epsilon zeta")

        a1 = np.frombuffer(r1, dtype=np.float32)
        a2 = np.frombuffer(r2, dtype=np.float32)

        cosine_sim = float(np.dot(a1, a2))
        # Different random embeddings should not be perfectly similar
        assert cosine_sim < 0.99
