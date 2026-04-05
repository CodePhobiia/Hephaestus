"""SQLite implementation of RepairBatchRepository."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.models import RepairBatch
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.repair_batch_repo import RepairBatchRepository


class SqliteRepairBatchRepository(RepairBatchRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, batch: RepairBatch) -> None:
        finding_ids_json = json.dumps([str(fid) for fid in batch.finding_ids])
        await self._db.execute(
            """INSERT INTO fb_repair_batches
            (batch_id, vault_id, batch_fingerprint, batch_strategy, batch_reason,
             finding_ids, policy_version, workbook_id, created_by_job_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(batch.batch_id),
                str(batch.vault_id),
                batch.batch_fingerprint,
                batch.batch_strategy,
                batch.batch_reason,
                finding_ids_json,
                batch.policy_version,
                str(batch.workbook_id) if batch.workbook_id else None,
                str(batch.created_by_job_id),
                batch.created_at.isoformat(),
            ),
        )

    async def get(self, batch_id: EntityId) -> RepairBatch | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_repair_batches WHERE batch_id = ?",
            (str(batch_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_batch(row)

    async def list_by_vault(self, vault_id: EntityId) -> list[RepairBatch]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_repair_batches WHERE vault_id = ?",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_batch(r) for r in rows]

    async def find_by_fingerprint(
        self,
        vault_id: EntityId,
        fingerprint: str,
    ) -> RepairBatch | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_repair_batches WHERE vault_id = ? AND batch_fingerprint = ?",
            (str(vault_id), fingerprint),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_batch(row)

    async def update_workbook(
        self,
        batch_id: EntityId,
        workbook_id: EntityId,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_repair_batches SET workbook_id = ? WHERE batch_id = ?",
            (str(workbook_id), str(batch_id)),
        )

    @staticmethod
    def _row_to_batch(row: aiosqlite.Row) -> RepairBatch:
        finding_ids_raw = json.loads(row["finding_ids"])
        return RepairBatch(
            batch_id=EntityId(row["batch_id"]),
            vault_id=EntityId(row["vault_id"]),
            batch_fingerprint=row["batch_fingerprint"],
            batch_strategy=row["batch_strategy"],
            batch_reason=row["batch_reason"],
            finding_ids=[EntityId(fid) for fid in finding_ids_raw],
            policy_version=row["policy_version"],
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            created_by_job_id=EntityId(row["created_by_job_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
