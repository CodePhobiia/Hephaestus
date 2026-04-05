"""Tests for ResolvableBySearchDetector."""

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
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimSupport,
    ClaimVersion,
    LintFinding,
)
from hephaestus.forgebase.domain.values import ActorRef, Version
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer
from hephaestus.forgebase.linting.detectors.resolvable_by_search import (
    ResolvableBySearchDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def env():
    """Minimal ForgeBase with a vault and one compiled source."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(
        name="resolvable-test", description="Vault for resolvable by search tests"
    )
    content = b"# Test\n\nContent for resolvable tests."
    source, sv = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=content,
        format=SourceFormat.MARKDOWN,
        title="Test Source",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:resolvable:s1",
    )
    norm = await fb.normalization.normalize(content, SourceFormat.MARKDOWN)
    nsv = await fb.ingest.normalize_source(
        source_id=source.source_id,
        normalized_content=norm,
        expected_version=sv.version,
        idempotency_key="test:resolvable:n1",
    )
    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source.source_id,
        source_version=nsv.version,
        vault_id=vault.vault_id,
    )
    yield fb, vault, source, clock, id_gen
    await fb.close()


async def _create_claim_with_support(
    uow,
    vault_id,
    page_id,
    statement,
    source_id,
    clock,
    id_gen,
    status=ClaimStatus.SUPPORTED,
    num_supports=1,
):
    """Create a claim with N support records."""
    claim_id = id_gen.claim_id()
    now = clock.now()
    claim = Claim(
        claim_id=claim_id,
        vault_id=vault_id,
        page_id=page_id,
        created_at=now,
    )
    cv = ClaimVersion(
        claim_id=claim_id,
        version=Version(1),
        statement=statement,
        status=status,
        support_type=SupportType.DIRECT,
        confidence=0.7,
        validated_at=now,
        fresh_until=None,
        created_at=now,
        created_by=ActorRef.system(),
    )
    await uow.claims.create(claim, cv)
    for i in range(num_supports):
        support = ClaimSupport(
            support_id=id_gen.support_id(),
            claim_id=claim_id,
            source_id=source_id,
            source_segment=f"Evidence segment {i}",
            strength=0.5,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claim_supports.create(support)
    return claim_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_inferred_claim(env):
    """An INFERRED claim with weak support should be flagged as resolvable."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = await _create_claim_with_support(
            uow,
            vault.vault_id,
            target_page.page_id,
            "Sodium-ion batteries will replace lithium-ion by 2030",
            source.source_id,
            clock,
            id_gen,
            status=ClaimStatus.INFERRED,
            num_supports=1,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        resolvable = [
            f
            for f in findings
            if f.category == FindingCategory.RESOLVABLE_BY_SEARCH and f.claim_id == claim_id
        ]
        assert len(resolvable) >= 1
        assert "search" in resolvable[0].description.lower()
        await uow2.rollback()


@pytest.mark.asyncio
async def test_detects_hypothesis_claim(env):
    """A HYPOTHESIS claim should be flagged as resolvable."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = await _create_claim_with_support(
            uow,
            vault.vault_id,
            target_page.page_id,
            "Hypothetical mechanism for SEI formation",
            source.source_id,
            clock,
            id_gen,
            status=ClaimStatus.HYPOTHESIS,
            num_supports=0,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        resolvable = [
            f
            for f in findings
            if f.category == FindingCategory.RESOLVABLE_BY_SEARCH and f.claim_id == claim_id
        ]
        assert len(resolvable) >= 1
        await uow2.rollback()


@pytest.mark.asyncio
async def test_skips_unsupported_claims(env):
    """Claims with SUPPORTED status and zero supports are skipped (covered by UnsupportedClaimDetector)."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        # Create a claim with SUPPORTED status but no supports
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
            statement="No support at all",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.5,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        # This claim should NOT be in resolvable findings (handled by UnsupportedClaimDetector)
        flagged_ids = [
            f.claim_id for f in findings if f.category == FindingCategory.RESOLVABLE_BY_SEARCH
        ]
        assert claim_id not in flagged_ids
        await uow2.rollback()


@pytest.mark.asyncio
async def test_no_finding_for_well_supported_claim(env):
    """A claim with 2+ supports should not be flagged."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = await _create_claim_with_support(
            uow,
            vault.vault_id,
            target_page.page_id,
            "Well supported claim with multiple sources",
            source.source_id,
            clock,
            id_gen,
            status=ClaimStatus.SUPPORTED,
            num_supports=3,
        )
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        flagged = [
            f
            for f in findings
            if f.category == FindingCategory.RESOLVABLE_BY_SEARCH and f.claim_id == claim_id
        ]
        assert len(flagged) == 0
        await uow2.rollback()


@pytest.mark.asyncio
async def test_is_resolved_when_support_strengthened(env):
    """Adding more support should resolve the finding."""
    fb, vault, source, clock, id_gen = env
    uow = fb.uow_factory()
    async with uow:
        pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = pages[0]

        claim_id = await _create_claim_with_support(
            uow,
            vault.vault_id,
            target_page.page_id,
            "Weakly supported claim needing search",
            source.source_id,
            clock,
            id_gen,
            status=ClaimStatus.SUPPORTED,
            num_supports=1,
        )
        await uow.commit()

    # Detect
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)
        resolvable = [
            f
            for f in findings
            if f.category == FindingCategory.RESOLVABLE_BY_SEARCH and f.claim_id == claim_id
        ]
        assert len(resolvable) >= 1
        await uow2.rollback()

    # Add more support
    uow3 = fb.uow_factory()
    async with uow3:
        for i in range(2):
            support = ClaimSupport(
                support_id=id_gen.support_id(),
                claim_id=claim_id,
                source_id=source.source_id,
                source_segment=f"Additional evidence {i}",
                strength=0.8,
                created_at=clock.now(),
                created_by=ActorRef.system(),
            )
            await uow3.claim_supports.create(support)
        await uow3.commit()

    # Verify resolved
    uow4 = fb.uow_factory()
    async with uow4:
        state2 = VaultLintState(uow4, vault.vault_id)
        detector2 = ResolvableBySearchDetector(analyzer=MockLintAnalyzer())
        new_findings = await detector2.detect(state2)

        fake_original = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault.vault_id,
            category=FindingCategory.RESOLVABLE_BY_SEARCH,
            severity=FindingSeverity.INFO,
            page_id=None,
            claim_id=claim_id,
            description="Test",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        resolved = await detector2.is_resolved(fake_original, state2, new_findings)
        assert resolved is True
        await uow4.rollback()
