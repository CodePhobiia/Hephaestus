"""SQLite implementation of FusionRunRepository."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import FusionMode
from hephaestus.forgebase.domain.models import FusionRun
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.fusion_run_repo import FusionRunRepository


class SqliteFusionRunRepository(FusionRunRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, run: FusionRun) -> None:
        await self._db.execute(
            """INSERT INTO fb_fusion_runs
            (fusion_run_id, vault_ids, problem, fusion_mode, status,
             bridge_count, transfer_count, manifest_id, policy_version,
             created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(run.fusion_run_id),
                json.dumps([str(v) for v in run.vault_ids]),
                run.problem,
                run.fusion_mode.value,
                run.status,
                run.bridge_count,
                run.transfer_count,
                str(run.manifest_id) if run.manifest_id else None,
                run.policy_version,
                run.created_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
            ),
        )

    async def get(self, fusion_run_id: EntityId) -> FusionRun | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_fusion_runs WHERE fusion_run_id = ?",
            (str(fusion_run_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    async def list_by_vaults(self, vault_ids: list[EntityId]) -> list[FusionRun]:
        # Match fusion runs that contain exactly these vault IDs (as JSON array)
        vault_ids_json = json.dumps(sorted(str(v) for v in vault_ids))
        cursor = await self._db.execute(
            "SELECT * FROM fb_fusion_runs ORDER BY created_at DESC",
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            stored_ids = sorted(json.loads(row["vault_ids"]))
            if json.dumps(stored_ids) == vault_ids_json:
                results.append(self._row_to_run(row))
        return results

    async def update_status(
        self,
        fusion_run_id: EntityId,
        status: str,
        bridge_count: int | None = None,
        transfer_count: int | None = None,
        manifest_id: EntityId | None = None,
        completed_at: str | None = None,
    ) -> None:
        updates = ["status = ?"]
        params: list[object] = [status]

        if bridge_count is not None:
            updates.append("bridge_count = ?")
            params.append(bridge_count)
        if transfer_count is not None:
            updates.append("transfer_count = ?")
            params.append(transfer_count)
        if manifest_id is not None:
            updates.append("manifest_id = ?")
            params.append(str(manifest_id))
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        params.append(str(fusion_run_id))
        sql = f"UPDATE fb_fusion_runs SET {', '.join(updates)} WHERE fusion_run_id = ?"
        await self._db.execute(sql, tuple(params))

    async def list_by_problem(self, problem: str) -> list[FusionRun]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_fusion_runs WHERE problem = ? ORDER BY created_at DESC",
            (problem,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_run(r) for r in rows]

    @staticmethod
    def _row_to_run(row: aiosqlite.Row) -> FusionRun:
        vault_ids_raw = json.loads(row["vault_ids"])
        return FusionRun(
            fusion_run_id=EntityId(row["fusion_run_id"]),
            vault_ids=[EntityId(v) for v in vault_ids_raw],
            problem=row["problem"],
            fusion_mode=FusionMode(row["fusion_mode"]),
            status=row["status"],
            bridge_count=row["bridge_count"],
            transfer_count=row["transfer_count"],
            manifest_id=EntityId(row["manifest_id"]) if row["manifest_id"] else None,
            policy_version=row["policy_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
        )
