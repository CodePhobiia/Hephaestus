"""Embeddings provider — lazy-loaded sentence-transformers."""

from __future__ import annotations

import logging
from typing import Any

from hephaestus.providers.base import ProviderCapability, ProviderStatus

logger = logging.getLogger(__name__)

_model_instance: Any = None
_import_error: str | None = None


def _lazy_import_st() -> Any:
    global _import_error
    if _import_error is not None:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer
    except ImportError as exc:
        _import_error = str(exc)
        logger.debug("sentence-transformers not available: %s", exc)
        return None


class EmbeddingsProvider:
    """Sentence-transformers embeddings with lazy model loading."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._status = ProviderStatus.UNAVAILABLE
        self._model: Any = None
        self._check_availability()

    def _check_availability(self) -> None:
        cls = _lazy_import_st()
        self._status = ProviderStatus.AVAILABLE if cls is not None else ProviderStatus.UNAVAILABLE

    @property
    def name(self) -> str:
        return "embeddings"

    @property
    def capabilities(self) -> list[ProviderCapability]:
        return [ProviderCapability.EMBEDDINGS]

    @property
    def status(self) -> ProviderStatus:
        return self._status

    def is_available(self) -> bool:
        return self._status == ProviderStatus.AVAILABLE

    def unavailability_reason(self) -> str:
        if _import_error:
            return f"sentence-transformers not installed: {_import_error}"
        return ""

    def get_model(self) -> Any:
        """Return the loaded SentenceTransformer model, loading on first call."""
        if not self.is_available():
            raise RuntimeError(f"Embeddings provider unavailable: {self.unavailability_reason()}")
        if self._model is None:
            cls = _lazy_import_st()
            self._model = cls(self._model_name)
            logger.info("Loaded embedding model: %s", self._model_name)
        return self._model

    def encode(self, texts: list[str], **kwargs: Any) -> Any:
        """Encode texts into embeddings."""
        model = self.get_model()
        return model.encode(texts, **kwargs)

    async def health_check(self) -> ProviderStatus:
        if not self.is_available():
            return ProviderStatus.UNAVAILABLE
        try:
            self.get_model()
            self._status = ProviderStatus.AVAILABLE
        except Exception as exc:
            logger.warning("Embeddings health check failed: %s", exc)
            self._status = ProviderStatus.DEGRADED
        return self._status


__all__ = ["EmbeddingsProvider"]
