"""LintAnalyzer ABC — lint-specific LLM reasoning contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContradictionResult:
    """Result of analyzing whether two claims contradict each other."""

    is_contradictory: bool
    explanation: str
    confidence: float


@dataclass
class SourceGapAssessment:
    """Assessment of whether a concept has insufficient source coverage."""

    is_gap: bool
    severity: str  # critical, moderate, minor
    explanation: str


@dataclass
class ResolvabilityAssessment:
    """Assessment of whether a claim's weakness could be resolved by web search."""

    is_resolvable: bool
    search_query: str
    confidence: float


class LintAnalyzer(ABC):
    """Lint-specific LLM reasoning — dedicated contract, separate from CompilerBackend.

    Implementations provide the analytical intelligence behind LLM-assisted
    lint detectors (contradiction detection, source gap assessment, search
    resolvability). The interface is deliberately narrow: each method maps
    to exactly one detector family.
    """

    @abstractmethod
    async def detect_contradictions(
        self,
        claim_pairs: list[tuple[str, str]],
    ) -> list[ContradictionResult]:
        """Analyse pairs of claims for contradictions.

        Args:
            claim_pairs: Pairs of claim text (a, b) to compare.

        Returns:
            One ContradictionResult per pair, in the same order.
        """
        ...

    @abstractmethod
    async def assess_source_gaps(
        self,
        concept: str,
        evidence_count: int,
        claims: list[str],
    ) -> SourceGapAssessment:
        """Assess whether a concept has a meaningful source gap.

        Args:
            concept: The concept name or identifier.
            evidence_count: Number of distinct sources backing the concept.
            claims: The claim texts associated with this concept.

        Returns:
            A single SourceGapAssessment.
        """
        ...

    @abstractmethod
    async def check_resolvable_by_search(
        self,
        claim: str,
        existing_support: list[str],
    ) -> ResolvabilityAssessment:
        """Check whether a weakly-supported claim could be resolved via web search.

        Args:
            claim: The claim text to evaluate.
            existing_support: Descriptions of current supporting evidence.

        Returns:
            A single ResolvabilityAssessment with a suggested search query.
        """
        ...
