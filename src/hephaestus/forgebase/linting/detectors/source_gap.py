"""SourceGapDetector — detects concepts with insufficient source coverage."""
from __future__ import annotations

from collections import defaultdict

from hephaestus.forgebase.domain.enums import (
    CandidateStatus,
    FindingCategory,
    FindingSeverity,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.analyzer import LintAnalyzer
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding
from hephaestus.forgebase.linting.state import VaultLintState

# Minimum unique sources required for a concept to be considered well-covered.
_MIN_SOURCES = 2


class SourceGapDetector(LintDetector):
    """Detects concepts backed by fewer than N distinct sources.

    Prefilter: group active concept candidates by ``normalized_name``,
    count unique ``source_id`` values per group.  Only groups with fewer
    than ``_MIN_SOURCES`` are sent to the analyzer.

    Analysis: ``analyzer.assess_source_gaps(concept, evidence_count, claims)``
    for each thin concept.
    """

    def __init__(self, analyzer: LintAnalyzer) -> None:
        self._analyzer = analyzer

    @property
    def name(self) -> str:
        return "source_gap"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.SOURCE_GAP]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        candidates = await state.candidates()

        # Group active candidates by normalized_name
        clusters: dict[str, list] = defaultdict(list)
        for c in candidates:
            if c.status == CandidateStatus.ACTIVE:
                clusters[c.normalized_name].append(c)

        findings: list[RawFinding] = []

        for concept_name, cluster in clusters.items():
            unique_sources = len({str(c.source_id) for c in cluster})
            if unique_sources >= _MIN_SOURCES:
                continue  # Well-covered, skip

            # Gather claim statements for this concept from related pages
            # (For now we pass the candidate names as context.)
            claim_texts: list[str] = [c.name for c in cluster]

            assessment = await self._analyzer.assess_source_gaps(
                concept=concept_name,
                evidence_count=unique_sources,
                claims=claim_texts,
            )

            if assessment.is_gap:
                # Use the first candidate's id as representative entity
                representative = cluster[0]
                findings.append(
                    RawFinding(
                        category=FindingCategory.SOURCE_GAP,
                        severity=FindingSeverity.INFO
                        if assessment.severity == "minor"
                        else FindingSeverity.WARNING,
                        description=(
                            f"Concept '{concept_name}' has only {unique_sources} "
                            f"source(s) — {assessment.explanation}"
                        ),
                        affected_entity_ids=[representative.candidate_id],
                        normalized_subject=concept_name,
                        suggested_action="Add more independent sources for this concept.",
                        confidence=0.7,
                    )
                )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the concept now has enough sources."""
        candidates = await current_state.candidates()

        # The normalized_subject stores the concept name
        # Look for the same concept in current candidates
        subject = original_finding.description  # fallback
        # Extract concept name from affected_entity_ids or description
        # Use a simple heuristic: if no new finding matches the same entities
        for new_f in new_findings:
            if (
                new_f.category == FindingCategory.SOURCE_GAP
                and new_f.affected_entity_ids == original_finding.affected_entity_ids
            ):
                return False  # Still flagged

        # If no new finding matched, check if the entity still exists
        for eid in original_finding.affected_entity_ids:
            found = any(c.candidate_id == eid for c in candidates)
            if not found:
                return True  # Entity gone

        # Entity exists but no new finding — gap was filled
        return True
