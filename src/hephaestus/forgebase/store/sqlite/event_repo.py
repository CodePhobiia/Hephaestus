"""SQLite event persistence for the transactional outbox."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import DomainEvent, EventDelivery
from hephaestus.forgebase.domain.values import EntityId, Version


class SqliteEventRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def insert_event(self, event: DomainEvent) -> None:
        await self._db.execute(
            "INSERT INTO fb_domain_events (event_id, event_type, schema_version, aggregate_type, aggregate_id, aggregate_version, vault_id, workbook_id, run_id, causation_id, correlation_id, actor_type, actor_id, occurred_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(event.event_id), event.event_type, event.schema_version,
                event.aggregate_type, str(event.aggregate_id),
                event.aggregate_version.number if event.aggregate_version else None,
                str(event.vault_id),
                str(event.workbook_id) if event.workbook_id else None,
                event.run_id,
                str(event.causation_id) if event.causation_id else None,
                event.correlation_id,
                event.actor_type.value, event.actor_id,
                event.occurred_at.isoformat(),
                json.dumps(event.payload),
            ),
        )

    async def insert_delivery(self, event_id: EntityId, consumer_name: str) -> None:
        await self._db.execute(
            "INSERT INTO fb_event_deliveries (event_id, consumer_name, status) VALUES (?, ?, 'pending')",
            (str(event_id), consumer_name),
        )

    async def flush_events(self, events: list[DomainEvent], consumer_names: list[str]) -> None:
        """Persist all buffered events + create delivery rows for each consumer."""
        for event in events:
            await self.insert_event(event)
            for consumer in consumer_names:
                await self.insert_delivery(event.event_id, consumer)
