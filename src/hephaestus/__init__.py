"""
Hephaestus — The Invention Engine.

Produces genuinely novel solutions to any problem by discovering and translating
solved patterns from distant knowledge domains.

Quick start::

    from hephaestus import Hephaestus

    async with Hephaestus.from_env() as heph:
        result = await heph.invent("I need a load balancer for traffic spikes")
        print(result.top_invention.invention_name)
        print(f"From: {result.top_invention.source_domain}")
        print(f"Novelty: {result.top_invention.novelty_score:.2f}")
        print(f"Cost: ${result.total_cost_usd:.2f}")

CLI::

    heph "I need a load balancer that handles unpredictable traffic spikes"
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Theyab & Butters"
__license__ = "MIT"

# High-level SDK client (primary user-facing class)
# Core pipeline
from hephaestus.core.genesis import (
    CostBreakdown,
    Genesis,
    GenesisConfig,
    GenesisError,
    InventionReport,
    PipelineStage,
    PipelineUpdate,
)

# DeepForge harness
from hephaestus.deepforge.harness import (
    DeepForgeHarness,
    ForgeResult,
    ForgeTrace,
    HarnessConfig,
)
from hephaestus.research import (
    BenchmarkCase,
    BenchmarkCorpus,
    BenchmarkCorpusBuilder,
    PerplexityClient,
    ResearchError,
)
from hephaestus.sdk.client import ConfigurationError, Hephaestus, HephaestusError

__all__ = [
    "__version__",
    # SDK
    "Hephaestus",
    "HephaestusError",
    "ConfigurationError",
    # Genesis
    "Genesis",
    "GenesisConfig",
    "InventionReport",
    "PipelineUpdate",
    "PipelineStage",
    "CostBreakdown",
    "GenesisError",
    # DeepForge
    "DeepForgeHarness",
    "HarnessConfig",
    "ForgeResult",
    "ForgeTrace",
    # Research
    "BenchmarkCase",
    "BenchmarkCorpus",
    "BenchmarkCorpusBuilder",
    "PerplexityClient",
    "ResearchError",
]
