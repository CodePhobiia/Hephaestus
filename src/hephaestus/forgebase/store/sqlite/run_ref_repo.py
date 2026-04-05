"""SQLite implementation of KnowledgeRunRefRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.models import KnowledgeRunRef
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.run_ref_repo import KnowledgeRunRefRepository


class SqliteRunRefRepository(KnowledgeRunRefRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, ref: KnowledgeRunRef) -> None:
        await self._db.execute(
            "INSERT INTO fb_run_refs (ref_id, vault_id, run_id, run_type, upstream_system, upstream_ref, source_hash, sync_status, sync_error, synced_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(ref.ref_id),
                str(ref.vault_id),
                ref.run_id,
                ref.run_type,
                ref.upstream_system,
                ref.upstream_ref,
                ref.source_hash,
                ref.sync_status,
                ref.sync_error,
                ref.synced_at.isoformat() if ref.synced_at else None,
                ref.created_at.isoformat(),
            ),
        )

    async def get(self, ref_id: EntityId) -> KnowledgeRunRef | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_run_refs WHERE ref_id = ?",
            (str(ref_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_ref(row)

    async def update_sync_status(
        self,
        ref_id: EntityId,
        sync_status: str,
        *,
        sync_error: str | None = None,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_run_refs SET sync_status = ?, sync_error = ? WHERE ref_id = ?",
            (sync_status, sync_error, str(ref_id)),
        )

    @staticmethod
    def _row_to_ref(row: aiosqlite.Row) -> KnowledgeRunRef:
        return KnowledgeRunRef(
            ref_id=EntityId(row["ref_id"]),
            vault_id=EntityId(row["vault_id"]),
            run_id=row["run_id"],
            run_type=row["run_type"],
            upstream_system=row["upstream_system"],
            upstream_ref=row["upstream_ref"],
            source_hash=row["source_hash"],
            sync_status=row["sync_status"],
            sync_error=row["sync_error"],
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
