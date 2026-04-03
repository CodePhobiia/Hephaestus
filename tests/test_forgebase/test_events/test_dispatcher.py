"""Tests for EventDispatcher — the outbox polling delivery engine."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.events.consumers import ConsumerRegistry, EventConsumer
from hephaestus.forgebase.events.dispatcher import EventDispatcher
from hephaestus.forgebase.store.sqlite.schema import initialize_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_id: str = "evt_00000000000000000000000001",
    event_type: str = "source.ingested",
    vault_id: str = "vault_00000000000000000000000001",
) -> DomainEvent:
    return DomainEvent(
        event_id=EntityId(event_id),
        event_type=event_type,
        schema_version=1,
        aggregate_type="source",
        aggregate_id=EntityId("source_00000000000000000000000001"),
        aggregate_version=Version(1),
        vault_id=EntityId(vault_id),
        workbook_id=None,
        run_id=None,
        causation_id=None,
        correlation_id=None,
        actor_type=ActorType.SYSTEM,
        actor_id="test",
        occurred_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
        payload={"key": "value"},
    )


async def _insert_event_row(db: aiosqlite.Connection, event: DomainEvent) -> None:
    """Insert a DomainEvent directly into fb_domain_events."""
    await db.execute(
        """INSERT INTO fb_domain_events
           (event_id, event_type, schema_version, aggregate_type, aggregate_id,
            aggregate_version, vault_id, workbook_id, run_id, causation_id,
            correlation_id, actor_type, actor_id, occurred_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(event.event_id),
            event.event_type,
            event.schema_version,
            event.aggregate_type,
            str(event.aggregate_id),
            event.aggregate_version.number if event.aggregate_version else None,
            str(event.vault_id),
            str(event.workbook_id) if event.workbook_id else None,
            event.run_id,
            str(event.causation_id) if event.causation_id else None,
            event.correlation_id,
            event.actor_type.value,
            event.actor_id,
            event.occurred_at.isoformat(),
            json.dumps(event.payload),
        ),
    )


