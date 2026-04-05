"""Knowledge run reference repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import KnowledgeRunRef
from hephaestus.forgebase.domain.values import EntityId


class KnowledgeRunRefRepository(ABC):
    @abstractmethod
    async def create(self, ref: KnowledgeRunRef) -> None: ...

    @abstractmethod
    async def get(self, ref_id: EntityId) -> KnowledgeRunRef | None: ...

    @abstractmethod
    async def update_sync_status(
        self, ref_id: EntityId, sync_status: str, *, sync_error: str | None = None
    ) -> None: ...
