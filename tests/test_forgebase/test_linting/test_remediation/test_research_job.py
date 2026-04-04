"""Tests for FindingResearchJob — research orchestration for findings."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    RemediationStatus,
    ResearchOutcome,
)
from hephaestus.forgebase.domain.models import ResearchPacket
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.linting.remediation.research_job import FindingResearchJob
from hephaestus.forgebase.research.augmentor import (
    ContradictionResolution,
    DiscoveredSource,
    FreshnessCheck,
)
from hephaestus.forgebase.research.perplexity_augmentor import NoOpAugmentor
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.vault_service import VaultService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_vault_and_finding(
    uow_factory,
    actor,
    category: FindingCategory = FindingCategory.CONTRADICTORY_CLAIM,
    severity: FindingSeverity = FindingSeverity.WARNING,
):
    """Create a vault, schedule a lint job, and open a finding."""
    vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    vault = await vault_svc.create_vault(name="research-test-vault")

    lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
    job = await lint_svc.schedule_lint(
        vault_id=vault.vault_id,
        idempotency_key=f"research-lint-{category.value}",
    )
    finding = await lint_svc.open_finding(
        job_id=job.job_id,
        vault_id=vault.vault_id,
        category=category,
        severity=severity,
        description="Test finding for research",
        suggested_action="Investigate further",
    )
    return vault, lint_svc, finding


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResearchContradictionFinding:
    """test_research_contradiction_finding -- NoOpAugmentor, verify packet created."""

    @pytest.mark.asyncio
    async def test_research_contradiction_finding(self, uow_factory, actor):
        vault, lint_svc, finding = await _setup_vault_and_finding(
            uow_factory,
            actor,
            category=FindingCategory.CONTRADICTORY_CLAIM,
        )

        augmentor = NoOpAugmentor()
        job = FindingResearchJob(
            uow_factory=uow_factory,
            augmentor=augmentor,
            lint_service=lint_svc,
            default_actor=actor,
        )

        packet = await job.execute(
            finding_id=finding.finding_id,
            vault_id=vault.vault_id,
        )

        assert isinstance(packet, ResearchPacket)
        assert packet.finding_id == finding.finding_id
        assert packet.vault_id == vault.vault_id
        assert packet.augmentor_kind == "NoOpAugmentor"
        # NoOp returns insufficient_evidence for contradiction
        assert packet.outcome == ResearchOutcome.INSUFFICIENT_EVIDENCE


class TestResearchSourceGapFinding:
    """test_research_source_gap_finding -- verify find_supporting_evidence called."""

    @pytest.mark.asyncio
    async def test_research_source_gap_finding(self, uow_factory, actor):
        vault, lint_svc, finding = await _setup_vault_and_finding(
            uow_factory,
            actor,
            category=FindingCategory.SOURCE_GAP,
        )

        # Use a mock augmentor to verify find_supporting_evidence is called
        mock_augmentor = AsyncMock(spec=NoOpAugmentor)
        mock_augmentor.find_supporting_evidence = AsyncMock(return_value=[
            DiscoveredSource(
                url="https://example.com/paper",
                title="Relevant Paper",
                summary="Fills the gap",
                relevance=0.8,
            ),
        ])

        job = FindingResearchJob(
            uow_factory=uow_factory,
            augmentor=mock_augmentor,
            lint_service=lint_svc,
            default_actor=actor,
        )

        packet = await job.execute(
            finding_id=finding.finding_id,
            vault_id=vault.vault_id,
        )

        mock_augmentor.find_supporting_evidence.assert_awaited_once()
        assert packet.outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR


class TestOutcomeClassification:
    """test_outcome_classification -- verify different outcomes."""

    def test_sufficient_when_high_relevance_sources(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[
                DiscoveredSource(
                    url="", title="A", summary="", relevance=0.9,
                ),
            ],
            contradiction_result=None,
            freshness_result=None,
        )
        assert outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR

    def test_new_sources_pending_when_low_relevance(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[
                DiscoveredSource(
                    url="", title="A", summary="", relevance=0.3,
                ),
            ],
            contradiction_result=None,
            freshness_result=None,
        )
        assert outcome == ResearchOutcome.NEW_SOURCES_PENDING

    def test_no_actionable_result_when_empty(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[],
            contradiction_result=None,
            freshness_result=None,
        )
        assert outcome == ResearchOutcome.NO_ACTIONABLE_RESULT

    def test_sufficient_for_high_confidence_contradiction(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[],
            contradiction_result=ContradictionResolution(
                summary="A is stronger",
                resolution="claim_a_stronger",
                confidence=0.9,
            ),
            freshness_result=None,
        )
        assert outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR

    def test_insufficient_for_low_confidence_contradiction(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[],
            contradiction_result=ContradictionResolution(
                summary="unclear",
                resolution="insufficient_evidence",
                confidence=0.4,
            ),
            freshness_result=None,
        )
        assert outcome == ResearchOutcome.INSUFFICIENT_EVIDENCE

    def test_sufficient_for_freshness_with_newer_evidence(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[],
            contradiction_result=None,
            freshness_result=FreshnessCheck(
                is_stale=True,
                reason="Newer study found",
                newer_evidence=["Study 2026"],
            ),
        )
        assert outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR

    def test_no_actionable_for_fresh_claim(self):
        outcome = FindingResearchJob._classify_outcome(
            discovered_sources=[],
            contradiction_result=None,
            freshness_result=FreshnessCheck(
                is_stale=False,
                reason="Still current",
            ),
        )
        assert outcome == ResearchOutcome.NO_ACTIONABLE_RESULT


class TestFindingStatusUpdated:
    """test_finding_status_updated -- verify RESEARCH_COMPLETED."""

    @pytest.mark.asyncio
    async def test_finding_status_updated(self, uow_factory, actor):
        vault, lint_svc, finding = await _setup_vault_and_finding(
            uow_factory,
            actor,
            category=FindingCategory.UNSUPPORTED_CLAIM,
        )

        augmentor = NoOpAugmentor()
        job = FindingResearchJob(
            uow_factory=uow_factory,
            augmentor=augmentor,
            lint_service=lint_svc,
            default_actor=actor,
        )

        await job.execute(
            finding_id=finding.finding_id,
            vault_id=vault.vault_id,
        )

        # Re-read the finding to check remediation status
        uow = uow_factory()
        async with uow:
            updated = await uow.findings.get(finding.finding_id)
            await uow.rollback()

        assert updated is not None
        assert updated.remediation_status == RemediationStatus.RESEARCH_COMPLETED


class TestInsufficientEvidenceOutcome:
    """test_insufficient_evidence_outcome -- augmentor returns empty."""

    @pytest.mark.asyncio
    async def test_insufficient_evidence_outcome(self, uow_factory, actor):
        vault, lint_svc, finding = await _setup_vault_and_finding(
            uow_factory,
            actor,
            category=FindingCategory.CONTRADICTORY_CLAIM,
        )

        # NoOpAugmentor returns insufficient_evidence for contradictions
        augmentor = NoOpAugmentor()
        job = FindingResearchJob(
            uow_factory=uow_factory,
            augmentor=augmentor,
            lint_service=lint_svc,
            default_actor=actor,
        )

        packet = await job.execute(
            finding_id=finding.finding_id,
            vault_id=vault.vault_id,
        )

        assert packet.outcome == ResearchOutcome.INSUFFICIENT_EVIDENCE

        # Verify the packet was persisted
        uow = uow_factory()
        async with uow:
            persisted = await uow.research_packets.get(packet.packet_id)
            await uow.rollback()

        assert persisted is not None
        assert persisted.outcome == ResearchOutcome.INSUFFICIENT_EVIDENCE
