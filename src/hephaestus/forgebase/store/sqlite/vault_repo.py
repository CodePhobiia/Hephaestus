"""SQLite implementation of VaultRepository."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId
from hephaestus.forgebase.repository.vault_repo import VaultRepository


class SqliteVaultRepository(VaultRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, vault: Vault, revision: VaultRevision) -> None:
        await self._db.execute(
            "INSERT INTO fb_vaults (vault_id, name, description, head_revision_id, created_at, updated_at, config) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(vault.vault_id),
                vault.name,
                vault.description,
                str(vault.head_revision_id),
                vault.created_at.isoformat(),
                vault.updated_at.isoformat(),
                json.dumps(vault.config),
            ),
        )
        await self.create_revision(revision)

    async def get(self, vault_id: EntityId) -> Vault | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_vaults WHERE vault_id = ?", (str(vault_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_vault(row)

    async def list_all(self) -> list[Vault]:
        cursor = await self._db.execute("SELECT * FROM fb_vaults ORDER BY created_at")
        rows = await cursor.fetchall()
        return [self._row_to_vault(r) for r in rows]

    async def update_head(self, vault_id: EntityId, revision_id: VaultRevisionId) -> None:
        await self._db.execute(
            "UPDATE fb_vaults SET head_revision_id = ?, updated_at = ? WHERE vault_id = ?",
            (str(revision_id), datetime.now().isoformat(), str(vault_id)),
        )

    async def update_config(self, vault_id: EntityId, config: dict) -> None:
        await self._db.execute(
            "UPDATE fb_vaults SET config = ?, updated_at = ? WHERE vault_id = ?",
            (json.dumps(config), datetime.now().isoformat(), str(vault_id)),
        )

    async def get_revision(self, revision_id: VaultRevisionId) -> VaultRevision | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_vault_revisions WHERE revision_id = ?", (str(revision_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_revision(row)

    async def create_revision(self, revision: VaultRevision) -> None:
        await self._db.execute(
            "INSERT INTO fb_vault_revisions (revision_id, vault_id, parent_revision_id, created_at, created_by_type, created_by_id, causation_event_id, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(revision.revision_id),
                str(revision.vault_id),
                str(revision.parent_revision_id) if revision.parent_revision_id else None,
                revision.created_at.isoformat(),
                revision.created_by.actor_type.value,
                revision.created_by.actor_id,
                str(revision.causation_event_id) if revision.causation_event_id else None,
                revision.summary,
            ),
        )

    async def get_canonical_page_head(self, vault_id: EntityId, page_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "page", page_id)

    async def set_canonical_page_head(
        self, vault_id: EntityId, page_id: EntityId, version: int
    ) -> None:
        await self._set_head(vault_id, "page", page_id, version)

    async def get_canonical_claim_head(self, vault_id: EntityId, claim_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "claim", claim_id)

    async def set_canonical_claim_head(
        self, vault_id: EntityId, claim_id: EntityId, version: int
    ) -> None:
        await self._set_head(vault_id, "claim", claim_id, version)

    async def get_canonical_link_head(self, vault_id: EntityId, link_id: EntityId) -> int | None:
        return await self._get_head(vault_id, "link", link_id)

    async def set_canonical_link_head(
        self, vault_id: EntityId, link_id: EntityId, version: int
    ) -> None:
        await self._set_head(vault_id, "link", link_id, version)

    async def get_canonical_source_head(
        self, vault_id: EntityId, source_id: EntityId
    ) -> int | None:
        return await self._get_head(vault_id, "source", source_id)

    async def set_canonical_source_head(
        self, vault_id: EntityId, source_id: EntityId, version: int
    ) -> None:
        await self._set_head(vault_id, "source", source_id, version)

    async def _get_head(self, vault_id: EntityId, kind: str, entity_id: EntityId) -> int | None:
        cursor = await self._db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE vault_id = ? AND entity_kind = ? AND entity_id = ?",
            (str(vault_id), kind, str(entity_id)),
        )
        row = await cursor.fetchone()
        return row["head_version"] if row else None

    async def _set_head(
        self, vault_id: EntityId, kind: str, entity_id: EntityId, version: int
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO fb_canonical_heads (vault_id, entity_kind, entity_id, head_version) VALUES (?, ?, ?, ?)",
            (str(vault_id), kind, str(entity_id), version),
        )

    @staticmethod
    def _row_to_vault(row: aiosqlite.Row) -> Vault:
        return Vault(
            vault_id=EntityId(row["vault_id"]),
            name=row["name"],
            description=row["description"],
            head_revision_id=VaultRevisionId(row["head_revision_id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            config=json.loads(row["config"]),
        )

    @staticmethod
    def _row_to_revision(row: aiosqlite.Row) -> VaultRevision:
        return VaultRevision(
            revision_id=VaultRevisionId(row["revision_id"]),
            vault_id=EntityId(row["vault_id"]),
            parent_revision_id=VaultRevisionId(row["parent_revision_id"])
            if row["parent_revision_id"]
            else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(
                actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]
            ),
            causation_event_id=EntityId(row["causation_event_id"])
            if row["causation_event_id"]
            else None,
            summary=row["summary"],
        )
