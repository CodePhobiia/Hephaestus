"""Tests for SQLite job and finding repositories."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
)
from hephaestus.forgebase.domain.models import Job, LintFinding
from hephaestus.forgebase.store.sqlite.finding_repo import SqliteFindingRepository
from hephaestus.forgebase.store.sqlite.job_repo import SqliteJobRepository


def _make_job(id_gen, clock, actor, **overrides) -> Job:
    defaults = dict(
        job_id=id_gen.job_id(),
        vault_id=id_gen.vault_id(),
        workbook_id=None,
        kind=JobKind.COMPILE,
        status=JobStatus.PENDING,
        config={"key": "value"},
        idempotency_key="idem-001",
        priority=5,
        attempt_count=0,
        max_attempts=3,
        next_attempt_at=None,
        leased_until=None,
        heartbeat_at=None,
        started_at=None,
        completed_at=None,
        error=None,
        created_by=actor,
        created_by_run=None,
    )
    defaults.update(overrides)
    return Job(**defaults)


@pytest.mark.asyncio
class TestSqliteJobRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor)

        await repo.create(job)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.job_id == job.job_id
        assert got.vault_id == job.vault_id
        assert got.workbook_id is None
        assert got.kind == JobKind.COMPILE
        assert got.status == JobStatus.PENDING
        assert got.config == {"key": "value"}
        assert got.idempotency_key == "idem-001"
        assert got.priority == 5
        assert got.attempt_count == 0
        assert got.max_attempts == 3
        assert got.created_by.actor_type == actor.actor_type
        assert got.created_by.actor_id == actor.actor_id
        assert got.created_by_run is None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteJobRepository(sqlite_db)
        assert await repo.get(id_gen.job_id()) is None

    async def test_create_with_all_fields(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        wb_id = id_gen.workbook_id()
        run_id = id_gen.ref_id()
        now = clock.now()

        job = _make_job(
            id_gen,
            clock,
            actor,
            workbook_id=wb_id,
            idempotency_key="idem-full",
            next_attempt_at=now,
            leased_until=now,
            heartbeat_at=now,
            started_at=now,
            completed_at=now,
            error="some error",
            created_by_run=run_id,
        )
        await repo.create(job)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.workbook_id == wb_id
        assert got.next_attempt_at is not None
        assert got.leased_until is not None
        assert got.heartbeat_at is not None
        assert got.started_at is not None
        assert got.completed_at is not None
        assert got.error == "some error"
        assert got.created_by_run == run_id

    async def test_find_by_idempotency_key(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor, idempotency_key="unique-key-42")

        await repo.create(job)
        await sqlite_db.commit()

        got = await repo.find_by_idempotency_key("unique-key-42")
        assert got is not None
        assert got.job_id == job.job_id

    async def test_find_by_idempotency_key_not_found(self, sqlite_db):
        repo = SqliteJobRepository(sqlite_db)
        assert await repo.find_by_idempotency_key("nonexistent") is None

    async def test_update_status(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor, idempotency_key="status-test")

        await repo.create(job)
        await sqlite_db.commit()

        await repo.update_status(job.job_id, JobStatus.RUNNING)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.status == JobStatus.RUNNING

    async def test_update_status_with_error_and_completed(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor, idempotency_key="fail-test")

        await repo.create(job)
        await sqlite_db.commit()

        completed_at = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)
        await repo.update_status(
            job.job_id,
            JobStatus.FAILED,
            error="out of memory",
            completed_at=completed_at,
        )
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.status == JobStatus.FAILED
        assert got.error == "out of memory"
        assert got.completed_at == completed_at

    async def test_increment_attempt(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor, idempotency_key="attempt-test")

        await repo.create(job)
        await sqlite_db.commit()

        await repo.increment_attempt(job.job_id)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.attempt_count == 1

        await repo.increment_attempt(job.job_id)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.attempt_count == 2

    async def test_increment_attempt_with_next_attempt_at(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteJobRepository(sqlite_db)
        job = _make_job(id_gen, clock, actor, idempotency_key="retry-test")

        await repo.create(job)
        await sqlite_db.commit()

        next_at = datetime(2026, 4, 3, 13, 0, 0, tzinfo=UTC)
        await repo.increment_attempt(job.job_id, next_attempt_at=next_at)
        await sqlite_db.commit()

        got = await repo.get(job.job_id)
        assert got is not None
        assert got.attempt_count == 1
        assert got.next_attempt_at == next_at


@pytest.mark.asyncio
class TestSqliteFindingRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        finding_id = id_gen.finding_id()
        job_id = id_gen.job_id()
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()

        finding = LintFinding(
            finding_id=finding_id,
            job_id=job_id,
            vault_id=vault_id,
            category=FindingCategory.DUPLICATE_PAGE,
            severity=FindingSeverity.WARNING,
            page_id=page_id,
            claim_id=None,
            description="Duplicate page found",
            suggested_action="Merge pages",
            status=FindingStatus.OPEN,
            resolved_at=None,
        )

        await repo.create(finding)
        await sqlite_db.commit()

        got = await repo.get(finding_id)
        assert got is not None
        assert got.finding_id == finding_id
        assert got.job_id == job_id
        assert got.vault_id == vault_id
        assert got.category == FindingCategory.DUPLICATE_PAGE
        assert got.severity == FindingSeverity.WARNING
        assert got.page_id == page_id
        assert got.claim_id is None
        assert got.description == "Duplicate page found"
        assert got.suggested_action == "Merge pages"
        assert got.status == FindingStatus.OPEN
        assert got.resolved_at is None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        assert await repo.get(id_gen.finding_id()) is None

    async def test_list_by_job(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        job_id = id_gen.job_id()
        other_job = id_gen.job_id()
        vault_id = id_gen.vault_id()

        f1 = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=job_id,
            vault_id=vault_id,
            category=FindingCategory.DUPLICATE_PAGE,
            severity=FindingSeverity.WARNING,
            page_id=None,
            claim_id=None,
            description="dup",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        f2 = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=job_id,
            vault_id=vault_id,
            category=FindingCategory.WEAK_BACKLINK,
            severity=FindingSeverity.INFO,
            page_id=None,
            claim_id=None,
            description="weak",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        f3 = LintFinding(
            finding_id=id_gen.finding_id(),
            job_id=other_job,
            vault_id=vault_id,
            category=FindingCategory.STALE_PAGE,
            severity=FindingSeverity.CRITICAL,
            page_id=None,
            claim_id=None,
            description="stale",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )

        await repo.create(f1)
        await repo.create(f2)
        await repo.create(f3)
        await sqlite_db.commit()

        results = await repo.list_by_job(job_id)
        assert len(results) == 2
        ids = {r.finding_id for r in results}
        assert f1.finding_id in ids
        assert f2.finding_id in ids

    async def test_list_by_job_empty(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        results = await repo.list_by_job(id_gen.job_id())
        assert results == []

    async def test_update_status_to_resolved(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        finding_id = id_gen.finding_id()

        finding = LintFinding(
            finding_id=finding_id,
            job_id=id_gen.job_id(),
            vault_id=id_gen.vault_id(),
            category=FindingCategory.UNSUPPORTED_CLAIM,
            severity=FindingSeverity.CRITICAL,
            page_id=None,
            claim_id=id_gen.claim_id(),
            description="unsupported",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        await repo.create(finding)
        await sqlite_db.commit()

        await repo.update_status(finding_id, FindingStatus.RESOLVED)
        await sqlite_db.commit()

        got = await repo.get(finding_id)
        assert got is not None
        assert got.status == FindingStatus.RESOLVED
        assert got.resolved_at is not None

    async def test_update_status_to_waived(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        finding_id = id_gen.finding_id()

        finding = LintFinding(
            finding_id=finding_id,
            job_id=id_gen.job_id(),
            vault_id=id_gen.vault_id(),
            category=FindingCategory.ORPHANED_PAGE,
            severity=FindingSeverity.INFO,
            page_id=None,
            claim_id=None,
            description="orphan",
            suggested_action=None,
            status=FindingStatus.OPEN,
        )
        await repo.create(finding)
        await sqlite_db.commit()

        await repo.update_status(finding_id, FindingStatus.WAIVED)
        await sqlite_db.commit()

        got = await repo.get(finding_id)
        assert got is not None
        assert got.status == FindingStatus.WAIVED
        # WAIVED is not a resolution — resolved_at should stay None
        # Actually, WAIVED could mean resolved. Let's just check it's not None
        # since the spec says "if resolving". The implementation should set
        # resolved_at for any status that isn't OPEN.
        assert got.resolved_at is not None

    async def test_create_with_both_page_and_claim(self, sqlite_db, id_gen):
        repo = SqliteFindingRepository(sqlite_db)
        finding_id = id_gen.finding_id()
        page_id = id_gen.page_id()
        claim_id = id_gen.claim_id()

        finding = LintFinding(
            finding_id=finding_id,
            job_id=id_gen.job_id(),
            vault_id=id_gen.vault_id(),
            category=FindingCategory.CONTRADICTORY_CLAIM,
            severity=FindingSeverity.CRITICAL,
            page_id=page_id,
            claim_id=claim_id,
            description="contradiction",
            suggested_action="Review claim",
            status=FindingStatus.OPEN,
        )
        await repo.create(finding)
        await sqlite_db.commit()

        got = await repo.get(finding_id)
        assert got is not None
        assert got.page_id == page_id
        assert got.claim_id == claim_id
