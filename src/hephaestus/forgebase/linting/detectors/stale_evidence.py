"""StaleEvidenceDetector -- finds claims with expired freshness."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


class StaleEvidenceDetector(LintDetector):
    """Detects claims whose ``fresh_until`` timestamp has expired.

    Findings are aggregated per page: if multiple stale claims belong
    to the same page, a single finding is produced for that page with
    all affected claim IDs listed.
    """

    @property
    def name(self) -> str:
        return "stale_evidence"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.STALE_EVIDENCE]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        now = datetime.now(UTC)
        stale_claims = await state.claims_past_freshness(now)

        if not stale_claims:
            return []

        # Aggregate stale claims per page
        by_page: dict[EntityId, list[tuple]] = defaultdict(list)
        for claim, cv in stale_claims:
            by_page[claim.page_id].append((claim, cv))

        findings: list[RawFinding] = []
        for page_id, claims_list in by_page.items():
            claim_ids = [c.claim_id for c, _cv in claims_list]
            statements = [cv.statement for _c, cv in claims_list]
            count = len(claims_list)
            desc = f"{count} claim(s) on this page have expired freshness: " + "; ".join(
                statements[:3]
            )
            if count > 3:
                desc += f" ... and {count - 3} more"

            findings.append(
                RawFinding(
                    category=FindingCategory.STALE_EVIDENCE,
                    severity=FindingSeverity.WARNING,
                    description=desc,
                    affected_entity_ids=claim_ids,
                    normalized_subject="|".join(sorted(str(cid) for cid in claim_ids)),
                    suggested_action="Re-validate claims or update fresh_until dates.",
                    confidence=1.0,
                    page_id=page_id,
                )
            )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if none of the originally-affected claims are still stale."""
        if not original_finding.affected_entity_ids:
            return True

        original_ids = {str(eid) for eid in original_finding.affected_entity_ids}

        # Check if any new finding still references these claim IDs
        for finding in new_findings:
            new_ids = {str(eid) for eid in finding.affected_entity_ids}
            if original_ids & new_ids:
                return False

        return True
