"""Claim repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Claim, ClaimVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class ClaimRepository(ABC):
    @abstractmethod
    async def create(self, claim: Claim, version: ClaimVersion) -> None: ...

    @abstractmethod
    async def get(self, claim_id: EntityId) -> Claim | None: ...

    @abstractmethod
    async def get_version(self, claim_id: EntityId, version: Version) -> ClaimVersion | None: ...

    @abstractmethod
    async def get_head_version(self, claim_id: EntityId) -> ClaimVersion | None: ...

    @abstractmethod
    async def create_version(self, version: ClaimVersion) -> None: ...

    @abstractmethod
    async def list_by_page(self, page_id: EntityId) -> list[Claim]: ...
