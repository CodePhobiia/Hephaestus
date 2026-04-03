"""Claim support repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import ClaimSupport
from hephaestus.forgebase.domain.values import EntityId


class ClaimSupportRepository(ABC):
    @abstractmethod
    async def create(self, support: ClaimSupport) -> None: ...

    @abstractmethod
    async def get(self, support_id: EntityId) -> ClaimSupport | None: ...

    @abstractmethod
    async def delete(self, support_id: EntityId) -> None: ...

    @abstractmethod
    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimSupport]: ...
