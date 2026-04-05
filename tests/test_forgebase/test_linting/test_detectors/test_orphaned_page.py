"""Tests for OrphanedPageDetector."""

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
from hephaestus.forgebase.linting.detectors.orphaned_page import OrphanedPageDetector
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_orphan(fb, clock, id_gen):
    """Create a vault with two concept pages: one linked, one orphaned."""
    vault = await fb.vaults.create_vault(
        name="orphan-test", description="Vault for orphan page tests"
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()

        # Page A: will have an inbound link
        page_a_id = id_gen.page_id()
        content_a = b"# Page A\n\nLinked page."
        ref_a = await uow.content.stage(content_a, "text/markdown")
        page_a = Page(
            page_id=page_a_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="page-a",
            created_at=now,
        )
        pv_a = PageVersion(
            page_id=page_a_id,
            version=Version(1),
            title="Page A",
            content_ref=ref_a.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content_a),
            summary="Page A",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page_a, pv_a)

        # Page B: orphan (no inbound links)
        page_b_id = id_gen.page_id()
        content_b = b"# Page B\n\nOrphan page."
        ref_b = await uow.content.stage(content_b, "text/markdown")
        page_b = Page(
            page_id=page_b_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="page-b",
            created_at=now,
        )
        pv_b = PageVersion(
            page_id=page_b_id,
            version=Version(1),
            title="Page B",
            content_ref=ref_b.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content_b),
            summary="Page B",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page_b, pv_b)

        # Link from B -> A (so A has an inbound link, B does not)
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
            source_entity=page_b_id,
            target_entity=page_a_id,
            label="relates to",
            weight=1.0,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.links.create(link, lv)
        await uow.commit()

    return vault, page_a_id, page_b_id, link_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_orphaned_page():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_a_id, page_b_id, _ = await _setup_vault_with_orphan(fb, clock, id_gen)

    detector = OrphanedPageDetector()

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        # Page B is orphaned (no inbound links)
        orphan_page_ids = set()
        for f in findings:
            assert f.category == FindingCategory.ORPHANED_PAGE
            orphan_page_ids.add(f.page_id)

        assert page_b_id in orphan_page_ids
        # Page A has an inbound link from B, so should NOT be orphaned
        assert page_a_id not in orphan_page_ids
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_source_cards_excluded():
    """SOURCE_CARD pages should never be reported as orphaned."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="source-card-test", description="Test")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        sc_id = id_gen.page_id()
        content = b"# Source Card\n\nRef."
        ref = await uow.content.stage(content, "text/markdown")
        sc = Page(
            page_id=sc_id,
            vault_id=vault.vault_id,
            page_type=PageType.SOURCE_CARD,
            page_key="source-card",
            created_at=now,
        )
        sc_pv = PageVersion(
            page_id=sc_id,
            version=Version(1),
            title="Source Card",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Source card",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(sc, sc_pv)
        await uow.commit()

    detector = OrphanedPageDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        orphan_ids = {f.page_id for f in findings}
        assert sc_id not in orphan_ids
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_link_added():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_a_id, page_b_id, _ = await _setup_vault_with_orphan(fb, clock, id_gen)

    detector = OrphanedPageDetector()

    # Step 1: Detect orphaned page B
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        orphan_ids = {f.page_id for f in findings}
        assert page_b_id in orphan_ids
        await uow.rollback()

    # Step 2: Add a link from A -> B
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
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
            source_entity=page_a_id,
            target_entity=page_b_id,
            label="relates to",
            weight=1.0,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.links.create(link, lv)
        await uow2.commit()

    # Step 3: Verify is_resolved
    original_finding = LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault.vault_id,
        category=FindingCategory.ORPHANED_PAGE,
        severity=FindingSeverity.INFO,
        page_id=page_b_id,
        claim_id=None,
        description="Orphaned page",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[page_b_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
