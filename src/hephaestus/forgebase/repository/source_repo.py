"""Source repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Source, SourceVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class SourceRepository(ABC):
    @abstractmethod
    async def create(self, source: Source, version: SourceVersion) -> None: ...

    @abstractmethod
    async def get(self, source_id: EntityId) -> Source | None: ...

    @abstractmethod
    async def get_version(self, source_id: EntityId, version: Version) -> SourceVersion | None: ...

    @abstractmethod
    async def get_head_version(self, source_id: EntityId) -> SourceVersion | None: ...

    @abstractmethod
    async def create_version(self, version: SourceVersion) -> None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[Source]: ...
