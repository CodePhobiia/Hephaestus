"""SQLite implementation of MergeConflictRepository."""
from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import EntityKind, MergeResolution
from hephaestus.forgebase.domain.models import MergeConflict
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.repository.merge_conflict_repo import MergeConflictRepository


class SqliteMergeConflictRepository(MergeConflictRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, conflict: MergeConflict) -> None:
        await self._db.execute(
            "INSERT INTO fb_merge_conflicts (conflict_id, merge_id, entity_kind, entity_id, base_version, branch_version, canonical_version, resolution, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(conflict.conflict_id),
                str(conflict.merge_id),
                conflict.entity_kind.value,
                str(conflict.entity_id),
                conflict.base_version.number,
                conflict.branch_version.number,
                conflict.canonical_version.number,
                conflict.resolution.value if conflict.resolution else None,
                conflict.resolved_at.isoformat() if conflict.resolved_at else None,
            ),
        )

    async def get(self, conflict_id: EntityId) -> MergeConflict | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_merge_conflicts WHERE conflict_id = ?",
            (str(conflict_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_conflict(row)

    async def list_by_merge(self, merge_id: EntityId) -> list[MergeConflict]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_merge_conflicts WHERE merge_id = ?",
            (str(merge_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_conflict(r) for r in rows]

    async def resolve(self, conflict_id: EntityId, resolution: MergeResolution) -> None:
        await self._db.execute(
            "UPDATE fb_merge_conflicts SET resolution = ?, resolved_at = ? WHERE conflict_id = ?",
            (resolution.value, datetime.now(UTC).isoformat(), str(conflict_id)),
        )

    @staticmethod
    def _row_to_conflict(row: aiosqlite.Row) -> MergeConflict:
        return MergeConflict(
            conflict_id=EntityId(row["conflict_id"]),
            merge_id=EntityId(row["merge_id"]),
            entity_kind=EntityKind(row["entity_kind"]),
            entity_id=EntityId(row["entity_id"]),
            base_version=Version(row["base_version"]),
            branch_version=Version(row["branch_version"]),
            canonical_version=Version(row["canonical_version"]),
            resolution=MergeResolution(row["resolution"]) if row["resolution"] else None,
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )
