"""
Hephaestus prompt management — system prompt assembly and variable population.
"""

from hephaestus.prompts.system_prompt import (
    VALID_DIVERGENCE_INTENSITIES,
    VALID_OUTPUT_LENGTHS,
    VALID_OUTPUT_MODES,
    build_system_prompt,
)

__all__ = [
    "build_system_prompt",
    "VALID_OUTPUT_MODES",
    "VALID_DIVERGENCE_INTENSITIES",
    "VALID_OUTPUT_LENGTHS",
]
