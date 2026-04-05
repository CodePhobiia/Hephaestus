"""UnsupportedClaimDetector — detects claims with SUPPORTED status but no support records."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.analyzer import LintAnalyzer
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding
from hephaestus.forgebase.linting.state import VaultLintState


class UnsupportedClaimDetector(LintDetector):
    """Finds claims marked SUPPORTED that have zero ClaimSupport records.

    This is a data-only detector: claims with zero supports are automatically
    findings (no LLM reasoning needed).  The LLM part (grading borderline
    evidence) is deferred to a future version.  The analyzer is accepted in
    the constructor to keep the interface consistent with other LLM detectors.
    """

    def __init__(self, analyzer: LintAnalyzer) -> None:
        self._analyzer = analyzer

    @property
    def name(self) -> str:
        return "unsupported_claim"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.UNSUPPORTED_CLAIM]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        unsupported = await state.claims_without_support()
        findings: list[RawFinding] = []
        for claim, cv in unsupported:
            findings.append(
                RawFinding(
                    category=FindingCategory.UNSUPPORTED_CLAIM,
                    severity=FindingSeverity.WARNING,
                    description=(
                        f"Claim '{cv.statement[:80]}' has SUPPORTED status "
                        f"but no supporting evidence records."
                    ),
                    affected_entity_ids=[claim.claim_id],
                    normalized_subject=cv.statement,
                    suggested_action="Add supporting evidence or change claim status.",
                    confidence=1.0,
                    page_id=claim.page_id,
                    claim_id=claim.claim_id,
                )
            )
        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the claim now has support or its status changed from SUPPORTED."""
        if original_finding.claim_id is None:
            return True

        all_claims = await current_state.claims()
        claim_data = all_claims.get(original_finding.claim_id)

        if claim_data is None:
            # Claim no longer exists — resolved
            return True

        cv, supports, _derivations = claim_data
        # Resolved if status changed away from SUPPORTED, or supports were added
        from hephaestus.forgebase.domain.enums import ClaimStatus

        if cv.status != ClaimStatus.SUPPORTED:
            return True
        return len(supports) > 0
