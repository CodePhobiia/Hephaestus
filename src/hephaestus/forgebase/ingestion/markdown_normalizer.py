"""Markdown normalization — clean up raw markdown content."""

from __future__ import annotations

import re


def normalize_markdown(raw: bytes) -> bytes:
    """Clean up markdown: normalize whitespace, fix headings, split sections.

    - Decode UTF-8 (with error replacement)
    - Normalize line endings to \\n
    - Strip excessive blank lines (max 2 consecutive)
    - Ensure headings have blank line before/after
    - Strip HTML comments
    - Re-encode as UTF-8 bytes
    """
    if not raw:
        return b""

    # Decode with error replacement for invalid UTF-8
    text = raw.decode("utf-8", errors="replace")

    # Normalize line endings: \r\n -> \n, then lone \r -> \n
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Strip HTML comments (including multiline)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Ensure headings have a blank line before and after.
    # Match lines that start with 1-6 '#' followed by a space.
    # We process line by line to handle this correctly.
    lines = text.split("\n")
    result_lines: list[str] = []
    for _i, line in enumerate(lines):
        stripped = line.strip()
        is_heading = bool(re.match(r"^#{1,6}\s", stripped))

        if is_heading:
            # Ensure blank line before heading (unless it's the first line)
            if result_lines and result_lines[-1].strip() != "":
                result_lines.append("")
            result_lines.append(line)
            # Mark that we need a blank line after (handled by checking next line)
            # We'll add it after the heading; the next line logic will handle dedup.
            result_lines.append("")
        else:
            result_lines.append(line)

    text = "\n".join(result_lines)

    # Strip excessive blank lines: collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip trailing whitespace
    text = text.strip()

    if not text:
        return b""

    # Ensure file ends with a single newline
    text += "\n"

    return text.encode("utf-8")
