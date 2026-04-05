"""SQLite implementation of DirtyMarkerRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.domain.models import SynthesisDirtyMarker
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.dirty_marker_repo import DirtyMarkerRepository


class SqliteDirtyMarkerRepository(DirtyMarkerRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, marker: SynthesisDirtyMarker) -> None:
        """Insert or update. Preserves first_dirtied_at, increments times_dirtied."""
        # Read existing to preserve first_dirtied_at
        existing = await self.find_by_target(
            vault_id=marker.vault_id,
            target_kind=marker.target_kind,
            target_key=marker.target_key,
            workbook_id=marker.workbook_id,
        )

        if existing is not None:
            # Update existing: preserve first_dirtied_at, increment times_dirtied
            await self._db.execute(
                """UPDATE fb_synthesis_dirty_markers
                SET last_dirtied_at = ?,
                    times_dirtied = times_dirtied + 1,
                    last_dirtied_by_source = ?,
                    last_dirtied_by_job = ?,
                    consumed_by_job = NULL,
                    consumed_at = NULL
                WHERE marker_id = ?""",
                (
                    marker.last_dirtied_at.isoformat(),
                    str(marker.last_dirtied_by_source),
                    str(marker.last_dirtied_by_job),
                    str(existing.marker_id),
                ),
            )
        else:
            # Insert new
            await self._db.execute(
                """INSERT INTO fb_synthesis_dirty_markers
                (marker_id, vault_id, workbook_id, target_kind, target_key,
                 first_dirtied_at, last_dirtied_at, times_dirtied,
                 last_dirtied_by_source, last_dirtied_by_job,
                 consumed_by_job, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(marker.marker_id),
                    str(marker.vault_id),
                    str(marker.workbook_id) if marker.workbook_id else None,
                    marker.target_kind.value,
                    marker.target_key,
                    marker.first_dirtied_at.isoformat(),
                    marker.last_dirtied_at.isoformat(),
                    marker.times_dirtied,
                    str(marker.last_dirtied_by_source),
                    str(marker.last_dirtied_by_job),
                    str(marker.consumed_by_job) if marker.consumed_by_job else None,
                    marker.consumed_at.isoformat() if marker.consumed_at else None,
                ),
            )

    async def get(self, marker_id: EntityId) -> SynthesisDirtyMarker | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_synthesis_dirty_markers WHERE marker_id = ?",
            (str(marker_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_marker(row)

    async def list_unconsumed(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> list[SynthesisDirtyMarker]:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id = ? AND consumed_by_job IS NULL ORDER BY first_dirtied_at",
                (str(vault_id), str(workbook_id)),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id IS NULL AND consumed_by_job IS NULL ORDER BY first_dirtied_at",
                (str(vault_id),),
            )
        rows = await cursor.fetchall()
        return [self._row_to_marker(r) for r in rows]

    async def count_unconsumed(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> int:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT COUNT(*) as cnt FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id = ? AND consumed_by_job IS NULL",
                (str(vault_id), str(workbook_id)),
            )
        else:
            cursor = await self._db.execute(
                "SELECT COUNT(*) as cnt FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id IS NULL AND consumed_by_job IS NULL",
                (str(vault_id),),
            )
        row = await cursor.fetchone()
        return row["cnt"]

    async def find_by_target(
        self,
        vault_id: EntityId,
        target_kind: DirtyTargetKind,
        target_key: str,
        workbook_id: EntityId | None = None,
    ) -> SynthesisDirtyMarker | None:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id = ? AND target_kind = ? AND target_key = ?",
                (str(vault_id), str(workbook_id), target_kind.value, target_key),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_synthesis_dirty_markers WHERE vault_id = ? AND workbook_id IS NULL AND target_kind = ? AND target_key = ?",
                (str(vault_id), target_kind.value, target_key),
            )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_marker(row)

    async def consume(
        self,
        marker_id: EntityId,
        consumed_by_job: EntityId,
    ) -> None:
        now = datetime.now().isoformat()
        await self._db.execute(
            "UPDATE fb_synthesis_dirty_markers SET consumed_by_job = ?, consumed_at = ? WHERE marker_id = ?",
            (str(consumed_by_job), now, str(marker_id)),
        )

    @staticmethod
    def _row_to_marker(row: aiosqlite.Row) -> SynthesisDirtyMarker:
        return SynthesisDirtyMarker(
            marker_id=EntityId(row["marker_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            target_kind=DirtyTargetKind(row["target_kind"]),
            target_key=row["target_key"],
            first_dirtied_at=datetime.fromisoformat(row["first_dirtied_at"]),
            last_dirtied_at=datetime.fromisoformat(row["last_dirtied_at"]),
            times_dirtied=row["times_dirtied"],
            last_dirtied_by_source=EntityId(row["last_dirtied_by_source"]),
            last_dirtied_by_job=EntityId(row["last_dirtied_by_job"]),
            consumed_by_job=EntityId(row["consumed_by_job"]) if row["consumed_by_job"] else None,
            consumed_at=datetime.fromisoformat(row["consumed_at"]) if row["consumed_at"] else None,
        )
