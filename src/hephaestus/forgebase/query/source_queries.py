"""Source queries — read sources with optional branch read-through."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import Source, SourceVersion
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.source_repo import SourceRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


async def _resolve_source_version(
    sources: SourceRepository,
    workbooks: WorkbookRepository,
    source_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> SourceVersion | None:
    """Read-through helper for source versions.

    If workbook_id provided:
      1. Check tombstone
      2. Check branch source head
      3. Fall through to canonical

    If workbook_id is None:
      Return canonical head directly.
    """
    if workbook_id is not None:
        tombstone = await workbooks.get_tombstone(workbook_id, EntityKind.SOURCE, source_id)
        if tombstone is not None:
            return None

        branch_head = await workbooks.get_source_head(workbook_id, source_id)
        if branch_head is not None:
            return await sources.get_version(source_id, branch_head.head_version)

    return await sources.get_head_version(source_id)


async def get_source(
    sources: SourceRepository,
    workbooks: WorkbookRepository,
    source_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> SourceVersion | None:
    """Get a source version, with optional branch read-through."""
    return await _resolve_source_version(sources, workbooks, source_id, workbook_id=workbook_id)


async def list_sources(
    sources: SourceRepository,
    workbooks: WorkbookRepository,
    vault_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> list[tuple[Source, SourceVersion]]:
    """List sources in a vault with their effective versions.

    If workbook_id is provided, includes branch-modified versions and
    excludes tombstoned sources.

    Returns a list of (Source, SourceVersion) tuples.
    """
    all_sources = await sources.list_by_vault(vault_id)
    results: list[tuple[Source, SourceVersion]] = []

    for source in all_sources:
        version = await _resolve_source_version(
            sources, workbooks, source.source_id, workbook_id=workbook_id
        )
        if version is not None:
            results.append((source, version))

    return results
