"""Repair batch repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import RepairBatch
from hephaestus.forgebase.domain.values import EntityId


class RepairBatchRepository(ABC):
    @abstractmethod
    async def create(self, batch: RepairBatch) -> None: ...

    @abstractmethod
    async def get(self, batch_id: EntityId) -> RepairBatch | None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[RepairBatch]: ...

    @abstractmethod
    async def find_by_fingerprint(
        self,
        vault_id: EntityId,
        fingerprint: str,
    ) -> RepairBatch | None: ...

    @abstractmethod
    async def update_workbook(
        self,
        batch_id: EntityId,
        workbook_id: EntityId,
    ) -> None: ...
