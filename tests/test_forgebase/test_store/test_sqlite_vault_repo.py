"""Tests for SQLite vault repository."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.store.sqlite.vault_repo import SqliteVaultRepository


@pytest.mark.asyncio
class TestSqliteVaultRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        rev_id = id_gen.revision_id()

        vault = Vault(
            vault_id=vault_id,
            name="test",
            description="test vault",
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
            summary="Initial revision",
        )

        await repo.create(vault, revision)
        await sqlite_db.commit()

        got = await repo.get(vault_id)
        assert got is not None
        assert got.name == "test"
        assert got.vault_id == vault_id

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteVaultRepository(sqlite_db)
        assert await repo.get(id_gen.vault_id()) is None

    async def test_list_all(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)

        for i in range(3):
            vid = id_gen.vault_id()
            rid = id_gen.revision_id()
            vault = Vault(
                vault_id=vid,
                name=f"v{i}",
                description="",
                head_revision_id=rid,
                created_at=clock.now(),
                updated_at=clock.now(),
                config={},
            )
            rev = VaultRevision(
                revision_id=rid,
                vault_id=vid,
                parent_revision_id=None,
                created_at=clock.now(),
                created_by=actor,
                causation_event_id=None,
                summary="init",
            )
            await repo.create(vault, rev)

        await sqlite_db.commit()
        vaults = await repo.list_all()
        assert len(vaults) == 3

    async def test_update_config(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteVaultRepository(sqlite_db)
        vid = id_gen.vault_id()
        rid = id_gen.revision_id()
        vault = Vault(
            vault_id=vid,
            name="test",
            description="",
            head_revision_id=rid,
            created_at=clock.now(),
            updated_at=clock.now(),
            config={},
        )
        rev = VaultRevision(
            revision_id=rid,
            vault_id=vid,
            parent_revision_id=None,
            created_at=clock.now(),
            created_by=actor,
            causation_event_id=None,
            summary="init",
        )
        await repo.create(vault, rev)
        await sqlite_db.commit()

        await repo.update_config(vid, {"depth": 5})
        await sqlite_db.commit()

        got = await repo.get(vid)
        assert got is not None
        assert got.config == {"depth": 5}
