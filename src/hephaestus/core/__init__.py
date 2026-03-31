"""
Hephaestus Core — Genesis Invention Pipeline.

Five-stage pipeline for producing genuinely novel cross-domain inventions:

Stage 1 — DECOMPOSE  :class:`hephaestus.core.decomposer.ProblemDecomposer`
Stage 2 — SEARCH     :class:`hephaestus.core.searcher.CrossDomainSearcher`
Stage 3 — SCORE      :class:`hephaestus.core.scorer.CandidateScorer`
Stage 4 — TRANSLATE  :class:`hephaestus.core.translator.SolutionTranslator`
Stage 5 — VERIFY     :class:`hephaestus.core.verifier.NoveltyVerifier`
Orchestrator         :class:`hephaestus.core.genesis.Genesis`

Quickstart::

    from hephaestus.core import Genesis, GenesisConfig

    genesis = Genesis(GenesisConfig(
        anthropic_api_key="...",
        openai_api_key="...",
    ))
    report = await genesis.invent("describe your problem here")
    print(report.top_invention.invention_name)
"""

from hephaestus.core.decomposer import (
    DecompositionError,
    ProblemDecomposer,
    ProblemStructure,
)
from hephaestus.core.genesis import (
    CostBreakdown,
    Genesis,
    GenesisConfig,
    GenesisError,
    InventionReport,
    PipelineStage,
    PipelineUpdate,
)
from hephaestus.core.scorer import (
    CandidateScorer,
    ScoredCandidate,
    ScoringError,
)
from hephaestus.core.searcher import (
    CrossDomainSearcher,
    SearchCandidate,
    SearchError,
)
from hephaestus.core.translator import (
    ElementMapping,
    SolutionTranslator,
    Translation,
    TranslationError,
)
from hephaestus.core.verifier import (
    AdversarialResult,
    NoveltyVerifier,
    VerificationError,
    VerifiedInvention,
)

__all__ = [
    # Decomposer
    "ProblemDecomposer",
    "ProblemStructure",
    "DecompositionError",
    # Searcher
    "CrossDomainSearcher",
    "SearchCandidate",
    "SearchError",
    # Scorer
    "CandidateScorer",
    "ScoredCandidate",
    "ScoringError",
    # Translator
    "SolutionTranslator",
    "Translation",
    "ElementMapping",
    "TranslationError",
    # Verifier
    "NoveltyVerifier",
    "VerifiedInvention",
    "AdversarialResult",
    "VerificationError",
    # Genesis orchestrator
    "Genesis",
    "GenesisConfig",
    "GenesisError",
    "InventionReport",
    "CostBreakdown",
    "PipelineStage",
    "PipelineUpdate",
]
