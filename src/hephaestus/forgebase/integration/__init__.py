"""ForgeBase integration bridge — connects upstream Hephaestus systems to ForgeBase."""
from __future__ import annotations

from hephaestus.forgebase.integration.bridge import (
    DefaultForgeBaseBridge,
    ForgeBaseIntegrationBridge,
    NoOpBridge,
)
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter

__all__ = [
    "DefaultForgeBaseBridge",
    "ForgeBaseIntegrationBridge",
    "GenesisAdapter",
    "NoOpBridge",
    "PantheonAdapter",
    "ResearchAdapter",
]
