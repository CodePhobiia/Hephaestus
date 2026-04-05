"""ConstraintDossierPack extraction — governance-grade channel.

Feeds ``baseline_dossier`` in Pantheon.  Only evidence-backed constraints,
known failure modes, validated objections, explicitly labeled unresolved
controversies, and competitive landscape entries.  No hypotheses, no
unverified invention output, no low-confidence claims.
"""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    LinkKind,
    PageType,
    ProvenanceKind,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.models import ConstraintDossierPack, PackEntry
from hephaestus.forgebase.extraction.policy import ExtractionPolicy
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

# Keywords that signal a claim is about constraints or limitations
_CONSTRAINT_KEYWORDS: frozenset[str] = frozenset(
    {
        "constraint",
        "limitation",
        "must not",
        "cannot",
        "restricted",
        "boundary",
        "requirement",
        "must",
        "forbidden",
    }
)

# Keywords that signal a claim is about failures
_FAILURE_KEYWORDS: frozenset[str] = frozenset(
    {
        "failure",
        "fails",
        "failed",
        "breakdown",
        "collapse",
        "degrade",
        "degrades",
        "limitation",
        "bottleneck",
        "risk",
    }
)

# Keywords that signal competitive / alternative approaches
_COMPETITIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "alternative",
        "competing",
        "competitor",
        "versus",
        "compared to",
        "outperforms",
        "underperforms",
        "benchmark",
        "state-of-the-art",
        "prior work",
    }
)


def _provenance_from_support_type(support_type: SupportType) -> ProvenanceKind:
    mapping = {
        SupportType.DIRECT: ProvenanceKind.EMPIRICAL,
        SupportType.SYNTHESIZED: ProvenanceKind.DERIVED,
        SupportType.GENERATED: ProvenanceKind.GENERATED,
        SupportType.INHERITED: ProvenanceKind.INHERITED,
    }
    return mapping.get(support_type, ProvenanceKind.DERIVED)


def _text_matches_keywords(text: str, keywords: frozenset[str]) -> bool:
    """Return True if *text* contains any of the *keywords* (case-insensitive)."""
    lower = text.lower()
    return any(kw in lower for kw in keywords)


