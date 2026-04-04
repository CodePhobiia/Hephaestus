"""Tests for RepairWorkbookJob — workbook branch repair for findings."""
from __future__ import annotations

from datetime import datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    ClaimStatus,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    LinkKind,
    PageType,
    RemediationStatus,
    ResearchOutcome,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    RepairBatch,
    ResearchPacket,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.linting.remediation.repair_job import RepairWorkbookJob
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_vault(uow_factory, actor):
    svc = VaultService(uow_factory=uow_factory, default_actor=actor)
    return await svc.create_vault(name="repair-test-vault")


async def _create_finding(lint_svc, vault_id, category, **kwargs):
    """Open a lint finding after scheduling a lint job."""
    job = await lint_svc.schedule_lint(
        vault_id=vault_id,
        idempotency_key=f"repair-lint-{category.value}-{id(kwargs)}",
    )
    return await lint_svc.open_finding(
        job_id=job.job_id,
        vault_id=vault_id,
        category=category,
        severity=kwargs.get("severity", FindingSeverity.WARNING),
        description=kwargs.get("description", "Test finding"),
        suggested_action=kwargs.get("suggested_action", None),
        page_id=kwargs.get("page_id", None),
        claim_id=kwargs.get("claim_id", None),
    )


def _make_batch(vault_id, finding_ids, job_id, id_gen):
    """Create a RepairBatch for testing."""
    return RepairBatch(
        batch_id=id_gen.batch_id(),
        vault_id=vault_id,
        batch_fingerprint="test-fp",
        batch_strategy="test",
        batch_reason="test batch",
        finding_ids=finding_ids,
        policy_version="1.0.0",
        workbook_id=None,
        created_by_job_id=job_id,
        created_at=datetime.now(),
    )


def _make_repair_job(uow_factory, actor):
    """Build a RepairWorkbookJob with all services wired."""
    return RepairWorkbookJob(
        uow_factory=uow_factory,
        branch_service=BranchService(uow_factory=uow_factory, default_actor=actor),
        page_service=PageService(uow_factory=uow_factory, default_actor=actor),
        claim_service=ClaimService(uow_factory=uow_factory, default_actor=actor),
        link_service=LinkService(uow_factory=uow_factory, default_actor=actor),
        lint_service=LintService(uow_factory=uow_factory, default_actor=actor),
        default_actor=actor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreatesWorkbookWithLintRepairPurpose:
    """test_creates_workbook_with_lint_repair_purpose"""

    @pytest.mark.asyncio
    async def test_creates_workbook_with_lint_repair_purpose(
        self, uow_factory, actor, id_gen,
    ):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)

        finding = await _create_finding(
            lint_svc, vault.vault_id, FindingCategory.BROKEN_REFERENCE,
        )
        batch = _make_batch(
            vault.vault_id, [finding.finding_id], finding.job_id, id_gen,
        )

        job = _make_repair_job(uow_factory, actor)
        workbook_id = await job.execute(batch, vault.vault_id)

        # Verify workbook was created with LINT_REPAIR purpose
        uow = uow_factory()
        async with uow:
            wb = await uow.workbooks.get(workbook_id)
            await uow.rollback()

        assert wb is not None
        assert wb.purpose == BranchPurpose.LINT_REPAIR
        assert wb.vault_id == vault.vault_id


class TestRepairsBrokenReference:
    """test_repairs_broken_reference -- removes broken link on branch."""

    @pytest.mark.asyncio
    async def test_repairs_broken_reference(self, uow_factory, actor, id_gen):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
        link_svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        # Create a page so we can create a link from it
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="source-page",
            page_type=PageType.CONCEPT,
            title="Source Page",
            content=b"# Source Page",
        )

        # Create a link to a non-existent target
        from hephaestus.forgebase.domain.enums import LinkKind
        fake_target = id_gen.page_id()
        link, _ = await link_svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.BACKLINK,
            source_entity=page.page_id,
            target_entity=fake_target,
        )

        # Open a BROKEN_REFERENCE finding with affected_entity_ids=[link_id]
        job = await lint_svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="repair-broken-link-test",
        )

        from hephaestus.forgebase.domain.enums import LinkKind

        # We need a finding that has affected_entity_ids set
        uow = uow_factory()
        async with uow:
            finding_id = uow.id_generator.finding_id()
            from hephaestus.forgebase.domain.models import LintFinding
            finding = LintFinding(
                finding_id=finding_id,
                job_id=job.job_id,
                vault_id=vault.vault_id,
                category=FindingCategory.BROKEN_REFERENCE,
                severity=FindingSeverity.WARNING,
                page_id=None,
                claim_id=None,
                description="Broken link",
                suggested_action=None,
                status=FindingStatus.OPEN,
                affected_entity_ids=[link.link_id],
            )
            await uow.findings.create(finding)
            await uow.commit()

        batch = _make_batch(
            vault.vault_id, [finding_id], job.job_id, id_gen,
        )

        repair_job = _make_repair_job(uow_factory, actor)
        workbook_id = await repair_job.execute(batch, vault.vault_id)

        # Verify the link was tombstoned on the branch
        uow2 = uow_factory()
        async with uow2:
            tombstones = await uow2.workbooks.list_tombstones(workbook_id)
            await uow2.rollback()

        link_tombstones = [
            t for t in tombstones
            if t.entity_kind == EntityKind.LINK and t.entity_id == link.link_id
        ]
        assert len(link_tombstones) == 1


