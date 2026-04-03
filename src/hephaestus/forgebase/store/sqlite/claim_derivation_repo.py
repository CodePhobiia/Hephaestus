"""SQLite implementation of ClaimDerivationRepository."""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import ClaimDerivation
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.claim_derivation_repo import ClaimDerivationRepository


class SqliteClaimDerivationRepository(ClaimDerivationRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, derivation: ClaimDerivation) -> None:
        await self._db.execute(
            "INSERT INTO fb_claim_derivations (derivation_id, claim_id, parent_claim_id, relationship, created_at, created_by_type, created_by_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(derivation.derivation_id),
                str(derivation.claim_id),
                str(derivation.parent_claim_id),
                derivation.relationship,
                derivation.created_at.isoformat(),
                derivation.created_by.actor_type.value,
                derivation.created_by.actor_id,
            ),
        )

    async def get(self, derivation_id: EntityId) -> ClaimDerivation | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_derivations WHERE derivation_id = ?", (str(derivation_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_derivation(row)

    async def delete(self, derivation_id: EntityId) -> None:
        await self._db.execute(
            "DELETE FROM fb_claim_derivations WHERE derivation_id = ?", (str(derivation_id),)
        )

    async def list_by_claim(self, claim_id: EntityId) -> list[ClaimDerivation]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_derivations WHERE claim_id = ? ORDER BY created_at",
            (str(claim_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_derivation(r) for r in rows]

    @staticmethod
    def _row_to_derivation(row: aiosqlite.Row) -> ClaimDerivation:
        return ClaimDerivation(
            derivation_id=EntityId(row["derivation_id"]),
            claim_id=EntityId(row["claim_id"]),
            parent_claim_id=EntityId(row["parent_claim_id"]),
            relationship=row["relationship"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
        )
