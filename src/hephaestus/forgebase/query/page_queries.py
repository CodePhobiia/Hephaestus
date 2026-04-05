"""Page queries — read pages with optional branch read-through."""

from __future__ import annotations

from hephaestus.forgebase.domain.models import Page, PageVersion
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.query.branch_queries import resolve_page_version
from hephaestus.forgebase.repository.page_repo import PageRepository
from hephaestus.forgebase.repository.vault_repo import VaultRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


async def get_page(
    pages: PageRepository,
    vaults: VaultRepository,
    workbooks: WorkbookRepository,
    page_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> PageVersion | None:
    """Get the effective page version, with optional branch read-through.

    Uses resolve_page_version under the hood.
    """
    return await resolve_page_version(pages, vaults, workbooks, page_id, workbook_id=workbook_id)


async def list_pages(
    pages: PageRepository,
    vaults: VaultRepository,
    workbooks: WorkbookRepository,
    vault_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
    page_type: str | None = None,
) -> list[tuple[Page, PageVersion]]:
    """List pages in a vault with their effective versions.

    If workbook_id is provided, includes branch-modified versions and
    excludes tombstoned pages. Pages born on the branch are included
    (they exist in the page table with vault_id).

    Returns a list of (Page, PageVersion) tuples.
    """
    all_pages = await pages.list_by_vault(vault_id, page_type=page_type)
    results: list[tuple[Page, PageVersion]] = []

    for page in all_pages:
        version = await resolve_page_version(
            pages, vaults, workbooks, page.page_id, workbook_id=workbook_id
        )
        if version is not None:
            results.append((page, version))

    return results
