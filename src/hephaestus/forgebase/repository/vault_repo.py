"""Vault repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId


class VaultRepository(ABC):
    @abstractmethod
    async def create(self, vault: Vault, revision: VaultRevision) -> None: ...

    @abstractmethod
    async def get(self, vault_id: EntityId) -> Vault | None: ...

    @abstractmethod
    async def list_all(self) -> list[Vault]: ...

    @abstractmethod
    async def update_head(self, vault_id: EntityId, revision_id: VaultRevisionId) -> None: ...

    @abstractmethod
    async def update_config(self, vault_id: EntityId, config: dict) -> None: ...

    @abstractmethod
    async def get_revision(self, revision_id: VaultRevisionId) -> VaultRevision | None: ...

    @abstractmethod
    async def create_revision(self, revision: VaultRevision) -> None: ...

    @abstractmethod
    async def get_canonical_page_head(self, vault_id: EntityId, page_id: EntityId) -> int | None:
        """Return current canonical version number for a page, or None."""

    @abstractmethod
    async def set_canonical_page_head(
        self, vault_id: EntityId, page_id: EntityId, version: int
    ) -> None: ...

    @abstractmethod
    async def get_canonical_claim_head(
        self, vault_id: EntityId, claim_id: EntityId
    ) -> int | None: ...

    @abstractmethod
    async def set_canonical_claim_head(
        self, vault_id: EntityId, claim_id: EntityId, version: int
    ) -> None: ...

    @abstractmethod
    async def get_canonical_link_head(
        self, vault_id: EntityId, link_id: EntityId
    ) -> int | None: ...

    @abstractmethod
    async def set_canonical_link_head(
        self, vault_id: EntityId, link_id: EntityId, version: int
    ) -> None: ...

    @abstractmethod
    async def get_canonical_source_head(
        self, vault_id: EntityId, source_id: EntityId
    ) -> int | None: ...

    @abstractmethod
    async def set_canonical_source_head(
        self, vault_id: EntityId, source_id: EntityId, version: int
    ) -> None: ...
