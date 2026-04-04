"""Image normalization — stub implementation."""
from __future__ import annotations


def normalize_image(raw: bytes, metadata: dict | None = None) -> bytes:
    """Extract image description. Currently a stub.

    A future implementation will use vision models or OCR to extract
    meaningful content from images. For now, returns a placeholder
    that includes the image title from metadata if available.
    """
    title = (metadata or {}).get("title", "Image")
    return f"# Image: {title}\n\n*Image description extraction not yet implemented.*\n".encode("utf-8")
