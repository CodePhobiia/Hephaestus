"""Perplexity-powered research primitives for Hephaestus."""

from hephaestus.research.benchmark_builder import BenchmarkCorpusBuilder
from hephaestus.research.perplexity import (
    BaselineDossier,
    BenchmarkCase,
    BenchmarkCorpus,
    ExternalGroundingReport,
    ImplementationRiskReview,
    PerplexityClient,
    PriorArtFinding,
    ResearchCitation,
    ResearchError,
    WorkspaceResearchDossier,
    build_research_reference_state,
    snapshot_research_artifact,
)

__all__ = [
    "BaselineDossier",
    "BenchmarkCase",
    "BenchmarkCorpus",
    "BenchmarkCorpusBuilder",
    "ExternalGroundingReport",
    "ImplementationRiskReview",
    "PerplexityClient",
    "PriorArtFinding",
    "ResearchCitation",
    "ResearchError",
    "WorkspaceResearchDossier",
    "build_research_reference_state",
    "snapshot_research_artifact",
]