class TestRepairsUnsupportedClaim:
    """test_repairs_unsupported_claim -- downgrades to HYPOTHESIS on branch."""

    @pytest.mark.asyncio
    async def test_repairs_unsupported_claim(self, uow_factory, actor, id_gen):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        claim_svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        # Create a page and a SUPPORTED claim on it
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="claim-page",
            page_type=PageType.CONCEPT,
            title="Claim Page",
            content=b"# Claims",
        )

        claim, claim_v = await claim_svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Water boils at 100C",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
        )

        # Open a finding with claim_id set
        job = await lint_svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="repair-unsupported-test",
        )

        uow = uow_factory()
        async with uow:
            finding_id = uow.id_generator.finding_id()
            from hephaestus.forgebase.domain.models import LintFinding
            finding = LintFinding(
                finding_id=finding_id,
                job_id=job.job_id,
                vault_id=vault.vault_id,
                category=FindingCategory.UNSUPPORTED_CLAIM,
                severity=FindingSeverity.WARNING,
                page_id=page.page_id,
                claim_id=claim.claim_id,
                description="Unsupported claim",
                suggested_action=None,
                status=FindingStatus.OPEN,
            )
            await uow.findings.create(finding)
            await uow.commit()

        batch = _make_batch(
            vault.vault_id, [finding_id], job.job_id, id_gen,
        )

        repair_job = _make_repair_job(uow_factory, actor)
        workbook_id = await repair_job.execute(batch, vault.vault_id)

        # Verify the claim was downgraded to HYPOTHESIS on the branch
        uow2 = uow_factory()
        async with uow2:
            # Get the branch head for this claim
            branch_heads = await uow2.workbooks.list_claim_heads(workbook_id)
            await uow2.rollback()

        # There should be a branch claim head for this claim
        matching = [h for h in branch_heads if h.claim_id == claim.claim_id]
        assert len(matching) == 1

        # Read the claim version on the branch
        uow3 = uow_factory()
        async with uow3:
            cv = await uow3.claims.get_version(
                claim.claim_id, matching[0].head_version,
            )
            await uow3.rollback()

        assert cv is not None
        assert cv.status == ClaimStatus.HYPOTHESIS


class TestContradictionUnresolvedCreatesOpenQuestion:
    """test_contradiction_unresolved_creates_open_question -- creates OPEN_QUESTION page."""

    @pytest.mark.asyncio
    async def test_contradiction_unresolved_creates_open_question(
        self, uow_factory, actor, id_gen,
    ):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)

        # Create a CONTRADICTORY_CLAIM finding (no research packet = unresolved)
        finding = await _create_finding(
            lint_svc, vault.vault_id,
            FindingCategory.CONTRADICTORY_CLAIM,
            description="Claim A vs Claim B",
        )

        batch = _make_batch(
            vault.vault_id, [finding.finding_id], finding.job_id, id_gen,
        )

        repair_job = _make_repair_job(uow_factory, actor)
        # No research_packets -> contradiction is unresolved
        workbook_id = await repair_job.execute(batch, vault.vault_id)

        # Verify an OPEN_QUESTION page was created on the branch
        uow = uow_factory()
        async with uow:
            branch_page_heads = await uow.workbooks.list_page_heads(workbook_id)
            await uow.rollback()

        # At least one page head should exist on the branch
        assert len(branch_page_heads) >= 1

        # Read the page(s) created on the branch
        uow2 = uow_factory()
        async with uow2:
            open_question_pages = []
            for bph in branch_page_heads:
                page = await uow2.pages.get(bph.page_id)
                if page is not None and page.page_type == PageType.OPEN_QUESTION:
                    open_question_pages.append(page)
            await uow2.rollback()

        assert len(open_question_pages) == 1
        assert "open-question" in open_question_pages[0].page_key


class TestFindingStatusUpdatedRepair:
    """test_finding_status_updated -- verify REPAIR_WORKBOOK_CREATED."""

    @pytest.mark.asyncio
    async def test_finding_status_updated(self, uow_factory, actor, id_gen):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)

        finding = await _create_finding(
            lint_svc, vault.vault_id, FindingCategory.BROKEN_REFERENCE,
        )

        batch = _make_batch(
            vault.vault_id, [finding.finding_id], finding.job_id, id_gen,
        )

        repair_job = _make_repair_job(uow_factory, actor)
        workbook_id = await repair_job.execute(batch, vault.vault_id)

        # Verify remediation status was updated
        uow = uow_factory()
        async with uow:
            updated = await uow.findings.get(finding.finding_id)
            await uow.rollback()

        assert updated is not None
        assert updated.remediation_status == RemediationStatus.REPAIR_WORKBOOK_CREATED
        assert updated.repair_workbook_id == workbook_id
        assert updated.repair_batch_id == batch.batch_id
