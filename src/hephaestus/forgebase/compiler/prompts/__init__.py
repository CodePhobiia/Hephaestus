"""Versioned prompt templates for the ForgeBase compiler.

Each sub-module exports:
    PROMPT_ID          — unique identifier for the prompt
    PROMPT_VERSION     — semver string (e.g. "1.0.0")
    SCHEMA_VERSION     — integer schema version for the OUTPUT_SCHEMA
    SYSTEM_PROMPT      — system-role instruction text
    USER_PROMPT_TEMPLATE — user-role template with {placeholders}
    OUTPUT_SCHEMA      — JSON Schema dict for structured output validation

The synthesis module additionally exports multiple prompt sets for
different page types (concept, mechanism, comparison, timeline,
open questions).
"""

from __future__ import annotations

from hephaestus.forgebase.compiler.prompts import (
    claim_extraction,
    concept_extraction,
    evidence_grading,
    source_card,
    synthesis,
)

ALL_PROMPT_MODULES = [
    claim_extraction,
    concept_extraction,
    source_card,
    evidence_grading,
    synthesis,
]

__all__ = [
    "claim_extraction",
    "concept_extraction",
    "evidence_grading",
    "source_card",
    "synthesis",
    "ALL_PROMPT_MODULES",
]
