"""Tests for SourceGapDetector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    SourceFormat,
    SourceTrustTier,
)
from hephaestus.forgebase.domain.models import ConceptCandidate, LintFinding
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer
from hephaestus.forgebase.linting.detectors.source_gap import SourceGapDetector
from hephaestus.forgebase.linting.state import VaultLintState
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def env():
    """ForgeBase with a vault and two compiled sources."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )
    vault = await fb.vaults.create_vault(
        name="source-gap-test", description="Vault for source gap tests"
    )

    # Ingest two sources
    c1 = b"# Source A\n\nContent about topic alpha."
    source1, sv1 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=c1,
        format=SourceFormat.MARKDOWN,
        title="Source A",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:gap:s1",
    )
    norm1 = await fb.normalization.normalize(c1, SourceFormat.MARKDOWN)
    nsv1 = await fb.ingest.normalize_source(
        source_id=source1.source_id,
        normalized_content=norm1,
        expected_version=sv1.version,
        idempotency_key="test:gap:n1",
    )
    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source1.source_id,
        source_version=nsv1.version,
        vault_id=vault.vault_id,
    )

    c2 = b"# Source B\n\nContent about topic beta."
    source2, sv2 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=c2,
        format=SourceFormat.MARKDOWN,
        title="Source B",
        trust_tier=SourceTrustTier.STANDARD,
        idempotency_key="test:gap:s2",
    )
    norm2 = await fb.normalization.normalize(c2, SourceFormat.MARKDOWN)
    nsv2 = await fb.ingest.normalize_source(
        source_id=source2.source_id,
        normalized_content=norm2,
        expected_version=sv2.version,
        idempotency_key="test:gap:n2",
    )
    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source2.source_id,
        source_version=nsv2.version,
        vault_id=vault.vault_id,
    )

    yield fb, vault, source1, source2, clock, id_gen
    await fb.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_single_source_concept(env):
    """A concept with only 1 source should be flagged as a source gap."""
    fb, vault, source1, source2, clock, id_gen = env

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        # Create a candidate from only one source
        cand = ConceptCandidate(
            candidate_id=id_gen.generate("cand"),
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source1.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Lonely Concept",
            normalized_name="lonely_concept",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.5,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow.concept_candidates.create(cand)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = SourceGapDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        gap_findings = [
            f for f in findings if f.category == FindingCategory.SOURCE_GAP
        ]
        # Should find the lonely concept
        lonely_findings = [
            f for f in gap_findings
            if "lonely_concept" in f.normalized_subject
        ]
        assert len(lonely_findings) >= 1
        assert lonely_findings[0].severity in (
            FindingSeverity.WARNING,
            FindingSeverity.INFO,
        )
        await uow2.rollback()


@pytest.mark.asyncio
async def test_no_gap_for_multi_source_concept(env):
    """A concept with 2+ sources should not be flagged."""
    fb, vault, source1, source2, clock, id_gen = env

    uow = fb.uow_factory()
    async with uow:
        now = clock.now()
        # Create two candidates from different sources with same normalized_name
        cand1 = ConceptCandidate(
            candidate_id=id_gen.generate("cand"),
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source1.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Well Covered",
            normalized_name="well_covered",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.7,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        cand2 = ConceptCandidate(
            candidate_id=id_gen.generate("cand"),
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source2.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Well Covered",
            normalized_name="well_covered",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.7,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow.concept_candidates.create(cand1)
        await uow.concept_candidates.create(cand2)
        await uow.commit()

    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = SourceGapDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)

        # "well_covered" should not appear in source gap findings
        well_covered_findings = [
            f for f in findings
            if f.category == FindingCategory.SOURCE_GAP
            and "well_covered" in f.normalized_subject
        ]
        assert len(well_covered_findings) == 0
        await uow2.rollback()


@pytest.mark.asyncio
async def test_is_resolved_when_source_added(env):
    """Adding a second source to a concept should resolve the gap."""
    fb, vault, source1, source2, clock, id_gen = env

    # Create a single-source candidate
    uow = fb.uow_factory()
    cand_id = id_gen.generate("cand")
    async with uow:
        now = clock.now()
        cand = ConceptCandidate(
            candidate_id=cand_id,
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source1.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Growing Concept",
            normalized_name="growing_concept",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.5,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow.concept_candidates.create(cand)
        await uow.commit()

    # Detect the gap
    uow2 = fb.uow_factory()
    async with uow2:
        state = VaultLintState(uow2, vault.vault_id)
        detector = SourceGapDetector(analyzer=MockLintAnalyzer())
        findings = await detector.detect(state)
        gap_findings = [
            f for f in findings
            if f.category == FindingCategory.SOURCE_GAP
            and "growing_concept" in f.normalized_subject
        ]
        assert len(gap_findings) >= 1
        await uow2.rollback()

    # Add a second source for the same concept
    uow3 = fb.uow_factory()
    async with uow3:
        now = clock.now()
        cand2 = ConceptCandidate(
            candidate_id=id_gen.generate("cand"),
            vault_id=vault.vault_id,
            workbook_id=None,
            source_id=source2.source_id,
            source_version=Version(2),
            source_compile_job_id=id_gen.job_id(),
            name="Growing Concept",
            normalized_name="growing_concept",
            aliases=[],
            candidate_kind=CandidateKind.CONCEPT,
            confidence=0.9,
            salience=0.6,
            status=CandidateStatus.ACTIVE,
            resolved_page_id=None,
            compiler_policy_version="1.0.0",
            created_at=now,
        )
        await uow3.concept_candidates.create(cand2)
        await uow3.commit()

    # Verify resolved
    uow4 = fb.uow_factory()
    async with uow4:
        state2 = VaultLintState(uow4, vault.vault_id)
        detector2 = SourceGapDetector(analyzer=MockLintAnalyzer())
        new_findings = await detector2.detect(state2)

        # growing_concept should no longer be in source gap findings
        still_gap = [
            f for f in new_findings
            if f.category == FindingCategory.SOURCE_GAP
            and "growing_concept" in f.normalized_subject
        ]
        assert len(still_gap) == 0

        # Also test is_resolved
        fake_original = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=id_gen.job_id(),
            vault_id=vault.vault_id,
            category=FindingCategory.SOURCE_GAP,
            severity=FindingSeverity.WARNING,
            page_id=None,
            claim_id=None,
            description="Test gap",
            suggested_action=None,
            status=FindingStatus.OPEN,
            affected_entity_ids=[cand_id],
        )
        resolved = await detector2.is_resolved(fake_original, state2, new_findings)
        assert resolved is True
        await uow4.rollback()
