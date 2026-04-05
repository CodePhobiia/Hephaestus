"""Tests for SQLite UnitOfWork -- transaction atomicity."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork


@pytest.mark.asyncio
class TestSqliteUoW:
    async def test_commit_persists_state_and_events(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen, consumer_names=["test_consumer"])

        async with uow:
            vault_id = uow.id_generator.vault_id()
            rev_id = uow.id_generator.revision_id()
            vault = Vault(
                vault_id=vault_id,
                name="test",
                description="",
                head_revision_id=rev_id,
                created_at=clock.now(),
                updated_at=clock.now(),
                config={},
            )
            revision = VaultRevision(
                revision_id=rev_id,
                vault_id=vault_id,
                parent_revision_id=None,
                created_at=clock.now(),
                created_by=actor,
                causation_event_id=None,
                summary="init",
            )
            await uow.vaults.create(vault, revision)

            event = uow.event_factory.create(
                event_type="vault.created",
                aggregate_type="vault",
                aggregate_id=vault_id,
                vault_id=vault_id,
                payload={"name": "test"},
                actor=actor,
            )
            uow.record_event(event)
            await uow.commit()

        # Verify state persisted
        got = await uow.vaults.get(vault_id)
        assert got is not None
        assert got.name == "test"

        # Verify event persisted
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_domain_events")
        row = await cursor.fetchone()
        assert row["c"] == 1

        # Verify delivery created
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_event_deliveries")
        row = await cursor.fetchone()
        assert row["c"] == 1

    async def test_rollback_discards_state_and_events(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen, consumer_names=["test_consumer"])

        vault_id = id_gen.vault_id()
        try:
            async with uow:
                rev_id = uow.id_generator.revision_id()
                vault = Vault(
                    vault_id=vault_id,
                    name="rollback_test",
                    description="",
                    head_revision_id=rev_id,
                    created_at=clock.now(),
                    updated_at=clock.now(),
                    config={},
                )
                revision = VaultRevision(
                    revision_id=rev_id,
                    vault_id=vault_id,
                    parent_revision_id=None,
                    created_at=clock.now(),
                    created_by=actor,
                    causation_event_id=None,
                    summary="init",
                )
                await uow.vaults.create(vault, revision)

                event = uow.event_factory.create(
                    event_type="vault.created",
                    aggregate_type="vault",
                    aggregate_id=vault_id,
                    vault_id=vault_id,
                    payload={},
                    actor=actor,
                )
                uow.record_event(event)
                raise ValueError("Simulated failure")
        except ValueError:
            pass

        # Verify state NOT persisted
        got = await uow.vaults.get(vault_id)
        assert got is None

        # Verify events NOT persisted
        cursor = await sqlite_db.execute("SELECT COUNT(*) as c FROM fb_domain_events")
        row = await cursor.fetchone()
        assert row["c"] == 0

    async def test_content_finalized_on_commit(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen)

        async with uow:
            ref = await uow.content.stage(b"test content", "text/plain")
            await uow.commit()

        # Content should be finalized and readable
        data = await content.read(ref.to_blob_ref())
        assert data == b"test content"

    async def test_content_aborted_on_rollback(self, sqlite_db, clock, id_gen, actor):
        content = InMemoryContentStore()
        uow = SqliteUnitOfWork(sqlite_db, content, clock, id_gen)

        try:
            async with uow:
                ref = await uow.content.stage(b"test content", "text/plain")
                raise ValueError("fail")
        except ValueError:
            pass

        with pytest.raises(KeyError):
            await content.read(ref.to_blob_ref())
