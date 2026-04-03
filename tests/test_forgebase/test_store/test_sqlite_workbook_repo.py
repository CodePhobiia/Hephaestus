"""Tests for SQLite workbook repository."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    EntityKind,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead,
    BranchClaimHead,
    BranchClaimSupportHead,
    BranchLinkHead,
    BranchPageHead,
    BranchSourceHead,
    BranchTombstone,
    Workbook,
)
from hephaestus.forgebase.domain.values import EntityId, Version, VaultRevisionId
from hephaestus.forgebase.store.sqlite.workbook_repo import SqliteWorkbookRepository


@pytest.mark.asyncio
class TestSqliteWorkbookRepo:
    """Tests for SqliteWorkbookRepository."""

    # ---- helpers ----

    def _make_workbook(self, id_gen, clock, actor, *, vault_id=None, status=WorkbookStatus.OPEN):
        wb_id = id_gen.workbook_id()
        v_id = vault_id or id_gen.vault_id()
        rev_id = id_gen.revision_id()
        return Workbook(
            workbook_id=wb_id,
            vault_id=v_id,
            name="test workbook",
            purpose=BranchPurpose.RESEARCH,
            status=status,
            base_revision_id=rev_id,
            created_at=clock.now(),
            created_by=actor,
            created_by_run=None,
        )

    # ================================================================
    # Workbook CRUD
    # ================================================================

    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb = self._make_workbook(id_gen, clock, actor)

        await repo.create(wb)
        await sqlite_db.commit()

        got = await repo.get(wb.workbook_id)
        assert got is not None
        assert got.workbook_id == wb.workbook_id
        assert got.vault_id == wb.vault_id
        assert got.name == "test workbook"
        assert got.purpose == BranchPurpose.RESEARCH
        assert got.status == WorkbookStatus.OPEN
        assert got.base_revision_id == wb.base_revision_id
        assert got.created_by == actor
        assert got.created_by_run is None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        assert await repo.get(id_gen.workbook_id()) is None

    async def test_list_by_vault(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteWorkbookRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        wb1 = self._make_workbook(id_gen, clock, actor, vault_id=vault_id)
        wb2 = self._make_workbook(id_gen, clock, actor, vault_id=vault_id)
        wb_other = self._make_workbook(id_gen, clock, actor)  # different vault

        await repo.create(wb1)
        await repo.create(wb2)
        await repo.create(wb_other)
        await sqlite_db.commit()

        results = await repo.list_by_vault(vault_id)
        assert len(results) == 2
        ids = {w.workbook_id for w in results}
        assert wb1.workbook_id in ids
        assert wb2.workbook_id in ids

    async def test_list_by_vault_with_status_filter(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteWorkbookRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        wb_open = self._make_workbook(id_gen, clock, actor, vault_id=vault_id, status=WorkbookStatus.OPEN)
        wb_merged = self._make_workbook(id_gen, clock, actor, vault_id=vault_id, status=WorkbookStatus.MERGED)

        await repo.create(wb_open)
        await repo.create(wb_merged)
        await sqlite_db.commit()

        open_list = await repo.list_by_vault(vault_id, status=WorkbookStatus.OPEN)
        assert len(open_list) == 1
        assert open_list[0].workbook_id == wb_open.workbook_id

        merged_list = await repo.list_by_vault(vault_id, status=WorkbookStatus.MERGED)
        assert len(merged_list) == 1
        assert merged_list[0].workbook_id == wb_merged.workbook_id

    async def test_update_status(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb = self._make_workbook(id_gen, clock, actor)
        await repo.create(wb)
        await sqlite_db.commit()

        await repo.update_status(wb.workbook_id, WorkbookStatus.MERGED)
        await sqlite_db.commit()

        got = await repo.get(wb.workbook_id)
        assert got is not None
        assert got.status == WorkbookStatus.MERGED

    # ================================================================
    # Branch Page Heads
    # ================================================================

    async def test_page_head_set_and_get(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        page_id = id_gen.page_id()

        head = BranchPageHead(
            workbook_id=wb_id,
            page_id=page_id,
            head_version=Version(3),
            base_version=Version(1),
        )
        await repo.set_page_head(head)
        await sqlite_db.commit()

        got = await repo.get_page_head(wb_id, page_id)
        assert got is not None
        assert got.workbook_id == wb_id
        assert got.page_id == page_id
        assert got.head_version == Version(3)
        assert got.base_version == Version(1)

    async def test_page_head_get_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        assert await repo.get_page_head(id_gen.workbook_id(), id_gen.page_id()) is None

    async def test_page_head_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        for i in range(3):
            pid = id_gen.page_id()
            await repo.set_page_head(BranchPageHead(wb_id, pid, Version(i + 1), Version(1)))

        await sqlite_db.commit()
        heads = await repo.list_page_heads(wb_id)
        assert len(heads) == 3

    async def test_page_head_overwrite(self, sqlite_db, id_gen):
        """Setting the same page head twice should upsert (update version)."""
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        page_id = id_gen.page_id()

        await repo.set_page_head(BranchPageHead(wb_id, page_id, Version(1), Version(1)))
        await sqlite_db.commit()

        # overwrite
        await repo.set_page_head(BranchPageHead(wb_id, page_id, Version(5), Version(1)))
        await sqlite_db.commit()

        got = await repo.get_page_head(wb_id, page_id)
        assert got is not None
        assert got.head_version == Version(5)

    # ================================================================
    # Branch Claim Heads
    # ================================================================

    async def test_claim_head_set_and_get(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        claim_id = id_gen.claim_id()

        head = BranchClaimHead(wb_id, claim_id, Version(2), Version(1))
        await repo.set_claim_head(head)
        await sqlite_db.commit()

        got = await repo.get_claim_head(wb_id, claim_id)
        assert got is not None
        assert got.head_version == Version(2)
        assert got.base_version == Version(1)

    async def test_claim_head_get_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        assert await repo.get_claim_head(id_gen.workbook_id(), id_gen.claim_id()) is None

    async def test_claim_head_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        for i in range(2):
            cid = id_gen.claim_id()
            await repo.set_claim_head(BranchClaimHead(wb_id, cid, Version(i + 1), Version(1)))

        await sqlite_db.commit()
        heads = await repo.list_claim_heads(wb_id)
        assert len(heads) == 2

    # ================================================================
    # Branch Link Heads
    # ================================================================

    async def test_link_head_set_and_get(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        link_id = id_gen.link_id()

        head = BranchLinkHead(wb_id, link_id, Version(4), Version(2))
        await repo.set_link_head(head)
        await sqlite_db.commit()

        got = await repo.get_link_head(wb_id, link_id)
        assert got is not None
        assert got.head_version == Version(4)
        assert got.base_version == Version(2)

    async def test_link_head_get_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        assert await repo.get_link_head(id_gen.workbook_id(), id_gen.link_id()) is None

    async def test_link_head_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        for i in range(2):
            lid = id_gen.link_id()
            await repo.set_link_head(BranchLinkHead(wb_id, lid, Version(i + 1), Version(1)))

        await sqlite_db.commit()
        heads = await repo.list_link_heads(wb_id)
        assert len(heads) == 2

    # ================================================================
    # Branch Source Heads
    # ================================================================

    async def test_source_head_set_and_get(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        source_id = id_gen.source_id()

        head = BranchSourceHead(wb_id, source_id, Version(3), Version(1))
        await repo.set_source_head(head)
        await sqlite_db.commit()

        got = await repo.get_source_head(wb_id, source_id)
        assert got is not None
        assert got.head_version == Version(3)
        assert got.base_version == Version(1)

    async def test_source_head_get_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        assert await repo.get_source_head(id_gen.workbook_id(), id_gen.source_id()) is None

    async def test_source_head_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        for i in range(2):
            sid = id_gen.source_id()
            await repo.set_source_head(BranchSourceHead(wb_id, sid, Version(i + 1), Version(1)))

        await sqlite_db.commit()
        heads = await repo.list_source_heads(wb_id)
        assert len(heads) == 2

    # ================================================================
    # Branch Claim Support Heads
    # ================================================================

    async def test_claim_support_head_set_and_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        sup1 = BranchClaimSupportHead(wb_id, id_gen.support_id(), True)
        sup2 = BranchClaimSupportHead(wb_id, id_gen.support_id(), False)

        await repo.set_claim_support_head(sup1)
        await repo.set_claim_support_head(sup2)
        await sqlite_db.commit()

        heads = await repo.list_claim_support_heads(wb_id)
        assert len(heads) == 2
        by_id = {h.support_id: h for h in heads}
        assert by_id[sup1.support_id].created_on_branch is True
        assert by_id[sup2.support_id].created_on_branch is False

    async def test_claim_support_head_overwrite(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        sup_id = id_gen.support_id()

        await repo.set_claim_support_head(BranchClaimSupportHead(wb_id, sup_id, False))
        await sqlite_db.commit()

        await repo.set_claim_support_head(BranchClaimSupportHead(wb_id, sup_id, True))
        await sqlite_db.commit()

        heads = await repo.list_claim_support_heads(wb_id)
        assert len(heads) == 1
        assert heads[0].created_on_branch is True

    # ================================================================
    # Branch Claim Derivation Heads
    # ================================================================

    async def test_claim_derivation_head_set_and_list(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        der1 = BranchClaimDerivationHead(wb_id, id_gen.derivation_id(), True)
        der2 = BranchClaimDerivationHead(wb_id, id_gen.derivation_id(), False)

        await repo.set_claim_derivation_head(der1)
        await repo.set_claim_derivation_head(der2)
        await sqlite_db.commit()

        heads = await repo.list_claim_derivation_heads(wb_id)
        assert len(heads) == 2
        by_id = {h.derivation_id: h for h in heads}
        assert by_id[der1.derivation_id].created_on_branch is True
        assert by_id[der2.derivation_id].created_on_branch is False

    async def test_claim_derivation_head_overwrite(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        der_id = id_gen.derivation_id()

        await repo.set_claim_derivation_head(BranchClaimDerivationHead(wb_id, der_id, False))
        await sqlite_db.commit()

        await repo.set_claim_derivation_head(BranchClaimDerivationHead(wb_id, der_id, True))
        await sqlite_db.commit()

        heads = await repo.list_claim_derivation_heads(wb_id)
        assert len(heads) == 1
        assert heads[0].created_on_branch is True

    # ================================================================
    # Tombstones
    # ================================================================

    async def test_tombstone_add_and_get(self, sqlite_db, clock, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        entity_id = id_gen.page_id()

        ts = BranchTombstone(
            workbook_id=wb_id,
            entity_kind=EntityKind.PAGE,
            entity_id=entity_id,
            tombstoned_at=clock.now(),
        )
        await repo.add_tombstone(ts)
        await sqlite_db.commit()

        got = await repo.get_tombstone(wb_id, EntityKind.PAGE, entity_id)
        assert got is not None
        assert got.workbook_id == wb_id
        assert got.entity_kind == EntityKind.PAGE
        assert got.entity_id == entity_id

    async def test_tombstone_get_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        got = await repo.get_tombstone(id_gen.workbook_id(), EntityKind.CLAIM, id_gen.claim_id())
        assert got is None

    async def test_tombstone_list(self, sqlite_db, clock, id_gen):
        repo = SqliteWorkbookRepository(sqlite_db)
        wb_id = id_gen.workbook_id()

        for kind, gen_fn in [(EntityKind.PAGE, id_gen.page_id), (EntityKind.CLAIM, id_gen.claim_id)]:
            await repo.add_tombstone(BranchTombstone(wb_id, kind, gen_fn(), clock.now()))

        await sqlite_db.commit()
        tombstones = await repo.list_tombstones(wb_id)
        assert len(tombstones) == 2

    async def test_workbook_created_by_run(self, sqlite_db, clock, id_gen, actor):
        """Workbook with a non-None created_by_run stores and restores correctly."""
        repo = SqliteWorkbookRepository(sqlite_db)
        run_id = id_gen.generate("run")
        wb_id = id_gen.workbook_id()
        rev_id = id_gen.revision_id()

        wb = Workbook(
            workbook_id=wb_id,
            vault_id=id_gen.vault_id(),
            name="run-created",
            purpose=BranchPurpose.COMPILATION,
            status=WorkbookStatus.OPEN,
            base_revision_id=rev_id,
            created_at=clock.now(),
            created_by=actor,
            created_by_run=run_id,
        )
        await repo.create(wb)
        await sqlite_db.commit()

        got = await repo.get(wb_id)
        assert got is not None
        assert got.created_by_run == run_id
        assert got.purpose == BranchPurpose.COMPILATION
