"""OrphanedPageDetector -- finds pages with no incoming links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


class OrphanedPageDetector(LintDetector):
    """Detects pages that have zero inbound links.

    SOURCE_CARD and SOURCE_INDEX pages are excluded by the prefilter
    (``pages_with_zero_inbound_links`` already handles this).
    """

    @property
    def name(self) -> str:
        return "orphaned_page"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.ORPHANED_PAGE]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        orphans = await state.pages_with_zero_inbound_links()

        findings: list[RawFinding] = []
        for page in orphans:
            findings.append(
                RawFinding(
                    category=FindingCategory.ORPHANED_PAGE,
                    severity=FindingSeverity.INFO,
                    description=f"Page '{page.page_key}' has no incoming links.",
                    affected_entity_ids=[page.page_id],
                    normalized_subject=str(page.page_id),
                    suggested_action="Add backlinks from related pages or remove if no longer needed.",
                    confidence=1.0,
                    page_id=page.page_id,
                )
            )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the page now has incoming links or no longer exists."""
        if not original_finding.affected_entity_ids:
            return True

        original_page_id = original_finding.affected_entity_ids[0]
        original_str = str(original_page_id)

        # Check if the page still appears in current orphans
        for finding in new_findings:
            for eid in finding.affected_entity_ids:
                if str(eid) == original_str:
                    return False

        return True
