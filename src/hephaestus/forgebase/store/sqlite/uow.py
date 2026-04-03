"""SQLite UnitOfWork implementation."""
from __future__ import annotations

import aiosqlite

from hephaestus.forgebase.domain.event_types import Clock, EventFactory
from hephaestus.forgebase.repository.content_store import StagedContentStore
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.forgebase.store.sqlite.event_repo import SqliteEventRepository
from hephaestus.forgebase.store.sqlite.vault_repo import SqliteVaultRepository


class SqliteUnitOfWork(AbstractUnitOfWork):
    """SQLite-backed UoW: single connection, single-writer."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        content: StagedContentStore,
        clock: Clock,
        id_generator: IdGenerator,
        consumer_names: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self.content = content
        self.clock = clock
        self.id_generator = id_generator
        self.event_factory = EventFactory(clock=clock, id_generator=id_generator)
        self._consumer_names = consumer_names or []
        self._event_repo = SqliteEventRepository(db)

        # Wire up repos
        self.vaults = SqliteVaultRepository(db)
        # Remaining repos will be wired in subsequent tasks as they're implemented

    async def begin(self) -> None:
        await self._db.execute("BEGIN")

    async def commit(self) -> None:
        # Flush events to outbox within the same transaction
        if self._event_buffer:
            await self._event_repo.flush_events(self._event_buffer, self._consumer_names)

        await self._db.commit()

        # Finalize content AFTER db commit succeeds
        await self.content.finalize()

        self._event_buffer.clear()

    async def rollback(self) -> None:
        await self._db.rollback()
        await self.content.abort()
        self._event_buffer.clear()
