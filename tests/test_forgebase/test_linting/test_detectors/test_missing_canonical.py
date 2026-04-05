"""Tests for MissingCanonicalDetector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.compiler.policy import SynthesisPolicy
from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    PageType,
    SourceFormat,
    SourceTrustTier,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import (
    ConceptCandidate,
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
from hephaestus.forgebase.linting.detectors.missing_canonical import (
    MissingCanonicalDetector,
)
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_vault_with_promotion_worthy_candidates(fb, clock, id_gen):
    """Create two candidates from different sources, same name, no resolved page."""
    vault = await fb.vaults.create_vault(
        name="canonical-test", description="Vault for missing canonical tests"
    )

    # We need two sources to meet min_sources_for_promotion=2
    s1_content = b"# Source 1\n\nContent about SEI."
    source1, sv1 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s1_content,
        format=SourceFormat.MARKDOWN,
        title="Source 1",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:canonical:s1",
    )

    s2_content = b"# Source 2\n\nMore content about SEI."
    source2, sv2 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s2_content,
        format=SourceFormat.MARKDOWN,
        title="Source 2",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:canonical:s2",
    )

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        c1_id = id_gen.generate("cand")
        c2_id = id_gen.generate("cand")
        job_id = id_gen.job_id()

        c1 = ConceptCandidate(
            candidate_id=c1_id,
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source1.source_id,
            source_version=sv1.version,
            source_compile_job_id=job_id,
            name="SEI Formation",
            normalized_name="sei_formation",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.7,
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
            source_version=sv2.version,
            source_compile_job_id=id_gen.job_id(),
            name="SEI Formation",
            normalized_name="sei_formation",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.7,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow.concept_candidates.create(c1)
        await uow.concept_candidates.create(c2)
        await uow.commit()

    return vault, c1_id, c2_id, source1, source2


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_missing_canonical():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    policy = SynthesisPolicy(min_sources_for_promotion=2)
    vault, c1_id, c2_id, *_ = await _setup_vault_with_promotion_worthy_candidates(fb, clock, id_gen)

    detector = MissingCanonicalDetector(policy=policy)

    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)

        assert len(findings) >= 1
        finding = findings[0]
        assert finding.category == FindingCategory.MISSING_CANONICAL
        affected_ids = set(finding.affected_entity_ids)
        assert c1_id in affected_ids or c2_id in affected_ids
        await uow.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_no_findings_when_candidates_have_resolved_pages():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    policy = SynthesisPolicy(min_sources_for_promotion=2)
    vault = await fb.vaults.create_vault(
        name="resolved-test", description="Candidates already resolved"
    )

    # Create sources
    s1_content = b"# Source 1\n\nContent."
    source1, sv1 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s1_content,
        format=SourceFormat.MARKDOWN,
        title="Source A",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:resolved:s1",
    )
    s2_content = b"# Source 2\n\nMore content."
    source2, sv2 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=s2_content,
        format=SourceFormat.MARKDOWN,
        title="Source B",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:resolved:s2",
    )

    resolved_page_id = id_gen.page_id()

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        # Create a page that the candidates resolve to
        content = b"# SEI Formation\n\nCanonical page."
        ref = await uow.content.stage(content, "text/markdown")
        page = Page(
            page_id=resolved_page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="sei-formation",
            created_at=now,
        )
        pv = PageVersion(
            page_id=resolved_page_id,
            version=Version(1),
            title="SEI Formation",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Canonical page",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow.pages.create(page, pv)

        # Both candidates already have resolved_page_id set
        c1_id = id_gen.generate("cand")
        c2_id = id_gen.generate("cand")
        job_id = id_gen.job_id()
        for cid, src in [(c1_id, source1), (c2_id, source2)]:
            c = ConceptCandidate(
                candidate_id=cid,
                vault_id=vault.vault_id,
                workbook_id=None,
                source_id=src.source_id,
                source_version=sv1.version,
                source_compile_job_id=job_id,
                name="SEI Formation",
                normalized_name="sei_formation",
                aliases=[],
                candidate_kind=CandidateKind.CONCEPT,
                confidence=0.9,
                salience=0.7,
                status=CandidateStatus.ACTIVE,
                resolved_page_id=resolved_page_id,
                compiler_policy_version="1.0.0",
                created_at=now,
            )
            await uow.concept_candidates.create(c)
        await uow.commit()

    detector = MissingCanonicalDetector(policy=policy)
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) == 0
        await uow2.rollback()

    await fb.close()


@pytest.mark.asyncio
async def test_is_resolved_when_page_created():
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    policy = SynthesisPolicy(min_sources_for_promotion=2)
    vault, c1_id, c2_id, *_ = await _setup_vault_with_promotion_worthy_candidates(fb, clock, id_gen)

    detector = MissingCanonicalDetector(policy=policy)

    # Step 1: Verify detection
    uow = fb.uow_factory()
    async with uow:
        state = VaultLintState(uow, vault.vault_id)
        findings = await detector.detect(state)
        assert len(findings) >= 1
        await uow.rollback()

    # Step 2: Resolve by updating candidate with resolved_page_id
    resolved_page_id = id_gen.page_id()
    uow2 = fb.uow_factory()
    async with uow2:
        now = clock.now()
        # Create the resolved page
        content = b"# SEI Formation\n\nCanonical page."
        ref = await uow2.content.stage(content, "text/markdown")
        page = Page(
            page_id=resolved_page_id,
            vault_id=vault.vault_id,
            page_type=PageType.CONCEPT,
            page_key="sei-formation",
            created_at=now,
        )
        pv = PageVersion(
            page_id=resolved_page_id,
            version=Version(1),
            title="SEI Formation",
            content_ref=ref.to_blob_ref(),
            content_hash=ContentHash.from_bytes(content),
            summary="Canonical",
            compiled_from=[],
            created_at=now,
            created_by=ActorRef.system(),
        )
        await uow2.pages.create(page, pv)

        # Update candidates to have resolved_page_id via update_status
        await uow2.concept_candidates.update_status(
            c1_id, CandidateStatus.PROMOTED, resolved_page_id=resolved_page_id
        )
        await uow2.concept_candidates.update_status(
            c2_id, CandidateStatus.PROMOTED, resolved_page_id=resolved_page_id
        )
        await uow2.commit()

    # Step 3: Verify is_resolved
    original_finding = LintFinding(
        finding_id=id_gen.finding_id(),
        job_id=id_gen.job_id(),
        vault_id=vault.vault_id,
        category=FindingCategory.MISSING_CANONICAL,
        severity=FindingSeverity.INFO,
        page_id=None,
        claim_id=None,
        description="Missing canonical page",
        suggested_action=None,
        status=FindingStatus.OPEN,
        affected_entity_ids=[c1_id, c2_id],
    )

    uow3 = fb.uow_factory()
    async with uow3:
        state = VaultLintState(uow3, vault.vault_id)
        new_findings = await detector.detect(state)
        resolved = await detector.is_resolved(original_finding, state, new_findings)
        assert resolved is True
        await uow3.rollback()

    await fb.close()
