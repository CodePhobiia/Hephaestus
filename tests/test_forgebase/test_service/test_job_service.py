"""Tests for CompileService and LintService — job lifecycle."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
)
from hephaestus.forgebase.service.compile_service import CompileService
from hephaestus.forgebase.service.exceptions import EntityNotFoundError
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestCompileService:
    async def _create_vault(self, uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="CompileVault")

    async def test_schedule_compile(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-001",
        )

        assert job.kind == JobKind.COMPILE
        assert job.status == JobStatus.PENDING
        assert job.idempotency_key == "compile-001"
        assert job.vault_id == vault.vault_id

    async def test_schedule_compile_idempotent(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        job1 = await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-idem",
        )
        job2 = await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-idem",
        )

        assert job1.job_id == job2.job_id

    async def test_schedule_compile_with_config(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_compile(
            vault_id=vault.vault_id,
            config={"depth": 5},
            idempotency_key="compile-config",
        )

        assert job.config == {"depth": 5}

    async def test_complete_compile(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-complete",
        )

        completed = await svc.complete_compile(job.job_id)
        assert completed.status == JobStatus.COMPLETED
        assert completed.completed_at is not None

    async def test_fail_compile(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-fail",
        )

        failed = await svc.fail_compile(job.job_id, error="Out of memory")
        assert failed.status == JobStatus.FAILED
        assert failed.error == "Out of memory"

    async def test_complete_compile_not_found_raises(self, uow_factory, actor, id_gen):
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)
        with pytest.raises(EntityNotFoundError, match="Job not found"):
            await svc.complete_compile(id_gen.job_id())

    async def test_fail_compile_not_found_raises(self, uow_factory, actor, id_gen):
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)
        with pytest.raises(EntityNotFoundError, match="Job not found"):
            await svc.fail_compile(id_gen.job_id(), error="oops")

    async def test_schedule_compile_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = CompileService(uow_factory=uow_factory, default_actor=actor)

        await svc.schedule_compile(
            vault_id=vault.vault_id,
            idempotency_key="compile-event",
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'compile.requested'"
        )
        row = await cursor.fetchone()
        assert row is not None


@pytest.mark.asyncio
class TestLintService:
    async def _create_vault(self, uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="LintVault")

    async def test_schedule_lint(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-001",
        )

        assert job.kind == JobKind.LINT
        assert job.status == JobStatus.PENDING

    async def test_schedule_lint_idempotent(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        job1 = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-idem",
        )
        job2 = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-idem",
        )

        assert job1.job_id == job2.job_id

    async def test_open_finding(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-finding",
        )

        finding = await svc.open_finding(
            job_id=job.job_id,
            vault_id=vault.vault_id,
            category=FindingCategory.UNSUPPORTED_CLAIM,
            severity=FindingSeverity.WARNING,
            description="Claim lacks evidence",
        )

        assert finding.status == FindingStatus.OPEN
        assert finding.category == FindingCategory.UNSUPPORTED_CLAIM
        assert finding.description == "Claim lacks evidence"

    async def test_resolve_finding(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-resolve",
        )

        finding = await svc.open_finding(
            job_id=job.job_id,
            vault_id=vault.vault_id,
            category=FindingCategory.STALE_EVIDENCE,
            severity=FindingSeverity.INFO,
            description="Page is stale",
        )

        resolved = await svc.resolve_finding(finding.finding_id)
        assert resolved.status == FindingStatus.RESOLVED

    async def test_complete_lint(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        job = await svc.schedule_lint(
            vault_id=vault.vault_id,
            idempotency_key="lint-complete",
        )

        completed = await svc.complete_lint(job.job_id)
        assert completed.status == JobStatus.COMPLETED

    async def test_open_finding_not_found_raises(self, uow_factory, actor, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        with pytest.raises(EntityNotFoundError, match="Job not found"):
            await svc.open_finding(
                job_id=id_gen.job_id(),
                vault_id=vault.vault_id,
                category=FindingCategory.STALE_EVIDENCE,
                severity=FindingSeverity.INFO,
                description="ghost finding",
            )

    async def test_resolve_finding_not_found_raises(self, uow_factory, actor, id_gen):
        svc = LintService(uow_factory=uow_factory, default_actor=actor)

        with pytest.raises(EntityNotFoundError, match="LintFinding not found"):
            await svc.resolve_finding(id_gen.finding_id())
