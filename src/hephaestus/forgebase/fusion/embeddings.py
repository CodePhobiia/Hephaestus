"""EmbeddingIndex — persistent, version-pinned embedding cache.

Stores embeddings keyed by (entity_id, version). Recomputes only when
entity version changes. Uses sentence-transformers (all-MiniLM-L6-v2)
with lazy loading to avoid heavy imports at module level.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class EmbeddingIndex:
    """Persistent, version-pinned embedding cache.

    Stores embeddings keyed by (entity_id, version). Recomputes only when
    entity version changes. Uses sentence-transformers (all-MiniLM-L6-v2).
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._uow_factory = uow_factory
        self._model_name = model_name
        self._model: Any = None  # Lazy-loaded SentenceTransformer

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _get_model(self) -> Any:
        """Lazy-load sentence-transformers model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    # ------------------------------------------------------------------
    # Embedding computation
    # ------------------------------------------------------------------

    def _compute_embedding(self, text: str) -> bytes:
        """Compute embedding and return as normalised numpy float32 bytes.

        This method is the seam for testing — subclasses or monkey-patches
        can override it to avoid loading the real model.
        """
        import numpy as np

        model = self._get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return np.array(embedding, dtype=np.float32).tobytes()

    # ------------------------------------------------------------------
    # Timestamp helper
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC time as ISO-8601 string."""
        return datetime.now(UTC).isoformat()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_compute(
        self,
        entity_id: EntityId,
        version: Version,
        text: str,
    ) -> bytes:
        """Return cached embedding bytes or compute + cache.

        Looks up the embedding by (entity_id, version). On cache miss,
        computes the embedding, stores it, and returns it.
        """
        eid_str = str(entity_id)
        ver_int = version.number

        uow = self._uow_factory()
        async with uow:
            cached = await uow.embedding_cache.get(eid_str, ver_int)
            if cached is not None:
                return cached

            embedding_blob = self._compute_embedding(text)
            await uow.embedding_cache.put(
                eid_str, ver_int, embedding_blob, self._now_iso(),
            )
            await uow.commit()
            return embedding_blob

    async def batch_get_or_compute(
        self,
        items: list[tuple[EntityId, Version, str]],
    ) -> list[bytes]:
        """Batch: return cached or compute for each item.

        Processes items sequentially, leveraging the cache for each one.
        """
        results: list[bytes] = []
        for entity_id, version, text in items:
            result = await self.get_or_compute(entity_id, version, text)
            results.append(result)
        return results

    async def invalidate(self, entity_id: EntityId) -> None:
        """Remove all cached embeddings for an entity (all versions)."""
        eid_str = str(entity_id)

        uow = self._uow_factory()
        async with uow:
            await uow.embedding_cache.invalidate(eid_str)
            await uow.commit()
