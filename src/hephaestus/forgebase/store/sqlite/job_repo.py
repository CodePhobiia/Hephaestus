"""SQLite implementation of JobRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType, JobKind, JobStatus
from hephaestus.forgebase.domain.models import Job
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.job_repo import JobRepository


class SqliteJobRepository(JobRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, job: Job) -> None:
        await self._db.execute(
            "INSERT INTO fb_jobs (job_id, vault_id, workbook_id, kind, status, config, idempotency_key, priority, attempt_count, max_attempts, next_attempt_at, leased_until, heartbeat_at, started_at, completed_at, error, created_by_type, created_by_id, created_by_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(job.job_id),
                str(job.vault_id),
                str(job.workbook_id) if job.workbook_id else None,
                job.kind.value,
                job.status.value,
                json.dumps(job.config),
                job.idempotency_key,
                job.priority,
                job.attempt_count,
                job.max_attempts,
                job.next_attempt_at.isoformat() if job.next_attempt_at else None,
                job.leased_until.isoformat() if job.leased_until else None,
                job.heartbeat_at.isoformat() if job.heartbeat_at else None,
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.error,
                job.created_by.actor_type.value,
                job.created_by.actor_id,
                str(job.created_by_run) if job.created_by_run else None,
            ),
        )

    async def get(self, job_id: EntityId) -> Job | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_jobs WHERE job_id = ?",
            (str(job_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    async def find_by_idempotency_key(self, key: str) -> Job | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_jobs WHERE idempotency_key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    async def update_status(
        self,
        job_id: EntityId,
        status: JobStatus,
        *,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_jobs SET status = ?, error = ?, completed_at = ? WHERE job_id = ?",
            (
                status.value,
                error,
                completed_at.isoformat() if completed_at else None,
                str(job_id),
            ),
        )

    async def increment_attempt(
        self,
        job_id: EntityId,
        next_attempt_at: datetime | None = None,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_jobs SET attempt_count = attempt_count + 1, next_attempt_at = ? WHERE job_id = ?",
            (
                next_attempt_at.isoformat() if next_attempt_at else None,
                str(job_id),
            ),
        )

    @staticmethod
    def _row_to_job(row: aiosqlite.Row) -> Job:
        return Job(
            job_id=EntityId(row["job_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            kind=JobKind(row["kind"]),
            status=JobStatus(row["status"]),
            config=json.loads(row["config"]),
            idempotency_key=row["idempotency_key"],
            priority=row["priority"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            next_attempt_at=datetime.fromisoformat(row["next_attempt_at"]) if row["next_attempt_at"] else None,
            leased_until=datetime.fromisoformat(row["leased_until"]) if row["leased_until"] else None,
            heartbeat_at=datetime.fromisoformat(row["heartbeat_at"]) if row["heartbeat_at"] else None,
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error=row["error"],
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
            created_by_run=EntityId(row["created_by_run"]) if row["created_by_run"] else None,
        )
