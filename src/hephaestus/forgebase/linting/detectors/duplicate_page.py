"""DuplicatePageDetector -- finds pages with identical normalized titles."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


def _normalize_title(title: str) -> str:
    """Lowercase and strip whitespace for comparison."""
    return title.strip().lower()


class DuplicatePageDetector(LintDetector):
    """Detects pages whose titles match after normalization (lowercase + strip).

    Produces one finding per duplicate group (2+ pages with the same
    normalized title).
    """

    @property
    def name(self) -> str:
        return "duplicate_page"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.DUPLICATE_PAGE]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        all_pages = await state.pages()

        # Group by normalized title
        groups: dict[str, list[tuple[EntityId, str]]] = defaultdict(list)
        for page, pv in all_pages:
            norm = _normalize_title(pv.title)
            groups[norm].append((page.page_id, pv.title))

        findings: list[RawFinding] = []
        for norm_title, page_entries in groups.items():
            if len(page_entries) < 2:
                continue

            page_ids = [pid for pid, _title in page_entries]
            titles = [t for _pid, t in page_entries]
            desc = (
                f"{len(page_entries)} pages share the normalized title "
                f"'{norm_title}': {', '.join(titles)}"
            )

            findings.append(
                RawFinding(
                    category=FindingCategory.DUPLICATE_PAGE,
                    severity=FindingSeverity.WARNING,
                    description=desc,
                    affected_entity_ids=page_ids,
                    normalized_subject=norm_title,
                    suggested_action="Merge duplicate pages or differentiate their titles.",
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
        """Resolved if the original set of pages no longer forms a duplicate group."""
        if not original_finding.affected_entity_ids:
            return True

        original_ids = {str(eid) for eid in original_finding.affected_entity_ids}

        # Check if any new duplicate-group finding still contains all the
        # original affected entities (or any overlapping subset of 2+).
        for finding in new_findings:
            new_ids = {str(eid) for eid in finding.affected_entity_ids}
            overlap = original_ids & new_ids
            if len(overlap) >= 2:
                return False

        return True
