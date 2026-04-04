"""Tests for VaultLintState — the query facade used by all lint detectors.

Creates a seeded vault with known state via the factory, then verifies
each lazy-cached selector returns the correct data.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hephaestus.forgebase.compiler.policy import SynthesisPolicy
from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    ClaimStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    LinkKind,
    PageType,
    SourceFormat,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimVersion,
    ConceptCandidate,
    LintFinding,
    Link,
    LinkVersion,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_compiled_vault(fb, clock):
    """Ingest + normalize + compile 2 sources, then run Tier 2 synthesis.

    Returns (vault, source1, source2).
    """
    vault = await fb.vaults.create_vault(
        name="lint-test-vault", description="Vault for lint state tests"
    )

    # --- Source 1 ---
    s1_content = b"""# Sodium-Ion Anode Research

## Methods
Electrochemical impedance spectroscopy was used to study SEI formation.

## Results
The solid electrolyte interphase (SEI) degrades during cycling,
leading to capacity fade. SEI instability is the primary degradation
mechanism in sodium-ion anodes.
"""
    source1, sv1 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s1_content,
        format=SourceFormat.MARKDOWN,
        title="Anode Research Paper",
        trust_tier=SourceTrustTier.AUTHORITATIVE,
        idempotency_key="test:lint:source1",
    )
    norm1 = await fb.normalization.normalize(s1_content, SourceFormat.MARKDOWN)
    nsv1 = await fb.ingest.normalize_source(
        source_id=source1.source_id,
        normalized_content=norm1,
        expected_version=sv1.version,
        idempotency_key="test:lint:norm1",
    )

    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source1.source_id,
        source_version=nsv1.version,
        vault_id=vault.vault_id,
    )

    # --- Source 2 ---
    s2_content = b"""# SEI Layer Formation Dynamics

## Abstract
This paper studies the formation dynamics of the solid electrolyte
interphase in sodium-ion batteries using in-situ TEM.

## Key Findings
SEI formation follows a two-stage nucleation process.
"""
    source2, sv2 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s2_content,
        format=SourceFormat.MARKDOWN,
        title="SEI Formation Paper",
        trust_tier=SourceTrustTier.AUTHORITATIVE,
        idempotency_key="test:lint:source2",
    )
    norm2 = await fb.normalization.normalize(s2_content, SourceFormat.MARKDOWN)
    nsv2 = await fb.ingest.normalize_source(
        source_id=source2.source_id,
        normalized_content=norm2,
        expected_version=sv2.version,
        idempotency_key="test:lint:norm2",
    )

    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source2.source_id,
        source_version=nsv2.version,
        vault_id=vault.vault_id,
    )

    # --- Tier 2 synthesis ---
    clock.tick(1)
    await fb.vault_synthesizer.synthesize(vault_id=vault.vault_id)

    return vault, source1, source2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_env():
    """Create a ForgeBase instance with a fully compiled vault."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault, source1, source2 = await _seed_compiled_vault(fb, clock)
    yield fb, vault, source1, source2, clock, id_gen
    await fb.close()


# ---------------------------------------------------------------------------
# Tests: core selectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pages_returns_all_pages(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        pages = await state.pages()
        assert len(pages) > 0
        # Each entry is a (Page, PageVersion) tuple
        for page, pv in pages:
            assert isinstance(page, Page)
            assert isinstance(pv, PageVersion)
            assert page.vault_id == vault.vault_id
        await uow.rollback()


