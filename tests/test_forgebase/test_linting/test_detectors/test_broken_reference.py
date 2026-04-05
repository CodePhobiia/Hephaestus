"""Tests for BrokenReferenceDetector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    LinkKind,
    PageType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    Link,
    LinkVersion,
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
from hephaestus.forgebase.linting.detectors.broken_reference import (
    BrokenReferenceDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_broken_link(fb, clock, id_gen):
    """Create a vault with a link pointing to a non-existent entity."""
    vault = await fb.vaults.create_vault(
        name="broken-ref-test", description="Vault for broken reference tests"
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()

        # Create one valid page
        page_id = id_gen.page_id()
        content = b"# Valid Page\n\nExists."
        ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="valid-page",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Valid Page",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Valid page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)

        # Create a link that points to a non-existent entity
        nonexistent_id = id_gen.page_id()  # this page_id was generated but never persisted
        link_id = id_gen.link_id()
        link = Link(
            link_id=link_id,
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            created_at=now,
        )
        lv = LinkVersion(
            link_id=link_id,
            version=Version(1),
            source_entity=page_id,
            target_entity=nonexistent_id,
            label="broken link",
            weight=1.0,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.links.create(link, lv)
        await uow.commit()

    return vault, page_id, link_id, nonexistent_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_broken_reference():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, link_id, nonexistent_id = await _setup_vault_with_broken_link(fb, clock, id_gen)

    detector = BrokenReferenceDetector()

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        assert len(findings) >= 1
        broken = findings[0]
        assert broken.category == FindingCategory.BROKEN_REFERENCE
        assert link_id in broken.affected_entity_ids
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_no_findings_when_all_links_valid():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="valid-links-test", description="All links are valid")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()

        page1_id = id_gen.page_id()
        content1 = b"# Page 1\n\nContent."
        ref1 = await uow.content.stage(content1, "text/markdown")
        page1 = Page(
            page_id=page1_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="p1",
            created_at=now,
        )
        pv1 = PageVersion(
            page_id=page1_id,
            version=Version(1),
            title="Page 1",
            content_ref=ref1.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content1),
            summary="Page 1",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page1, pv1)

        page2_id = id_gen.page_id()
        content2 = b"# Page 2\n\nContent."
        ref2 = await uow.content.stage(content2, "text/markdown")
        page2 = Page(
            page_id=page2_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="p2",
            created_at=now,
        )
        pv2 = PageVersion(
            page_id=page2_id,
            version=Version(1),
            title="Page 2",
            content_ref=ref2.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content2),
            summary="Page 2",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page2, pv2)

        # Valid link: page1 -> page2
        link_id = id_gen.link_id()
        link = Link(
            link_id=link_id,
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            created_at=now,
        )
        lv = LinkVersion(
            link_id=link_id,
            version=Version(1),
            source_entity=page1_id,
            target_entity=page2_id,
            label="valid",
            weight=1.0,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.links.create(link, lv)
        await uow.commit()

    detector = BrokenReferenceDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) == 0
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_target_created():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, link_id, nonexistent_id = await _setup_vault_with_broken_link(fb, clock, id_gen)

    detector = BrokenReferenceDetector()

    # Step 1: Verify broken ref detected
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        await uow.rollback()

    # Step 2: Fix by creating the missing page
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
        content = b"# Previously Missing\n\nNow exists."
        ref = await uow2.content.stage(content, "text/markdown")
        missing_page = Page(
            page_id=nonexistent_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="previously-missing",
            created_at=now,
        )
        missing_pv = PageVersion(
            page_id=nonexistent_id,
            version=Version(1),
            title="Previously Missing",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Now exists",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.pages.create(missing_page, missing_pv)
        await uow2.commit()

    # Step 3: Verify resolved
    original_finding = LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault.vault_id,
        category=FindingCategory.BROKEN_REFERENCE,
        severity=FindingSeverity.WARNING,
        page_id=None,
        claim_id=None,
        description="Broken reference",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[link_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
