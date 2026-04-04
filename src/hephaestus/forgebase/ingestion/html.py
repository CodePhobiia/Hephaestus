"""HTML normalization — convert HTML to clean markdown text."""
from __future__ import annotations

import re


def normalize_html(raw: bytes) -> bytes:
    """Convert HTML to clean markdown.

    - Decode UTF-8
    - Remove <script> and <style> blocks
    - Strip all HTML tags (simple regex approach)
    - Normalize whitespace
    - Return as UTF-8 markdown bytes

    Follows the same approach as research/ingestion.py _strip_html_tags.
    """
    if not raw:
        return b""

    text = raw.decode("utf-8", errors="replace")

    # Remove script and style blocks entirely
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Strip all remaining HTML tags, replacing with a space
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace: collapse multiple spaces/tabs to single space
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse multiple newlines
    text = re.sub(r"\n\s*\n", "\n\n", text)

    text = text.strip()

    if not text:
        return b""

    text += "\n"

    return text.encode("utf-8")
