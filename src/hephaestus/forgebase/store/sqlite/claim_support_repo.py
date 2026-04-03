"""SQLite implementation of ClaimSupportRepository."""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import ClaimSupport
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.claim_support_repo import ClaimSupportRepository


class SqliteClaimSupportRepository(ClaimSupportRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, support: ClaimSupport) -> None:
        await self._db.execute(
            "INSERT INTO fb_claim_supports (support_id, claim_id, source_id, source_segment, strength, created_at, created_by_type, created_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(support.support_id),
                str(support.claim_id),
                str(support.source_id),
                support.source_segment,
                support.strength,
                support.created_at.isoformat(),
                support.created_by.actor_type.value,
                support.created_by.actor_id,
            ),
        )

    async def get(self, support_id: EntityId) -> ClaimSupport | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_supports WHERE support_id = ?", (str(support_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_support(row)

    async def delete(self, support_id: EntityId) -> None:
        await self._db.execute(
            "DELETE FROM fb_claim_supports WHERE support_id = ?", (str(support_id),)
        )

    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimSupport]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_supports WHERE claim_id = ? ORDER BY created_at",
            (str(claim_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_support(r) for r in rows]

    @staticmethod
    def _row_to_support(row: aiosqlite.Row) -> ClaimSupport:
        return ClaimSupport(
            support_id=EntityId(row["support_id"]),
            claim_id=EntityId(row["claim_id"]),
            source_id=EntityId(row["source_id"]),
            source_segment=row["source_segment"],
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
        )
