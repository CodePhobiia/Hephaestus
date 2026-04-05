"""Tests for FindingVerificationJob — post-merge detector-specific verification."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    LinkKind,
    PageType,
    RemediationStatus,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.broken_reference import (
    BrokenReferenceDetector,
)
from hephaestus.forgebase.linting.remediation.verification_job import (
    FindingVerificationJob,
)
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
    return await svc.create_vault(name="verify-test-vault")


def _make_verification_job(uow_factory, actor, detectors):
    lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
    return FindingVerificationJob(
        uow_factory=uow_factory,
        detectors=detectors,
        lint_service=lint_svc,
        default_actor=actor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolvedFindingGetsResolvedDisposition:
    """test_resolved_finding_gets_resolved_disposition -- fix the issue, verify resolved."""

    @pytest.mark.asyncio
    async def test_resolved_finding_gets_resolved_disposition(
        self,
        uow_factory,
        actor,
        id_gen,
    ):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
        link_svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        # Create two pages so we have a valid link target
        page_a, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-a",
            page_type=PageType.CONCEPT,
            title="Page A",
            content=b"# Page A",
        )
        page_b, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-b",
            page_type=PageType.CONCEPT,
            title="Page B",
            content=b"# Page B",
        )

        # Create a link from A to B (valid, not broken)
        link, _ = await link_svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        # Create a BROKEN_REFERENCE finding that references this link.
        # BUT the link is actually valid now (target exists), so
        # verification should mark it RESOLVED.
        job = await lint_svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="verify-resolved-test",
        )

        uow = uow_factory()
        async with uow:
            finding_id = uow.id_generator.finding_id()
            finding = LintFinding(
                finding_id=finding_id,
                job_id=job.job_id,
                vault_id=vault.vault_id,
                category=FindingCategory.BROKEN_REFERENCE,
                severity=FindingSeverity.WARNING,
                page_id=None,
                claim_id=None,
                description="Link was broken",
                suggested_action=None,
                status=FindingStatus.OPEN,
                affected_entity_ids=[link.link_id],
            )
            await uow.findings.create(finding)
            await uow.commit()

        # Set up detectors
        detectors = {
            FindingCategory.BROKEN_REFERENCE.value: BrokenReferenceDetector(),
        }

        verification_job = _make_verification_job(uow_factory, actor, detectors)
        results = await verification_job.execute(
            finding_ids=[finding_id],
            vault_id=vault.vault_id,
        )

        assert results[finding_id] is True

        # Verify disposition was set to RESOLVED
        uow2 = uow_factory()
        async with uow2:
            updated = await uow2.findings.get(finding_id)
            await uow2.rollback()

        assert updated is not None
        assert updated.disposition == FindingDisposition.RESOLVED
        assert updated.remediation_status == RemediationStatus.VERIFIED


class TestUnresolvedFindingGetsReopened:
    """test_unresolved_finding_gets_reopened -- don't fix the issue, verify reopened."""

    @pytest.mark.asyncio
    async def test_unresolved_finding_gets_reopened(
        self,
        uow_factory,
        actor,
        id_gen,
    ):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
        link_svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        # Create a page
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="orphan-source",
            page_type=PageType.CONCEPT,
            title="Source Page",
            content=b"# Source",
        )

        # Create a link to a non-existent target (broken reference)
        fake_target = id_gen.page_id()
        link, _ = await link_svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page.page_id,
            target_entity=fake_target,
        )

        # Create a finding for the broken link
        job = await lint_svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="verify-unresolved-test",
        )

        uow = uow_factory()
        async with uow:
            finding_id = uow.id_generator.finding_id()
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

        # Do NOT fix the issue -- the link still points to a non-existent target

        detectors = {
            FindingCategory.BROKEN_REFERENCE.value: BrokenReferenceDetector(),
        }

        verification_job = _make_verification_job(uow_factory, actor, detectors)
        results = await verification_job.execute(
            finding_ids=[finding_id],
            vault_id=vault.vault_id,
        )

        assert results[finding_id] is False

        # Verify finding was reopened
        uow2 = uow_factory()
        async with uow2:
            updated = await uow2.findings.get(finding_id)
            await uow2.rollback()

        assert updated is not None
        assert updated.disposition == FindingDisposition.ACTIVE
        assert updated.remediation_status == RemediationStatus.OPEN


class TestMultipleFindingsMixed:
    """test_multiple_findings_mixed -- some resolved, some not."""

    @pytest.mark.asyncio
    async def test_multiple_findings_mixed(self, uow_factory, actor, id_gen):
        vault = await _create_vault(uow_factory, actor)
        lint_svc = LintService(uow_factory=uow_factory, default_actor=actor)
        link_svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        claim_svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        # Set up: two pages
        page_a, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-mixed-a",
            page_type=PageType.CONCEPT,
            title="Page A",
            content=b"# Page A",
        )
        page_b, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-mixed-b",
            page_type=PageType.CONCEPT,
            title="Page B",
            content=b"# Page B",
        )

        # Finding 1: Broken link to non-existent target (NOT fixed)
        fake_target = id_gen.page_id()
        broken_link, _ = await link_svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=fake_target,
        )

        # Finding 2: Valid link (the target exists) -- should be resolved
        valid_link, _ = await link_svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.PAGE_TO_PAGE,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        job = await lint_svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="verify-mixed-test",
        )

        uow = uow_factory()
        async with uow:
            # Finding 1: broken link (not fixed)
            finding_id_1 = uow.id_generator.finding_id()
            f1 = LintFinding(
                finding_id=finding_id_1,
                job_id=job.job_id,
                vault_id=vault.vault_id,
                category=FindingCategory.BROKEN_REFERENCE,
                severity=FindingSeverity.WARNING,
                page_id=None,
                claim_id=None,
                description="Broken link 1",
                suggested_action=None,
                status=FindingStatus.OPEN,
                affected_entity_ids=[broken_link.link_id],
            )
            await uow.findings.create(f1)

            # Finding 2: link that used to be broken but is now valid
            finding_id_2 = uow.id_generator.finding_id()
            f2 = LintFinding(
                finding_id=finding_id_2,
                job_id=job.job_id,
                vault_id=vault.vault_id,
                category=FindingCategory.BROKEN_REFERENCE,
                severity=FindingSeverity.WARNING,
                page_id=None,
                claim_id=None,
                description="Link was broken but now fixed",
                suggested_action=None,
                status=FindingStatus.OPEN,
                affected_entity_ids=[valid_link.link_id],
            )
            await uow.findings.create(f2)
            await uow.commit()

        detectors = {
            FindingCategory.BROKEN_REFERENCE.value: BrokenReferenceDetector(),
        }

        verification_job = _make_verification_job(uow_factory, actor, detectors)
        results = await verification_job.execute(
            finding_ids=[finding_id_1, finding_id_2],
            vault_id=vault.vault_id,
        )

        # Finding 1: still broken -> not resolved
        assert results[finding_id_1] is False
        # Finding 2: target exists now -> resolved
        assert results[finding_id_2] is True

        # Verify the DB state
        uow2 = uow_factory()
        async with uow2:
            f1_updated = await uow2.findings.get(finding_id_1)
            f2_updated = await uow2.findings.get(finding_id_2)
            await uow2.rollback()

        assert f1_updated.disposition == FindingDisposition.ACTIVE
        assert f1_updated.remediation_status == RemediationStatus.OPEN

        assert f2_updated.disposition == FindingDisposition.RESOLVED
        assert f2_updated.remediation_status == RemediationStatus.VERIFIED
