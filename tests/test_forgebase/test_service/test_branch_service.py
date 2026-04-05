"""Tests for BranchService — create and abandon workbooks."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import BranchPurpose, WorkbookStatus
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.exceptions import EntityNotFoundError
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestBranchService:
    async def _create_vault(self, uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="TestVault")

    async def test_create_workbook_basic(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="Research Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        assert wb.name == "Research Branch"
        assert wb.purpose == BranchPurpose.RESEARCH
        assert wb.status == WorkbookStatus.OPEN
        assert wb.base_revision_id == vault.head_revision_id
        assert wb.vault_id == vault.vault_id
        assert wb.created_by == actor

    async def test_create_workbook_persisted(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="Persisted",
            purpose=BranchPurpose.MANUAL,
        )

        cursor = await sqlite_db.execute(
            "SELECT name, status FROM fb_workbooks WHERE workbook_id = ?",
            (str(wb.workbook_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["name"] == "Persisted"
        assert row["status"] == "open"

    async def test_create_workbook_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="Evented",
            purpose=BranchPurpose.COMPILATION,
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id FROM fb_domain_events WHERE event_type = 'workbook.created'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["aggregate_id"] == str(wb.workbook_id)

    async def test_create_workbook_vault_not_found_raises(self, uow_factory, actor, id_gen):
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.vault_id()
        with pytest.raises(EntityNotFoundError, match="Vault not found"):
            await svc.create_workbook(
                vault_id=fake_id,
                name="Ghost",
                purpose=BranchPurpose.RESEARCH,
            )

    async def test_create_workbook_with_run_id(self, uow_factory, actor, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        run_id = id_gen.generate("run")

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="Run Branch",
            purpose=BranchPurpose.RESEARCH,
            run_id=run_id,
        )

        assert wb.created_by_run == run_id

    async def test_abandon_workbook(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="To Abandon",
            purpose=BranchPurpose.MANUAL,
        )
        assert wb.status == WorkbookStatus.OPEN

        abandoned = await svc.abandon_workbook(wb.workbook_id)
        assert abandoned.status == WorkbookStatus.ABANDONED

        # Verify persisted
        cursor = await sqlite_db.execute(
            "SELECT status FROM fb_workbooks WHERE workbook_id = ?",
            (str(wb.workbook_id),),
        )
        row = await cursor.fetchone()
        assert row["status"] == "abandoned"

    async def test_abandon_workbook_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        wb = await svc.create_workbook(
            vault_id=vault.vault_id,
            name="To Abandon Events",
            purpose=BranchPurpose.MANUAL,
        )

        await svc.abandon_workbook(wb.workbook_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'workbook.abandoned'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_abandon_workbook_not_found_raises(self, uow_factory, actor, id_gen):
        svc = BranchService(uow_factory=uow_factory, default_actor=actor)

        fake_id = id_gen.workbook_id()
        with pytest.raises(EntityNotFoundError, match="Workbook not found"):
            await svc.abandon_workbook(fake_id)
