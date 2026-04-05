"""DomainContextPack extraction — the broadest channel.

Feeds ``reference_context`` in LensSelector.  Includes concepts,
mechanisms, open questions, hypothesis claims, and explored directions
(even rejected inventions — as summaries only).  Each category is
capped by the policy and ranked by salience.
"""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    PageType,
    ProvenanceKind,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.models import DomainContextPack, PackEntry
from hephaestus.forgebase.extraction.policy import ExtractionPolicy
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


def _provenance_from_support_type(support_type: SupportType) -> ProvenanceKind:
    mapping = {
        SupportType.DIRECT: ProvenanceKind.EMPIRICAL,
        SupportType.SYNTHESIZED: ProvenanceKind.DERIVED,
        SupportType.GENERATED: ProvenanceKind.GENERATED,
        SupportType.INHERITED: ProvenanceKind.INHERITED,
    }
    return mapping.get(support_type, ProvenanceKind.DERIVED)


def _cap_and_rank(entries: list[PackEntry], max_count: int) -> list[PackEntry]:
    """Sort entries by salience descending, then cap to *max_count*."""
    entries.sort(key=lambda e: e.salience, reverse=True)
    return entries[:max_count]


async def extract_domain_context_pack(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    policy: ExtractionPolicy,
    workbook_id: EntityId | None = None,
) -> DomainContextPack:
    """Extract domain context for LensSelector ``reference_context``.

    INCLUDES (broadest channel):
    - All canonical concept page titles and summaries
    - Mechanism page summaries
    - Open question pages
    - HYPOTHESIS claims as context
    - Prior invention directions (even contested/rejected, for diversity)
      as title + source-domain + one-line mechanism SUMMARIES ONLY.

    All categories are capped to policy maximums, ranked by salience.
    """
    vault = await uow.vaults.get(vault_id)
    if vault is None:
        raise ValueError(f"Vault not found: {vault_id}")

    vault_revision_id = vault.head_revision_id
    now = uow.clock.now()

    all_pages = await uow.pages.list_by_vault(vault_id)

    # ------------------------------------------------------------------ #
    # 1. Concepts — concept pages with title + summary
    # ------------------------------------------------------------------ #
    concept_entries: list[PackEntry] = []
    concept_pages = [p for p in all_pages if p.page_type == PageType.CONCEPT]
    for page in concept_pages:
        pv = await uow.pages.get_head_version(page.page_id)
        if pv is None:
            continue
        # Salience: use number of claims on the page as a proxy
        claims = await uow.claims.list_by_page(page.page_id)
        salience = min(1.0, len(claims) * 0.2) if claims else 0.1

        concept_entries.append(
            PackEntry(
                text=f"{pv.title}: {pv.summary}" if pv.summary else pv.title,
                origin_kind="concept_page",
                claim_ids=[],
                page_ids=[page.page_id],
                source_refs=[],
                epistemic_state="canonical",
                trust_tier=SourceTrustTier.STANDARD.value,
                salience=salience,
                provenance_kind=ProvenanceKind.EMPIRICAL,
            )
        )

    # ------------------------------------------------------------------ #
    # 2. Mechanisms — mechanism pages with title + summary
    # ------------------------------------------------------------------ #
    mechanism_entries: list[PackEntry] = []
    mechanism_pages = [p for p in all_pages if p.page_type == PageType.MECHANISM]
    for page in mechanism_pages:
        pv = await uow.pages.get_head_version(page.page_id)
        if pv is None:
            continue
        claims = await uow.claims.list_by_page(page.page_id)
        salience = min(1.0, len(claims) * 0.2) if claims else 0.1

        mechanism_entries.append(
            PackEntry(
                text=f"{pv.title}: {pv.summary}" if pv.summary else pv.title,
                origin_kind="mechanism_page",
                claim_ids=[],
                page_ids=[page.page_id],
                source_refs=[],
                epistemic_state="canonical",
                trust_tier=SourceTrustTier.STANDARD.value,
                salience=salience,
                provenance_kind=ProvenanceKind.EMPIRICAL,
            )
        )

    # ------------------------------------------------------------------ #
    # 3. Open questions
    # ------------------------------------------------------------------ #
    oq_entries: list[PackEntry] = []
    if policy.context_include_open_questions:
        oq_pages = [p for p in all_pages if p.page_type == PageType.OPEN_QUESTION]
        for page in oq_pages:
            pv = await uow.pages.get_head_version(page.page_id)
            if pv is None:
                continue
            claims = await uow.claims.list_by_page(page.page_id)
            salience = min(1.0, len(claims) * 0.2) if claims else 0.1

            oq_entries.append(
                PackEntry(
                    text=f"{pv.title}: {pv.summary}" if pv.summary else pv.title,
                    origin_kind="open_question",
                    claim_ids=[],
                    page_ids=[page.page_id],
                    source_refs=[],
                    epistemic_state="open",
                    trust_tier=SourceTrustTier.STANDARD.value,
                    salience=salience,
                    provenance_kind=ProvenanceKind.DERIVED,
                )
            )

    # ------------------------------------------------------------------ #
    # 4. Explored directions — ALL invention pages (including REJECTED)
    #    as SUMMARIES ONLY: title + source domain + one-line mechanism.
    # ------------------------------------------------------------------ #
    direction_entries: list[PackEntry] = []
    if policy.context_include_prior_directions:
        all_invention_metas = await uow.invention_meta.list_by_vault(vault_id)
        for meta in all_invention_metas:
            pv = await uow.pages.get_head_version(meta.page_id)
            if pv is None:
                continue

            # Build a concise summary — NOT full page text
            summary_parts = [pv.title]
            if meta.source_domain:
                summary_parts.append(f"(source: {meta.source_domain})")
            if pv.summary:
                summary_parts.append(f"- {pv.summary}")

            summary_text = " ".join(summary_parts)

            # Salience: novelty_score if available, else a default
            salience = meta.novelty_score if meta.novelty_score is not None else 0.3

            direction_entries.append(
                PackEntry(
                    text=summary_text,
                    origin_kind="invention",
                    claim_ids=[],
                    page_ids=[meta.page_id],
                    source_refs=[],
                    epistemic_state=meta.invention_state.value,
                    trust_tier=SourceTrustTier.STANDARD.value,
                    salience=salience,
                    provenance_kind=ProvenanceKind.GENERATED,
                )
            )

    # ------------------------------------------------------------------ #
    # Cap each category to policy limits, ranked by salience
    # ------------------------------------------------------------------ #
    concepts = _cap_and_rank(concept_entries, policy.context_max_concepts)
    mechanisms = _cap_and_rank(mechanism_entries, policy.context_max_mechanisms)
    open_questions = _cap_and_rank(oq_entries, policy.context_max_open_questions)
    explored_directions = _cap_and_rank(direction_entries, policy.context_max_explored_directions)

    return DomainContextPack(
        concepts=concepts,
        mechanisms=mechanisms,
        open_questions=open_questions,
        explored_directions=explored_directions,
        vault_id=vault_id,
        vault_revision_id=vault_revision_id,
        branch_id=workbook_id,
        extraction_policy_version=policy.policy_version,
        assembler_version=policy.assembler_version,
        extracted_at=now,
    )
