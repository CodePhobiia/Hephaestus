"""Transliminality Engine — Layer 2 of the Hephaestus invention stack.

Retrieves structurally compatible mechanisms from remote domains, validates
whether the analogy is real, and injects that bridge into invention-time
reasoning.  Sits between ForgeBase/fusion (knowledge) and Genesis/DeepForge
(generation), with Pantheon providing verification.
"""

from hephaestus.transliminality.domain.enums import TransliminalityMode
from hephaestus.transliminality.domain.models import (
    TransliminalityConfig,
    TransliminalityPack,
    TransliminalityRequest,
)
from hephaestus.transliminality.service.engine import BuildPackResult

__all__ = [
    "BuildPackResult",
    "TransliminalityConfig",
    "TransliminalityMode",
    "TransliminalityPack",
    "TransliminalityRequest",
]
