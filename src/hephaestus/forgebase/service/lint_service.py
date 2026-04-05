"""LintService — schedule lint, manage findings, complete/fail."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    RemediationRoute,
    RemediationStatus,
    RouteSource,
)
from hephaestus.forgebase.domain.models import Job, LintFinding
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import EntityNotFoundError


class LintService:
    """Command service for lint job lifecycle and findings management."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def schedule_lint(
        self,
        vault_id: EntityId,
        *,
        workbook_id: EntityId | None = None,
        config: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> Job:
        """Schedule a lint job. Idempotent: returns existing job if key matches."""
        uow = self._uow_factory()
        async with uow:
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
                kind=JobKind.LINT,
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
                    event_type="lint.requested",
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

    async def open_finding(
        self,
        job_id: EntityId,
        vault_id: EntityId,
        category: FindingCategory,
        severity: FindingSeverity,
        description: str,
        *,
        page_id: EntityId | None = None,
        claim_id: EntityId | None = None,
        suggested_action: str | None = None,
        finding_fingerprint: str | None = None,
        detector_version: str | None = None,
        confidence: float = 1.0,
        affected_entity_ids: list[EntityId] | None = None,
    ) -> LintFinding:
        """Open a new lint finding."""
        uow = self._uow_factory()
        async with uow:
            job = await uow.jobs.get(job_id)
            if job is None:
                raise EntityNotFoundError("Job", str(job_id))

            finding_id = uow.id_generator.finding_id()

            finding = LintFinding(
                finding_id=finding_id,
                job_id=job_id,
                vault_id=vault_id,
                category=category,
                severity=severity,
                page_id=page_id,
                claim_id=claim_id,
                description=description,
                suggested_action=suggested_action,
                status=FindingStatus.OPEN,
                finding_fingerprint=finding_fingerprint,
                detector_version=detector_version,
                confidence=confidence,
                affected_entity_ids=affected_entity_ids or [],
            )

            await uow.findings.create(finding)

            uow.record_event(
                uow.event_factory.create(
                    event_type="lint.finding_opened",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=vault_id,
                    payload={
                        "job_id": str(job_id),
                        "category": category.value,
                        "severity": severity.value,
                        "description": description,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return finding

    async def resolve_finding(
        self,
        finding_id: EntityId,
    ) -> LintFinding:
        """Resolve a lint finding."""
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.update_status(finding_id, FindingStatus.RESOLVED)

            uow.record_event(
                uow.event_factory.create(
                    event_type="lint.finding_resolved",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.status = FindingStatus.RESOLVED
        return finding

    async def complete_lint(
        self,
        job_id: EntityId,
    ) -> Job:
        """Mark a lint job as completed."""
        uow = self._uow_factory()
        async with uow:
            job = await uow.jobs.get(job_id)
            if job is None:
                raise EntityNotFoundError("Job", str(job_id))

            now = uow.clock.now()
            await uow.jobs.update_status(job_id, JobStatus.COMPLETED, completed_at=now)

            uow.record_event(
                uow.event_factory.create(
                    event_type="lint.completed",
                    aggregate_type="job",
                    aggregate_id=job_id,
                    vault_id=job.vault_id,
                    payload={},
                    actor=self._default_actor,
                    workbook_id=job.workbook_id,
                )
            )

            await uow.commit()

        job.status = JobStatus.COMPLETED
        job.completed_at = now
        return job

    # ------------------------------------------------------------------
    # Remediation lifecycle methods
    # ------------------------------------------------------------------

    async def update_finding_remediation(
        self,
        finding_id: EntityId,
        remediation_status: RemediationStatus,
        *,
        route: RemediationRoute | None = None,
        route_source: RouteSource | None = None,
    ) -> LintFinding:
        """Update a finding's remediation status, optionally setting route.

        Emits ``finding.triaged`` when status becomes TRIAGED, or
        ``finding.route_assigned`` when a route is provided.
        """
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.update_remediation_status(
                finding_id,
                remediation_status,
                route=route,
                route_source=route_source,
            )

            # Determine event type
            if route is not None:
                event_type = "finding.route_assigned"
            elif remediation_status == RemediationStatus.TRIAGED:
                event_type = "finding.triaged"
            else:
                event_type = "finding.triaged"

            uow.record_event(
                uow.event_factory.create(
                    event_type=event_type,
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={
                        "remediation_status": remediation_status.value,
                        "route": route.value if route else None,
                        "route_source": route_source.value if route_source else None,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.remediation_status = remediation_status
        if route is not None:
            finding.remediation_route = route
        if route_source is not None:
            finding.route_source = route_source
        return finding

    async def update_finding_disposition(
        self,
        finding_id: EntityId,
        disposition: FindingDisposition,
    ) -> LintFinding:
        """Update a finding's disposition and emit the appropriate event."""
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.update_disposition(finding_id, disposition)

            # Map disposition to event type
            event_map = {
                FindingDisposition.RESOLVED: "finding.resolved",
                FindingDisposition.FALSE_POSITIVE: "finding.false_positive",
                FindingDisposition.WONT_FIX: "finding.wont_fix",
                FindingDisposition.ABANDONED: "finding.abandoned",
            }
            event_type = event_map.get(disposition, "finding.triaged")

            uow.record_event(
                uow.event_factory.create(
                    event_type=event_type,
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={"disposition": disposition.value},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.disposition = disposition
        return finding

    async def set_finding_research_job(
        self,
        finding_id: EntityId,
        research_job_id: EntityId,
    ) -> LintFinding:
        """Link a finding to its research job."""
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.set_research_job_id(finding_id, research_job_id)

            uow.record_event(
                uow.event_factory.create(
                    event_type="finding.research_requested",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={"research_job_id": str(research_job_id)},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.research_job_id = research_job_id
        return finding

    async def set_finding_repair_workbook(
        self,
        finding_id: EntityId,
        repair_workbook_id: EntityId,
        repair_batch_id: EntityId,
    ) -> LintFinding:
        """Link a finding to its repair workbook and batch."""
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.set_repair_workbook(
                finding_id,
                repair_workbook_id,
                repair_batch_id,
            )

            uow.record_event(
                uow.event_factory.create(
                    event_type="finding.repair_requested",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={
                        "repair_workbook_id": str(repair_workbook_id),
                        "repair_batch_id": str(repair_batch_id),
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.repair_workbook_id = repair_workbook_id
        finding.repair_batch_id = repair_batch_id
        return finding

    async def set_finding_verification_job(
        self,
        finding_id: EntityId,
        verification_job_id: EntityId,
    ) -> LintFinding:
        """Link a finding to its verification job."""
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.set_verification_job_id(finding_id, verification_job_id)

            uow.record_event(
                uow.event_factory.create(
                    event_type="finding.verification_requested",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={"verification_job_id": str(verification_job_id)},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.verification_job_id = verification_job_id
        return finding

    async def reopen_finding(
        self,
        finding_id: EntityId,
    ) -> LintFinding:
        """Reopen a finding: sets disposition=ACTIVE, remediation_status=OPEN.

        Emits ``finding.reopened``.
        """
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise EntityNotFoundError("LintFinding", str(finding_id))

            await uow.findings.update_disposition(finding_id, FindingDisposition.ACTIVE)
            await uow.findings.update_remediation_status(finding_id, RemediationStatus.OPEN)

            uow.record_event(
                uow.event_factory.create(
                    event_type="finding.reopened",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=finding.vault_id,
                    payload={},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        finding.disposition = FindingDisposition.ACTIVE
        finding.remediation_status = RemediationStatus.OPEN
        return finding
