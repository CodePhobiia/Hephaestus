"""Tests for domain event types, EventFactory, Clock, and IdGenerator."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.event_types import (
    EVENT_TAXONOMY,
    Clock,
    EventFactory,
    FixedClock,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.service.id_generator import IdGenerator, DeterministicIdGenerator


class TestEventTaxonomy:
    def test_source_events_exist(self):
        assert "source.ingested" in EVENT_TAXONOMY
        assert "source.normalized" in EVENT_TAXONOMY

    def test_page_events_exist(self):
        assert "page.version_created" in EVENT_TAXONOMY

    def test_claim_events_exist(self):
        assert "claim.support_added" in EVENT_TAXONOMY
        assert "claim.invalidated" in EVENT_TAXONOMY

    def test_workbook_events_exist(self):
        assert "workbook.created" in EVENT_TAXONOMY
        assert "workbook.merged" in EVENT_TAXONOMY

    def test_lint_events_exist(self):
        assert "lint.finding_opened" in EVENT_TAXONOMY

    def test_integration_events_exist(self):
        assert "artifact.attached" in EVENT_TAXONOMY
        assert "invention.output_committed" in EVENT_TAXONOMY


class TestFixedClock:
    def test_returns_fixed_time(self):
        t = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(t)
        assert clock.now() == t
        assert clock.now() == t

    def test_tick_advances(self):
        t = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(t)
        clock.tick()
        assert clock.now() > t


class TestDeterministicIdGenerator:
    def test_produces_valid_entity_ids(self):
        gen = DeterministicIdGenerator()
        eid = gen.generate("vault")
        assert eid.prefix == "vault"

    def test_sequential_ids_are_unique(self):
        gen = DeterministicIdGenerator()
        a = gen.generate("page")
        b = gen.generate("page")
        assert a != b

    def test_shortcut_methods(self):
        gen = DeterministicIdGenerator()
        assert gen.vault_id().prefix == "vault"
        assert gen.page_id().prefix == "page"
        assert gen.source_id().prefix == "source"
        assert gen.claim_id().prefix == "claim"
        assert gen.event_id().prefix == "evt"
        assert gen.revision_id().prefix == "rev"


class TestEventFactory:
    def test_creates_event_with_consistent_fields(self):
        t = datetime(2026, 4, 3, tzinfo=UTC)
        clock = FixedClock(t)
        gen = DeterministicIdGenerator()
        factory = EventFactory(clock=clock, id_generator=gen, default_schema_version=1)

        vault_id = gen.vault_id()
        source_id = gen.source_id()
        actor = ActorRef.system()

        event = factory.create(
            event_type="source.ingested",
            aggregate_type="source",
            aggregate_id=source_id,
            vault_id=vault_id,
            payload={"source_id": str(source_id)},
            actor=actor,
            aggregate_version=Version(1),
        )

        assert event.event_type == "source.ingested"
        assert event.occurred_at == t
        assert event.schema_version == 1
        assert event.aggregate_id == source_id
        assert event.vault_id == vault_id
        assert event.actor_type == ActorType.SYSTEM
        assert event.event_id.prefix == "evt"

    def test_rejects_unknown_event_type(self):
        clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
        gen = DeterministicIdGenerator()
        factory = EventFactory(clock=clock, id_generator=gen, default_schema_version=1)

        with pytest.raises(ValueError, match="Unknown event type"):
            factory.create(
                event_type="bogus.event",
                aggregate_type="x",
                aggregate_id=gen.vault_id(),
                vault_id=gen.vault_id(),
                payload={},
                actor=ActorRef.system(),
            )
