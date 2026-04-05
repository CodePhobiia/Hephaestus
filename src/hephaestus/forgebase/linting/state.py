"""VaultLintState — read-only, branch-aware, lazily-cached query facade.

Constructed once per lint run. Provides selectors that detectors use
to inspect vault state without coupling to repository internals.
Uses lazy caching: the first call loads data, subsequent calls return
the cached result.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from hephaestus.forgebase.compiler.policy import SynthesisPolicy
from hephaestus.forgebase.domain.enums import (
    CandidateStatus,
    ClaimStatus,
    PageType,
)
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimDerivation,
    ClaimSupport,
    ClaimVersion,
    ConceptCandidate,
    Link,
    LinkVersion,
    LintFinding,
    Page,
    PageVersion,
    Source,
    SourceVersion,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.query.claim_queries import get_claim as _get_claim_q
from hephaestus.forgebase.query.link_queries import _resolve_link_version
from hephaestus.forgebase.query.page_queries import list_pages as _list_pages_q
from hephaestus.forgebase.query.source_queries import list_sources as _list_sources_q
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class VaultLintState:
    """Read-only, branch-aware query facade over vault state for lint detectors."""

    def __init__(
        self,
        uow: AbstractUnitOfWork,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> None:
        self._uow = uow
        self._vault_id = vault_id
        self._workbook_id = workbook_id
        # Lazy caches (None = not yet loaded)
        self._pages_cache: list[tuple[Page, PageVersion]] | None = None
        self._claims_cache: (
            dict[
                EntityId,
                tuple[ClaimVersion, list[ClaimSupport], list[ClaimDerivation]],
            ]
            | None
        ) = None
        self._links_cache: list[tuple[Link, LinkVersion]] | None = None
        self._sources_cache: list[tuple[Source, SourceVersion]] | None = None
        self._candidates_cache: list[ConceptCandidate] | None = None
        self._findings_cache: list[LintFinding] | None = None

    # --- Public properties ---

    @property
    def vault_id(self) -> EntityId:
        return self._vault_id

    @property
    def workbook_id(self) -> EntityId | None:
        return self._workbook_id

    # --- Core selectors (lazy-cached, branch-aware) ---

    async def pages(self) -> list[tuple[Page, PageVersion]]:
        """All pages with their head versions (branch-aware)."""
        if self._pages_cache is None:
            self._pages_cache = await _list_pages_q(
                self._uow.pages,
                self._uow.vaults,
                self._uow.workbooks,
                self._vault_id,
                workbook_id=self._workbook_id,
            )
        return self._pages_cache

    async def claims(
        self,
    ) -> dict[
        EntityId,
        tuple[ClaimVersion, list[ClaimSupport], list[ClaimDerivation]],
    ]:
        """All claims with supports and derivations (branch-aware).

        Returns a dict keyed by claim_id -> (ClaimVersion, supports, derivations).
        """
        if self._claims_cache is None:
            result: dict[
                EntityId,
                tuple[ClaimVersion, list[ClaimSupport], list[ClaimDerivation]],
            ] = {}
            all_claims = await self._uow.claims.list_by_vault(self._vault_id)
            for claim in all_claims:
                data = await _get_claim_q(
                    self._uow.claims,
                    self._uow.claim_supports,
                    self._uow.claim_derivations,
                    self._uow.workbooks,
                    claim.claim_id,
                    workbook_id=self._workbook_id,
                )
                if data is not None:
                    result[claim.claim_id] = data
            self._claims_cache = result
        return self._claims_cache

    async def links(self) -> list[tuple[Link, LinkVersion]]:
        """All links with head versions (branch-aware)."""
        if self._links_cache is None:
            all_links = await self._uow.links.list_by_vault(self._vault_id)
            results: list[tuple[Link, LinkVersion]] = []
            for link in all_links:
                version = await _resolve_link_version(
                    self._uow.links,
                    self._uow.workbooks,
                    link.link_id,
                    workbook_id=self._workbook_id,
                )
                if version is not None:
                    results.append((link, version))
            self._links_cache = results
        return self._links_cache

    async def sources(self) -> list[tuple[Source, SourceVersion]]:
        """All sources with head versions (branch-aware)."""
        if self._sources_cache is None:
            self._sources_cache = await _list_sources_q(
                self._uow.sources,
                self._uow.workbooks,
                self._vault_id,
                workbook_id=self._workbook_id,
            )
        return self._sources_cache

    async def candidates(self) -> list[ConceptCandidate]:
        """All active concept candidates."""
        if self._candidates_cache is None:
            self._candidates_cache = await self._uow.concept_candidates.list_active(
                self._vault_id,
                self._workbook_id,
            )
        return self._candidates_cache

    async def existing_findings(self) -> list[LintFinding]:
        """All existing lint findings for this vault."""
        if self._findings_cache is None:
            self._findings_cache = await self._uow.findings.list_by_vault(
                self._vault_id,
            )
        return self._findings_cache

    # --- Helper selectors (avoid full scans in detectors) ---

    async def claims_without_support(self) -> list[tuple[Claim, ClaimVersion]]:
        """Claims with SUPPORTED status but no ClaimSupport records."""
        all_claims = await self.claims()
        result: list[tuple[Claim, ClaimVersion]] = []
        for claim_id, (cv, supports, _derivations) in all_claims.items():
            if cv.status == ClaimStatus.SUPPORTED and len(supports) == 0:
                claim = await self._uow.claims.get(claim_id)
                if claim is not None:
                    result.append((claim, cv))
        return result

    async def pages_with_zero_inbound_links(self) -> list[Page]:
        """Pages that have no incoming links (excluding source cards and indexes)."""
        all_pages = await self.pages()
        all_links = await self.links()
        # Build set of target entity IDs from links
        link_targets: set[str] = {str(lv.target_entity) for _, lv in all_links}
        result: list[Page] = []
        for page, _pv in all_pages:
            if page.page_type in (PageType.SOURCE_CARD, PageType.SOURCE_INDEX):
                continue
            if str(page.page_id) not in link_targets:
                result.append(page)
        return result

    async def claims_past_freshness(self, now: datetime) -> list[tuple[Claim, ClaimVersion]]:
        """Claims where fresh_until is set and has passed."""
        all_claims = await self.claims()
        result: list[tuple[Claim, ClaimVersion]] = []
        for claim_id, (cv, _supports, _derivations) in all_claims.items():
            if cv.fresh_until is not None and cv.fresh_until < now:
                claim = await self._uow.claims.get(claim_id)
                if claim is not None:
                    result.append((claim, cv))
        return result

    async def candidates_promotion_worthy(self, policy: SynthesisPolicy) -> list[ConceptCandidate]:
        """Active candidates that cross promotion thresholds with no resolved page."""
        all_candidates = await self.candidates()
        # Group active candidates by normalized_name
        clusters: dict[str, list[ConceptCandidate]] = defaultdict(list)
        for c in all_candidates:
            if c.status == CandidateStatus.ACTIVE:
                clusters[c.normalized_name].append(c)

        worthy: list[ConceptCandidate] = []
        for _name, cluster in clusters.items():
            unique_sources = len({str(c.source_id) for c in cluster})
            max_salience = max(c.salience for c in cluster)
            if (
                unique_sources >= policy.min_sources_for_promotion
                or max_salience >= policy.min_salience_single_source
            ):
                # Only include candidates without resolved pages
                for c in cluster:
                    if c.resolved_page_id is None:
                        worthy.append(c)
        return worthy

    async def page_content(self, page_id: EntityId) -> bytes:
        """Read the content bytes for a page's head version."""
        # Find the page version from the cache or query directly
        all_pages = await self.pages()
        for _page, pv in all_pages:
            if _page.page_id == page_id:
                return await self._uow.content.read(pv.content_ref)
        raise ValueError(f"Page not found: {page_id}")
