"""Claim queries — read claims with optional branch read-through."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import ClaimDerivation, ClaimSupport, ClaimVersion
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.claim_derivation_repo import ClaimDerivationRepository
from hephaestus.forgebase.repository.claim_repo import ClaimRepository
from hephaestus.forgebase.repository.claim_support_repo import ClaimSupportRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository


async def _resolve_claim_version(
    claims: ClaimRepository,
    workbooks: WorkbookRepository,
    claim_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> ClaimVersion | None:
    """Read-through helper for claim versions.

    If workbook_id is provided:
      1. Check tombstone
      2. Check branch claim head
      3. Fall through to canonical head

    If workbook_id is None:
      Return canonical head directly.
    """
    if workbook_id is not None:
        tombstone = await workbooks.get_tombstone(workbook_id, EntityKind.CLAIM, claim_id)
        if tombstone is not None:
            return None

        branch_head = await workbooks.get_claim_head(workbook_id, claim_id)
        if branch_head is not None:
            return await claims.get_version(claim_id, branch_head.head_version)

    return await claims.get_head_version(claim_id)


async def get_claim(
    claims: ClaimRepository,
    claim_supports: ClaimSupportRepository,
    claim_derivations: ClaimDerivationRepository,
    workbooks: WorkbookRepository,
    claim_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> tuple[ClaimVersion, list[ClaimSupport], list[ClaimDerivation]] | None:
    """Get a claim with its supports and derivations.

    Returns (ClaimVersion, supports, derivations) or None if not found / tombstoned.
    """
    version = await _resolve_claim_version(claims, workbooks, claim_id, workbook_id=workbook_id)
    if version is None:
        return None

    supports = await claim_supports.list_by_claim(claim_id)
    derivations = await claim_derivations.list_by_claim(claim_id)

    return version, supports, derivations


async def list_claims(
    claims: ClaimRepository,
    workbooks: WorkbookRepository,
    page_id: EntityId,
    *,
    workbook_id: EntityId | None = None,
) -> list[ClaimVersion]:
    """List claim versions for a page, with optional branch read-through.

    Returns the effective version for each claim (branch version if modified,
    canonical otherwise). Tombstoned claims are excluded.
    """
    all_claims = await claims.list_by_page(page_id)
    results: list[ClaimVersion] = []

    for claim in all_claims:
        version = await _resolve_claim_version(
            claims, workbooks, claim.claim_id, workbook_id=workbook_id
        )
        if version is not None:
            results.append(version)

    return results
