"""Link repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Link, LinkVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class LinkRepository(ABC):
    @abstractmethod
    async def create(self, link: Link, version: LinkVersion) -> None: ...

    @abstractmethod
    async def get(self, link_id: EntityId) -> Link | None: ...

    @abstractmethod
    async def get_version(self, link_id: EntityId, version: Version) -> LinkVersion | None: ...

    @abstractmethod
    async def get_head_version(self, link_id: EntityId) -> LinkVersion | None: ...

    @abstractmethod
    async def create_version(self, version: LinkVersion) -> None: ...

    @abstractmethod
    async def list_by_entity(
        self, entity_id: EntityId, *, direction: str = "both", kind: str | None = None
    ) -> list[Link]: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[Link]: ...
