"""Branch queries — workbook CRUD reads and COW read-through helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.enums import EntityKind, WorkbookStatus
from hephaestus.forgebase.domain.models import (
    PageVersion,
    Workbook,
)
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId
from hephaestus.forgebase.repository.page_repo import PageRepository
from hephaestus.forgebase.repository.vault_repo import VaultRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


@dataclass
class WorkbookDiff:
    """Result of comparing a workbook's branch heads against canonical."""

    workbook_id: EntityId
    base_revision_id: VaultRevisionId
    added_pages: list[EntityId] = field(default_factory=list)
    modified_pages: list[EntityId] = field(default_factory=list)
    deleted_pages: list[EntityId] = field(default_factory=list)
    added_claims: list[EntityId] = field(default_factory=list)
    modified_claims: list[EntityId] = field(default_factory=list)
    deleted_claims: list[EntityId] = field(default_factory=list)
    added_links: list[EntityId] = field(default_factory=list)
    modified_links: list[EntityId] = field(default_factory=list)
    deleted_links: list[EntityId] = field(default_factory=list)
    added_sources: list[EntityId] = field(default_factory=list)
    modified_sources: list[EntityId] = field(default_factory=list)
    deleted_sources: list[EntityId] = field(default_factory=list)


async def get_workbook(
    workbooks: WorkbookRepository,
    workbook_id: EntityId,
) -> Workbook | None:
    """Get a workbook by ID."""
    return await workbooks.get(workbook_id)


async def list_workbooks(
    workbooks: WorkbookRepository,
    vault_id: EntityId,
    *,
    status: WorkbookStatus | None = None,
) -> list[Workbook]:
    """List workbooks for a vault, optionally filtering by status."""
    return await workbooks.list_by_vault(vault_id, status=status)


async def diff_workbook(
    workbooks: WorkbookRepository,
    vaults: VaultRepository,
    workbook_id: EntityId,
) -> WorkbookDiff:
    """Compare a workbook's branch heads against canonical heads.

    Entities are classified as:
    - added: base_version == 0 (born on branch, no canonical predecessor)
    - modified: base_version > 0 and head_version > base_version
    - deleted: tombstoned on branch

    Note: base_version == 0 is a convention indicating the entity did not exist
    in canonical when the branch was created. Version(1) with base_version=Version(1)
    where head_version > base_version indicates modification.
    """
    workbook = await workbooks.get(workbook_id)
    if workbook is None:
        raise ValueError(f"Workbook not found: {workbook_id}")

    diff = WorkbookDiff(
        workbook_id=workbook_id,
        base_revision_id=workbook.base_revision_id,
    )

    # Classify page changes
    page_heads = await workbooks.list_page_heads(workbook_id)
    for ph in page_heads:
        canonical = await vaults.get_canonical_page_head(workbook.vault_id, ph.page_id)
        if canonical is None:
            # Entity didn't exist canonically — born on branch
            diff.added_pages.append(ph.page_id)
        else:
            diff.modified_pages.append(ph.page_id)

    # Classify claim changes
    claim_heads = await workbooks.list_claim_heads(workbook_id)
    for ch in claim_heads:
        canonical = await vaults.get_canonical_claim_head(workbook.vault_id, ch.claim_id)
        if canonical is None:
            diff.added_claims.append(ch.claim_id)
        else:
            diff.modified_claims.append(ch.claim_id)

    # Classify link changes
    link_heads = await workbooks.list_link_heads(workbook_id)
    for lh in link_heads:
        canonical = await vaults.get_canonical_link_head(workbook.vault_id, lh.link_id)
        if canonical is None:
            diff.added_links.append(lh.link_id)
        else:
            diff.modified_links.append(lh.link_id)

    # Classify source changes
    source_heads = await workbooks.list_source_heads(workbook_id)
    for sh in source_heads:
        canonical = await vaults.get_canonical_source_head(workbook.vault_id, sh.source_id)
        if canonical is None:
            diff.added_sources.append(sh.source_id)
        else:
            diff.modified_sources.append(sh.source_id)

    # Tombstones = deleted
    tombstones = await workbooks.list_tombstones(workbook_id)
    for ts in tombstones:
        if ts.entity_kind == EntityKind.PAGE:
            diff.deleted_pages.append(ts.entity_id)
        elif ts.entity_kind == EntityKind.CLAIM:
            diff.deleted_claims.append(ts.entity_id)
        elif ts.entity_kind == EntityKind.LINK:
            diff.deleted_links.append(ts.entity_id)
        elif ts.entity_kind == EntityKind.SOURCE:
            diff.deleted_sources.append(ts.entity_id)

    return diff


async def resolve_page_version(
    pages: PageRepository,
    vaults: VaultRepository,
    workbooks: WorkbookRepository,
    page_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> PageVersion | None:
    """Read-through helper for page versions.

    If workbook_id is provided:
      1. Check tombstone — if tombstoned, return None (entity deleted on branch)
      2. Check branch page head — if found, get that version
      3. Fall through to canonical head version

    If workbook_id is None:
      Return the canonical head version directly.
    """
    if workbook_id is not None:
        # Check tombstone
        tombstone = await workbooks.get_tombstone(workbook_id, EntityKind.PAGE, page_id)
        if tombstone is not None:
            return None

        # Check branch head
        branch_head = await workbooks.get_page_head(workbook_id, page_id)
        if branch_head is not None:
            return await pages.get_version(page_id, branch_head.head_version)

    # Fall through to canonical
    return await pages.get_head_version(page_id)
