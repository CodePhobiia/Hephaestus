"""ResolvableBySearchDetector — detects claims that could be strengthened by web search."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    FindingCategory,
    FindingSeverity,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.analyzer import LintAnalyzer
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding
from hephaestus.forgebase.linting.state import VaultLintState


class ResolvableBySearchDetector(LintDetector):
    """Detects weakly-supported claims that could be resolved via web search.

    Prefilter: claims with weak or no support (SUPPORTED with few supports,
    or INFERRED/HYPOTHESIS status).  Excludes claims already flagged as
    UNSUPPORTED (zero supports) to avoid overlap with UnsupportedClaimDetector.

    Analysis: ``analyzer.check_resolvable_by_search(claim_statement, existing_support)``
    for each candidate claim.
    """

    def __init__(self, analyzer: LintAnalyzer) -> None:
        self._analyzer = analyzer

    @property
    def name(self) -> str:
        return "resolvable_by_search"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.RESOLVABLE_BY_SEARCH]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        all_claims = await state.claims()

        findings: list[RawFinding] = []

        for claim_id, (cv, supports, _derivations) in all_claims.items():
            # Skip claims with zero supports — those are covered by UnsupportedClaimDetector
            if cv.status == ClaimStatus.SUPPORTED and len(supports) == 0:
                continue

            # Target: claims with weak support (few supports) or non-SUPPORTED status
            is_weak = False
            if (
                cv.status in (ClaimStatus.INFERRED, ClaimStatus.HYPOTHESIS)
                or cv.status == ClaimStatus.SUPPORTED
                and len(supports) < 2
            ):
                is_weak = True

            if not is_weak:
                continue

            # Ask the analyzer
            support_texts = [s.source_segment or "" for s in supports]
            assessment = await self._analyzer.check_resolvable_by_search(
                claim=cv.statement,
                existing_support=support_texts,
            )

            if assessment.is_resolvable:
                claim = await state._uow.claims.get(claim_id)
                page_id = claim.page_id if claim else None
                findings.append(
                    RawFinding(
                        category=FindingCategory.RESOLVABLE_BY_SEARCH,
                        severity=FindingSeverity.INFO,
                        description=(
                            f"Claim '{cv.statement[:80]}' may be resolvable "
                            f"via search: '{assessment.search_query}'"
                        ),
                        affected_entity_ids=[claim_id],
                        normalized_subject=cv.statement,
                        suggested_action=f"Search for: {assessment.search_query}",
                        confidence=assessment.confidence,
                        page_id=page_id,
                        claim_id=claim_id,
                    )
                )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the claim now has stronger support."""
        if original_finding.claim_id is None:
            return True

        all_claims = await current_state.claims()
        claim_data = all_claims.get(original_finding.claim_id)

        if claim_data is None:
            return True  # Claim no longer exists

        cv, supports, _derivations = claim_data
        # Resolved if the claim now has 2+ supports (no longer weak)
        return bool(cv.status == ClaimStatus.SUPPORTED and len(supports) >= 2)
