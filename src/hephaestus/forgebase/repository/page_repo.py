"""Page repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Page, PageVersion
from hephaestus.forgebase.domain.values import EntityId, Version


class PageRepository(ABC):
    @abstractmethod
    async def create(self, page: Page, version: PageVersion) -> None: ...

    @abstractmethod
    async def get(self, page_id: EntityId) -> Page | None: ...

    @abstractmethod
    async def get_version(self, page_id: EntityId, version: Version) -> PageVersion | None: ...

    @abstractmethod
    async def get_head_version(self, page_id: EntityId) -> PageVersion | None:
        """Get the latest version for this page (canonical context)."""

    @abstractmethod
    async def create_version(self, version: PageVersion) -> None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId, *, page_type: str | None = None) -> list[Page]: ...

    @abstractmethod
    async def find_by_key(self, vault_id: EntityId, page_key: str) -> Page | None: ...