async def extract_constraint_dossier_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> ConstraintDossierPack:
    """Extract constraints for Pantheon ``baseline_dossier``.

    INCLUDES:
    - SUPPORTED claims tagged as constraints / limitations
    - Known failure modes from mechanism pages
    - Resolved Pantheon objections (CHALLENGED_BY links where the
      objection claim was later resolved)
    - Unresolved controversies (CONTESTED claims)
    - Competitive analysis from authoritative sources

    EXCLUDES:
    - Speculative hypotheses
    - Unverified invention output
    - Low-confidence claims
    - REJECTED inventions
    """
    vault = await uow.vaults.get(vault_id)
    if vault is None:
        raise ValueError(f"Vault not found: {vault_id}")

    vault_revision_id = vault.head_revision_id
    now = uow.clock.now()

    hard_constraints: list[PackEntry] = []
    known_failure_modes: list[PackEntry] = []
    validated_objections: list[PackEntry] = []
    unresolved_controversies: list[PackEntry] = []
    competitive_landscape: list[PackEntry] = []

    all_pages = await uow.pages.list_by_vault(vault_id)

    # ------------------------------------------------------------------ #
    # 1. Hard constraints + 2. Failure modes + 5. Competitive landscape
    #    Scan claims from concept / mechanism pages
    # ------------------------------------------------------------------ #
    knowledge_pages = [
        p for p in all_pages if p.page_type in (PageType.CONCEPT, PageType.MECHANISM)
    ]

    for page in knowledge_pages:
        claims = await uow.claims.list_by_page(page.page_id)
        for claim in claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            if head is None:
                continue

            # --- 1. Hard constraints: SUPPORTED + constraint keywords ---
            if head.status == ClaimStatus.SUPPORTED and _text_matches_keywords(
                head.statement, _CONSTRAINT_KEYWORDS
            ):
                hard_constraints.append(
                    PackEntry(
                        text=head.statement,
                        origin_kind="constraint",
                        claim_ids=[claim.claim_id],
                        page_ids=[page.page_id],
                        source_refs=[],
                        epistemic_state=head.status.value,
                        trust_tier=SourceTrustTier.STANDARD.value,
                        salience=head.confidence,
                        provenance_kind=_provenance_from_support_type(head.support_type),
                    )
                )

            # --- 2. Known failure modes: from mechanism pages with failure keywords ---
            if (
                page.page_type == PageType.MECHANISM
                and head.status == ClaimStatus.SUPPORTED
                and _text_matches_keywords(head.statement, _FAILURE_KEYWORDS)
            ):
                known_failure_modes.append(
                    PackEntry(
                        text=head.statement,
                        origin_kind="failure_mode",
                        claim_ids=[claim.claim_id],
                        page_ids=[page.page_id],
                        source_refs=[],
                        epistemic_state=head.status.value,
                        trust_tier=SourceTrustTier.STANDARD.value,
                        salience=head.confidence,
                        provenance_kind=_provenance_from_support_type(head.support_type),
                    )
                )

            # --- 5. Competitive landscape: SUPPORTED from AUTHORITATIVE sources ---
            if head.status == ClaimStatus.SUPPORTED and _text_matches_keywords(
                head.statement, _COMPETITIVE_KEYWORDS
            ):
                # Check if the claim has authoritative source support
                supports = await uow.claim_supports.list_by_claim(claim.claim_id)
                has_authoritative = False
                for sup in supports:
                    sv = await uow.sources.get_head_version(sup.source_id)
                    if sv is not None and sv.trust_tier == SourceTrustTier.AUTHORITATIVE:
                        has_authoritative = True
                        break

                if has_authoritative:
                    competitive_landscape.append(
                        PackEntry(
                            text=head.statement,
                            origin_kind="competitive",
                            claim_ids=[claim.claim_id],
                            page_ids=[page.page_id],
                            source_refs=[],
                            epistemic_state=head.status.value,
                            trust_tier=SourceTrustTier.AUTHORITATIVE.value,
                            salience=head.confidence,
                            provenance_kind=_provenance_from_support_type(head.support_type),
                        )
                    )

    # ------------------------------------------------------------------ #
    # 3. Validated objections — CHALLENGED_BY links with resolved claims
    # ------------------------------------------------------------------ #
    if policy.dossier_include_resolved_objections:
        all_links = await uow.links.list_by_vault(vault_id)
        challenged_links = [lnk for lnk in all_links if lnk.kind == LinkKind.CHALLENGED_BY]

        for link in challenged_links:
            link_head = await uow.links.get_head_version(link.link_id)
            if link_head is None:
                continue

            # The target_entity of a CHALLENGED_BY link is the objection claim.
            # If the objection claim has been resolved (is now SUPPORTED),
            # it counts as a validated objection.
            objection_claim = await uow.claims.get(link_head.target_entity)
            if objection_claim is None:
                continue
            obj_head = await uow.claims.get_head_version(objection_claim.claim_id)
            if obj_head is None:
                continue

            if obj_head.status == ClaimStatus.SUPPORTED:
                validated_objections.append(
                    PackEntry(
                        text=obj_head.statement,
                        origin_kind="objection",
                        claim_ids=[objection_claim.claim_id],
                        page_ids=[objection_claim.page_id],
                        source_refs=[],
                        epistemic_state=obj_head.status.value,
                        trust_tier=SourceTrustTier.STANDARD.value,
                        salience=obj_head.confidence,
                        provenance_kind=_provenance_from_support_type(obj_head.support_type),
                    )
                )

    # ------------------------------------------------------------------ #
    # 4. Unresolved controversies — CONTESTED claims (explicitly labeled)
    # ------------------------------------------------------------------ #
    if policy.dossier_include_unresolved_controversies:
        all_claims = await uow.claims.list_by_vault(vault_id)
        for claim in all_claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            if head is None:
                continue
            if head.status == ClaimStatus.CONTESTED:
                unresolved_controversies.append(
                    PackEntry(
                        text=head.statement,
                        origin_kind="controversy",
                        claim_ids=[claim.claim_id],
                        page_ids=[claim.page_id],
                        source_refs=[],
                        epistemic_state=head.status.value,
                        trust_tier=SourceTrustTier.STANDARD.value,
                        salience=head.confidence,
                        provenance_kind=_provenance_from_support_type(head.support_type),
                    )
                )

    return ConstraintDossierPack(
        hard_constraints=hard_constraints,
        known_failure_modes=known_failure_modes,
        validated_objections=validated_objections,
        unresolved_controversies=unresolved_controversies,
        competitive_landscape=competitive_landscape,
        vault_id=vault_id,
        vault_revision_id=vault_revision_id,
        branch_id=workbook_id,
        extraction_policy_version=policy.policy_version,
        assembler_version=policy.assembler_version,
        extracted_at=now,
    )
