"""Merge conflict repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import MergeResolution
from hephaestus.forgebase.domain.models import MergeConflict
from hephaestus.forgebase.domain.values import EntityId


class MergeConflictRepository(ABC):
    @abstractmethod
    async def create(self, conflict: MergeConflict) -> None: ...

    @abstractmethod
    async def get(self, conflict_id: EntityId) -> MergeConflict | None: ...

    @abstractmethod
    async def list_by_merge(self, merge_id: EntityId) -> list[MergeConflict]: ...

    @abstractmethod
    async def resolve(self, conflict_id: EntityId, resolution: MergeResolution) -> None: ...
