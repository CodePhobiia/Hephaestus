"""Tests for LintService remediation lifecycle extensions."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    RemediationRoute,
    RemediationStatus,
    RouteSource,
)
from hephaestus.forgebase.service.exceptions import EntityNotFoundError
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.vault_service import VaultService


class TestLintServiceRemediation:
    """Tests for the new remediation lifecycle methods on LintService."""

    @staticmethod
    async def _create_vault(uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="lint-ext-vault")

    @staticmethod
    async def _open_finding(svc, vault_id, uow_factory):
        """Helper: schedule lint job + open a finding, return the finding."""
        job = await svc.schedule_lint(
            vault_id=vault_id,
            idempotency_key="lint-ext-test",
        )
        finding = await svc.open_finding(
            job_id=job.job_id,
            vault_id=vault_id,
            category=FindingCategory.STALE_EVIDENCE,
            severity=FindingSeverity.WARNING,
            description="Evidence is stale",
        )
        return finding

    @pytest.mark.asyncio
    async def test_update_finding_remediation_status_only(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        updated = await svc.update_finding_remediation(
            finding.finding_id,
            RemediationStatus.TRIAGED,
        )
        assert updated.remediation_status == RemediationStatus.TRIAGED

    @pytest.mark.asyncio
    async def test_update_finding_remediation_with_route(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        updated = await svc.update_finding_remediation(
            finding.finding_id,
            RemediationStatus.TRIAGED,
            route=RemediationRoute.RESEARCH_THEN_REPAIR,
            route_source=RouteSource.POLICY,
        )
        assert updated.remediation_status == RemediationStatus.TRIAGED
        assert updated.remediation_route == RemediationRoute.RESEARCH_THEN_REPAIR
        assert updated.route_source == RouteSource.POLICY

    @pytest.mark.asyncio
    async def test_update_finding_remediation_not_found(self, uow_factory, actor, id_gen):
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        with pytest.raises(EntityNotFoundError, match="LintFinding not found"):
            await svc.update_finding_remediation(
                id_gen.finding_id(),
                RemediationStatus.TRIAGED,
            )

    @pytest.mark.asyncio
    async def test_update_finding_disposition(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        updated = await svc.update_finding_disposition(
            finding.finding_id,
            FindingDisposition.FALSE_POSITIVE,
        )
        assert updated.disposition == FindingDisposition.FALSE_POSITIVE

    @pytest.mark.asyncio
    async def test_update_finding_disposition_not_found(self, uow_factory, actor, id_gen):
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        with pytest.raises(EntityNotFoundError, match="LintFinding not found"):
            await svc.update_finding_disposition(
                id_gen.finding_id(),
                FindingDisposition.RESOLVED,
            )

    @pytest.mark.asyncio
    async def test_set_finding_research_job(self, uow_factory, actor, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        research_job_id = id_gen.job_id()
        updated = await svc.set_finding_research_job(
            finding.finding_id,
            research_job_id,
        )
        assert updated.research_job_id == research_job_id

    @pytest.mark.asyncio
    async def test_set_finding_repair_workbook(self, uow_factory, actor, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        wb_id = id_gen.workbook_id()
        batch_id = id_gen.batch_id()
        updated = await svc.set_finding_repair_workbook(
            finding.finding_id,
            wb_id,
            batch_id,
        )
        assert updated.repair_workbook_id == wb_id
        assert updated.repair_batch_id == batch_id

    @pytest.mark.asyncio
    async def test_set_finding_verification_job(self, uow_factory, actor, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        ver_job_id = id_gen.job_id()
        updated = await svc.set_finding_verification_job(
            finding.finding_id,
            ver_job_id,
        )
        assert updated.verification_job_id == ver_job_id

    @pytest.mark.asyncio
    async def test_reopen_finding(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        finding = await self._open_finding(svc, vault.vault_id, uow_factory)

        # First resolve it
        await svc.update_finding_disposition(
            finding.finding_id,
            FindingDisposition.RESOLVED,
        )
        await svc.update_finding_remediation(
            finding.finding_id,
            RemediationStatus.VERIFIED,
        )

        # Now reopen it
        reopened = await svc.reopen_finding(finding.finding_id)
        assert reopened.disposition == FindingDisposition.ACTIVE
        assert reopened.remediation_status == RemediationStatus.OPEN

    @pytest.mark.asyncio
    async def test_reopen_finding_not_found(self, uow_factory, actor, id_gen):
        svc = LintService(uow_factory=uow_factory, default_actor=actor)
        with pytest.raises(EntityNotFoundError, match="LintFinding not found"):
            await svc.reopen_finding(id_gen.finding_id())
