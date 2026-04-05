"""InventionIngester — structured ingestion of Genesis invention outputs into ForgeBase.

This is the core of Flow B. It takes raw Genesis output and produces
structured ForgeBase knowledge: INVENTION pages, InventionPageMeta,
hypothesis claims, concept candidates, semantic links, and run artifacts.

All claims are created as HYPOTHESIS with GENERATED support_type —
never auto-promoted.  Confidence is based on fidelity (verifier
strength), not novelty.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from hephaestus.forgebase.domain.enums import (
    CandidateKind,
    CandidateStatus,
    ClaimStatus,
    EntityKind,
    InventionEpistemicState,
    LinkKind,
    PageType,
    SupportType,
)
from hephaestus.forgebase.domain.models import ConceptCandidate, InventionPageMeta
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a string to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


def _extract_inventions(report: Any) -> list[dict]:
    """Extract invention data from a report (dict or object), resiliently."""
    if isinstance(report, dict):
        inventions = report.get("verified_inventions", report.get("translations", []))
    else:
        inventions = getattr(report, "verified_inventions", [])
        if not inventions:
            inventions = getattr(report, "translations", [])

    results: list[dict] = []
    for inv in inventions:
        if isinstance(inv, dict):
            results.append(inv)
        else:
            results.append(
                {
                    "invention_name": getattr(inv, "invention_name", "Unnamed"),
                    "source_domain": getattr(inv, "source_domain", ""),
                    "target_domain": getattr(inv, "target_domain", ""),
                    "mechanism": getattr(
                        inv, "mechanism_description", getattr(inv, "mechanism", "")
                    ),
                    "mapping": getattr(inv, "structural_mapping", getattr(inv, "mapping", "")),
                    "architecture": getattr(inv, "architecture", ""),
                    "roadmap": getattr(inv, "implementation_roadmap", getattr(inv, "roadmap", "")),
                    "limitations": getattr(inv, "limitations", ""),
                    "novelty_score": getattr(inv, "novelty_score", None),
                    "fidelity_score": getattr(inv, "fidelity_score", None),
                    "domain_distance": getattr(inv, "domain_distance", None),
                    "key_insight": getattr(inv, "key_insight", ""),
                }
            )
    return results


def _extract_report_meta(report: Any) -> dict:
    """Extract report-level metadata (cost, models, problem)."""
    if isinstance(report, dict):
        return {
            "total_cost_usd": report.get("total_cost_usd", 0.0),
            "models_used": report.get("models_used", []),
            "problem": report.get("problem", ""),
        }
    return {
        "total_cost_usd": getattr(report, "total_cost_usd", 0.0),
        "models_used": getattr(report, "models_used", []),
        "problem": getattr(report, "problem", ""),
    }


def _render_invention_markdown(inv_data: dict) -> str:
    """Render an invention dict to markdown content."""
    lines = [f"# Invention: {inv_data.get('invention_name', 'Unnamed')}"]
    lines.append(f"\n**Source Domain:** {inv_data.get('source_domain', 'Unknown')}")
    if inv_data.get("target_domain"):
        lines.append(f"**Target Domain:** {inv_data['target_domain']}")
    lines.append("")  # blank line after header section
    if inv_data.get("key_insight"):
        lines += ["## Key Insight", "", inv_data["key_insight"], ""]
    if inv_data.get("mechanism"):
        lines += ["## Mechanism", "", inv_data["mechanism"], ""]
    if inv_data.get("mapping"):
        lines += ["## Structural Mapping", "", inv_data["mapping"], ""]
    if inv_data.get("architecture"):
        lines += ["## Architecture", "", inv_data["architecture"], ""]
    if inv_data.get("roadmap"):
        lines += ["## Implementation Roadmap", "", inv_data["roadmap"], ""]
    if inv_data.get("limitations"):
        lines += ["## Limitations", "", inv_data["limitations"], ""]
    return "\n".join(lines)


def _extract_claims_from_invention(inv_data: dict) -> list[dict]:
    """Extract claim dicts from an invention.

    Each claim has: statement, confidence.
    All claims are HYPOTHESIS/GENERATED — no auto-promotion.
    Confidence is derived from fidelity_score (verifier strength), not novelty.
    """
    claims: list[dict] = []
    fidelity = inv_data.get("fidelity_score") or 0.5

    # Mechanism claim — the core structural assertion
    if inv_data.get("mechanism"):
        claims.append(
            {
                "statement": (
                    f"[Mechanism] {inv_data.get('invention_name', 'Unnamed')}: "
                    f"{inv_data['mechanism']}"
                ),
                "confidence": fidelity,
            }
        )

    # Architecture claim — implementation approach
    if inv_data.get("architecture"):
        claims.append(
            {
                "statement": (
                    f"[Architecture] {inv_data.get('invention_name', 'Unnamed')}: "
                    f"{inv_data['architecture']}"
                ),
                "confidence": fidelity * 0.9,  # slightly lower — derived from mechanism
            }
        )

    return claims


def _extract_concept_names(inv_data: dict) -> list[tuple[str, CandidateKind]]:
    """Extract concept candidate names from an invention.

    Returns list of (name, kind) tuples for source domain, target domain,
    and bridge concepts.
    """
    concepts: list[tuple[str, CandidateKind]] = []

    source_domain = inv_data.get("source_domain", "")
    target_domain = inv_data.get("target_domain", "")

    if source_domain:
        concepts.append((source_domain, CandidateKind.CONCEPT))
    if target_domain:
        concepts.append((target_domain, CandidateKind.CONCEPT))

    # The invention itself is a bridge mechanism concept
    invention_name = inv_data.get("invention_name", "")
    if invention_name:
        concepts.append((invention_name, CandidateKind.MECHANISM))

    return concepts


class InventionIngester:
    """Structured ingestion of Genesis invention outputs into ForgeBase.

    For each invention in a report:
      1. Create INVENTION page with rendered markdown
      2. Create InventionPageMeta (state=PROPOSED)
      3. Extract mechanism/architecture claims (HYPOTHESIS, GENERATED)
      4. Extract concept candidates
      5. Create semantic links (MAPS_TO between source/target domains)
      6. Record run artifacts

    Returns list of created page IDs.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        page_service: PageService,
        claim_service: ClaimService,
        link_service: LinkService,
        ingest_service: IngestService,
        run_integration_service: RunIntegrationService,
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._page_service = page_service
        self._claim_service = claim_service
        self._link_service = link_service
        self._ingest_service = ingest_service
        self._run_integration_service = run_integration_service
        self._default_actor = default_actor

    async def ingest_invention_report(
        self,
        vault_id: EntityId,
        run_id: str,
        report: Any,
        workbook_id: EntityId | None = None,
    ) -> list[EntityId]:
        """Ingest all inventions from a Genesis report.

        Returns list of created page IDs.
        """
        inventions = _extract_inventions(report)
        if not inventions:
            return []

        report_meta = _extract_report_meta(report)
        run_slug = _slugify(run_id)

        # Step 6a: Attach the run
        ref = await self._run_integration_service.attach_run(
            vault_id=vault_id,
            run_id=run_id,
            run_type="genesis",
            upstream_system="RunStore",
        )

        created_page_ids: list[EntityId] = []

        try:
            for inv_data in inventions:
                page_id = await self._ingest_single_invention(
                    vault_id=vault_id,
                    run_id=run_id,
                    run_slug=run_slug,
                    inv_data=inv_data,
                    report_meta=report_meta,
                    ref_id=ref.ref_id,
                    workbook_id=workbook_id,
                )
                created_page_ids.append(page_id)

            # Mark sync as completed
            await self._update_sync_status(ref.ref_id, "synced")

        except Exception:
            await self._update_sync_status(ref.ref_id, "failed")
            raise

        return created_page_ids

    async def _ingest_single_invention(
        self,
        vault_id: EntityId,
        run_id: str,
        run_slug: str,
        inv_data: dict,
        report_meta: dict,
        ref_id: EntityId,
        workbook_id: EntityId | None,
    ) -> EntityId:
        """Ingest a single invention, creating all structured knowledge."""
        invention_name = inv_data.get("invention_name", "Unnamed")
        invention_slug = _slugify(invention_name)

        # --- Step 1: Create INVENTION page ---
        page_key = f"inventions/{run_slug}/{invention_slug}"
        markdown = _render_invention_markdown(inv_data)
        content_bytes = markdown.encode("utf-8")

        page, _page_version = await self._page_service.create_page(
            vault_id=vault_id,
            page_key=page_key,
            page_type=PageType.INVENTION,
            title=invention_name,
            content=content_bytes,
            compiled_from=[],  # generated, not compiled from sources
            workbook_id=workbook_id,
            summary=inv_data.get("key_insight", ""),
        )

        page_id = page.page_id

        # --- Step 2: Create InventionPageMeta ---
        models_used = report_meta.get("models_used", [])
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            meta = InventionPageMeta(
                page_id=page_id,
                vault_id=vault_id,
                invention_state=InventionEpistemicState.PROPOSED,
                run_id=run_id,
                run_type="genesis",
                models_used=models_used,
                created_at=now,
                updated_at=now,
                novelty_score=inv_data.get("novelty_score"),
                fidelity_score=inv_data.get("fidelity_score"),
                domain_distance=inv_data.get("domain_distance"),
                source_domain=inv_data.get("source_domain"),
                target_domain=inv_data.get("target_domain"),
                total_cost_usd=report_meta.get("total_cost_usd", 0.0),
            )
            await uow.invention_meta.create(meta)
            await uow.commit()

        # --- Step 3: Extract claims ---
        claim_dicts = _extract_claims_from_invention(inv_data)
        claim_ids: list[EntityId] = []
        for claim_dict in claim_dicts:
            claim, _claim_version = await self._claim_service.create_claim(
                vault_id=vault_id,
                page_id=page_id,
                statement=claim_dict["statement"],
                status=ClaimStatus.HYPOTHESIS,
                support_type=SupportType.GENERATED,
                confidence=claim_dict["confidence"],
                workbook_id=workbook_id,
            )
            claim_ids.append(claim.claim_id)

        # --- Step 4: Extract concept candidates ---
        concept_names = _extract_concept_names(inv_data)
        candidate_ids: list[EntityId] = []
        if concept_names:
            uow2 = self._uow_factory()
            async with uow2:
                now2 = uow2.clock.now()
                # We need a fake source_id and job_id for the candidate structure.
                # Use the page_id-derived identifiers.
                for concept_name, kind in concept_names:
                    cand_id = uow2.id_generator.generate("cand")
                    candidate = ConceptCandidate(
                        candidate_id=cand_id,
                        vault_id=vault_id,
                        workbook_id=workbook_id,
                        source_id=page_id,  # page as the "source" of this candidate
                        source_version=Version(1),
                        source_compile_job_id=page_id,  # no compile job — use page_id as sentinel
                        name=concept_name,
                        normalized_name=concept_name.lower().strip(),
                        aliases=[],
                        candidate_kind=kind,
                        confidence=inv_data.get("fidelity_score") or 0.5,
                        salience=inv_data.get("novelty_score") or 0.5,
                        status=CandidateStatus.ACTIVE,
                        resolved_page_id=None,
                        compiler_policy_version="invention_ingester_v1",
                        created_at=now2,
                    )
                    await uow2.concept_candidates.create(candidate)
                    candidate_ids.append(cand_id)
                await uow2.commit()

        # --- Step 5: Create semantic links ---
        # MAPS_TO: link between source domain concept candidate and target domain candidate
        source_domain = inv_data.get("source_domain", "")
        target_domain = inv_data.get("target_domain", "")
        if source_domain and target_domain and len(candidate_ids) >= 2:
            # candidate_ids[0] = source domain, candidate_ids[1] = target domain
            await self._link_service.create_link(
                vault_id=vault_id,
                kind=LinkKind.MAPS_TO,
                source_entity=candidate_ids[0],
                target_entity=candidate_ids[1],
                label=f"{source_domain} -> {target_domain}",
                workbook_id=workbook_id,
            )

        # --- Step 6b: Record page artifact on the run ref ---
        idempotency_key = f"{run_id}:invention_page:{page_id}"
        await self._run_integration_service.record_artifact(
            ref_id=ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=page_id,
            role="invention_page",
            idempotency_key=idempotency_key,
        )

        return page_id

    async def _update_sync_status(self, ref_id: EntityId, status: str) -> None:
        """Update sync_status on the KnowledgeRunRef via a fresh UoW."""
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.run_refs.update_sync_status(ref_id, status)
                await uow.commit()
        except Exception:
            logger.exception(
                "Failed to update sync_status to %r for ref_id=%s",
                status,
                ref_id,
            )
