"""SQLite implementation of InventionPageMetaRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import InventionEpistemicState
from hephaestus.forgebase.domain.models import InventionPageMeta
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.invention_meta_repo import (
    InventionPageMetaRepository,
)


class SqliteInventionPageMetaRepository(InventionPageMetaRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, meta: InventionPageMeta) -> None:
        await self._db.execute(
            """INSERT INTO fb_invention_page_meta (
                page_id, vault_id, invention_state, run_id, run_type,
                models_used, novelty_score, fidelity_score, domain_distance,
                source_domain, target_domain, pantheon_verdict,
                pantheon_outcome_tier, pantheon_consensus,
                objection_count_open, objection_count_resolved,
                total_cost_usd, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(meta.page_id),
                str(meta.vault_id),
                meta.invention_state.value,
                meta.run_id,
                meta.run_type,
                json.dumps(meta.models_used),
                meta.novelty_score,
                meta.fidelity_score,
                meta.domain_distance,
                meta.source_domain,
                meta.target_domain,
                meta.pantheon_verdict,
                meta.pantheon_outcome_tier,
                self._bool_to_int(meta.pantheon_consensus),
                meta.objection_count_open,
                meta.objection_count_resolved,
                meta.total_cost_usd,
                meta.created_at.isoformat(),
                meta.updated_at.isoformat(),
            ),
        )

    async def get(self, page_id: EntityId) -> InventionPageMeta | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_invention_page_meta WHERE page_id = ?",
            (str(page_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_meta(row)

    async def update_state(
        self, page_id: EntityId, state: InventionEpistemicState
    ) -> None:
        await self._db.execute(
            "UPDATE fb_invention_page_meta SET invention_state = ?, updated_at = ? WHERE page_id = ?",
            (state.value, datetime.now().isoformat(), str(page_id)),
        )

    async def update_pantheon(
        self,
        page_id: EntityId,
        verdict: str,
        outcome_tier: str,
        consensus: bool,
        objection_count_open: int,
        objection_count_resolved: int,
    ) -> None:
        await self._db.execute(
            """UPDATE fb_invention_page_meta SET
                pantheon_verdict = ?,
                pantheon_outcome_tier = ?,
                pantheon_consensus = ?,
                objection_count_open = ?,
                objection_count_resolved = ?,
                updated_at = ?
            WHERE page_id = ?""",
            (
                verdict,
                outcome_tier,
                self._bool_to_int(consensus),
                objection_count_open,
                objection_count_resolved,
                datetime.now().isoformat(),
                str(page_id),
            ),
        )

    async def list_by_vault(
        self,
        vault_id: EntityId,
        state: InventionEpistemicState | None = None,
    ) -> list[InventionPageMeta]:
        if state is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_invention_page_meta WHERE vault_id = ? AND invention_state = ?",
                (str(vault_id), state.value),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_invention_page_meta WHERE vault_id = ?",
                (str(vault_id),),
            )
        rows = await cursor.fetchall()
        return [self._row_to_meta(r) for r in rows]

    async def list_by_state(
        self,
        vault_id: EntityId,
        state: InventionEpistemicState,
    ) -> list[InventionPageMeta]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_invention_page_meta WHERE vault_id = ? AND invention_state = ?",
            (str(vault_id), state.value),
        )
        rows = await cursor.fetchall()
        return [self._row_to_meta(r) for r in rows]

    @staticmethod
    def _bool_to_int(value: bool | None) -> int | None:
        if value is None:
            return None
        return 1 if value else 0

    @staticmethod
    def _int_to_bool(value: int | None) -> bool | None:
        if value is None:
            return None
        return bool(value)

    @staticmethod
    def _row_to_meta(row: aiosqlite.Row) -> InventionPageMeta:
        consensus_raw = row["pantheon_consensus"]
        return InventionPageMeta(
            page_id=EntityId(row["page_id"]),
            vault_id=EntityId(row["vault_id"]),
            invention_state=InventionEpistemicState(row["invention_state"]),
            run_id=row["run_id"],
            run_type=row["run_type"],
            models_used=json.loads(row["models_used"]),
            novelty_score=row["novelty_score"],
            fidelity_score=row["fidelity_score"],
            domain_distance=row["domain_distance"],
            source_domain=row["source_domain"],
            target_domain=row["target_domain"],
            pantheon_verdict=row["pantheon_verdict"],
            pantheon_outcome_tier=row["pantheon_outcome_tier"],
            pantheon_consensus=None if consensus_raw is None else bool(consensus_raw),
            objection_count_open=row["objection_count_open"],
            objection_count_resolved=row["objection_count_resolved"],
            total_cost_usd=row["total_cost_usd"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
