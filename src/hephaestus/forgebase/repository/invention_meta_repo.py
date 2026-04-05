"""InventionPageMeta repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import InventionEpistemicState
from hephaestus.forgebase.domain.models import InventionPageMeta
from hephaestus.forgebase.domain.values import EntityId


class InventionPageMetaRepository(ABC):
    @abstractmethod
    async def create(self, meta: InventionPageMeta) -> None: ...

    @abstractmethod
    async def get(self, page_id: EntityId) -> InventionPageMeta | None: ...

    @abstractmethod
    async def update_state(self, page_id: EntityId, state: InventionEpistemicState) -> None: ...

    @abstractmethod
    async def update_pantheon(
        self,
        page_id: EntityId,
        verdict: str,
        outcome_tier: str,
        consensus: bool,
        objection_count_open: int,
        objection_count_resolved: int,
    ) -> None: ...

    @abstractmethod
    async def list_by_vault(
        self,
        vault_id: EntityId,
        state: InventionEpistemicState | None = None,
    ) -> list[InventionPageMeta]: ...

    @abstractmethod
    async def list_by_state(
        self,
        vault_id: EntityId,
        state: InventionEpistemicState,
    ) -> list[InventionPageMeta]: ...
