"""SQLite implementation of LinkRepository."""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType, LinkKind
from hephaestus.forgebase.domain.models import Link, LinkVersion
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.link_repo import LinkRepository


class SqliteLinkRepository(LinkRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, link: Link, version: LinkVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_links (link_id, vault_id, kind, created_at) VALUES (?, ?, ?, ?)",
            (str(link.link_id), str(link.vault_id), link.kind.value, link.created_at.isoformat()),
        )
        await self.create_version(version)

    async def get(self, link_id: EntityId) -> Link | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_links WHERE link_id = ?", (str(link_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_link(row)

    async def get_version(self, link_id: EntityId, version: Version) -> LinkVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_link_versions WHERE link_id = ? AND version = ?",
            (str(link_id), version.number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_link_version(row)

    async def get_head_version(self, link_id: EntityId) -> LinkVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_link_versions WHERE link_id = ? ORDER BY version DESC LIMIT 1",
            (str(link_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_link_version(row)

    async def create_version(self, version: LinkVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_link_versions (link_id, version, source_entity, target_entity, label, weight, created_at, created_by_type, created_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(version.link_id),
                version.version.number,
                str(version.source_entity),
                str(version.target_entity),
                version.label,
                version.weight,
                version.created_at.isoformat(),
                version.created_by.actor_type.value,
                version.created_by.actor_id,
            ),
        )

    async def list_by_entity(
        self,
        entity_id: EntityId,
        *,
        direction: str = "both",
        kind: str | None = None,
    ) -> list[Link]:
        # Join links with their head version (max version per link_id).
        # We use a subquery to find the head version number for each link,
        # then join to get the full version row for direction filtering.
        base_sql = """
            SELECT l.*
            FROM fb_links l
            JOIN fb_link_versions lv ON l.link_id = lv.link_id
            JOIN (
                SELECT link_id, MAX(version) AS max_ver
                FROM fb_link_versions
                GROUP BY link_id
            ) head ON lv.link_id = head.link_id AND lv.version = head.max_ver
            WHERE 1=1
        """
        params: list[object] = []

        entity_str = str(entity_id)
        if direction == "outgoing":
            base_sql += " AND lv.source_entity = ?"
            params.append(entity_str)
        elif direction == "incoming":
            base_sql += " AND lv.target_entity = ?"
            params.append(entity_str)
        else:  # "both"
            base_sql += " AND (lv.source_entity = ? OR lv.target_entity = ?)"
            params.append(entity_str)
            params.append(entity_str)

        if kind is not None:
            base_sql += " AND l.kind = ?"
            params.append(kind)

        base_sql += " ORDER BY l.created_at"

        cursor = await self._db.execute(base_sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_link(r) for r in rows]

    async def list_by_vault(self, vault_id: EntityId) -> list[Link]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_links WHERE vault_id = ? ORDER BY created_at",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_link(r) for r in rows]

    @staticmethod
    def _row_to_link(row: aiosqlite.Row) -> Link:
        return Link(
            link_id=EntityId(row["link_id"]),
            vault_id=EntityId(row["vault_id"]),
            kind=LinkKind(row["kind"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_link_version(row: aiosqlite.Row) -> LinkVersion:
        return LinkVersion(
            link_id=EntityId(row["link_id"]),
            version=Version(row["version"]),
            source_entity=EntityId(row["source_entity"]),
            target_entity=EntityId(row["target_entity"]),
            label=row["label"],
            weight=row["weight"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(actor_type=ActorType(row["created_by_type"]), actor_id=row["created_by_id"]),
        )
