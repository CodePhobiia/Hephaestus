"""Tests for UnresolvedTodoDetector."""

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
from hephaestus.forgebase.linting.detectors.unresolved_todo import (
    UnresolvedTodoDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_todo_page(fb, clock, id_gen):
    """Create a vault with a page containing TODO markers."""
    vault = await fb.vaults.create_vault(
        name="todo-test", description="Vault for unresolved TODO tests"
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()

        # Page with TODO markers
        page_id = id_gen.page_id()
        content = b"# Research Notes\n\nSEI formation is complex.\n\nTODO: Add more references.\nFIXME: Check the numbers.\nThis section has a PLACEHOLDER for the diagram.\n"
        ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="todo-page",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Research Notes",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Page with TODOs",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)

        # Clean page (no TODO markers)
        clean_page_id = id_gen.page_id()
        clean_content = b"# Clean Page\n\nAll content is complete."
        clean_ref = await uow.content.stage(clean_content, "text/markdown")
        clean_page = Page(
            page_id=clean_page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="clean-page",
            created_at=now,
        )
        clean_pv = PageVersion(
            page_id=clean_page_id,
            version=Version(1),
            title="Clean Page",
            content_ref=clean_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(clean_content),
            summary="Clean page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(clean_page, clean_pv)
        await uow.commit()

    return vault, page_id, clean_page_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_unresolved_todos():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, clean_page_id = await _setup_vault_with_todo_page(fb, clock, id_gen)

    detector = UnresolvedTodoDetector()

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        # Should find the todo page but not the clean page
        assert len(findings) >= 1
        finding_page_ids = {f.page_id for f in findings}
        assert page_id in finding_page_ids
        assert clean_page_id not in finding_page_ids

        # Verify metadata
        for f in findings:
            if f.page_id == page_id:
                assert f.category == FindingCategory.UNRESOLVED_TODO
                assert f.severity == FindingSeverity.INFO
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_no_findings_for_clean_content():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="clean-test", description="No TODOs")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        page_id = id_gen.page_id()
        content = b"# Complete Page\n\nEverything is done."
        ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="complete",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Complete Page",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Complete",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)
        await uow.commit()

    detector = UnresolvedTodoDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) == 0
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_case_insensitive_detection():
    """Ensure detection works for mixed case: todo, Todo, fixme, Tbd."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="case-test", description="Mixed case")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        page_id = id_gen.page_id()
        content = b"# Notes\n\ntodo: do something.\nTbd whether this works."
        ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="mixed-case",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Mixed Case Notes",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Mixed case",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)
        await uow.commit()

    detector = UnresolvedTodoDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        assert findings[0].page_id == page_id
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_todos_removed():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, _ = await _setup_vault_with_todo_page(fb, clock, id_gen)

    detector = UnresolvedTodoDetector()

    # Step 1: Detect
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        await uow.rollback()

    # Step 2: Fix by replacing content without TODOs
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
        clean_content = b"# Research Notes\n\nSEI formation is complex.\n\nAll references added.\nNumbers verified.\nDiagram included.\n"
        ref = await uow2.content.stage(clean_content, "text/markdown")
        new_pv = PageVersion(
            page_id=page_id,
            version=Version(2),
            title="Research Notes",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(clean_content),
            summary="Cleaned up",
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
        category=FindingCategory.UNRESOLVED_TODO,
        severity=FindingSeverity.INFO,
        page_id=page_id,
        claim_id=None,
        description="Unresolved TODO markers",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[page_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
