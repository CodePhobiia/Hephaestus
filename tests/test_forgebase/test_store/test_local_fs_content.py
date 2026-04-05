"""Tests for content store implementations."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore


@pytest.mark.asyncio
class TestInMemoryContentStore:
    async def test_stage_and_finalize(self):
        store = InMemoryContentStore()
        ref = await store.stage(b"hello world", "text/plain")
        assert ref.size_bytes == 11
        await store.finalize()
        data = await store.read(ref.to_blob_ref())
        assert data == b"hello world"

    async def test_stage_and_abort(self):
        store = InMemoryContentStore()
        ref = await store.stage(b"hello world", "text/plain")
        await store.abort()
        with pytest.raises(KeyError):
            await store.read(ref.to_blob_ref())

    async def test_read_nonexistent_raises(self):
        store = InMemoryContentStore()
        from hephaestus.forgebase.domain.values import BlobRef, ContentHash

        ref = BlobRef(
            content_hash=ContentHash(sha256="x" * 64), size_bytes=0, mime_type="text/plain"
        )
        with pytest.raises(KeyError):
            await store.read(ref)

    async def test_multiple_stages_before_finalize(self):
        store = InMemoryContentStore()
        r1 = await store.stage(b"one", "text/plain")
        r2 = await store.stage(b"two", "text/plain")
        await store.finalize()
        assert await store.read(r1.to_blob_ref()) == b"one"
        assert await store.read(r2.to_blob_ref()) == b"two"
