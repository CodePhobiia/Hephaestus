"""MissingCanonicalDetector -- finds promotion-worthy candidates with no page."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from hephaestus.forgebase.compiler.policy import SynthesisPolicy
from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


class MissingCanonicalDetector(LintDetector):
    """Detects promotion-worthy concept candidates that lack a canonical page.

    Requires a ``SynthesisPolicy`` to determine promotion thresholds.
    Candidates are grouped by ``normalized_name``; each group with
    unresolved candidates produces one finding.
    """

    def __init__(self, policy: SynthesisPolicy) -> None:
        self._policy = policy

    @property
    def name(self) -> str:
        return "missing_canonical"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.MISSING_CANONICAL]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        worthy = await state.candidates_promotion_worthy(self._policy)

        if not worthy:
            return []

        # Group by normalized_name to produce one finding per concept cluster
        clusters: dict[str, list] = defaultdict(list)
        for candidate in worthy:
            clusters[candidate.normalized_name].append(candidate)

        findings: list[RawFinding] = []
        for norm_name, candidates in clusters.items():
            candidate_ids = [c.candidate_id for c in candidates]
            source_count = len({str(c.source_id) for c in candidates})
            desc = (
                f"Concept '{candidates[0].name}' has {source_count} source(s) "
                f"and {len(candidates)} candidate(s) but no canonical page."
            )
            findings.append(
                RawFinding(
                    category=FindingCategory.MISSING_CANONICAL,
                    severity=FindingSeverity.INFO,
                    description=desc,
                    affected_entity_ids=candidate_ids,
                    normalized_subject=norm_name,
                    suggested_action="Create a canonical page for this concept via synthesis.",
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
        """Resolved if the candidates now have a resolved_page_id or have been rejected."""
        if not original_finding.affected_entity_ids:
            return True

        original_ids = {str(eid) for eid in original_finding.affected_entity_ids}

        # Check if any new finding still references these candidate IDs
        for finding in new_findings:
            new_ids = {str(eid) for eid in finding.affected_entity_ids}
            if original_ids & new_ids:
                return False

        return True
