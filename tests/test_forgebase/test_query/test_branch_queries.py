"""Tests for branch queries — read-through, diff, tombstone exclusion."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import BranchPurpose, PageType, WorkbookStatus
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.query.branch_queries import (
    diff_workbook,
    get_workbook,
    list_workbooks,
    resolve_page_version,
)
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestGetWorkbook:
    async def test_get_existing(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="QueryVault")

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="QueryBranch",
            purpose=BranchPurpose.RESEARCH,
        )

        uow = uow_factory()
        async with uow:
            result = await get_workbook(uow.workbooks, wb.workbook_id)
            await uow.rollback()

        assert result is not None
        assert result.name == "QueryBranch"

    async def test_get_nonexistent(self, uow_factory, id_gen):
        uow = uow_factory()
        async with uow:
            result = await get_workbook(uow.workbooks, id_gen.workbook_id())
            await uow.rollback()

        assert result is None


@pytest.mark.asyncio
class TestListWorkbooks:
    async def test_list_by_vault(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ListVault")

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="WB1",
            purpose=BranchPurpose.RESEARCH,
        )
        await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="WB2",
            purpose=BranchPurpose.MANUAL,
        )

        uow = uow_factory()
        async with uow:
            results = await list_workbooks(uow.workbooks, vault.vault_id)
            await uow.rollback()

        assert len(results) == 2

    async def test_list_by_vault_with_status_filter(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="FilterVault")

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb1 = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Active",
            purpose=BranchPurpose.RESEARCH,
        )
        wb2 = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Abandoned",
            purpose=BranchPurpose.MANUAL,
        )
        await branch_svc.abandon_workbook(wb2.workbook_id)

        uow = uow_factory()
        async with uow:
            open_wbs = await list_workbooks(
                uow.workbooks, vault.vault_id, status=WorkbookStatus.OPEN
            )
            abandoned_wbs = await list_workbooks(
                uow.workbooks, vault.vault_id, status=WorkbookStatus.ABANDONED
            )
            await uow.rollback()

        assert len(open_wbs) == 1
        assert open_wbs[0].name == "Active"
        assert len(abandoned_wbs) == 1
        assert abandoned_wbs[0].name == "Abandoned"


@pytest.mark.asyncio
class TestResolvePageVersion:
    async def _setup(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ReadThroughVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, pv = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="rt-page",
            page_type=PageType.CONCEPT,
            title="ReadThrough Page",
            content=b"original content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="ReadThrough Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        return vault, page, pv, wb

    async def test_resolve_canonical_without_workbook(self, uow_factory, actor):
        """Without workbook_id, returns canonical head version."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        uow = uow_factory()
        async with uow:
            result = await resolve_page_version(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "ReadThrough Page"
        assert result.version == Version(1)

    async def test_resolve_falls_through_to_canonical(self, uow_factory, actor):
        """With workbook_id but no branch head, falls through to canonical."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        uow = uow_factory()
        async with uow:
            result = await resolve_page_version(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "ReadThrough Page"

    async def test_resolve_returns_branch_version(self, uow_factory, actor):
        """With workbook_id and branch head, returns branch version."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        # Update on branch
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Branch Updated",
            workbook_id=wb.workbook_id,
        )

        uow = uow_factory()
        async with uow:
            result = await resolve_page_version(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "Branch Updated"
        assert result.version == Version(2)

    async def test_resolve_tombstoned_returns_none(self, uow_factory, actor):
        """Tombstoned page on branch should return None."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        # Delete on branch
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.delete_page(page.page_id, wb.workbook_id)

        uow = uow_factory()
        async with uow:
            result = await resolve_page_version(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is None

    async def test_tombstoned_still_visible_canonically(self, uow_factory, actor):
        """Tombstoned on branch, but without workbook_id should still show canonical."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.delete_page(page.page_id, wb.workbook_id)

        uow = uow_factory()
        async with uow:
            result = await resolve_page_version(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                # No workbook_id — canonical view
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "ReadThrough Page"


@pytest.mark.asyncio
class TestDiffWorkbook:
    async def test_diff_modified_pages(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="DiffVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="diff-page",
            page_type=PageType.CONCEPT,
            title="Diff Page",
            content=b"diff content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Diff Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        # Modify on branch
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Diff Updated",
            workbook_id=wb.workbook_id,
        )

        uow = uow_factory()
        async with uow:
            diff = await diff_workbook(uow.workbooks, uow.vaults, wb.workbook_id)
            await uow.rollback()

        assert len(diff.modified_pages) == 1
        assert diff.modified_pages[0] == page.page_id
        assert len(diff.added_pages) == 0
        assert len(diff.deleted_pages) == 0

    async def test_diff_added_pages(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="DiffAddVault")

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Add Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        # Create page on branch
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="new-on-branch",
            page_type=PageType.CONCEPT,
            title="New Page",
            content=b"brand new",
            workbook_id=wb.workbook_id,
        )

        uow = uow_factory()
        async with uow:
            diff = await diff_workbook(uow.workbooks, uow.vaults, wb.workbook_id)
            await uow.rollback()

        assert len(diff.added_pages) == 1
        assert diff.added_pages[0] == page.page_id

    async def test_diff_deleted_pages(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="DiffDelVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="to-delete",
            page_type=PageType.CONCEPT,
            title="Delete Me",
            content=b"content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Del Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Delete on branch
        await page_svc.delete_page(page.page_id, wb.workbook_id)

        uow = uow_factory()
        async with uow:
            diff = await diff_workbook(uow.workbooks, uow.vaults, wb.workbook_id)
            await uow.rollback()

        assert len(diff.deleted_pages) == 1
        assert diff.deleted_pages[0] == page.page_id
