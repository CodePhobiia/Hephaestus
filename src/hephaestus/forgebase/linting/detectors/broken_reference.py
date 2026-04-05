"""BrokenReferenceDetector -- finds links whose target entity does not exist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


class BrokenReferenceDetector(LintDetector):
    """Detects links whose target entity does not exist in the current vault state.

    Checks target entities against pages, claims, and sources.
    """

    @property
    def name(self) -> str:
        return "broken_reference"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.BROKEN_REFERENCE]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        all_links = await state.links()

        if not all_links:
            return []

        # Build a set of all known entity IDs (pages, claims, sources)
        known_ids: set[str] = set()

        for page, _pv in await state.pages():
            known_ids.add(str(page.page_id))

        for claim_id in await state.claims():
            known_ids.add(str(claim_id))

        for source, _sv in await state.sources():
            known_ids.add(str(source.source_id))

        findings: list[RawFinding] = []
        for link, lv in all_links:
            target_str = str(lv.target_entity)
            if target_str not in known_ids:
                findings.append(
                    RawFinding(
                        category=FindingCategory.BROKEN_REFERENCE,
                        severity=FindingSeverity.WARNING,
                        description=(
                            f"Link '{link.link_id}' references non-existent "
                            f"target '{lv.target_entity}'."
                        ),
                        affected_entity_ids=[link.link_id],
                        normalized_subject=f"{link.link_id}:{lv.target_entity}",
                        suggested_action="Remove the broken link or create the missing target entity.",
                        confidence=1.0,
                    )
                )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the link no longer exists or its target now exists."""
        if not original_finding.affected_entity_ids:
            return True

        original_link_ids = {str(eid) for eid in original_finding.affected_entity_ids}

        # Check if any new broken-reference finding still contains these links
        for finding in new_findings:
            new_ids = {str(eid) for eid in finding.affected_entity_ids}
            if original_link_ids & new_ids:
                return False

        return True
