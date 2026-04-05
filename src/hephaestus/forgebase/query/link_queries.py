"""Link queries — read links with optional branch read-through."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import LinkVersion
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.link_repo import LinkRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


async def _resolve_link_version(
    links: LinkRepository,
    workbooks: WorkbookRepository,
    link_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> LinkVersion | None:
    """Read-through helper for link versions.

    If workbook_id provided:
      1. Check tombstone
      2. Check branch link head
      3. Fall through to canonical

    If workbook_id is None:
      Return canonical head directly.
    """
    if workbook_id is not None:
        tombstone = await workbooks.get_tombstone(workbook_id, EntityKind.LINK, link_id)
        if tombstone is not None:
            return None

        branch_head = await workbooks.get_link_head(workbook_id, link_id)
        if branch_head is not None:
            return await links.get_version(link_id, branch_head.head_version)

    return await links.get_head_version(link_id)


async def list_links(
    links: LinkRepository,
    workbooks: WorkbookRepository,
    entity_id: EntityId,
    *,
    direction: str = "both",
    kind: str | None = None,
    workbook_id: EntityId | None = None,
) -> list[LinkVersion]:
    """List link versions for an entity, with optional branch read-through.

    Returns the effective version for each link (branch version if modified,
    canonical otherwise). Tombstoned links are excluded.
    """
    all_links = await links.list_by_entity(entity_id, direction=direction, kind=kind)
    results: list[LinkVersion] = []

    for link in all_links:
        version = await _resolve_link_version(
            links, workbooks, link.link_id, workbook_id=workbook_id
        )
        if version is not None:
            results.append(version)

    return results


async def get_backlinks(
    links: LinkRepository,
    workbooks: WorkbookRepository,
    page_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> list[LinkVersion]:
    """Get all links pointing TO a page (backlinks).

    Uses direction='target' to find links where target_entity == page_id.
    """
    return await list_links(
        links,
        workbooks,
        page_id,
        direction="target",
        workbook_id=workbook_id,
    )
