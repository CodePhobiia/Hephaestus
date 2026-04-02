"""Lenient JSON parsing that survives Qwen/LLM output quirks.

Qwen 3.6 Free outputs invalid escapes like \\s, \\p, \\d inside JSON strings
that crash standard json.loads(). This module patches them before parsing.
"""
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The problem: Qwen emits \\s, \\p, \\d etc. — invalid JSON escapes
# Valid JSON escapes: ", \, /, b, f, n, r, t, uXXXX
# ---------------------------------------------------------------------------


def _fix_escapes(text: str) -> str:
    """Double invalid backslash escapes so json.loads() accepts them.

    Walks the string character by character to avoid mangling
    valid \\uXXXX or \\n escapes.
    """
    VALID_ESCAPES = set('"\\/bfnrt')

    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            nxt = text[i + 1]

            # Valid \\uXXXX — pass through
            if nxt == 'u' and i + 5 < len(text):
                suffix = text[i + 2 : i + 6]
                if all(c in '0123456789abcdefABCDEF' for c in suffix):
                    out.append(text[i : i + 6])
                    i += 6
                    continue

            # Valid single-char escape — pass through
            if nxt in VALID_ESCAPES:
                out.append(text[i : i + 2])
                i += 2
                continue

            # Backslash at end of string — leave as-is
            if i + 1 >= len(text):
                out.append(text[i:])
                i = len(text)
                continue

            # Invalid escape like \\s, \\p, \\d → double it: \\\\s, \\\\p
            out.append('\\\\')
            out.append(nxt)
            i += 2
            continue

        out.append(text[i])
        i += 1

    return ''.join(out)


def loads(text: str, *, default: Any = None, label: str = "") -> Any:
    """Parse JSON with lenient escape handling.

    Tries progressively more aggressive fixes:
    1. json.loads (strict=False) as-is
    2. Fix invalid backslash escapes
    3. Extract JSON blocks from surrounding text
    4. Fix escapes + extract blocks

    On total failure returns *default*.
    """
    if not text or not text.strip():
        return default

    cleaned = text.strip()

    # 1. Try strict=False as-is (allows control chars in strings)
    try:
        return json.loads(cleaned, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Fix escapes and try again
    fixed = _fix_escapes(cleaned)
    if fixed != cleaned:
        try:
            return json.loads(fixed, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Extract JSON objects/arrays from surrounding markdown/text
    for pattern in (r'\{.*\}', r'\[.*\]'):
        m = re.search(pattern, cleaned, re.DOTALL)
        if m:
            block = m.group()
            try:
                return json.loads(block, strict=False)
            except (json.JSONDecodeError, ValueError):
                pass
            # 4. Fix escapes on the extracted block
            fixed_block = _fix_escapes(block)
            if fixed_block != block:
                try:
                    return json.loads(fixed_block, strict=False)
                except (json.JSONDecodeError, ValueError):
                    pass

    tag = f"[{label}] " if label else ""
    logger.debug(
        "%sFailed to parse JSON after lenient recovery (first 200 chars):\n%.200s",
        tag,
        text,
    )
    return default
