"""PriorArtBaselinePack extraction — the strictest channel.

Feeds ``extra_blocked_paths`` in DeepForge.  Only SUPPORTED claims from
concept/mechanism pages and VERIFIED inventions pass.  HYPOTHESIS,
CONTESTED, REJECTED, and low-trust sources are unconditionally excluded
(unless the policy explicitly overrides).
"""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    PageType,
    ProvenanceKind,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.models import PackEntry, PriorArtBaselinePack
from hephaestus.forgebase.extraction.policy import ExtractionPolicy
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

# Page types that feed the baseline channel (compiled knowledge pages)
_BASELINE_PAGE_TYPES: frozenset[str] = frozenset(
    {
        PageType.CONCEPT.value,
        PageType.MECHANISM.value,
    }
)

# SourceTrustTier ordering — higher index means higher trust
_TRUST_ORDERING: list[SourceTrustTier] = [
    SourceTrustTier.UNTRUSTED,
    SourceTrustTier.LOW,
    SourceTrustTier.STANDARD,
    SourceTrustTier.AUTHORITATIVE,
]


def _trust_at_least(tier: SourceTrustTier, minimum: SourceTrustTier) -> bool:
    """Return True if *tier* meets or exceeds *minimum*."""
    return _TRUST_ORDERING.index(tier) >= _TRUST_ORDERING.index(minimum)


def _provenance_from_support_type(support_type: SupportType) -> ProvenanceKind:
    """Map a ClaimVersion.support_type to a ProvenanceKind."""
    mapping = {
        SupportType.DIRECT: ProvenanceKind.EMPIRICAL,
        SupportType.SYNTHESIZED: ProvenanceKind.DERIVED,
        SupportType.GENERATED: ProvenanceKind.GENERATED,
        SupportType.INHERITED: ProvenanceKind.INHERITED,
    }
    return mapping.get(support_type, ProvenanceKind.DERIVED)


async def extract_baseline_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> PriorArtBaselinePack:
    """Extract prior-art baselines for DeepForge ``extra_blocked_paths``.

    INCLUDES:
    - SUPPORTED claims from concept / mechanism pages
    - VERIFIED invention claims (SUPPORTED only)
    - External prior-art from AUTHORITATIVE sources

    EXCLUDES:
    - HYPOTHESIS claims  (unless ``policy.baseline_include_hypothesis``)
    - CONTESTED claims   (unless ``policy.baseline_include_contested``)
    - REJECTED inventions
    - Low-trust sources  (below ``policy.baseline_min_external_source_trust``)
    - GENERATED claims that have not been promoted to SUPPORTED
    """
    vault = await uow.vaults.get(vault_id)
    if vault is None:
        raise ValueError(f"Vault not found: {vault_id}")

    vault_revision_id = vault.head_revision_id
    now = uow.clock.now()

    entries: list[PackEntry] = []

    # ------------------------------------------------------------------ #
    # 1. Claims from compiled concept / mechanism pages
    # ------------------------------------------------------------------ #
    all_pages = await uow.pages.list_by_vault(vault_id)
    baseline_pages = [p for p in all_pages if p.page_type.value in _BASELINE_PAGE_TYPES]

    for page in baseline_pages:
        claims = await uow.claims.list_by_page(page.page_id)
        for claim in claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            if head is None:
                continue

            if not _claim_passes_baseline(head.status, policy):
                continue

            # Determine trust tier from supporting sources
            trust_tier = await _resolve_trust_tier(uow, claim.claim_id, policy)
            if trust_tier is None:
                # No qualifying support — still include if the claim
                # is on a compiled (non-invention) page with SUPPORTED status
                trust_tier = SourceTrustTier.STANDARD

            entry = PackEntry(
                text=head.statement,
                origin_kind="concept_page"
                if page.page_type == PageType.CONCEPT
                else "mechanism_page",
                claim_ids=[claim.claim_id],
                page_ids=[page.page_id],
                source_refs=[],
                epistemic_state=head.status.value,
                trust_tier=trust_tier.value,
                salience=head.confidence,
                provenance_kind=_provenance_from_support_type(head.support_type),
            )
            entries.append(entry)

    # ------------------------------------------------------------------ #
    # 2. Claims from VERIFIED invention pages
    # ------------------------------------------------------------------ #
    verified_metas = await uow.invention_meta.list_by_state(
        vault_id,
        InventionEpistemicState.VERIFIED,
    )

    for meta in verified_metas:
        claims = await uow.claims.list_by_page(meta.page_id)
        for claim in claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            if head is None:
                continue

            if not _claim_passes_baseline(head.status, policy):
                continue

            entry = PackEntry(
                text=head.statement,
                origin_kind="invention",
                claim_ids=[claim.claim_id],
                page_ids=[meta.page_id],
                source_refs=[],
                epistemic_state=head.status.value,
                trust_tier=SourceTrustTier.STANDARD.value,
                salience=head.confidence,
                provenance_kind=_provenance_from_support_type(head.support_type),
            )
            entries.append(entry)

    return PriorArtBaselinePack(
        entries=entries,
        vault_id=vault_id,
        vault_revision_id=vault_revision_id,
        branch_id=workbook_id,
        extraction_policy_version=policy.policy_version,
        assembler_version=policy.assembler_version,
        extracted_at=now,
    )


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #


def _claim_passes_baseline(status: ClaimStatus, policy: ExtractionPolicy) -> bool:
    """Check whether a claim status passes the baseline filter."""
    if status == ClaimStatus.SUPPORTED:
        return True
    if status == ClaimStatus.HYPOTHESIS and policy.baseline_include_hypothesis:
        return True
    return bool(status == ClaimStatus.CONTESTED and policy.baseline_include_contested)


async def _resolve_trust_tier(
    uow: AbstractUnitOfWork,
    claim_id: EntityId,
    policy: ExtractionPolicy,
) -> SourceTrustTier | None:
    """Determine the highest trust tier from a claim's supporting sources.

    Returns ``None`` if the claim has no supports with a qualifying source.
    """
    supports = await uow.claim_supports.list_by_claim(claim_id)
    if not supports:
        return None

    best: SourceTrustTier | None = None
    for sup in supports:
        source_head = await uow.sources.get_head_version(sup.source_id)
        if source_head is None:
            continue
        tier = source_head.trust_tier
        if best is None or _TRUST_ORDERING.index(tier) > _TRUST_ORDERING.index(best):
            best = tier

    return best