@pytest.mark.asyncio
async def test_claims_returns_all_with_supports(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        claims = await state.claims()
        assert len(claims) > 0
        for claim_id, (cv, supports, derivations) in claims.items():
            assert isinstance(cv, ClaimVersion)
            assert isinstance(supports, list)
            assert isinstance(derivations, list)
        await uow.rollback()


@pytest.mark.asyncio
async def test_links_returns_all(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        links = await state.links()
        assert len(links) > 0
        for link, lv in links:
            assert isinstance(link, Link)
            assert isinstance(lv, LinkVersion)
            assert link.vault_id == vault.vault_id
        await uow.rollback()


@pytest.mark.asyncio
async def test_sources_returns_all(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        sources = await state.sources()
        assert len(sources) >= 2  # We ingested 2 sources
        await uow.rollback()


@pytest.mark.asyncio
async def test_candidates_returns_active(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        candidates = await state.candidates()
        # All returned candidates should be ACTIVE or at least come from the vault
        assert isinstance(candidates, list)
        for c in candidates:
            assert isinstance(c, ConceptCandidate)
        await uow.rollback()


@pytest.mark.asyncio
async def test_claims_without_support(seeded_env):
    """Create a claim manually with SUPPORTED status but no support records."""
    fb, vault, _, _, clock, id_gen = seeded_env
    uow = fb.uow_factory()
    async with uow:
        # First, get an existing page to attach the claim to
        all_pages = await uow.pages.list_by_vault(vault.vault_id)
        assert len(all_pages) > 0
        target_page = all_pages[0]

        # Create a claim with SUPPORTED status but no actual support records
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
            statement="Unsupported test claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.8,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    # Now test the selector
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        without_support = await state.claims_without_support()
        assert len(without_support) > 0
        found = False
        for c, cv in without_support:
            if c.claim_id == claim_id:
                found = True
                assert cv.status == ClaimStatus.SUPPORTED
                assert cv.statement == "Unsupported test claim"
        assert found, "Expected to find our manually created claim"
        await uow2.rollback()


@pytest.mark.asyncio
async def test_pages_with_zero_inbound_links(seeded_env):
    """Create a concept page with no links pointing to it."""
    fb, vault, _, _, clock, id_gen = seeded_env
    uow = fb.uow_factory()
    async with uow:
        # Create an orphan concept page
        orphan_page_id = id_gen.page_id()
        now = clock.now()
        content = b"# Orphan Page\n\nThis page has no inbound links."
        content_ref = await uow.content.stage(content, "text/markdown")

        orphan_page = Page(
            page_id=orphan_page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="orphan-page",
            created_at=now,
        )
        orphan_pv = PageVersion(
            page_id=orphan_page_id,
            version=Version(1),
            title="Orphan Page",
            content_ref=content_ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Orphan page for testing",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(orphan_page, orphan_pv)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        orphans = await state.pages_with_zero_inbound_links()
        assert len(orphans) > 0
        orphan_ids = [str(p.page_id) for p in orphans]
        assert str(orphan_page_id) in orphan_ids
        # Ensure SOURCE_CARD and SOURCE_INDEX pages are excluded
        for p in orphans:
            assert p.page_type not in (PageType.SOURCE_CARD, PageType.SOURCE_INDEX)
        await uow2.rollback()


@pytest.mark.asyncio
async def test_claims_past_freshness(seeded_env):
    """Create a claim with expired fresh_until."""
    fb, vault, _, _, clock, id_gen = seeded_env
    uow = fb.uow_factory()
    async with uow:
        all_pages = await uow.pages.list_by_vault(vault.vault_id)
        target_page = all_pages[0]

        claim_id = id_gen.claim_id()
        now = clock.now()
        expired_time = now - timedelta(days=7)

        claim = Claim(
            claim_id=claim_id,
            vault_id=vault.vault_id,
            page_id=target_page.page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="Stale claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.7,
            validated_at=expired_time,
            fresh_until=expired_time,
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.claims.create(claim, cv)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        stale = await state.claims_past_freshness(clock.now())
        found = False
        for c, cv in stale:
            if c.claim_id == claim_id:
                found = True
                assert cv.fresh_until is not None
                assert cv.fresh_until < clock.now()
        assert found, "Expected to find our stale claim"
        await uow2.rollback()


@pytest.mark.asyncio
async def test_candidates_promotion_worthy(seeded_env):
    """Create active candidates that cross promotion thresholds."""
    fb, vault, source1, source2, clock, id_gen = seeded_env

    policy = SynthesisPolicy(
        min_sources_for_promotion=2,
        min_salience_single_source=0.8,
    )

    uow = fb.uow_factory()
    async with uow:
        # Create two candidates from different sources with same normalized_name,
        # with no resolved_page_id — they should be promotion-worthy
        now = clock.now()
        c1_id = id_gen.generate("cand")
        c2_id = id_gen.generate("cand")

        c1 = ConceptCandidate(
            candidate_id=c1_id,
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source1.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Promotion Candidate",
            normalized_name="promotion_candidate",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.6,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        c2 = ConceptCandidate(
            candidate_id=c2_id,
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source2.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Promotion Candidate",
            normalized_name="promotion_candidate",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.6,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow.concept_candidates.create(c1)
        await uow.concept_candidates.create(c2)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        worthy = await state.candidates_promotion_worthy(policy)
        assert len(worthy) >= 2
        worthy_ids = {str(c.candidate_id) for c in worthy}
        assert str(c1_id) in worthy_ids
        assert str(c2_id) in worthy_ids
        await uow2.rollback()


@pytest.mark.asyncio
async def test_page_content_reads_bytes(seeded_env):
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        pages = await state.pages()
        assert len(pages) > 0
        page, pv = pages[0]
        content = await state.page_content(page.page_id)
        assert isinstance(content, bytes)
        assert len(content) > 0
        await uow.rollback()


@pytest.mark.asyncio
async def test_caching(seeded_env):
    """Call pages() twice and verify the same object is returned (lazy cache)."""
    fb, vault, *_ = seeded_env
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        pages1 = await state.pages()
        pages2 = await state.pages()
        assert pages1 is pages2, "Second call should return cached object"

        claims1 = await state.claims()
        claims2 = await state.claims()
        assert claims1 is claims2

        links1 = await state.links()
        links2 = await state.links()
        assert links1 is links2

        sources1 = await state.sources()
        sources2 = await state.sources()
        assert sources1 is sources2

        candidates1 = await state.candidates()
        candidates2 = await state.candidates()
        assert candidates1 is candidates2
        await uow.rollback()


@pytest.mark.asyncio
async def test_existing_findings(seeded_env):
    """Create a finding and verify it appears in existing_findings()."""
    fb, vault, _, _, clock, id_gen = seeded_env
    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        finding = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault.vault_id,
            category=FindingCategory.ORPHANED_PAGE,
            severity=FindingSeverity.WARNING,
            page_id=None,
            claim_id=None,
            description="Test finding",
            suggested_action="Fix it",
            status=FindingStatus.OPEN,
        )
        await uow.findings.create(finding)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await state.existing_findings()
        assert len(findings) >= 1
        found = any(f.finding_id == finding.finding_id for f in findings)
        assert found, "Expected to find our created finding"
        await uow2.rollback()
