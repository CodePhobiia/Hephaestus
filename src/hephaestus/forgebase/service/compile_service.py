"""CompileService — schedule, complete, and fail compilation jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hephaestus.forgebase.domain.enums import JobKind, JobStatus
from hephaestus.forgebase.domain.models import Job
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import EntityNotFoundError


class CompileService:
    """Command service for compilation job lifecycle."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def schedule_compile(
        self,
        vault_id: EntityId,
        *,
        workbook_id: EntityId | None = None,
        config: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> Job:
        """Schedule a compilation job. Idempotent: returns existing job if key matches."""
        uow = self._uow_factory()
        async with uow:
            # Idempotency check
            existing = await uow.jobs.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                await uow.rollback()
                return existing

            now = uow.clock.now()
            job_id = uow.id_generator.job_id()

            job = Job(
                job_id=job_id,
                vault_id=vault_id,
                workbook_id=workbook_id,
                kind=JobKind.COMPILE,
                status=JobStatus.PENDING,
                config=config or {},
                idempotency_key=idempotency_key,
                priority=0,
                attempt_count=0,
                max_attempts=3,
                next_attempt_at=now,
                leased_until=None,
                heartbeat_at=None,
                started_at=None,
                completed_at=None,
                error=None,
                created_by=self._default_actor,
            )

            await uow.jobs.create(job)

            uow.record_event(
                uow.event_factory.create(
                    event_type="compile.requested",
                    aggregate_type="job",
                    aggregate_id=job_id,
                    vault_id=vault_id,
                    payload={
                        "idempotency_key": idempotency_key,
                        "config": config or {},
                    },
                    actor=self._default_actor,
                    workbook_id=workbook_id,
                )
            )

            await uow.commit()

        return job

    async def complete_compile(
        self,
        job_id: EntityId,
        *,
        result: dict[str, Any] | None = None,
    ) -> Job:
        """Mark a compilation job as completed."""
        uow = self._uow_factory()
        async with uow:
            job = await uow.jobs.get(job_id)
            if job is None:
                raise EntityNotFoundError("Job", str(job_id))

            now = uow.clock.now()
            await uow.jobs.update_status(job_id, JobStatus.COMPLETED, completed_at=now)

            uow.record_event(
                uow.event_factory.create(
                    event_type="compile.completed",
                    aggregate_type="job",
                    aggregate_id=job_id,
                    vault_id=job.vault_id,
                    payload={"result": result or {}},
                    actor=self._default_actor,
                    workbook_id=job.workbook_id,
                )
            )

            await uow.commit()

        job.status = JobStatus.COMPLETED
        job.completed_at = now
        return job

    async def fail_compile(
        self,
        job_id: EntityId,
        error: str,
    ) -> Job:
        """Mark a compilation job as failed."""
        uow = self._uow_factory()
        async with uow:
            job = await uow.jobs.get(job_id)
            if job is None:
                raise EntityNotFoundError("Job", str(job_id))

            now = uow.clock.now()
            await uow.jobs.update_status(job_id, JobStatus.FAILED, error=error, completed_at=now)

            uow.record_event(
                uow.event_factory.create(
                    event_type="compile.failed",
                    aggregate_type="job",
                    aggregate_id=job_id,
                    vault_id=job.vault_id,
                    payload={"error": error},
                    actor=self._default_actor,
                    workbook_id=job.workbook_id,
                )
            )

            await uow.commit()

        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = now
        return job
