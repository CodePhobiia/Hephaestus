"""SQLite implementation of PageRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ActorType, PageType
from hephaestus.forgebase.domain.models import Page, PageVersion
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.page_repo import PageRepository


class SqlitePageRepository(PageRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, page: Page, version: PageVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_pages (page_id, vault_id, page_type, page_key, created_at, created_by_run) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(page.page_id),
                str(page.vault_id),
                page.page_type.value,
                page.page_key,
                page.created_at.isoformat(),
                str(page.created_by_run) if page.created_by_run else None,
            ),
        )
        await self.create_version(version)

    async def get(self, page_id: EntityId) -> Page | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_pages WHERE page_id = ?", (str(page_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    async def get_version(
        self, page_id: EntityId, version: Version
    ) -> PageVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_page_versions WHERE page_id = ? AND version = ?",
            (str(page_id), version.number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_page_version(row)

    async def get_head_version(self, page_id: EntityId) -> PageVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_page_versions WHERE page_id = ? ORDER BY version DESC LIMIT 1",
            (str(page_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_page_version(row)

    async def create_version(self, version: PageVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_page_versions (page_id, version, title, content_hash, content_size, content_mime, content_hash_sha, summary, compiled_from, created_at, created_by_type, created_by_id, schema_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(version.page_id),
                version.version.number,
                version.title,
                version.content_ref.content_hash.sha256,
                version.content_ref.size_bytes,
                version.content_ref.mime_type,
                version.content_hash.sha256,
                version.summary,
                json.dumps([str(eid) for eid in version.compiled_from]),
                version.created_at.isoformat(),
                version.created_by.actor_type.value,
                version.created_by.actor_id,
                version.schema_version,
            ),
        )

    async def list_by_vault(
        self, vault_id: EntityId, *, page_type: str | None = None
    ) -> list[Page]:
        if page_type is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_pages WHERE vault_id = ? AND page_type = ? ORDER BY created_at",
                (str(vault_id), page_type),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_pages WHERE vault_id = ? ORDER BY created_at",
                (str(vault_id),),
            )
        rows = await cursor.fetchall()
        return [self._row_to_page(r) for r in rows]

    async def find_by_key(self, vault_id: EntityId, page_key: str) -> Page | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_pages WHERE vault_id = ? AND page_key = ?",
            (str(vault_id), page_key),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    @staticmethod
    def _row_to_page(row: aiosqlite.Row) -> Page:
        return Page(
            page_id=EntityId(row["page_id"]),
            vault_id=EntityId(row["vault_id"]),
            page_type=PageType(row["page_type"]),
            page_key=row["page_key"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by_run=EntityId(row["created_by_run"]) if row["created_by_run"] else None,
        )

    @staticmethod
    def _row_to_page_version(row: aiosqlite.Row) -> PageVersion:
        return PageVersion(
            page_id=EntityId(row["page_id"]),
            version=Version(row["version"]),
            title=row["title"],
            content_ref=BlobRef(
                content_hash=ContentHash(sha256=row["content_hash"]),
                size_bytes=row["content_size"],
                mime_type=row["content_mime"],
            ),
            content_hash=ContentHash(sha256=row["content_hash_sha"]),
            summary=row["summary"],
            compiled_from=[EntityId(eid) for eid in json.loads(row["compiled_from"])],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(
                actor_type=ActorType(row["created_by_type"]),
                actor_id=row["created_by_id"],
            ),
            schema_version=row["schema_version"],
        )
