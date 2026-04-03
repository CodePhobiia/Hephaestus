"""Merge proposal repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import MergeProposal
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId


class MergeProposalRepository(ABC):
    @abstractmethod
    async def create(self, proposal: MergeProposal) -> None: ...

    @abstractmethod
    async def get(self, merge_id: EntityId) -> MergeProposal | None: ...

    @abstractmethod
    async def set_result(self, merge_id: EntityId, resulting_revision: VaultRevisionId) -> None: ...
