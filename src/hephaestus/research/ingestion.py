"""Content ingestion controls — size limits, MIME filtering, parse containment."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_SIZE_BYTES = 500 * 1024  # 500 KB
_ALLOWED_MIME_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "text/markdown",
    "text/xml",
    "application/xml",
}


@dataclass
class IngestedSource:
    """A normalized, ingested research source."""

    url: str
    content: str = ""
    content_type: str = ""
    size_bytes: int = 0
    truncated: bool = False
    parse_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return bool(self.content) and self.parse_error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "truncated": self.truncated,
            "is_valid": self.is_valid,
            "parse_error": self.parse_error,
        }


class IngestionConfig:
    """Configuration for content ingestion controls."""

    def __init__(
        self,
        *,
        max_size_bytes: int = _DEFAULT_MAX_SIZE_BYTES,
        allowed_mime_types: set[str] | None = None,
        strip_html: bool = True,
    ) -> None:
        self.max_size_bytes = max_size_bytes
        self.allowed_mime_types = allowed_mime_types or _ALLOWED_MIME_TYPES
        self.strip_html = strip_html


def ingest_content(
    url: str,
    raw_content: str | bytes,
    *,
    content_type: str = "text/plain",
    config: IngestionConfig | None = None,
) -> IngestedSource:
    """Ingest raw content with size limits, MIME filtering, and parse containment.

    This function never raises — all errors are captured in the result.
    """
    cfg = config or IngestionConfig()

    try:
        # Normalize to string
        if isinstance(raw_content, bytes):
            try:
                text = raw_content.decode("utf-8", errors="replace")
            except Exception as exc:
                return IngestedSource(url=url, parse_error=f"Decode error: {exc}")
        else:
            text = raw_content

        # Size check
        size = len(text.encode("utf-8"))
        truncated = False
        if size > cfg.max_size_bytes:
            # Truncate to limit
            text = text[: cfg.max_size_bytes]
            truncated = True
            logger.debug("Content from %s truncated: %d > %d bytes", url, size, cfg.max_size_bytes)

        # MIME type check
        base_type = content_type.split(";")[0].strip().lower()
        if base_type not in cfg.allowed_mime_types:
            return IngestedSource(
                url=url,
                content_type=base_type,
                size_bytes=size,
                parse_error=f"MIME type '{base_type}' not in allowed set",
            )

        # Basic HTML stripping if configured
        if cfg.strip_html and base_type == "text/html":
            text = _strip_html_tags(text)

        return IngestedSource(
            url=url,
            content=text,
            content_type=base_type,
            size_bytes=len(text.encode("utf-8")),
            truncated=truncated,
        )

    except Exception as exc:
        logger.warning("Ingestion error for %s: %s", url, exc)
        return IngestedSource(url=url, parse_error=str(exc))


def _strip_html_tags(html: str) -> str:
    """Basic HTML tag stripping — removes tags and normalizes whitespace."""
    import re

    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


__all__ = [
    "IngestedSource",
    "IngestionConfig",
    "ingest_content",
]
