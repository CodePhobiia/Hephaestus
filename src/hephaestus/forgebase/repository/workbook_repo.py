"""Workbook (branch) repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import EntityKind, WorkbookStatus
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead,
    BranchClaimHead,
    BranchClaimSupportHead,
    BranchLinkHead,
    BranchPageHead,
    BranchSourceHead,
    BranchTombstone,
    Workbook,
)
from hephaestus.forgebase.domain.values import EntityId


class WorkbookRepository(ABC):
    @abstractmethod
    async def create(self, workbook: Workbook) -> None: ...

    @abstractmethod
    async def get(self, workbook_id: EntityId) -> Workbook | None: ...

    @abstractmethod
    async def list_by_vault(
        self, vault_id: EntityId, *, status: WorkbookStatus | None = None
    ) -> list[Workbook]: ...

    @abstractmethod
    async def update_status(self, workbook_id: EntityId, status: WorkbookStatus) -> None: ...

    # Branch page heads
    @abstractmethod
    async def set_page_head(self, head: BranchPageHead) -> None: ...

    @abstractmethod
    async def get_page_head(
        self, workbook_id: EntityId, page_id: EntityId
    ) -> BranchPageHead | None: ...

    @abstractmethod
    async def list_page_heads(self, workbook_id: EntityId) -> list[BranchPageHead]: ...

    # Branch claim heads
    @abstractmethod
    async def set_claim_head(self, head: BranchClaimHead) -> None: ...

    @abstractmethod
    async def get_claim_head(
        self, workbook_id: EntityId, claim_id: EntityId
    ) -> BranchClaimHead | None: ...

    @abstractmethod
    async def list_claim_heads(self, workbook_id: EntityId) -> list[BranchClaimHead]: ...

    # Branch link heads
    @abstractmethod
    async def set_link_head(self, head: BranchLinkHead) -> None: ...

    @abstractmethod
    async def get_link_head(
        self, workbook_id: EntityId, link_id: EntityId
    ) -> BranchLinkHead | None: ...

    @abstractmethod
    async def list_link_heads(self, workbook_id: EntityId) -> list[BranchLinkHead]: ...

    # Branch source heads
    @abstractmethod
    async def set_source_head(self, head: BranchSourceHead) -> None: ...

    @abstractmethod
    async def get_source_head(
        self, workbook_id: EntityId, source_id: EntityId
    ) -> BranchSourceHead | None: ...

    @abstractmethod
    async def list_source_heads(self, workbook_id: EntityId) -> list[BranchSourceHead]: ...

    # Claim support / derivation heads
    @abstractmethod
    async def set_claim_support_head(self, head: BranchClaimSupportHead) -> None: ...

    @abstractmethod
    async def list_claim_support_heads(
        self, workbook_id: EntityId
    ) -> list[BranchClaimSupportHead]: ...

    @abstractmethod
    async def set_claim_derivation_head(self, head: BranchClaimDerivationHead) -> None: ...

    @abstractmethod
    async def list_claim_derivation_heads(
        self, workbook_id: EntityId
    ) -> list[BranchClaimDerivationHead]: ...

    # Tombstones
    @abstractmethod
    async def add_tombstone(self, tombstone: BranchTombstone) -> None: ...

    @abstractmethod
    async def get_tombstone(
        self, workbook_id: EntityId, entity_kind: EntityKind, entity_id: EntityId
    ) -> BranchTombstone | None: ...

    @abstractmethod
    async def list_tombstones(self, workbook_id: EntityId) -> list[BranchTombstone]: ...
