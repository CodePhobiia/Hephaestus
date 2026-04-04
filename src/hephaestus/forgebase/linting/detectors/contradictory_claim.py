"""ContradictoryClaimDetector — detects contradicting claims on the same page."""
from __future__ import annotations

from collections import defaultdict

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.analyzer import LintAnalyzer
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding
from hephaestus.forgebase.linting.state import VaultLintState

# Limit per page to prevent combinatorial explosion.
_MAX_CLAIMS_PER_PAGE = 10
_MAX_PAIRS_PER_PAGE = 50


class ContradictoryClaimDetector(LintDetector):
    """Detects pairs of claims on the same page that contradict each other.

    Prefilter: group claims by page_id, generate pairs for pages with 2+
    claims (capped to avoid combinatorial explosion).
    Analysis: ``analyzer.detect_contradictions(...)`` on the reduced pair set.
    """

    def __init__(self, analyzer: LintAnalyzer) -> None:
        self._analyzer = analyzer

    @property
    def name(self) -> str:
        return "contradictory_claim"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.CONTRADICTORY_CLAIM]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        all_claims = await state.claims()

        # Group claims by page_id
        page_claims: dict[EntityId, list[tuple[EntityId, object]]] = defaultdict(list)
        for claim_id, (cv, _supports, _derivations) in all_claims.items():
            claim = await state._uow.claims.get(claim_id)
            if claim is not None:
                page_claims[claim.page_id].append((claim_id, cv))

        # Generate pairs per page, capping to avoid explosion
        pairs_to_check: list[tuple[tuple[EntityId, object], tuple[EntityId, object]]] = []
        for _page_id, claims_list in page_claims.items():
            if len(claims_list) < 2:
                continue
            cap = min(len(claims_list), _MAX_CLAIMS_PER_PAGE)
            page_pair_count = 0
            for i in range(cap):
                for j in range(i + 1, cap):
                    pairs_to_check.append((claims_list[i], claims_list[j]))
                    page_pair_count += 1
                    if page_pair_count >= _MAX_PAIRS_PER_PAGE:
                        break
                if page_pair_count >= _MAX_PAIRS_PER_PAGE:
                    break

        if not pairs_to_check:
            return []

        # Send text pairs to analyzer
        text_pairs = [(cv_a.statement, cv_b.statement) for (_id_a, cv_a), (_id_b, cv_b) in pairs_to_check]
        results = await self._analyzer.detect_contradictions(text_pairs)

        findings: list[RawFinding] = []
        for pair, result in zip(pairs_to_check, results):
            if result.is_contradictory:
                (cid_a, cv_a), (cid_b, cv_b) = pair
                findings.append(
                    RawFinding(
                        category=FindingCategory.CONTRADICTORY_CLAIM,
                        severity=FindingSeverity.WARNING,
                        description=(
                            f"Contradiction: '{cv_a.statement[:50]}' "
                            f"vs '{cv_b.statement[:50]}'"
                        ),
                        affected_entity_ids=[cid_a, cid_b],
                        normalized_subject=f"{cv_a.statement}|{cv_b.statement}",
                        confidence=result.confidence,
                        claim_id=cid_a,
                    )
                )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if at least one of the contradictory claims no longer exists."""
        for eid in original_finding.affected_entity_ids:
            claim_data = (await current_state.claims()).get(eid)
            if claim_data is None:
                return True  # At least one claim is gone
        return False  # Both still exist — re-detection will re-evaluate
