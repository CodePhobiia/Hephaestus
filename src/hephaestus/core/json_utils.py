"""Lenient JSON parsing for LLM-generated output.

Many LLMs (especially free/cheap ones) emit JSON with invalid Python escape
sequences like ``\\s``, ``\\p``, ``\\a`` — characters that are NOT valid JSON
escapes.  Python's ``json.loads()`` rejects these by default, causing the
entire Genesis pipeline to crash mid-stream.

This module provides ``loads_lenient()``, which:
1. Attempts standard ``json.loads(strict=False)``
2. If that fails, fixes invalid backslash escapes (``\\x`` → ``\\\\x``)
3. Falls back to extraction-from-prose via regex
4. Returns a caller-supplied default on total failure

Usage
-----
>>> from hephaestus.core.json_utils import loads_lenient
>>> loads_lenient(text, default={}, label="scorer")
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Characters that form valid JSON escape sequences after a backslash.
# ``"\\/bfnrt`` cover ``\"``, ``\\``, ``\/``, ``\b``, ``\f``, ``\n``, ``\r``, ``\t``.
# We handle ``\uXXXX`` separately via regex.
_VALID_JSON_ESCAPES = frozenset('"\\/bfnrt')
_HEX4 = re.compile(r"[0-9a-fA-F]{4}")


# ---------------------------------------------------------------------------
# Core: fix invalid backslash escapes in a raw string
# ---------------------------------------------------------------------------


def _fix_json_escapes(text: str) -> str:
    """Double every backslash that does *not* form a valid JSON escape.

    ``\\s`` (invalid) → ``\\\\s`` (literal backslash + ``s`` when parsed).
    ``\\n`` (valid)   → ``\\n``     (newline when parsed, untouched).
    ``\\u0041`` (valid) → ``\\u0041`` (letter A, untouched).
    """
    if "\\" not in text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "u" and i + 5 < n and _HEX4.match(text, i + 2, i + 6):
                # Valid \uXXXX → pass through
                out.append(text[i : i + 6])
                i += 6
                continue
            elif nxt in _VALID_JSON_ESCAPES:
                # Valid escape → pass through
                out.append(text[i : i + 2])
                i += 2
                continue
            else:
                # Invalid escape → double the backslash
                out.append("\\\\")
                out.append(nxt)
                i += 2
                continue
        elif text[i] == "\\" and i + 1 >= n:
            # Trailing backslash → double it
            out.append("\\\\")
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def loads_lenient(
    raw: str,
    *,
    default: Any | None = None,
    label: str = "",
) -> Any:
    """Parse JSON from LLM output with automatic recovery from bad escapes.

    Tries (in order):
    1. ``json.loads(raw, strict=False)``
    2. Extract the outermost ``{...}`` block → ``json.loads`` with ``strict=False``
    3. Fix invalid escapes in the extracted block → ``json.loads``, ``strict=False``
    4. Fix escapes in the full text → try steps 1-2 again on that

    On total failure logs a warning and returns *default*.

    Parameters
    ----------
    raw: Raw text from the model (may contain markdown fences, prose).
    default: Value to return if every strategy fails.
    label: Human-readable tag for log messages (e.g. ``"pantheon"``).
    """
    if not raw or not raw.strip():
        return default

    tag = f"[{label}] " if label else ""

    # 1. Direct parse
    try:
        return json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Extract block + direct parse
    m = _JSON_BLOCK.search(raw)
    if m:
        blob = m.group()
        try:
            return json.loads(blob, strict=False)
        except (json.JSONDecodeError, ValueError):
            # 3. Extract block + escape fix
            try:
                return json.loads(_fix_json_escapes(blob), strict=False)
            except (json.JSONDecodeError, ValueError):
                pass

    # 4. Escape-fix the full text, then extract block
    fixed = _fix_json_escapes(raw)
    m_fixed = _JSON_BLOCK.search(fixed)
    if m_fixed:
        try:
            return json.loads(m_fixed.group(), strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    # Total failure
    logger.warning(
        "%sFailed to parse JSON after lenient recovery (first 300 chars): %.300s",
        tag,
        raw,
    )
    return default


__all__ = ["loads_lenient", "_fix_json_escapes"]
