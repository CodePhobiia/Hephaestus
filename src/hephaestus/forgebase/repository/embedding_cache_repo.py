"""Embedding cache repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingCacheRepository(ABC):
    @abstractmethod
    async def get(self, entity_id: str, version: int) -> bytes | None: ...

    @abstractmethod
    async def put(
        self,
        entity_id: str,
        version: int,
        embedding_blob: bytes,
        computed_at: str,
    ) -> None: ...

    @abstractmethod
    async def invalidate(self, entity_id: str) -> None: ...

    @abstractmethod
    async def batch_get(
        self,
        items: list[tuple[str, int]],
    ) -> dict[tuple[str, int], bytes]: ...
