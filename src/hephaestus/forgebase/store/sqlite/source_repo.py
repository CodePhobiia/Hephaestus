"""SQLite implementation of SourceRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import (
    ActorType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
)
from hephaestus.forgebase.domain.models import Source, SourceVersion
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.source_repo import SourceRepository


class SqliteSourceRepository(SourceRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, source: Source, version: SourceVersion) -> None:
        await self._db.execute(
            "INSERT INTO fb_sources (source_id, vault_id, format, origin_locator, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                str(source.source_id),
                str(source.vault_id),
                source.format.value,
                source.origin_locator,
                source.created_at.isoformat(),
            ),
        )
        await self.create_version(version)

    async def get(self, source_id: EntityId) -> Source | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_sources WHERE source_id = ?", (str(source_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_source(row)

    async def get_version(
        self, source_id: EntityId, version: Version
    ) -> SourceVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_source_versions WHERE source_id = ? AND version = ?",
            (str(source_id), version.number),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_source_version(row)

    async def get_head_version(self, source_id: EntityId) -> SourceVersion | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_source_versions WHERE source_id = ? ORDER BY version DESC LIMIT 1",
            (str(source_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_source_version(row)

    async def create_version(self, version: SourceVersion) -> None:
        normalized_hash = None
        normalized_size = None
        normalized_mime = None
        if version.normalized_ref is not None:
            normalized_hash = version.normalized_ref.content_hash.sha256
            normalized_size = version.normalized_ref.size_bytes
            normalized_mime = version.normalized_ref.mime_type

        await self._db.execute(
            "INSERT INTO fb_source_versions (source_id, version, title, authors, url, raw_artifact_hash, raw_artifact_size, raw_artifact_mime, normalized_hash, normalized_size, normalized_mime, content_hash, metadata, trust_tier, status, created_at, created_by_type, created_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(version.source_id),
                version.version.number,
                version.title,
                json.dumps(version.authors),
                version.url,
                version.raw_artifact_ref.content_hash.sha256,
                version.raw_artifact_ref.size_bytes,
                version.raw_artifact_ref.mime_type,
                normalized_hash,
                normalized_size,
                normalized_mime,
                version.content_hash.sha256,
                json.dumps(version.metadata),
                version.trust_tier.value,
                version.status.value,
                version.created_at.isoformat(),
                version.created_by.actor_type.value,
                version.created_by.actor_id,
            ),
        )

    async def list_by_vault(self, vault_id: EntityId) -> list[Source]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_sources WHERE vault_id = ? ORDER BY created_at",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_source(r) for r in rows]

    @staticmethod
    def _row_to_source(row: aiosqlite.Row) -> Source:
        return Source(
            source_id=EntityId(row["source_id"]),
            vault_id=EntityId(row["vault_id"]),
            format=SourceFormat(row["format"]),
            origin_locator=row["origin_locator"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_source_version(row: aiosqlite.Row) -> SourceVersion:
        normalized_ref = None
        if row["normalized_hash"] is not None:
            normalized_ref = BlobRef(
                content_hash=ContentHash(sha256=row["normalized_hash"]),
                size_bytes=row["normalized_size"],
                mime_type=row["normalized_mime"],
            )

        return SourceVersion(
            source_id=EntityId(row["source_id"]),
            version=Version(row["version"]),
            title=row["title"],
            authors=json.loads(row["authors"]),
            url=row["url"],
            raw_artifact_ref=BlobRef(
                content_hash=ContentHash(sha256=row["raw_artifact_hash"]),
                size_bytes=row["raw_artifact_size"],
                mime_type=row["raw_artifact_mime"],
            ),
            normalized_ref=normalized_ref,
            content_hash=ContentHash(sha256=row["content_hash"]),
            metadata=json.loads(row["metadata"]),
            trust_tier=SourceTrustTier(row["trust_tier"]),
            status=SourceStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=ActorRef(
                actor_type=ActorType(row["created_by_type"]),
                actor_id=row["created_by_id"],
            ),
        )
