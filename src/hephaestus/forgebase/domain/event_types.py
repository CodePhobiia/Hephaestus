"""Domain event schemas, taxonomy, EventFactory, and Clock."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version

# Complete event taxonomy — every valid event_type
EVENT_TAXONOMY: frozenset[str] = frozenset({
    # Source lifecycle
    "source.ingested",
    "source.normalization_requested",
    "source.normalized",
    "source.ingest_failed",
    # Compilation lifecycle
    "compile.requested",
    "page.version_created",
    "page.deleted",
    "claim.version_created",
    "link.version_created",
    "link.deleted",
    "compile.completed",
    "compile.failed",
    # Provenance lifecycle
    "claim.support_added",
    "claim.support_removed",
    "claim.status_changed",
    "claim.invalidated",
    "claim.freshness_changed",
    "claim.derivation_added",
    # Workbook lifecycle
    "workbook.created",
    "workbook.updated",
    "merge.proposed",
    "merge.conflict_detected",
    "workbook.merged",
    "workbook.abandoned",
    # Lint lifecycle
    "lint.requested",
    "lint.finding_opened",
    "lint.finding_resolved",
    "lint.completed",
    # Run / integration lifecycle
    "artifact.attached",
    "research.output_committed",
    "invention.output_committed",
    "pantheon.verdict_recorded",
    # Vault lifecycle
    "vault.created",
    "vault.config_updated",
})


class Clock(ABC):
    """Injectable time provider."""

    @abstractmethod
    def now(self) -> datetime: ...


class WallClock(Clock):
    """Production clock — real UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class FixedClock(Clock):
    """Test clock — returns a fixed or manually advanced time."""

    _time: datetime

    def now(self) -> datetime:
        return self._time

    def tick(self, seconds: float = 1.0) -> None:
        self._time = self._time + timedelta(seconds=seconds)

    def set(self, t: datetime) -> None:
        self._time = t


class EventFactory:
    """Centralized event construction with consistent metadata."""

    def __init__(
        self,
        clock: Clock,
        id_generator: object,  # IdGenerator — imported at usage to avoid circular
        default_schema_version: int = 1,
    ) -> None:
        self._clock = clock
        self._id_gen = id_generator
        self._default_schema_version = default_schema_version

    def create(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: EntityId,
        vault_id: EntityId,
        payload: dict,
        actor: ActorRef,
        aggregate_version: Version | None = None,
        workbook_id: EntityId | None = None,
        run_id: str | None = None,
        causation_id: EntityId | None = None,
        correlation_id: str | None = None,
        schema_version: int | None = None,
    ) -> DomainEvent:
        if event_type not in EVENT_TAXONOMY:
            raise ValueError(f"Unknown event type: {event_type!r}")

        return DomainEvent(
            event_id=self._id_gen.event_id(),  # type: ignore[attr-defined]
            event_type=event_type,
            schema_version=schema_version or self._default_schema_version,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            vault_id=vault_id,
            workbook_id=workbook_id,
            run_id=run_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            occurred_at=self._clock.now(),
            payload=payload,
        )