async def _insert_delivery_row(
    db: aiosqlite.Connection,
    event_id: str,
    consumer_name: str,
    *,
    status: str = "pending",
    attempt_count: int = 0,
    next_attempt_at: str | None = None,
    last_error: str | None = None,
) -> None:
    """Insert a delivery row directly into fb_event_deliveries."""
    await db.execute(
        """INSERT INTO fb_event_deliveries
           (event_id, consumer_name, status, attempt_count, next_attempt_at, last_error)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event_id, consumer_name, status, attempt_count, next_attempt_at, last_error),
    )


async def _get_delivery(
    db: aiosqlite.Connection, event_id: str, consumer_name: str
) -> aiosqlite.Row:
    cursor = await db.execute(
        "SELECT * FROM fb_event_deliveries WHERE event_id = ? AND consumer_name = ?",
        (event_id, consumer_name),
    )
    row = await cursor.fetchone()
    assert row is not None, f"Delivery row not found: {event_id}/{consumer_name}"
    return row


class RecordingConsumer(EventConsumer):
    """Consumer that records received events."""

    def __init__(self, consumer_name: str) -> None:
        self._name = consumer_name
        self.received: list[DomainEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def handle(self, event: DomainEvent) -> None:
        self.received.append(event)


class FailingConsumer(EventConsumer):
    """Consumer that always raises."""

    def __init__(self, consumer_name: str, error_msg: str = "boom") -> None:
        self._name = consumer_name
        self._error_msg = error_msg

    @property
    def name(self) -> str:
        return self._name

    async def handle(self, event: DomainEvent) -> None:
        raise RuntimeError(self._error_msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    db_path = tmp_path / "dispatcher_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventDispatcher:
    @pytest.mark.asyncio
    async def test_poll_delivers_pending_events(self, sqlite_db: aiosqlite.Connection) -> None:
        """A pending delivery is dispatched to its consumer and marked delivered."""
        event = _make_event()
        await _insert_event_row(sqlite_db, event)
        await _insert_delivery_row(sqlite_db, str(event.event_id), "indexer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        consumer = RecordingConsumer("indexer")
        registry.register(consumer)

        dispatcher = EventDispatcher(sqlite_db, registry)
        count = await dispatcher.poll_once()

        assert count == 1
        assert len(consumer.received) == 1
        assert str(consumer.received[0].event_id) == str(event.event_id)

        row = await _get_delivery(sqlite_db, str(event.event_id), "indexer")
        assert row["status"] == "delivered"
        assert row["delivered_at"] is not None

    @pytest.mark.asyncio
    async def test_poll_no_pending_returns_zero(self, sqlite_db: aiosqlite.Connection) -> None:
        """When there are no pending deliveries, poll_once returns 0."""
        registry = ConsumerRegistry()
        registry.register(RecordingConsumer("indexer"))

        dispatcher = EventDispatcher(sqlite_db, registry)
        count = await dispatcher.poll_once()

        assert count == 0

    @pytest.mark.asyncio
    async def test_consumer_failure_increments_attempt(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """When a consumer raises, attempt_count is incremented and next_attempt_at is set."""
        event = _make_event()
        await _insert_event_row(sqlite_db, event)
        await _insert_delivery_row(sqlite_db, str(event.event_id), "indexer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        registry.register(FailingConsumer("indexer", "connection refused"))

        dispatcher = EventDispatcher(sqlite_db, registry, max_attempts=5)
        count = await dispatcher.poll_once()

        assert count == 0  # Nothing delivered

        row = await _get_delivery(sqlite_db, str(event.event_id), "indexer")
        assert row["status"] == "pending"
        assert row["attempt_count"] == 1
        assert row["last_error"] == "connection refused"
        assert row["next_attempt_at"] is not None

    @pytest.mark.asyncio
    async def test_dead_letter_after_max_attempts(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """When attempt_count reaches max_attempts, status becomes dead_letter."""
        event = _make_event()
        await _insert_event_row(sqlite_db, event)
        # Pre-set attempt_count to max_attempts - 1, so the next failure tips it over
        await _insert_delivery_row(
            sqlite_db, str(event.event_id), "indexer", attempt_count=4
        )
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        registry.register(FailingConsumer("indexer", "persistent failure"))

        dispatcher = EventDispatcher(sqlite_db, registry, max_attempts=5)
        count = await dispatcher.poll_once()

        assert count == 0

        row = await _get_delivery(sqlite_db, str(event.event_id), "indexer")
        assert row["status"] == "dead_letter"
        assert row["last_error"] == "persistent failure"

    @pytest.mark.asyncio
    async def test_respects_next_attempt_at(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """Events with a future next_attempt_at are NOT delivered yet."""
        event = _make_event()
        await _insert_event_row(sqlite_db, event)

        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        await _insert_delivery_row(
            sqlite_db,
            str(event.event_id),
            "indexer",
            next_attempt_at=future_time,
        )
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        consumer = RecordingConsumer("indexer")
        registry.register(consumer)

        dispatcher = EventDispatcher(sqlite_db, registry)
        count = await dispatcher.poll_once()

        assert count == 0
        assert len(consumer.received) == 0

        # The delivery should still be pending
        row = await _get_delivery(sqlite_db, str(event.event_id), "indexer")
        assert row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_delivers_multiple_events_in_batch(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """Multiple pending deliveries are processed in a single poll."""
        e1 = _make_event("evt_00000000000000000000000001")
        e2 = _make_event("evt_00000000000000000000000002")
        await _insert_event_row(sqlite_db, e1)
        await _insert_event_row(sqlite_db, e2)
        await _insert_delivery_row(sqlite_db, str(e1.event_id), "indexer")
        await _insert_delivery_row(sqlite_db, str(e2.event_id), "indexer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        consumer = RecordingConsumer("indexer")
        registry.register(consumer)

        dispatcher = EventDispatcher(sqlite_db, registry)
        count = await dispatcher.poll_once()

        assert count == 2
        assert len(consumer.received) == 2

    @pytest.mark.asyncio
    async def test_batch_size_limit(self, sqlite_db: aiosqlite.Connection) -> None:
        """Only batch_size deliveries are processed per poll."""
        events = []
        for i in range(1, 6):
            e = _make_event(f"evt_{i:026d}")
            events.append(e)
            await _insert_event_row(sqlite_db, e)
            await _insert_delivery_row(sqlite_db, str(e.event_id), "indexer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        consumer = RecordingConsumer("indexer")
        registry.register(consumer)

        dispatcher = EventDispatcher(sqlite_db, registry, batch_size=3)
        count = await dispatcher.poll_once()

        assert count == 3
        assert len(consumer.received) == 3

    @pytest.mark.asyncio
    async def test_unregistered_consumer_skipped(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """Deliveries for unregistered consumers are skipped (not counted as delivered)."""
        event = _make_event()
        await _insert_event_row(sqlite_db, event)
        await _insert_delivery_row(sqlite_db, str(event.event_id), "unknown_consumer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        dispatcher = EventDispatcher(sqlite_db, registry)
        count = await dispatcher.poll_once()

        assert count == 0

        # Delivery should still be pending
        row = await _get_delivery(sqlite_db, str(event.event_id), "unknown_consumer")
        assert row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_event_reconstruction_fidelity(
        self, sqlite_db: aiosqlite.Connection
    ) -> None:
        """The DomainEvent reconstructed from the DB matches the original."""
        original = _make_event()
        await _insert_event_row(sqlite_db, original)
        await _insert_delivery_row(sqlite_db, str(original.event_id), "indexer")
        await sqlite_db.commit()

        registry = ConsumerRegistry()
        consumer = RecordingConsumer("indexer")
        registry.register(consumer)

        dispatcher = EventDispatcher(sqlite_db, registry)
        await dispatcher.poll_once()

        assert len(consumer.received) == 1
        reconstructed = consumer.received[0]

        assert str(reconstructed.event_id) == str(original.event_id)
        assert reconstructed.event_type == original.event_type
        assert reconstructed.schema_version == original.schema_version
        assert reconstructed.aggregate_type == original.aggregate_type
        assert str(reconstructed.aggregate_id) == str(original.aggregate_id)
        assert reconstructed.aggregate_version == original.aggregate_version
        assert str(reconstructed.vault_id) == str(original.vault_id)
        assert reconstructed.actor_type == original.actor_type
        assert reconstructed.actor_id == original.actor_id
        assert reconstructed.payload == original.payload
