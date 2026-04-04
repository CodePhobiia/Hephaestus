"""Source normalization pipeline — dispatches by SourceFormat."""
from __future__ import annotations

import csv
import io
import json
import logging

from hephaestus.forgebase.domain.enums import SourceFormat
from hephaestus.forgebase.ingestion.html import normalize_html
from hephaestus.forgebase.ingestion.images import normalize_image
from hephaestus.forgebase.ingestion.markdown_normalizer import normalize_markdown
from hephaestus.forgebase.ingestion.pdf import normalize_pdf

logger = logging.getLogger(__name__)


class NormalizationPipeline:
    """Dispatches source normalization by format."""

    async def normalize(
        self,
        raw_content: bytes,
        format: SourceFormat,
        metadata: dict | None = None,
    ) -> bytes:
        """Convert raw source content to normalized markdown bytes.

        Dispatches to format-specific handlers.
        Returns normalized markdown as UTF-8 bytes.
        """
        handler = self._dispatch_table.get(format)
        if handler is None:
            # Passthrough for unhandled formats
            return raw_content
        return handler(self, raw_content, metadata)

    def _handle_markdown(self, raw: bytes, metadata: dict | None) -> bytes:
        return normalize_markdown(raw)

    def _handle_html(self, raw: bytes, metadata: dict | None) -> bytes:
        return normalize_html(raw)

    def _handle_pdf(self, raw: bytes, metadata: dict | None) -> bytes:
        return normalize_pdf(raw)

    def _handle_image(self, raw: bytes, metadata: dict | None) -> bytes:
        return normalize_image(raw, metadata)

    def _handle_csv(self, raw: bytes, metadata: dict | None) -> bytes:
        return _normalize_csv(raw)

    def _handle_json(self, raw: bytes, metadata: dict | None) -> bytes:
        return _normalize_json(raw)

    def _handle_heph_output(self, raw: bytes, metadata: dict | None) -> bytes:
        # Treat as markdown — normalize formatting
        return normalize_markdown(raw)

    _dispatch_table: dict[SourceFormat, object] = {
        SourceFormat.MARKDOWN: _handle_markdown,
        SourceFormat.URL: _handle_html,
        SourceFormat.PDF: _handle_pdf,
        SourceFormat.IMAGE: _handle_image,
        SourceFormat.CSV: _handle_csv,
        SourceFormat.JSON: _handle_json,
        SourceFormat.HEPH_OUTPUT: _handle_heph_output,
    }


def _normalize_csv(raw: bytes) -> bytes:
    """Convert CSV data to a markdown table."""
    if not raw.strip():
        return b"# CSV Source\n\n*Empty CSV content.*\n"

    text = raw.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))

    rows = list(reader)
    if not rows:
        return b"# CSV Source\n\n*Empty CSV content.*\n"

    lines: list[str] = ["# CSV Data", ""]

    # First row as header
    header = rows[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")

    # Data rows
    for row in rows[1:]:
        # Pad row to match header length
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")

    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _normalize_json(raw: bytes) -> bytes:
    """Convert JSON data to a structured markdown summary."""
    if not raw.strip():
        return b"# JSON Source\n\n*Empty JSON content.*\n"

    text = raw.decode("utf-8", errors="replace")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse JSON for normalization: %s", exc)
        return f"# JSON Source\n\n*Failed to parse JSON: {exc}*\n".encode("utf-8")

    lines: list[str] = ["# JSON Data", ""]

    if isinstance(data, list):
        lines.append(f"Array with {len(data)} items.")
        lines.append("")
        if data and isinstance(data[0], dict):
            # Render as table if items are dicts
            keys = list(data[0].keys())
            lines.append("| " + " | ".join(str(k) for k in keys) + " |")
            lines.append("| " + " | ".join("---" for _ in keys) + " |")
            for item in data:
                vals = [str(item.get(k, "")) for k in keys]
                lines.append("| " + " | ".join(vals) + " |")
            lines.append("")
        else:
            for i, item in enumerate(data):
                lines.append(f"- Item {i + 1}: {item}")
            lines.append("")
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                lines.append(f"- **{key}**: `{json.dumps(value)}`")
            else:
                lines.append(f"- **{key}**: {value}")
        lines.append("")
    else:
        lines.append(f"Value: {data}")
        lines.append("")

    return "\n".join(lines).encode("utf-8")
