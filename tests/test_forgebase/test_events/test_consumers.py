"""Tests for ConsumerRegistry and PostCommitFanout."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.events.consumers import ConsumerRegistry, EventConsumer
from hephaestus.forgebase.events.fanout import PostCommitFanout

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str = "source.ingested") -> DomainEvent:
    return DomainEvent(
        event_id=EntityId("evt_00000000000000000000000001"),
        event_type=event_type,
        schema_version=1,
        aggregate_type="source",
        aggregate_id=EntityId("source_00000000000000000000000001"),
        aggregate_version=Version(1),
        vault_id=EntityId("vault_00000000000000000000000001"),
        workbook_id=None,
        run_id=None,
        causation_id=None,
        correlation_id=None,
        actor_type=ActorType.SYSTEM,
        actor_id="test",
        occurred_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
        payload={"key": "value"},
    )


class StubConsumer(EventConsumer):
    def __init__(self, consumer_name: str) -> None:
        self._name = consumer_name
        self.received: list[DomainEvent] = []

    @property
    def name(self) -> str:
        return self._name

    async def handle(self, event: DomainEvent) -> None:
        self.received.append(event)


# ---------------------------------------------------------------------------
# ConsumerRegistry tests
# ---------------------------------------------------------------------------


class TestConsumerRegistry:
    def test_register_and_get(self) -> None:
        registry = ConsumerRegistry()
        consumer = StubConsumer("indexer")
        registry.register(consumer)

        result = registry.get("indexer")
        assert result is consumer

    def test_get_missing_returns_none(self) -> None:
        registry = ConsumerRegistry()
        assert registry.get("nonexistent") is None

    def test_all_names(self) -> None:
        registry = ConsumerRegistry()
        registry.register(StubConsumer("beta"))
        registry.register(StubConsumer("alpha"))
        registry.register(StubConsumer("gamma"))

        assert registry.all_names() == ["alpha", "beta", "gamma"]

    def test_duplicate_registration_raises(self) -> None:
        registry = ConsumerRegistry()
        registry.register(StubConsumer("indexer"))

        with pytest.raises(ValueError, match="already registered"):
            registry.register(StubConsumer("indexer"))


# ---------------------------------------------------------------------------
# PostCommitFanout tests
# ---------------------------------------------------------------------------


class TestPostCommitFanout:
    @pytest.mark.asyncio
    async def test_fanout_notifies_subscribers(self) -> None:
        fanout = PostCommitFanout()
        received: list[DomainEvent] = []

        async def callback(event: DomainEvent) -> None:
            received.append(event)

        fanout.subscribe(callback)

        event = _make_event()
        await fanout.notify([event])

        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_fanout_notifies_multiple_subscribers(self) -> None:
        fanout = PostCommitFanout()
        calls_a: list[DomainEvent] = []
        calls_b: list[DomainEvent] = []

        async def sub_a(event: DomainEvent) -> None:
            calls_a.append(event)

        async def sub_b(event: DomainEvent) -> None:
            calls_b.append(event)

        fanout.subscribe(sub_a)
        fanout.subscribe(sub_b)

        event = _make_event()
        await fanout.notify([event])

        assert len(calls_a) == 1
        assert len(calls_b) == 1

    @pytest.mark.asyncio
    async def test_fanout_swallows_errors(self) -> None:
        fanout = PostCommitFanout()
        healthy_calls: list[DomainEvent] = []

        async def failing_sub(event: DomainEvent) -> None:
            raise RuntimeError("boom")

        async def healthy_sub(event: DomainEvent) -> None:
            healthy_calls.append(event)

        fanout.subscribe(failing_sub)
        fanout.subscribe(healthy_sub)

        event = _make_event()
        # Should not raise even though first subscriber fails
        await fanout.notify([event])

        # The healthy subscriber should still have been called
        assert len(healthy_calls) == 1

    @pytest.mark.asyncio
    async def test_fanout_delivers_multiple_events(self) -> None:
        fanout = PostCommitFanout()
        received: list[DomainEvent] = []

        async def callback(event: DomainEvent) -> None:
            received.append(event)

        fanout.subscribe(callback)

        e1 = _make_event("source.ingested")
        e2 = _make_event("page.version_created")
        await fanout.notify([e1, e2])

        assert len(received) == 2
