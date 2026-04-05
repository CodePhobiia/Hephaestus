"""Tests for IngestService."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import SourceFormat, SourceStatus
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.service.exceptions import ConflictError
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestIngestService:
    async def _create_vault(self, uow_factory, actor):
        """Helper to create a vault for source ingestion."""
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="TestVault")

    async def test_ingest_source_basic(self, uow_factory, actor, sqlite_db, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, version = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"raw pdf bytes",
            format=SourceFormat.PDF,
            title="My Paper",
            metadata={"doi": "10.1234/test"},
        )

        assert source.vault_id == vault.vault_id
        assert source.format == SourceFormat.PDF
        assert version.version == Version(1)
        assert version.status == SourceStatus.INGESTED
        assert version.title == "My Paper"
        assert version.metadata == {"doi": "10.1234/test"}
        assert version.normalized_ref is None

    async def test_ingest_source_content_stored(self, uow_factory, actor, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, version = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"stored content",
            format=SourceFormat.MARKDOWN,
        )

        # Content should be readable after commit
        data = await content_store.read(version.raw_artifact_ref)
        assert data == b"stored content"

    async def test_ingest_source_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"data",
            format=SourceFormat.JSON,
            idempotency_key="key-1",
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id FROM fb_domain_events WHERE event_type = ?",
            ("source.ingested",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["aggregate_id"] == str(source.source_id)

    async def test_ingest_source_sets_canonical_head(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"data",
            format=SourceFormat.MARKDOWN,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(source.source_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1

    async def test_ingest_source_sets_branch_head(self, uow_factory, actor, sqlite_db, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        # Use a workbook_id (we just need an EntityId; the workbook doesn't need
        # to exist in the DB for the branch head to be stored)
        wb_id = id_gen.workbook_id()

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"branch data",
            format=SourceFormat.CSV,
            workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version, base_version FROM fb_branch_source_heads WHERE source_id = ?",
            (str(source.source_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1

        # No canonical head should be set
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_canonical_heads WHERE entity_id = ?",
            (str(source.source_id),),
        )
        canonical_row = await cursor.fetchone()
        assert canonical_row is None

    async def test_normalize_source(self, uow_factory, actor, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, v1 = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"raw bytes",
            format=SourceFormat.PDF,
            title="Paper",
        )

        v2 = await svc.normalize_source(
            source_id=source.source_id,
            normalized_content=b"normalized text",
            expected_version=Version(1),
        )

        assert v2.version == Version(2)
        assert v2.status == SourceStatus.NORMALIZED
        assert v2.normalized_ref is not None
        assert v2.title == "Paper"  # carried over from v1

        # Content readable
        data = await content_store.read(v2.normalized_ref)
        assert data == b"normalized text"

    async def test_normalize_source_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"raw",
            format=SourceFormat.MARKDOWN,
        )

        await svc.normalize_source(
            source_id=source.source_id,
            normalized_content=b"normalized",
            expected_version=Version(1),
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("source.normalized",),
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_normalize_source_updates_canonical_head(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"raw",
            format=SourceFormat.MARKDOWN,
        )

        await svc.normalize_source(
            source_id=source.source_id,
            normalized_content=b"norm",
            expected_version=Version(1),
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(source.source_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 2

    async def test_normalize_source_optimistic_concurrency(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        source, _ = await svc.ingest_source(
            vault_id=vault.vault_id,
            raw_content=b"raw",
            format=SourceFormat.MARKDOWN,
        )

        # Normalize once (v1 -> v2)
        await svc.normalize_source(
            source_id=source.source_id,
            normalized_content=b"norm1",
            expected_version=Version(1),
        )

        # Try to normalize again with stale expected_version=1
        with pytest.raises(ConflictError) as exc_info:
            await svc.normalize_source(
                source_id=source.source_id,
                normalized_content=b"norm2",
                expected_version=Version(1),
            )
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

    async def test_normalize_source_not_found(self, uow_factory, actor, id_gen):
        svc = IngestService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.source_id()
        with pytest.raises(ValueError, match="Source not found"):
            await svc.normalize_source(
                source_id=fake_id,
                normalized_content=b"data",
                expected_version=Version(1),
            )
