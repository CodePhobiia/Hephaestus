"""Tests for SQLite EmbeddingCacheRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.store.sqlite.embedding_cache_repo import SqliteEmbeddingCacheRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteEmbeddingCacheRepository(sqlite_db)


def _now_iso() -> str:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC).isoformat()


class TestEmbeddingCacheCRUD:
    @pytest.mark.asyncio
    async def test_put_and_get(self, repo, sqlite_db):
        blob = b"\x00\x01\x02\x03" * 96  # 384-byte fake embedding
        await repo.put("page_00000000000000000000000001", 1, blob, _now_iso())
        await sqlite_db.commit()

        result = await repo.get("page_00000000000000000000000001", 1)
        assert result is not None
        assert result == blob

    @pytest.mark.asyncio
    async def test_cache_miss(self, repo):
        result = await repo.get("page_00000000000000000000000001", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_version_specific(self, repo, sqlite_db):
        blob_v1 = b"\x01" * 384
        blob_v2 = b"\x02" * 384
        entity_id = "page_00000000000000000000000001"

        await repo.put(entity_id, 1, blob_v1, _now_iso())
        await repo.put(entity_id, 2, blob_v2, _now_iso())
        await sqlite_db.commit()

        result_v1 = await repo.get(entity_id, 1)
        result_v2 = await repo.get(entity_id, 2)
        assert result_v1 == blob_v1
        assert result_v2 == blob_v2
        assert result_v1 != result_v2

    @pytest.mark.asyncio
    async def test_overwrite_same_version(self, repo, sqlite_db):
        entity_id = "page_00000000000000000000000001"
        old_blob = b"\x01" * 384
        new_blob = b"\x02" * 384

        await repo.put(entity_id, 1, old_blob, _now_iso())
        await sqlite_db.commit()

        await repo.put(entity_id, 1, new_blob, _now_iso())
        await sqlite_db.commit()

        result = await repo.get(entity_id, 1)
        assert result == new_blob

    @pytest.mark.asyncio
    async def test_invalidate(self, repo, sqlite_db):
        entity_id = "page_00000000000000000000000001"
        blob_v1 = b"\x01" * 384
        blob_v2 = b"\x02" * 384

        await repo.put(entity_id, 1, blob_v1, _now_iso())
        await repo.put(entity_id, 2, blob_v2, _now_iso())
        await sqlite_db.commit()

        # Both versions exist
        assert await repo.get(entity_id, 1) is not None
        assert await repo.get(entity_id, 2) is not None

        # Invalidate removes all versions for that entity
        await repo.invalidate(entity_id)
        await sqlite_db.commit()

        assert await repo.get(entity_id, 1) is None
        assert await repo.get(entity_id, 2) is None

    @pytest.mark.asyncio
    async def test_invalidate_does_not_affect_others(self, repo, sqlite_db):
        entity_a = "page_00000000000000000000000001"
        entity_b = "page_00000000000000000000000002"

        await repo.put(entity_a, 1, b"\x01" * 384, _now_iso())
        await repo.put(entity_b, 1, b"\x02" * 384, _now_iso())
        await sqlite_db.commit()

        await repo.invalidate(entity_a)
        await sqlite_db.commit()

        assert await repo.get(entity_a, 1) is None
        assert await repo.get(entity_b, 1) is not None

    @pytest.mark.asyncio
    async def test_batch_get(self, repo, sqlite_db):
        e1 = "page_00000000000000000000000001"
        e2 = "page_00000000000000000000000002"
        e3 = "page_00000000000000000000000003"
        blob1 = b"\x01" * 384
        blob2 = b"\x02" * 384

        await repo.put(e1, 1, blob1, _now_iso())
        await repo.put(e2, 1, blob2, _now_iso())
        await sqlite_db.commit()

        results = await repo.batch_get(
            [
                (e1, 1),
                (e2, 1),
                (e3, 1),  # doesn't exist
            ]
        )

        assert len(results) == 2
        assert results[(e1, 1)] == blob1
        assert results[(e2, 1)] == blob2
        assert (e3, 1) not in results

    @pytest.mark.asyncio
    async def test_batch_get_empty(self, repo):
        results = await repo.batch_get([])
        assert results == {}
