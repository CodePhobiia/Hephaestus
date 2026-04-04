"""Dirty marker management for the compiler."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.domain.models import SynthesisDirtyMarker
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.dirty_marker_repo import DirtyMarkerRepository
from hephaestus.forgebase.service.id_generator import IdGenerator


class DirtyTracker:
    """Higher-level dirty tracking for the compiler.

    Tier 1 uses mark_dirty() to flag concepts/families for re-synthesis.
    Tier 2 uses get_dirty_targets() and consume() to process them.
    """

    def __init__(
        self,
        repo: DirtyMarkerRepository,
        id_generator: IdGenerator,
        clock_fn: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._id_gen = id_generator
        self._clock = clock_fn

    async def mark_dirty(
        self,
        vault_id: EntityId,
        target_kind: DirtyTargetKind,
        target_key: str,
        dirtied_by_source: EntityId,
        dirtied_by_job: EntityId,
        workbook_id: EntityId | None = None,
    ) -> SynthesisDirtyMarker:
        """Mark a concept/family as needing re-synthesis. Upsert semantics."""
        now = self._clock()

        # Check if marker already exists (unconsumed)
        existing = await self._repo.find_by_target(
            vault_id, target_kind, target_key, workbook_id
        )

        if existing and existing.consumed_by_job is None:
            # Upsert: preserve first_dirtied_at, update the rest
            marker = SynthesisDirtyMarker(
                marker_id=existing.marker_id,
                vault_id=vault_id,
                workbook_id=workbook_id,
                target_kind=target_kind,
                target_key=target_key,
                first_dirtied_at=existing.first_dirtied_at,
                last_dirtied_at=now,
                times_dirtied=existing.times_dirtied + 1,
                last_dirtied_by_source=dirtied_by_source,
                last_dirtied_by_job=dirtied_by_job,
                consumed_by_job=None,
                consumed_at=None,
            )
        else:
            # New marker (or re-dirtying a consumed one)
            marker = SynthesisDirtyMarker(
                marker_id=self._id_gen.generate("dirty"),
                vault_id=vault_id,
                workbook_id=workbook_id,
                target_kind=target_kind,
                target_key=target_key,
                first_dirtied_at=now,
                last_dirtied_at=now,
                times_dirtied=1,
                last_dirtied_by_source=dirtied_by_source,
                last_dirtied_by_job=dirtied_by_job,
                consumed_by_job=None,
                consumed_at=None,
            )

        await self._repo.upsert(marker)
        return marker

    async def get_dirty_targets(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
        target_kind: DirtyTargetKind | None = None,
    ) -> list[SynthesisDirtyMarker]:
        """Get all unconsumed dirty markers, optionally filtered by kind."""
        markers = await self._repo.list_unconsumed(vault_id, workbook_id)
        if target_kind is not None:
            markers = [m for m in markers if m.target_kind == target_kind]
        return markers

    async def count_dirty(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> int:
        """Count unconsumed dirty markers."""
        return await self._repo.count_unconsumed(vault_id, workbook_id)

    async def consume(
        self,
        marker_id: EntityId,
        consumed_by_job: EntityId,
    ) -> None:
        """Mark a dirty marker as consumed by a synthesis job."""
        await self._repo.consume(marker_id, consumed_by_job)

    async def should_trigger_synthesis(
        self,
        vault_id: EntityId,
        threshold: int = 5,
        workbook_id: EntityId | None = None,
    ) -> bool:
        """Check if enough dirty markers have accumulated to trigger Tier 2."""
        count = await self.count_dirty(vault_id, workbook_id)
        return count >= threshold
