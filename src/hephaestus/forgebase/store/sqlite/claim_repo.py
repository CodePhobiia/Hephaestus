"""SQLite implementation of ClaimRepository."""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType, ClaimStatus, SupportType
from hephaestus.forgebase.domain.models import Claim, ClaimVersion
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.claim_repo import ClaimRepository


class SqliteClaimRepository(ClaimRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, claim: Claim, version: ClaimVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_claims (claim_id, vault_id, page_id, created_at) VALUES (?, ?, ?, ?)",
            (str(claim.claim_id), str(claim.vault_id), str(claim.page_id), claim.created_at.isoformat()),
        )
        await self.create_version(version)

    async def get(self, claim_id: EntityId) -> Claim | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claims WHERE claim_id = ?", (str(claim_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_claim(row)

    async def get_version(self, claim_id: EntityId, version: Version) -> ClaimVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_versions WHERE claim_id = ? AND version = ?",
            (str(claim_id), version.number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_claim_version(row)

    async def get_head_version(self, claim_id: EntityId) -> ClaimVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claim_versions WHERE claim_id = ? ORDER BY version DESC LIMIT 1",
            (str(claim_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_claim_version(row)

    async def create_version(self, version: ClaimVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_claim_versions (claim_id, version, statement, status, support_type, confidence, validated_at, fresh_until, created_at, created_by_type, created_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(version.claim_id),
                version.version.number,
                version.statement,
                version.status.value,
                version.support_type.value,
                version.confidence,
                version.validated_at.isoformat(),
                version.fresh_until.isoformat() if version.fresh_until else None,
                version.created_at.isoformat(),
                version.created_by.actor_type.value,
                version.created_by.actor_id,
            ),
        )

    async def list_by_page(self, page_id: EntityId) -> list[Claim]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claims WHERE page_id = ? ORDER BY created_at",
            (str(page_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_claim(r) for r in rows]

    async def list_by_vault(self, vault_id: EntityId) -> list[Claim]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_claims WHERE vault_id = ? ORDER BY created_at",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_claim(r) for r in rows]

    @staticmethod
    def _row_to_claim(row: aiosqlite.Row) -> Claim:
        return Claim(
            claim_id=EntityId(row["claim_id"]),
            vault_id=EntityId(row["vault_id"]),
            page_id=EntityId(row["page_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_claim_version(row: aiosqlite.Row) -> ClaimVersion:
        return ClaimVersion(
            claim_id=EntityId(row["claim_id"]),
            version=Version(row["version"]),
            statement=row["statement"],
            status=ClaimStatus(row["status"]),
            support_type=SupportType(row["support_type"]),
            confidence=row["confidence"],
            validated_at=datetime.fromisoformat(row["validated_at"]),
            fresh_until=datetime.fromisoformat(row["fresh_until"]) if row["fresh_until"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
        )
