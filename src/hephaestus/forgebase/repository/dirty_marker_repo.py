"""Repository contract for synthesis dirty markers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.domain.models import SynthesisDirtyMarker
from hephaestus.forgebase.domain.values import EntityId


class DirtyMarkerRepository(ABC):
    @abstractmethod
    async def upsert(self, marker: SynthesisDirtyMarker) -> None:
        """Insert or update. Preserves first_dirtied_at, increments times_dirtied."""

    @abstractmethod
    async def get(self, marker_id: EntityId) -> SynthesisDirtyMarker | None: ...

    @abstractmethod
    async def list_unconsumed(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> list[SynthesisDirtyMarker]: ...

    @abstractmethod
    async def count_unconsumed(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> int: ...

    @abstractmethod
    async def find_by_target(
        self,
        vault_id: EntityId,
        target_kind: DirtyTargetKind,
        target_key: str,
        workbook_id: EntityId | None = None,
    ) -> SynthesisDirtyMarker | None: ...

    @abstractmethod
    async def consume(
        self,
        marker_id: EntityId,
        consumed_by_job: EntityId,
    ) -> None:
        """Mark a dirty marker as consumed by a synthesis job."""
