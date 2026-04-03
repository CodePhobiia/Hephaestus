"""Tests for VaultService."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestVaultService:
    async def test_create_vault_basic(self, uow_factory, actor, sqlite_db):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(name="Research", description="My vault")

        assert vault.name == "Research"
        assert vault.description == "My vault"
        assert vault.config == {}

        # Verify persisted
        cursor = await sqlite_db.execute(
            "SELECT name FROM fb_vaults WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "Research"

    async def test_create_vault_with_config(self, uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(
            name="Custom",
            config={"depth": 3, "auto_lint": True},
        )

        assert vault.config == {"depth": 3, "auto_lint": True}

    async def test_create_vault_emits_event(self, uow_factory, actor, sqlite_db):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(name="Evented")

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id, vault_id FROM fb_domain_events"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["event_type"] == "vault.created"
        assert row["aggregate_id"] == str(vault.vault_id)
        assert row["vault_id"] == str(vault.vault_id)

    async def test_create_vault_creates_initial_revision(self, uow_factory, actor, sqlite_db):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(name="Revisioned")

        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_vault_revisions WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["parent_revision_id"] is None
        assert row["summary"] == "Initial vault creation"

    async def test_update_vault_config(self, uow_factory, actor, sqlite_db):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(name="Configurable")
        assert vault.config == {}

        updated = await svc.update_vault_config(
            vault_id=vault.vault_id,
            config={"max_pages": 100},
        )

        assert updated.config == {"max_pages": 100}

        # Verify persisted via direct DB query
        cursor = await sqlite_db.execute(
            "SELECT config FROM fb_vaults WHERE vault_id = ?",
            (str(vault.vault_id),),
        )
        row = await cursor.fetchone()
        assert '"max_pages": 100' in row["config"]

    async def test_update_vault_config_emits_event(self, uow_factory, actor, sqlite_db):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        vault = await svc.create_vault(name="Configurable2")
        await svc.update_vault_config(vault.vault_id, {"key": "value"})

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events ORDER BY occurred_at"
        )
        rows = await cursor.fetchall()
        event_types = [r["event_type"] for r in rows]
        assert "vault.created" in event_types
        assert "vault.config_updated" in event_types

    async def test_update_vault_config_not_found_raises(self, uow_factory, actor, id_gen):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.vault_id()
        with pytest.raises(ValueError, match="Vault not found"):
            await svc.update_vault_config(fake_id, {"x": 1})
