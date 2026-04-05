"""Tests for SQLite source repository."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import SourceFormat, SourceStatus, SourceTrustTier
from hephaestus.forgebase.domain.models import Source, SourceVersion
from hephaestus.forgebase.domain.values import BlobRef, ContentHash, Version
from hephaestus.forgebase.store.sqlite.source_repo import SqliteSourceRepository


@pytest.mark.asyncio
class TestSqliteSourceRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteSourceRepository(sqlite_db)
        source_id = id_gen.source_id()
        vault_id = id_gen.vault_id()

        source = Source(
            source_id=source_id,
            vault_id=vault_id,
            format=SourceFormat.PDF,
            origin_locator="https://example.com/paper.pdf",
            created_at=clock.now(),
        )
        version = SourceVersion(
            source_id=source_id,
            version=Version(1),
            title="Test Paper",
            authors=["Alice", "Bob"],
            url="https://example.com/paper.pdf",
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256="abc123" * 8 + "abcd1234"),
                size_bytes=1024,
                mime_type="application/pdf",
            ),
            normalized_ref=None,
            content_hash=ContentHash(sha256="def456" * 8 + "defg5678"),
            metadata={"pages": 10},
            trust_tier=SourceTrustTier.STANDARD,
            status=SourceStatus.INGESTED,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(source, version)
        await sqlite_db.commit()

        got = await repo.get(source_id)
        assert got is not None
        assert got.source_id == source_id
        assert got.vault_id == vault_id
        assert got.format == SourceFormat.PDF
        assert got.origin_locator == "https://example.com/paper.pdf"

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteSourceRepository(sqlite_db)
        assert await repo.get(id_gen.source_id()) is None

    async def test_get_version(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteSourceRepository(sqlite_db)
        source_id = id_gen.source_id()
        vault_id = id_gen.vault_id()

        source = Source(
            source_id=source_id,
            vault_id=vault_id,
            format=SourceFormat.URL,
            origin_locator=None,
            created_at=clock.now(),
        )
        v1 = SourceVersion(
            source_id=source_id,
            version=Version(1),
            title="V1 Title",
            authors=["Carol"],
            url=None,
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=512,
                mime_type="text/html",
            ),
            normalized_ref=BlobRef(
                content_hash=ContentHash(sha256="b" * 64),
                size_bytes=256,
                mime_type="text/plain",
            ),
            content_hash=ContentHash(sha256="c" * 64),
            metadata={},
            trust_tier=SourceTrustTier.AUTHORITATIVE,
            status=SourceStatus.NORMALIZED,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(source, v1)
        await sqlite_db.commit()

        got = await repo.get_version(source_id, Version(1))
        assert got is not None
        assert got.title == "V1 Title"
        assert got.authors == ["Carol"]
        assert got.raw_artifact_ref.size_bytes == 512
        assert got.normalized_ref is not None
        assert got.normalized_ref.size_bytes == 256
        assert got.trust_tier == SourceTrustTier.AUTHORITATIVE
        assert got.status == SourceStatus.NORMALIZED

    async def test_get_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteSourceRepository(sqlite_db)
        assert await repo.get_version(id_gen.source_id(), Version(1)) is None

    async def test_get_head_version(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteSourceRepository(sqlite_db)
        source_id = id_gen.source_id()
        vault_id = id_gen.vault_id()

        source = Source(
            source_id=source_id,
            vault_id=vault_id,
            format=SourceFormat.MARKDOWN,
            origin_locator=None,
            created_at=clock.now(),
        )
        v1 = SourceVersion(
            source_id=source_id,
            version=Version(1),
            title="First",
            authors=[],
            url=None,
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="text/markdown",
            ),
            normalized_ref=None,
            content_hash=ContentHash(sha256="c" * 64),
            metadata={},
            trust_tier=SourceTrustTier.STANDARD,
            status=SourceStatus.INGESTED,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(source, v1)
        await sqlite_db.commit()

        # Head should be v1
        head = await repo.get_head_version(source_id)
        assert head is not None
        assert head.version == Version(1)
        assert head.title == "First"

    async def test_create_version_chain(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteSourceRepository(sqlite_db)
        source_id = id_gen.source_id()
        vault_id = id_gen.vault_id()

        source = Source(
            source_id=source_id,
            vault_id=vault_id,
            format=SourceFormat.PDF,
            origin_locator=None,
            created_at=clock.now(),
        )
        v1 = SourceVersion(
            source_id=source_id,
            version=Version(1),
            title="V1",
            authors=[],
            url=None,
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="application/pdf",
            ),
            normalized_ref=None,
            content_hash=ContentHash(sha256="c" * 64),
            metadata={},
            trust_tier=SourceTrustTier.STANDARD,
            status=SourceStatus.INGESTED,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(source, v1)

        v2 = SourceVersion(
            source_id=source_id,
            version=Version(2),
            title="V2",
            authors=["Dave"],
            url="https://example.com",
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256="d" * 64),
                size_bytes=200,
                mime_type="application/pdf",
            ),
            normalized_ref=None,
            content_hash=ContentHash(sha256="e" * 64),
            metadata={"updated": True},
            trust_tier=SourceTrustTier.AUTHORITATIVE,
            status=SourceStatus.INGESTED,
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create_version(v2)
        await sqlite_db.commit()

        # Head should be v2
        head = await repo.get_head_version(source_id)
        assert head is not None
        assert head.version == Version(2)
        assert head.title == "V2"

        # v1 still accessible
        got_v1 = await repo.get_version(source_id, Version(1))
        assert got_v1 is not None
        assert got_v1.title == "V1"

    async def test_list_by_vault(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteSourceRepository(sqlite_db)
        vault_a = id_gen.vault_id()
        vault_b = id_gen.vault_id()

        for vault_id, count in [(vault_a, 3), (vault_b, 1)]:
            for _ in range(count):
                sid = id_gen.source_id()
                source = Source(
                    source_id=sid,
                    vault_id=vault_id,
                    format=SourceFormat.PDF,
                    origin_locator=None,
                    created_at=clock.now(),
                )
                ver = SourceVersion(
                    source_id=sid,
                    version=Version(1),
                    title="t",
                    authors=[],
                    url=None,
                    raw_artifact_ref=BlobRef(
                        content_hash=ContentHash(sha256="a" * 64),
                        size_bytes=10,
                        mime_type="application/pdf",
                    ),
                    normalized_ref=None,
                    content_hash=ContentHash(sha256="c" * 64),
                    metadata={},
                    trust_tier=SourceTrustTier.STANDARD,
                    status=SourceStatus.INGESTED,
                    created_at=clock.now(),
                    created_by=actor,
                )
                await repo.create(source, ver)

        await sqlite_db.commit()

        sources_a = await repo.list_by_vault(vault_a)
        assert len(sources_a) == 3

        sources_b = await repo.list_by_vault(vault_b)
        assert len(sources_b) == 1

    async def test_get_head_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteSourceRepository(sqlite_db)
        assert await repo.get_head_version(id_gen.source_id()) is None
