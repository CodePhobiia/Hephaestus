"""Event dispatcher — polls the outbox and delivers to registered consumers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime, timedelta

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.events.consumers import ConsumerRegistry

logger = logging.getLogger(__name__)

# Retry defaults
DEFAULT_MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 2.0


def _row_to_domain_event(row: aiosqlite.Row) -> DomainEvent:
    """Reconstruct a ``DomainEvent`` from a ``fb_domain_events`` row."""
    return DomainEvent(
        event_id=EntityId(row["event_id"]),
        event_type=row["event_type"],
        schema_version=row["schema_version"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=EntityId(row["aggregate_id"]),
        aggregate_version=(
            Version(row["aggregate_version"]) if row["aggregate_version"] is not None else None
        ),
        vault_id=EntityId(row["vault_id"]),
        workbook_id=(EntityId(row["workbook_id"]) if row["workbook_id"] is not None else None),
        run_id=row["run_id"],
        causation_id=(EntityId(row["causation_id"]) if row["causation_id"] is not None else None),
        correlation_id=row["correlation_id"],
        actor_type=ActorType(row["actor_type"]),
        actor_id=row["actor_id"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        payload=json.loads(row["payload"]),
    )


class EventDispatcher:
    """Polls ``fb_event_deliveries`` for pending work and dispatches to consumers.

    The main entry point is :meth:`poll_once`, which is a single pass over the
    outbox.  :meth:`start` runs ``poll_once`` in a loop until :meth:`stop` is
    called.
    """

    def __init__(
        self,
        db: aiosqlite.Connection,
        consumers: ConsumerRegistry,
        *,
        poll_interval: float = 1.0,
        batch_size: int = 50,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = BACKOFF_BASE_SECONDS,
    ) -> None:
        self._db = db
        self._consumers = consumers
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Graceful shutdown — waits for the current poll to finish."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        """Internal loop — polls at the configured interval."""
        while self._running:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("EventDispatcher poll error")
            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Core poll logic
    # ------------------------------------------------------------------

    async def poll_once(self) -> int:
        """Execute one polling pass.  Returns the number of events delivered."""
        now = datetime.now(UTC).isoformat()

        cursor = await self._db.execute(
            """
            SELECT d.event_id, d.consumer_name, d.attempt_count
            FROM fb_event_deliveries d
            WHERE d.status = 'pending'
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
            ORDER BY d.event_id
            LIMIT ?
            """,
            (now, self._batch_size),
        )
        rows = await cursor.fetchall()

        delivered = 0
        for row in rows:
            event_id_str: str = row["event_id"]
            consumer_name: str = row["consumer_name"]
            attempt_count: int = row["attempt_count"]

            consumer = self._consumers.get(consumer_name)
            if consumer is None:
                logger.warning(
                    "No consumer registered for %r — skipping delivery for event %s",
                    consumer_name,
                    event_id_str,
                )
                continue

            # Load the full event
            event = await self._load_event(event_id_str)
            if event is None:
                logger.error(
                    "Event %s not found in fb_domain_events — marking dead letter",
                    event_id_str,
                )
                await self._mark_dead_letter(event_id_str, consumer_name, "event row missing")
                await self._db.commit()
                continue

            # Attempt delivery
            try:
                await consumer.handle(event)
            except Exception as exc:
                await self._record_failure(event_id_str, consumer_name, attempt_count, str(exc))
                await self._db.commit()
                continue

            # Success
            await self._mark_delivered(event_id_str, consumer_name)
            await self._db.commit()
            delivered += 1

        return delivered

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_event(self, event_id_str: str) -> DomainEvent | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_domain_events WHERE event_id = ?",
            (event_id_str,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_domain_event(row)

    async def _mark_delivered(self, event_id: str, consumer_name: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            UPDATE fb_event_deliveries
            SET status = 'delivered', delivered_at = ?
            WHERE event_id = ? AND consumer_name = ?
            """,
            (now, event_id, consumer_name),
        )

    async def _record_failure(
        self,
        event_id: str,
        consumer_name: str,
        attempt_count: int,
        error_msg: str,
    ) -> None:
        new_attempt = attempt_count + 1
        if new_attempt >= self._max_attempts:
            await self._mark_dead_letter(event_id, consumer_name, error_msg)
            return

        backoff_seconds = self._backoff_base * (2**new_attempt)
        next_attempt = (datetime.now(UTC) + timedelta(seconds=backoff_seconds)).isoformat()

        await self._db.execute(
            """
            UPDATE fb_event_deliveries
            SET attempt_count = ?,
                last_error = ?,
                next_attempt_at = ?
            WHERE event_id = ? AND consumer_name = ?
            """,
            (new_attempt, error_msg, next_attempt, event_id, consumer_name),
        )

    async def _mark_dead_letter(self, event_id: str, consumer_name: str, error_msg: str) -> None:
        await self._db.execute(
            """
            UPDATE fb_event_deliveries
            SET status = 'dead_letter',
                last_error = ?
            WHERE event_id = ? AND consumer_name = ?
            """,
            (error_msg, event_id, consumer_name),
        )
