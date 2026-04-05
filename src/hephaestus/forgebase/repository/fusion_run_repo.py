"""Fusion run repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import FusionRun
from hephaestus.forgebase.domain.values import EntityId


class FusionRunRepository(ABC):
    @abstractmethod
    async def create(self, run: FusionRun) -> None: ...

    @abstractmethod
    async def get(self, fusion_run_id: EntityId) -> FusionRun | None: ...

    @abstractmethod
    async def list_by_vaults(self, vault_ids: list[EntityId]) -> list[FusionRun]: ...

    @abstractmethod
    async def update_status(
        self,
        fusion_run_id: EntityId,
        status: str,
        bridge_count: int | None = None,
        transfer_count: int | None = None,
        manifest_id: EntityId | None = None,
        completed_at: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def list_by_problem(self, problem: str) -> list[FusionRun]: ...
