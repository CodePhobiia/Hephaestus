"""UnresolvedTodoDetector -- scans page content for TODO/FIXME/TBD/PLACEHOLDER."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState

# Case-insensitive pattern matching TODO, FIXME, TBD, PLACEHOLDER
_TODO_PATTERN = re.compile(
    r"\b(TODO|FIXME|TBD|PLACEHOLDER)\b",
    re.IGNORECASE,
)


class UnresolvedTodoDetector(LintDetector):
    """Detects pages containing unresolved TODO/FIXME/TBD/PLACEHOLDER markers.

    Scans page content bytes (decoded as UTF-8) for the marker patterns.
    One finding per affected page.
    """

    @property
    def name(self) -> str:
        return "unresolved_todo"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.UNRESOLVED_TODO]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        all_pages = await state.pages()

        findings: list[RawFinding] = []
        for page, _pv in all_pages:
            try:
                content_bytes = await state.page_content(page.page_id)
            except (ValueError, KeyError):
                continue

            text = content_bytes.decode("utf-8", errors="replace")
            matches = _TODO_PATTERN.findall(text)

            if matches:
                unique_markers = sorted(set(m.upper() for m in matches))
                desc = (
                    f"Page '{page.page_key}' contains unresolved markers: "
                    f"{', '.join(unique_markers)} ({len(matches)} occurrence(s))."
                )
                findings.append(
                    RawFinding(
                        category=FindingCategory.UNRESOLVED_TODO,
                        severity=FindingSeverity.INFO,
                        description=desc,
                        affected_entity_ids=[page.page_id],
                        normalized_subject=str(page.page_id),
                        suggested_action="Resolve or remove TODO/FIXME/TBD/PLACEHOLDER markers.",
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
        """Resolved if the page no longer contains TODO markers."""
        if not original_finding.affected_entity_ids:
            return True

        original_page_str = str(original_finding.affected_entity_ids[0])

        # Check if any new finding still references this page
        for finding in new_findings:
            for eid in finding.affected_entity_ids:
                if str(eid) == original_page_str:
                    return False

        return True
