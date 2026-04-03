"""Claim derivation repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import ClaimDerivation
from hephaestus.forgebase.domain.values import EntityId


class ClaimDerivationRepository(ABC):
    @abstractmethod
    async def create(self, derivation: ClaimDerivation) -> None: ...

    @abstractmethod
    async def get(self, derivation_id: EntityId) -> ClaimDerivation | None: ...

    @abstractmethod
    async def delete(self, derivation_id: EntityId) -> None: ...

    @abstractmethod
    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimDerivation]: ...
