"""ForgeBase integration bridge — connects upstream Hephaestus systems to ForgeBase."""

from __future__ import annotations

from hephaestus.forgebase.integration.bridge import (
    DefaultForgeBaseBridge,
    ForgeBaseIntegrationBridge,
    NoOpBridge,
)
from hephaestus.forgebase.integration.genesis_adapter import GenesisAdapter
from hephaestus.forgebase.integration.invention_ingester import InventionIngester
from hephaestus.forgebase.integration.pantheon_adapter import PantheonAdapter
from hephaestus.forgebase.integration.pantheon_ingester import PantheonIngester
from hephaestus.forgebase.integration.research_adapter import ResearchAdapter

__all__ = [
    "DefaultForgeBaseBridge",
    "ForgeBaseIntegrationBridge",
    "GenesisAdapter",
    "InventionIngester",
    "NoOpBridge",
    "PantheonAdapter",
    "PantheonIngester",
    "ResearchAdapter",
]
