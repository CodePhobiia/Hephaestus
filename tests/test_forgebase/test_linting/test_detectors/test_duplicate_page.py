"""Tests for DuplicatePageDetector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    PageType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    LintFinding,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    Version,
)
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.detectors.duplicate_page import DuplicatePageDetector
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_duplicates(fb, clock, id_gen):
    """Create a vault with two pages that have the same normalized title."""
    vault = await fb.vaults.create_vault(
        name="dup-test", description="Vault for duplicate page tests"
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()

        # Page 1: "Sodium Ion"
        page1_id = id_gen.page_id()
        content1 = b"# Sodium Ion\n\nContent about sodium ion."
        ref1 = await uow.content.stage(content1, "text/markdown")
        page1 = Page(
            page_id=page1_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="sodium-ion-1",
            created_at=now,
        )
        pv1 = PageVersion(
            page_id=page1_id,
            version=Version(1),
            title="Sodium Ion",
            content_ref=ref1.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content1),
            summary="Sodium ion page 1",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page1, pv1)

        # Page 2: " sodium ion " (same after normalize)
        page2_id = id_gen.page_id()
        content2 = b"# Sodium Ion\n\nAnother page about sodium ion."
        ref2 = await uow.content.stage(content2, "text/markdown")
        page2 = Page(
            page_id=page2_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="sodium-ion-2",
            created_at=now,
        )
        pv2 = PageVersion(
            page_id=page2_id,
            version=Version(1),
            title=" sodium ion ",
            content_ref=ref2.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content2),
            summary="Sodium ion page 2",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page2, pv2)

        # Page 3: unique title
        page3_id = id_gen.page_id()
        content3 = b"# Lithium Ion\n\nDifferent."
        ref3 = await uow.content.stage(content3, "text/markdown")
        page3 = Page(
            page_id=page3_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="lithium-ion",
            created_at=now,
        )
        pv3 = PageVersion(
            page_id=page3_id,
            version=Version(1),
            title="Lithium Ion",
            content_ref=ref3.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content3),
            summary="Lithium ion page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page3, pv3)
        await uow.commit()

    return vault, page1_id, page2_id, page3_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_duplicate_pages():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page1_id, page2_id, page3_id = await _setup_vault_with_duplicates(fb, clock, id_gen)

    detector = DuplicatePageDetector()

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        assert len(findings) >= 1
        # The finding should reference both duplicate pages
        dup_finding = findings[0]
        assert dup_finding.category == FindingCategory.DUPLICATE_PAGE
        assert page1_id in dup_finding.affected_entity_ids
        assert page2_id in dup_finding.affected_entity_ids
        # The unique page should NOT be in any finding
        all_affected = set()
        for f in findings:
            all_affected.update(f.affected_entity_ids)
        assert page3_id not in all_affected
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_no_findings_when_titles_unique():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="unique-test", description="All unique titles")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        for i, title in enumerate(["Alpha", "Beta", "Gamma"]):
            pid = id_gen.page_id()
            content = f"# {title}\n\nContent.".encode()
            ref = await uow.content.stage(content, "text/markdown")
            page = Page(
                page_id=pid,
                vault_id=vault.vault_id,
                page_type=PageType.CONCEPT,
                page_key=f"page-{i}",
                created_at=now,
            )
            pv = PageVersion(
                page_id=pid,
                version=Version(1),
                title=title,
                content_ref=ref.to_blob_ref(),
                content_hash=ContentHash.from_bytes(content),
                summary=title,
                compiled_from=[],
                created_at=now,
                created_by=ActorRef.system(),
            )
            await uow.pages.create(page, pv)
        await uow.commit()

    detector = DuplicatePageDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) == 0
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_title_changed():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page1_id, page2_id, _ = await _setup_vault_with_duplicates(fb, clock, id_gen)

    detector = DuplicatePageDetector()

    # Step 1: Verify detected
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        await uow.rollback()

    # Step 2: Fix by changing page2's title
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
        content = b"# Sodium Ion Revised\n\nUpdated page."
        ref = await uow2.content.stage(content, "text/markdown")
        new_pv = PageVersion(
            page_id=page2_id,
            version=Version(2),
            title="Sodium Ion Battery",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Renamed page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.pages.create_version(new_pv)
        await uow2.commit()

    # Step 3: Verify resolved
    original_finding = LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault.vault_id,
        category=FindingCategory.DUPLICATE_PAGE,
        severity=FindingSeverity.WARNING,
        page_id=None,
        claim_id=None,
        description="Duplicate pages: sodium ion",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[page1_id, page2_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
