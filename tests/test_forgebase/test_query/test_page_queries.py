"""Tests for page queries — get and list with branch read-through."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import BranchPurpose, PageType
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.query.page_queries import get_page, list_pages
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestGetPage:
    async def _setup(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="PageQueryVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, pv = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="pq-page",
            page_type=PageType.CONCEPT,
            title="Page Query Page",
            content=b"page content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="PQ Branch",
            purpose=BranchPurpose.RESEARCH,
        )

        return vault, page, pv, wb

    async def test_get_page_canonical(self, uow_factory, actor):
        """Get page without workbook returns canonical version."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        uow = uow_factory()
        async with uow:
            result = await get_page(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "Page Query Page"

    async def test_get_page_with_branch_modification(self, uow_factory, actor):
        """Get page with workbook returns branch version when modified."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Branch Title",
            workbook_id=wb.workbook_id,
        )

        uow = uow_factory()
        async with uow:
            result = await get_page(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "Branch Title"

    async def test_get_page_tombstoned_on_branch(self, uow_factory, actor):
        """Get tombstoned page with workbook returns None."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.delete_page(page.page_id, wb.workbook_id)

        uow = uow_factory()
        async with uow:
            result = await get_page(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is None

    async def test_get_page_falls_through(self, uow_factory, actor):
        """Page not modified on branch falls through to canonical."""
        vault, page, pv, wb = await self._setup(uow_factory, actor)

        uow = uow_factory()
        async with uow:
            result = await get_page(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                page.page_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert result is not None
        assert result.title == "Page Query Page"  # canonical version


@pytest.mark.asyncio
class TestListPages:
    async def test_list_canonical(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ListPagesVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="p1",
            page_type=PageType.CONCEPT,
            title="Page 1",
            content=b"c1",
        )
        await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="p2",
            page_type=PageType.MECHANISM,
            title="Page 2",
            content=b"c2",
        )

        uow = uow_factory()
        async with uow:
            results = await list_pages(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                vault.vault_id,
            )
            await uow.rollback()

        assert len(results) == 2
        titles = {pv.title for _, pv in results}
        assert titles == {"Page 1", "Page 2"}

    async def test_list_with_tombstone_exclusion(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="TombstoneListVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page1, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="alive",
            page_type=PageType.CONCEPT,
            title="Alive",
            content=b"alive",
        )
        page2, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="dead",
            page_type=PageType.CONCEPT,
            title="Dead",
            content=b"dead",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Tomb Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Tombstone page2 on branch
        await page_svc.delete_page(page2.page_id, wb.workbook_id)

        uow = uow_factory()
        async with uow:
            results = await list_pages(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                vault.vault_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert len(results) == 1
        assert results[0][1].title == "Alive"

    async def test_list_with_branch_modification(self, uow_factory, actor):
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        vault = await vault_svc.create_vault(name="ModListVault")

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="modifiable",
            page_type=PageType.CONCEPT,
            title="Original Title",
            content=b"content",
        )

        branch_svc = BranchService(uow_factory=uow_factory, default_actor=actor)
        wb = await branch_svc.create_workbook(
            vault_id=vault.vault_id,
            name="Mod Branch",
            purpose=BranchPurpose.MANUAL,
        )

        # Modify on branch
        await page_svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Modified Title",
            workbook_id=wb.workbook_id,
        )

        uow = uow_factory()
        async with uow:
            results = await list_pages(
                uow.pages,
                uow.vaults,
                uow.workbooks,
                vault.vault_id,
                workbook_id=wb.workbook_id,
            )
            await uow.rollback()

        assert len(results) == 1
        assert results[0][1].title == "Modified Title"
