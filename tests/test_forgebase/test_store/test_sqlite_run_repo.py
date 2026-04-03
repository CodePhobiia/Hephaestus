"""Tests for SQLite run ref and run artifact repositories."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import KnowledgeRunArtifact, KnowledgeRunRef
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.store.sqlite.run_ref_repo import SqliteRunRefRepository
from hephaestus.forgebase.store.sqlite.run_artifact_repo import (
    SqliteRunArtifactRepository,
)


@pytest.mark.asyncio
class TestSqliteRunRefRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen):
        repo = SqliteRunRefRepository(sqlite_db)
        ref_id = id_gen.ref_id()
        vault_id = id_gen.vault_id()
        now = clock.now()

        ref = KnowledgeRunRef(
            ref_id=ref_id,
            vault_id=vault_id,
            run_id="run-abc-123",
            run_type="compile",
            upstream_system="hephaestus",
            upstream_ref="ref-xyz",
            source_hash="sha256:abc123",
            sync_status="pending",
            sync_error=None,
            synced_at=None,
            created_at=now,
        )

        await repo.create(ref)
        await sqlite_db.commit()

        got = await repo.get(ref_id)
        assert got is not None
        assert got.ref_id == ref_id
        assert got.vault_id == vault_id
        assert got.run_id == "run-abc-123"
        assert got.run_type == "compile"
        assert got.upstream_system == "hephaestus"
        assert got.upstream_ref == "ref-xyz"
        assert got.source_hash == "sha256:abc123"
        assert got.sync_status == "pending"
        assert got.sync_error is None
        assert got.synced_at is None
        assert got.created_at == now

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteRunRefRepository(sqlite_db)
        assert await repo.get(id_gen.ref_id()) is None

    async def test_create_with_nullable_fields_none(self, sqlite_db, clock, id_gen):
        repo = SqliteRunRefRepository(sqlite_db)
        ref_id = id_gen.ref_id()

        ref = KnowledgeRunRef(
            ref_id=ref_id,
            vault_id=id_gen.vault_id(),
            run_id="run-minimal",
            run_type="lint",
            upstream_system="ext",
            upstream_ref=None,
            source_hash=None,
            sync_status="pending",
            sync_error=None,
            synced_at=None,
            created_at=clock.now(),
        )

        await repo.create(ref)
        await sqlite_db.commit()

        got = await repo.get(ref_id)
        assert got is not None
        assert got.upstream_ref is None
        assert got.source_hash is None

    async def test_update_sync_status(self, sqlite_db, clock, id_gen):
        repo = SqliteRunRefRepository(sqlite_db)
        ref_id = id_gen.ref_id()

        ref = KnowledgeRunRef(
            ref_id=ref_id,
            vault_id=id_gen.vault_id(),
            run_id="run-sync",
            run_type="compile",
            upstream_system="heph",
            upstream_ref=None,
            source_hash=None,
            sync_status="pending",
            sync_error=None,
            synced_at=None,
            created_at=clock.now(),
        )
        await repo.create(ref)
        await sqlite_db.commit()

        await repo.update_sync_status(ref_id, "synced")
        await sqlite_db.commit()

        got = await repo.get(ref_id)
        assert got is not None
        assert got.sync_status == "synced"
        assert got.sync_error is None

    async def test_update_sync_status_with_error(self, sqlite_db, clock, id_gen):
        repo = SqliteRunRefRepository(sqlite_db)
        ref_id = id_gen.ref_id()

        ref = KnowledgeRunRef(
            ref_id=ref_id,
            vault_id=id_gen.vault_id(),
            run_id="run-err",
            run_type="compile",
            upstream_system="heph",
            upstream_ref=None,
            source_hash=None,
            sync_status="pending",
            sync_error=None,
            synced_at=None,
            created_at=clock.now(),
        )
        await repo.create(ref)
        await sqlite_db.commit()

        await repo.update_sync_status(ref_id, "failed", sync_error="timeout")
        await sqlite_db.commit()

        got = await repo.get(ref_id)
        assert got is not None
        assert got.sync_status == "failed"
        assert got.sync_error == "timeout"


@pytest.mark.asyncio
class TestSqliteRunArtifactRepository:
    async def test_create_and_list_by_ref(self, sqlite_db, id_gen):
        repo = SqliteRunArtifactRepository(sqlite_db)
        ref_id = id_gen.ref_id()
        page_id = id_gen.page_id()
        claim_id = id_gen.claim_id()

        a1 = KnowledgeRunArtifact(
            ref_id=ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=page_id,
            role="created",
        )
        a2 = KnowledgeRunArtifact(
            ref_id=ref_id,
            entity_kind=EntityKind.CLAIM,
            entity_id=claim_id,
            role="updated",
        )

        await repo.create(a1)
        await repo.create(a2)
        await sqlite_db.commit()

        results = await repo.list_by_ref(ref_id)
        assert len(results) == 2
        kinds = {r.entity_kind for r in results}
        assert EntityKind.PAGE in kinds
        assert EntityKind.CLAIM in kinds

    async def test_list_by_ref_empty(self, sqlite_db, id_gen):
        repo = SqliteRunArtifactRepository(sqlite_db)
        results = await repo.list_by_ref(id_gen.ref_id())
        assert results == []

    async def test_list_by_ref_filters_by_ref_id(self, sqlite_db, id_gen):
        repo = SqliteRunArtifactRepository(sqlite_db)
        ref1 = id_gen.ref_id()
        ref2 = id_gen.ref_id()

        a1 = KnowledgeRunArtifact(
            ref_id=ref1,
            entity_kind=EntityKind.PAGE,
            entity_id=id_gen.page_id(),
            role="created",
        )
        a2 = KnowledgeRunArtifact(
            ref_id=ref2,
            entity_kind=EntityKind.PAGE,
            entity_id=id_gen.page_id(),
            role="created",
        )

        await repo.create(a1)
        await repo.create(a2)
        await sqlite_db.commit()

        results = await repo.list_by_ref(ref1)
        assert len(results) == 1
        assert results[0].ref_id == ref1

    async def test_composite_pk(self, sqlite_db, id_gen):
        """Verify that the composite PK (ref_id, entity_kind, entity_id) works."""
        repo = SqliteRunArtifactRepository(sqlite_db)
        ref_id = id_gen.ref_id()
        entity_id = id_gen.page_id()

        # Same ref_id and entity_id but different entity_kind should be allowed
        a1 = KnowledgeRunArtifact(
            ref_id=ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=entity_id,
            role="created",
        )
        # Different entity_kind so this should work
        a2 = KnowledgeRunArtifact(
            ref_id=ref_id,
            entity_kind=EntityKind.CLAIM,
            entity_id=entity_id,
            role="updated",
        )

        await repo.create(a1)
        await repo.create(a2)
        await sqlite_db.commit()

        results = await repo.list_by_ref(ref_id)
        assert len(results) == 2
