"""End-to-end lifecycle test — validates the 10 minimum real flows.

This is the integration proof for the ForgeBase Foundation Platform.
It uses create_forgebase() with deterministic fixtures and exercises
every major flow in sequence.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    ClaimStatus,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SupportType,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.query.branch_queries import diff_workbook
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.mark.asyncio
async def test_full_forgebase_lifecycle():
    """Execute all 10 minimum flows from the spec end-to-end."""

    clock = FixedClock(datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()

    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    try:
        # ---------------------------------------------------------------
        # Flow 1: Create vault
        # ---------------------------------------------------------------
        vault = await fb.vaults.create_vault(
            name="battery-materials",
            description="Research vault for battery materials",
        )
        assert vault.name == "battery-materials"
        assert vault.description == "Research vault for battery materials"
        assert vault.vault_id.prefix == "vault"
        vault_id = vault.vault_id

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 2: Ingest raw source -> store raw artifact
        # ---------------------------------------------------------------
        source, sv = await fb.ingest.ingest_source(
            vault_id=vault_id,
            raw_content=b"# Sodium-Ion Anode Research\n\nKey findings on longevity...",
            format=SourceFormat.MARKDOWN,
            metadata={"title": "Anode Research Paper", "trust_tier": "authoritative"},
            idempotency_key="test:source:001",
            title="Anode Research Paper",
        )
        assert source.source_id.prefix == "source"
        assert sv.status == SourceStatus.INGESTED
        assert sv.version == Version(1)
        source_id = source.source_id

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 3: Normalize source
        # ---------------------------------------------------------------
        nsv = await fb.ingest.normalize_source(
            source_id=source_id,
            normalized_content=b"# Normalized: Sodium-Ion Anode Research\n\nCleaned content...",
            expected_version=sv.version,
            idempotency_key="test:normalize:001",
        )
        assert nsv.status == SourceStatus.NORMALIZED
        assert nsv.version == Version(2)

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 4: Create page (source card)
        # ---------------------------------------------------------------
        page, pv = await fb.pages.create_page(
            vault_id=vault_id,
            page_key="source-card/anode-research",
            page_type=PageType.SOURCE_CARD,
            title="Source: Anode Research Paper",
            content=b"## Summary\nKey findings on sodium-ion anode longevity...",
            compiled_from=[source_id],
        )
        assert page.page_id.prefix == "page"
        assert pv.version == Version(1)
        assert pv.compiled_from == [source_id]

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 5: Create concept page
        # ---------------------------------------------------------------
        concept_page, cpv = await fb.pages.create_page(
            vault_id=vault_id,
            page_key="concepts/sodium-ion-longevity",
            page_type=PageType.CONCEPT,
            title="Sodium-Ion Anode Longevity",
            content=b"# Sodium-Ion Anode Longevity\n\nMechanisms and bottlenecks...",
        )
        assert concept_page.page_type == PageType.CONCEPT
        assert cpv.version == Version(1)
        concept_page_id = concept_page.page_id

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 6: Attach claims with provenance
        # ---------------------------------------------------------------
        claim, cv = await fb.claims.create_claim(
            vault_id=vault_id,
            page_id=concept_page_id,
            statement=(
                "SEI layer instability is the primary degradation "
                "mechanism in sodium-ion anodes"
            ),
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.85,
        )
        assert claim.claim_id.prefix == "claim"
        assert cv.version == Version(1)
        assert cv.confidence == 0.85

        clock.tick(1)

        support = await fb.claims.add_support(
            claim_id=claim.claim_id,
            source_id=source_id,
            source_segment="Section 3.2: SEI Formation Analysis",
            strength=0.9,
        )
        assert support.strength == 0.9
        assert support.source_id == source_id

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 7: Open workbook branch
        # ---------------------------------------------------------------
        workbook = await fb.branches.create_workbook(
            vault_id=vault_id,
            name="research-update",
            purpose=BranchPurpose.RESEARCH,
        )
        assert workbook.status == WorkbookStatus.OPEN
        assert workbook.workbook_id.prefix == "wb"
        assert workbook.base_revision_id == vault.head_revision_id
        workbook_id = workbook.workbook_id

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 8: Propose updates in workbook (modify page on branch)
        # ---------------------------------------------------------------
        updated_pv = await fb.pages.update_page(
            page_id=concept_page_id,
            expected_version=cpv.version,
            title="Sodium-Ion Anode Longevity (Updated)",
            content=b"# Sodium-Ion Anode Longevity\n\nUpdated with new findings...",
            summary="Added new experimental results",
            workbook_id=workbook_id,
        )
        assert updated_pv.version == Version(2)
        assert updated_pv.title == "Sodium-Ion Anode Longevity (Updated)"

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 9: Diff workbook vs canonical
        # ---------------------------------------------------------------
        # diff_workbook takes repo instances — get them from a fresh UoW
        uow = fb.uow_factory()
        async with uow:
            diff = await diff_workbook(
                workbooks=uow.workbooks,
                vaults=uow.vaults,
                workbook_id=workbook_id,
            )
            # The concept page should show as modified (it existed
            # canonically and was updated on the branch)
            assert concept_page_id in diff.modified_pages
            # No added/deleted pages expected
            assert diff.deleted_pages == []
            await uow.rollback()

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 10: Merge workbook into vault
        # ---------------------------------------------------------------
        proposal = await fb.merge.propose_merge(workbook_id=workbook_id)
        assert proposal.verdict == MergeVerdict.CLEAN
        assert proposal.merge_id.prefix == "merge"

        clock.tick(1)

        new_revision = await fb.merge.execute_merge(merge_id=proposal.merge_id)
        assert new_revision is not None
        assert new_revision.revision_id.prefix == "rev"
        assert new_revision.summary == "Merge workbook research-update"

        # ---------------------------------------------------------------
        # Verify post-merge state
        # ---------------------------------------------------------------

        # The vault's head should now point to the new revision
        uow2 = fb.uow_factory()
        async with uow2:
            vault_after = await uow2.vaults.get(vault_id)
            assert vault_after is not None
            assert vault_after.head_revision_id == new_revision.revision_id

            # The workbook should be MERGED
            wb_after = await uow2.workbooks.get(workbook_id)
            assert wb_after is not None
            assert wb_after.status == WorkbookStatus.MERGED

            # Canonical page head for the concept page should be updated
            canonical_page_ver = await uow2.vaults.get_canonical_page_head(
                vault_id, concept_page_id
            )
            assert canonical_page_ver is not None
            assert canonical_page_ver > 1  # merged version is > 1

            await uow2.rollback()

        # ---------------------------------------------------------------
        # Verify events were emitted throughout
        # ---------------------------------------------------------------
        uow3 = fb.uow_factory()
        async with uow3:
            cursor = await uow3._db.execute(
                "SELECT event_type FROM fb_domain_events ORDER BY event_id"
            )
            rows = await cursor.fetchall()
            event_types = [row["event_type"] for row in rows]

            # We expect at minimum these event types to have been emitted
            assert "vault.created" in event_types
            assert "source.ingested" in event_types
            assert "source.normalized" in event_types
            assert "page.version_created" in event_types
            assert "claim.version_created" in event_types
            assert "claim.support_added" in event_types
            assert "workbook.created" in event_types
            assert "merge.proposed" in event_types
            assert "workbook.merged" in event_types

            await uow3.rollback()

    finally:
        await fb.close()
