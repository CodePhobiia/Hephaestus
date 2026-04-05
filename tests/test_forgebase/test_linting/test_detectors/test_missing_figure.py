"""Tests for MissingFigureDetector."""

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
from hephaestus.forgebase.linting.detectors.missing_figure import (
    MissingFigureDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def env():
    """Minimal ForgeBase with a vault."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(
        name="figure-test", description="Vault for missing figure tests"
    )
    yield fb, vault, clock, id_gen
    await fb.close()


async def _create_page(uow, vault_id, content_str: str, title: str, clock, id_gen):
    """Create a page with the given content string."""
    page_id = id_gen.page_id()
    now = clock.now()
    content = content_str.encode("utf-8")
    content_ref = await uow.content.stage(content, "text/markdown")
    page = Page(
        page_id=page_id,
        vault_id=vault_id,
        page_type=PageType.CONCEPT,
        page_key=title.lower().replace(" ", "-"),
        created_at=now,
    )
    pv = PageVersion(
        page_id=page_id,
        version=Version(1),
        title=title,
        content_ref=content_ref.to_blob_ref(),
        content_hash=ContentHash.from_bytes(content),
        summary=f"Page: {title}",
        compiled_from=[],
        created_at=now,
        created_by=ActorRef.system(),
    )
    await uow.pages.create(page, pv)
    return page_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_empty_alt_text(env):
    """Markdown image with empty alt text should be detected."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            "# Test Page\n\nSome text.\n\n![](image.png)\n\nMore text.",
            "Empty Alt Page",
            clock,
            id_gen,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)

        figure_findings = [
            f for f in findings if f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
        ]
        assert len(figure_findings) >= 1
        assert figure_findings[0].severity == FindingSeverity.INFO
        assert "empty" in figure_findings[0].description.lower()
        await uow2.rollback()


@pytest.mark.asyncio
async def test_detects_generic_alt_text(env):
    """Markdown image with generic alt text like 'image' should be detected."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            "# Page\n\n![image](diagram.png)\n\nText after.",
            "Generic Alt Page",
            clock,
            id_gen,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)

        figure_findings = [
            f for f in findings if f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
        ]
        assert len(figure_findings) >= 1
        assert "generic" in figure_findings[0].description.lower()
        await uow2.rollback()


@pytest.mark.asyncio
async def test_no_finding_for_meaningful_alt(env):
    """Markdown image with meaningful alt text should not be flagged."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            "# Page\n\n![Diagram showing SEI layer formation](diagram.png)\n\nText.",
            "Good Alt Page",
            clock,
            id_gen,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)

        # Our page should NOT be flagged
        flagged_page_ids = {
            str(f.page_id)
            for f in findings
            if f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
        }
        assert str(page_id) not in flagged_page_ids
        await uow2.rollback()


@pytest.mark.asyncio
async def test_detects_html_img_empty_alt(env):
    """HTML <img> with empty alt attribute should be detected."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            '# HTML Page\n\n<img src="photo.jpg" alt="" />\n\nText.',
            "HTML Empty Alt",
            clock,
            id_gen,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)

        figure_findings = [
            f
            for f in findings
            if f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
            and str(page_id) in {str(e) for e in f.affected_entity_ids}
        ]
        assert len(figure_findings) >= 1
        await uow2.rollback()


@pytest.mark.asyncio
async def test_no_finding_for_page_without_images(env):
    """A page with no images should produce zero findings."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            "# Text Only\n\nThis page has no images at all.",
            "Text Only Page",
            clock,
            id_gen,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)

        flagged = [
            f
            for f in findings
            if f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
            and str(page_id) in {str(e) for e in f.affected_entity_ids}
        ]
        assert len(flagged) == 0
        await uow2.rollback()


@pytest.mark.asyncio
async def test_is_resolved_when_alt_text_added(env):
    """Fixing the alt text should resolve the finding."""
    fb, vault, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        page_id = await _create_page(
            uow,
            vault.vault_id,
            "# Page\n\n![](bad.png)\n\nText.",
            "Fix Alt Page",
            clock,
            id_gen,
        )
        await uow.commit()

    # Detect
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = MissingFigureDetector()
        findings = await detector.detect(state)
        assert any(f.category == FindingCategory.MISSING_FIGURE_EXPLANATION for f in findings)
        await uow2.rollback()

    # Fix: update the page content with a meaningful alt text
    uow3 = fb.uow_factory()
    async with uow3:
        new_content = b"# Page\n\n![Detailed diagram of the process](bad.png)\n\nText."
        content_ref = await uow3.content.stage(new_content, "text/markdown")
        pv2 = PageVersion(
            page_id=page_id,
            version=Version(2),
            title="Fix Alt Page",
            content_ref=content_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(new_content),
            summary="Fixed alt text",
            compiled_from=[],
            created_at=clock.now(),
            created_by=ActorRef.system(),
        )
        await uow3.pages.create_version(pv2)
        await uow3.commit()

    # Verify resolved
    uow4 = fb.uow_factory()
    async with uow4:
        state2 = VaultLintState(uow4, vault.vault_id)
        detector2 = MissingFigureDetector()
        new_findings = await detector2.detect(state2)

        fake_original = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault.vault_id,
            category=FindingCategory.MISSING_FIGURE_EXPLANATION,
            severity=FindingSeverity.INFO,
            page_id=page_id,
            claim_id=None,
            description="Test",
            suggested_action=None,
            status=FindingStatus.OPEN,
            affected_entity_ids=[page_id],
        )
        resolved = await detector2.is_resolved(fake_original, state2, new_findings)
        assert resolved is True
        await uow4.rollback()
