"""Tests for StaleEvidenceDetector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    PageType,
    SupportType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimVersion,
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
from hephaestus.forgebase.linting.detectors.stale_evidence import (
    StaleEvidenceDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_stale_claim(fb, clock, id_gen):
    """Create a vault with a page and a claim whose fresh_until has expired."""
    vault = await fb.vaults.create_vault(
        name="stale-test", description="Vault for stale evidence tests"
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        page_id = id_gen.page_id()
        content = b"# Test Page\n\nSome content."
        content_ref = await uow.content.stage(content, "text/markdown")

        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="test-page",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Test Page",
            content_ref=content_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Test page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)

        # Create a claim with expired freshness
        claim_id = id_gen.claim_id()
        expired = now - timedelta(days=7)
        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="SEI layer degrades during cycling",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.8,
            validated_at=expired,
            fresh_until=expired,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    return vault, page_id, claim_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_stale_claims():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, claim_id = await _setup_vault_with_stale_claim(fb, clock, id_gen)

    detector = StaleEvidenceDetector()

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        assert len(findings) >= 1
        # Finding should be at the page level, aggregated
        stale_finding = findings[0]
        assert stale_finding.category == FindingCategory.STALE_EVIDENCE
        assert stale_finding.severity == FindingSeverity.WARNING
        assert stale_finding.page_id == page_id
        assert claim_id in stale_finding.affected_entity_ids
        assert stale_finding.confidence == 1.0
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_no_findings_when_claims_are_fresh():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(name="fresh-test", description="Vault with fresh claims")

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        page_id = id_gen.page_id()
        content = b"# Fresh Page\n\nAll good."
        content_ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="fresh-page",
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Fresh Page",
            content_ref=content_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Fresh page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)

        # Claim with fresh_until in the future
        claim_id = id_gen.claim_id()
        future = now + timedelta(days=30)
        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="This is fresh",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
            validated_at=now,
            fresh_until=future,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    detector = StaleEvidenceDetector()
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) == 0
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_freshness_updated():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, page_id, claim_id = await _setup_vault_with_stale_claim(fb, clock, id_gen)

    detector = StaleEvidenceDetector()

    # Step 1: Detect the stale claim
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        await uow.rollback()

    # Step 2: Fix it by creating a new claim version with fresh_until in the future
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
        future = now + timedelta(days=30)
        new_cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(2),
            statement="SEI layer degrades during cycling",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.8,
            validated_at=now,
            fresh_until=future,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.claims.create_version(new_cv)
        await uow2.commit()

    # Step 3: Verify is_resolved returns True
    original_finding = LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault.vault_id,
        category=FindingCategory.STALE_EVIDENCE,
        severity=FindingSeverity.WARNING,
        page_id=page_id,
        claim_id=claim_id,
        description="Stale claim",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[claim_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
