"""Tests for UnsupportedClaimDetector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    SourceFormat,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimSupport,
    ClaimVersion,
    LintFinding,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer
from hephaestus.forgebase.linting.detectors.unsupported_claim import (
    UnsupportedClaimDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def env():
    """Minimal ForgeBase with a vault and one source compiled."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(
        name="unsupported-test", description="Vault for unsupported claim tests"
    )
    # Ingest + compile one source to get pages
    content = b"# Test\n\nSome content for testing unsupported claims."
    source, sv = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=content,
        format=SourceFormat.MARKDOWN,
        title="Test Source",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:unsup:s1",
    )
    norm = await fb.normalization.normalize(content, SourceFormat.MARKDOWN)
    nsv = await fb.ingest.normalize_source(
        source_id=source.source_id,
        normalized_content=norm,
        expected_version=sv.version,
        idempotency_key="test:unsup:n1",
    )
    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source.source_id,
        source_version=nsv.version,
        vault_id=vault.vault_id,
    )
    yield fb, vault, source, clock, id_gen
    await fb.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_unsupported_claim(env):
    """A claim with SUPPORTED status but zero supports should be detected."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        assert len(pages) > 0
        target_page = pages[0]

        # Create a claim with SUPPORTED status but no support records
        claim_id = id_gen.claim_id()
        now = clock.now()
        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=target_page.page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="Water boils at 100C at sea level",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    # Run detector
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = UnsupportedClaimDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        # Should find at least our manually created unsupported claim
        unsupported_ids = [
            f.claim_id for f in findings if f.category == FindingCategory.UNSUPPORTED_CLAIM
        ]
        assert claim_id in unsupported_ids
        # Verify the finding's attributes
        our_finding = [f for f in findings if f.claim_id == claim_id][0]
        assert our_finding.severity == FindingSeverity.WARNING
        assert our_finding.confidence == 1.0
        assert "Water boils" in our_finding.description
        await uow2.rollback()


@pytest.mark.asyncio
async def test_does_not_flag_supported_with_evidence(env):
    """A claim with SUPPORTED status and actual support should not be detected."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = id_gen.claim_id()
        support_id = id_gen.support_id()
        now = clock.now()
        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=target_page.page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="Properly supported claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        # Add actual support
        support = ClaimSupport(
            support_id=support_id,
            claim_id=claim_id,
            source_id=source.source_id,
            source_segment="Evidence text here",
            strength=0.8,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claim_supports.create(support)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = UnsupportedClaimDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        # Our claim should NOT be in the findings
        flagged_ids = [f.claim_id for f in findings]
        assert claim_id not in flagged_ids
        await uow2.rollback()


@pytest.mark.asyncio
async def test_is_resolved_when_support_added(env):
    """Adding support to a previously unsupported claim resolves the finding."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = id_gen.claim_id()
        now = clock.now()
        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=target_page.page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="Will get support later",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    # Detect the finding
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = UnsupportedClaimDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)
        assert any(f.claim_id == claim_id for f in findings)
        await uow2.rollback()

    # Now add support
    uow3 = fb.uow_factory()
    async with uow3:
        support_id = id_gen.support_id()
        support = ClaimSupport(
            support_id=support_id,
            claim_id=claim_id,
            source_id=source.source_id,
            source_segment="New evidence",
            strength=0.9,
            created_at=clock.now(),
            created_by=ActorRef.system(),
        )
        await uow3.claim_supports.create(support)
        await uow3.commit()

    # Verify it's resolved
    uow4 = fb.uow_factory()
    async with uow4:
        state2 = VaultLintState(uow4, vault.vault_id)
        detector2 = UnsupportedClaimDetector(analyzer=MockLintAnalyzer())
        new_findings = await detector2.detect(state2)

        fake_original = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault.vault_id,
            category=FindingCategory.UNSUPPORTED_CLAIM,
            severity=FindingSeverity.WARNING,
            page_id=None,
            claim_id=claim_id,
            description="Test",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        resolved = await detector2.is_resolved(fake_original, state2, new_findings)
        assert resolved is True
        await uow4.rollback()
