"""SQLite implementation of EmbeddingCacheRepository."""

from __future__ import annotations

import aiosqlite

from hephaestus.forgebase.repository.embedding_cache_repo import EmbeddingCacheRepository


class SqliteEmbeddingCacheRepository(EmbeddingCacheRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, entity_id: str, version: int) -> bytes | None:
        cursor = await self._db.execute(
            "SELECT embedding_blob FROM fb_embedding_cache WHERE entity_id = ? AND version = ?",
            (entity_id, version),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return row["embedding_blob"]

    async def put(
        self,
        entity_id: str,
        version: int,
        embedding_blob: bytes,
        computed_at: str,
    ) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO fb_embedding_cache
            (entity_id, version, embedding_blob, computed_at)
            VALUES (?, ?, ?, ?)""",
            (entity_id, version, embedding_blob, computed_at),
        )

    async def invalidate(self, entity_id: str) -> None:
        await self._db.execute(
            "DELETE FROM fb_embedding_cache WHERE entity_id = ?",
            (entity_id,),
        )

    async def batch_get(
        self,
        items: list[tuple[str, int]],
    ) -> dict[tuple[str, int], bytes]:
        if not items:
            return {}

        results: dict[tuple[str, int], bytes] = {}
        # SQLite has a limit on variables, batch if needed
        for entity_id, version in items:
            blob = await self.get(entity_id, version)
            if blob is not None:
                results[(entity_id, version)] = blob
        return results
