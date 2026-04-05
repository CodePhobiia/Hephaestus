"""
Output Formatting System.

Formats Hephaestus invention reports in multiple output formats and
generates formal novelty proofs backed by prior art searches.

Components
----------
:class:`~hephaestus.output.formatter.OutputFormatter`
    Renders :class:`~hephaestus.output.formatter.InventionReport` as
    Markdown, JSON, or plain text.
:class:`~hephaestus.output.proof.NoveltyProofGenerator`
    Generates formal novelty proofs from pipeline results.
:class:`~hephaestus.output.prior_art.PriorArtSearcher`
    Searches Google Patents and Semantic Scholar for prior art.

Quick start::

    from hephaestus.output import (
        InventionReport,
        OutputFormatter,
        OutputFormat,
        NoveltyProofGenerator,
        PriorArtSearcher,
    )

    formatter = OutputFormatter()
    report = InventionReport(
        problem="my problem",
        structural_form="abstract structure",
        invention_name="MyInvention",
        source_domain="Biology",
        domain_distance=0.92,
        structural_fidelity=0.88,
        novelty_score=0.90,
        mechanism="...",
        translation="...",
        architecture="...",
        where_analogy_breaks="...",
    )
    print(formatter.format(report))  # Markdown by default
"""

from hephaestus.output.formatter import (
    AlternativeInvention,
    InventionReport,
    OutputFormat,
    OutputFormatter,
)
from hephaestus.output.prior_art import (
    PaperResult,
    PatentResult,
    PriorArtReport,
    PriorArtSearcher,
)
from hephaestus.output.proof import (
    DomainDistanceAnalysis,
    MechanismOriginalityAnalysis,
    NoveltyProof,
    NoveltyProofGenerator,
    PriorArtAnalysis,
    StructuralMappingAnalysis,
)

__all__ = [
    # Formatter
    "OutputFormatter",
    "OutputFormat",
    "InventionReport",
    "AlternativeInvention",
    # Prior art
    "PriorArtSearcher",
    "PriorArtReport",
    "PatentResult",
    "PaperResult",
    # Proof
    "NoveltyProofGenerator",
    "NoveltyProof",
    "StructuralMappingAnalysis",
    "DomainDistanceAnalysis",
    "PriorArtAnalysis",
    "MechanismOriginalityAnalysis",
]
