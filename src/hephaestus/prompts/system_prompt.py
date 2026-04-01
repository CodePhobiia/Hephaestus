"""
Hephaestus V2 system prompt — template extraction and variable population.

The master prompt lives in ``SYSTEM_PROMPT_V2.md`` and is extracted at import
time.  ``build_system_prompt()`` populates the ``{{variable}}`` placeholders
and returns the ready-to-inject string.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Valid parameter values (from the V2 spec)
# ---------------------------------------------------------------------------

VALID_OUTPUT_MODES: tuple[str, ...] = (
    "MECHANISM",
    "FRAMEWORK",
    "NARRATIVE",
    "SYSTEM",
    "PROTOCOL",
    "TAXONOMY",
    "INTERFACE",
)

VALID_DIVERGENCE_INTENSITIES: tuple[str, ...] = (
    "STANDARD",
    "AGGRESSIVE",
    "MAXIMUM",
)

VALID_OUTPUT_LENGTHS: tuple[str, ...] = (
    "DENSE",
    "FULL",
    "EXPANSIVE",
)

# ---------------------------------------------------------------------------
# Template extraction (runs once at import time)
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).parent / "SYSTEM_PROMPT_V2.md"


def _extract_template() -> str:
    """Extract the content between <system_prompt> and </system_prompt> tags."""
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"<system_prompt>\s*\n(.*?)\n</system_prompt>",
        raw,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"Could not find <system_prompt>...</system_prompt> in {_TEMPLATE_PATH}"
        )
    return match.group(1)


# Cache the template on first import
_SYSTEM_PROMPT_TEMPLATE: str = _extract_template()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_system_prompt(
    user_prompt: str,
    anti_memory_zone: str = "",
    banned_baselines: str = "",
    domain_a: str = "",
    domain_b: str = "",
    output_mode: str = "MECHANISM",
    divergence_intensity: str = "STANDARD",
    output_length: str = "FULL",
) -> str:
    """
    Populate all ``{{variables}}`` in the V2 system prompt template.

    Parameters
    ----------
    user_prompt:
        The user's creative/intellectual target.
    anti_memory_zone:
        Accumulated exclusion zone from prior runs (can be empty on first run).
    banned_baselines:
        Concatenated obvious baselines to exclude.
    domain_a:
        Forced structural collision partner A.
    domain_b:
        Forced structural collision partner B.
    output_mode:
        One of VALID_OUTPUT_MODES (default ``MECHANISM``).
    divergence_intensity:
        One of VALID_DIVERGENCE_INTENSITIES (default ``STANDARD``).
    output_length:
        One of VALID_OUTPUT_LENGTHS (default ``FULL``).

    Returns
    -------
    str
        The complete system prompt with all variables populated.
    """
    # Validate enums
    output_mode = output_mode.upper()
    if output_mode not in VALID_OUTPUT_MODES:
        raise ValueError(
            f"Invalid output_mode {output_mode!r}. Must be one of {VALID_OUTPUT_MODES}"
        )

    divergence_intensity = divergence_intensity.upper()
    if divergence_intensity not in VALID_DIVERGENCE_INTENSITIES:
        raise ValueError(
            f"Invalid divergence_intensity {divergence_intensity!r}. "
            f"Must be one of {VALID_DIVERGENCE_INTENSITIES}"
        )

    output_length = output_length.upper()
    if output_length not in VALID_OUTPUT_LENGTHS:
        raise ValueError(
            f"Invalid output_length {output_length!r}. Must be one of {VALID_OUTPUT_LENGTHS}"
        )

    # Default anti-memory zone text for first run
    if not anti_memory_zone.strip():
        anti_memory_zone = "No prior concepts explored. The full solution space is open."

    # Default banned baselines text
    if not banned_baselines.strip():
        banned_baselines = "(No baselines provided — all consensus responses are still banned by default.)"

    # Default domains
    if not domain_a.strip():
        domain_a = "(No domain specified — select from the domain bank.)"
    if not domain_b.strip():
        domain_b = "(No domain specified — select from the domain bank.)"

    # Perform variable substitution
    prompt = _SYSTEM_PROMPT_TEMPLATE
    prompt = prompt.replace("{{anti_memory_exclusion_zone}}", anti_memory_zone)
    prompt = prompt.replace("{{banned_baselines}}", banned_baselines)
    prompt = prompt.replace("{{entropy_domain_1}}", domain_a)
    prompt = prompt.replace("{{entropy_domain_2}}", domain_b)
    prompt = prompt.replace("{{user_prompt}}", user_prompt)
    prompt = prompt.replace("{{output_mode}}", output_mode)
    prompt = prompt.replace("{{divergence_intensity}}", divergence_intensity)
    prompt = prompt.replace("{{output_length}}", output_length)

    return prompt


def get_template() -> str:
    """Return the raw system prompt template (with ``{{variables}}``)."""
    return _SYSTEM_PROMPT_TEMPLATE
