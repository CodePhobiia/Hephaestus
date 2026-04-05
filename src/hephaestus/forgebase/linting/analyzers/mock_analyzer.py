"""Mock LintAnalyzer for testing."""

from __future__ import annotations

from hephaestus.forgebase.linting.analyzer import (
    ContradictionResult,
    LintAnalyzer,
    ResolvabilityAssessment,
    SourceGapAssessment,
)


class MockLintAnalyzer(LintAnalyzer):
    """Returns deterministic results for testing.

    Contradiction detection uses a simple keyword heuristic: if exactly one
    of the two claims contains the word "not" (case-insensitive), the pair
    is flagged as contradictory.  This is intentionally naive — the real
    Anthropic analyzer will use LLM reasoning.
    """

    async def detect_contradictions(
        self,
        claim_pairs: list[tuple[str, str]],
    ) -> list[ContradictionResult]:
        results: list[ContradictionResult] = []
        for a, b in claim_pairs:
            a_has_not = "not" in a.lower()
            b_has_not = "not" in b.lower()
            is_contra = a_has_not != b_has_not
            results.append(
                ContradictionResult(
                    is_contradictory=is_contra,
                    explanation=f"Mock analysis of '{a[:30]}' vs '{b[:30]}'",
                    confidence=0.8 if is_contra else 0.2,
                )
            )
        return results

    async def assess_source_gaps(
        self,
        concept: str,
        evidence_count: int,
        claims: list[str],
    ) -> SourceGapAssessment:
        is_gap = evidence_count < 2
        return SourceGapAssessment(
            is_gap=is_gap,
            severity="moderate" if is_gap else "minor",
            explanation=f"Mock: {concept} has {evidence_count} source(s)",
        )

    async def check_resolvable_by_search(
        self,
        claim: str,
        existing_support: list[str],
    ) -> ResolvabilityAssessment:
        is_resolvable = len(existing_support) < 2
        return ResolvabilityAssessment(
            is_resolvable=is_resolvable,
            search_query=f"evidence for: {claim[:50]}",
            confidence=0.7 if is_resolvable else 0.3,
        )
