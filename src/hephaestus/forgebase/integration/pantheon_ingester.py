"""PantheonIngester — structured ingestion of Pantheon deliberation into ForgeBase.

Converts Pantheon state (AthenaCanon, HermesDossier, verdict, objections) into
first-class ForgeBase records: claims, links, InventionPageMeta updates, and
ingested sources.  Objections with CHALLENGED_BY links are especially important
for the epistemic feedback loop.

The ingester accepts ``state: Any`` to avoid importing Pantheon types and
creating circular dependencies.  It is resilient to missing/partial fields.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    EntityKind,
    InventionEpistemicState,
    LinkKind,
    SourceFormat,
    SupportType,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verdict → InventionEpistemicState mapping
# ---------------------------------------------------------------------------

_VERDICT_TO_STATE: dict[str, InventionEpistemicState] = {
    "UNANIMOUS_CONSENSUS": InventionEpistemicState.REVIEWED,
    "QUALIFIED_CONSENSUS": InventionEpistemicState.REVIEWED,
    "FAIL_CLOSED_REJECTION": InventionEpistemicState.REJECTED,
}


# ---------------------------------------------------------------------------
# State extraction helpers (resilient to dict vs object)
# ---------------------------------------------------------------------------


def _extract_canon(state: Any) -> dict | None:
    """Extract AthenaCanon from Pantheon state."""
    if isinstance(state, dict):
        canon = state.get("canon")
    else:
        canon = getattr(state, "canon", None)
    if canon is None:
        return None
    if isinstance(canon, dict):
        return canon
    return {
        "mandatory_constraints": getattr(canon, "mandatory_constraints", []),
        "anti_goals": getattr(canon, "anti_goals", []),
        "structural_form": getattr(canon, "structural_form", ""),
        "confidence": getattr(canon, "confidence", 0.0),
    }


def _extract_dossier(state: Any) -> dict | None:
    """Extract HermesDossier from Pantheon state."""
    if isinstance(state, dict):
        dossier = state.get("dossier")
    else:
        dossier = getattr(state, "dossier", None)
    if dossier is None:
        return None
    if isinstance(dossier, dict):
        return dossier
    return {
        "competitor_patterns": getattr(dossier, "competitor_patterns", []),
        "ecosystem_constraints": getattr(dossier, "ecosystem_constraints", []),
    }


def _extract_verdict(state: Any) -> dict:
    """Extract verdict fields from Pantheon state.

    Returns a dict with ``final_verdict``, ``outcome_tier``, ``consensus_achieved``.
    Missing fields are returned as None/False.
    """
    if isinstance(state, dict):
        return {
            "final_verdict": state.get("final_verdict"),
            "outcome_tier": state.get("outcome_tier"),
            "consensus_achieved": state.get("consensus_achieved", False),
        }
    return {
        "final_verdict": getattr(state, "final_verdict", None),
        "outcome_tier": getattr(state, "outcome_tier", None),
        "consensus_achieved": getattr(state, "consensus_achieved", False),
    }


def _extract_objections(state: Any) -> list[dict]:
    """Extract objection ledger from Pantheon state.

    Each objection is normalized to a dict with ``statement``, ``status``, ``severity``.
    """
    if isinstance(state, dict):
        raw = state.get("objection_ledger")
    else:
        raw = getattr(state, "objection_ledger", None)

    if not isinstance(raw, list):
        return []

    result: list[dict] = []
    for obj in raw:
        if isinstance(obj, dict):
            result.append({
                "statement": obj.get("statement", ""),
                "status": obj.get("status", "UNKNOWN"),
                "severity": obj.get("severity", "UNKNOWN"),
            })
        else:
            result.append({
                "statement": getattr(obj, "statement", str(obj)),
                "status": getattr(obj, "status", "UNKNOWN"),
                "severity": getattr(obj, "severity", "UNKNOWN"),
            })
    return result


def _safe_bytes(value: Any) -> bytes:
    """Coerce a value to bytes for ingestion."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    try:
        return json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return str(value).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """Short hex digest for idempotency keys."""
    return hashlib.sha256(data).hexdigest()[:16]


# ---------------------------------------------------------------------------
# PantheonIngester
# ---------------------------------------------------------------------------


class PantheonIngester:
    """Structured ingestion of Pantheon deliberation into ForgeBase.

    Converts Pantheon state into:
      1. KnowledgeRunRef for the Pantheon run
      2. Constraint claims from AthenaCanon with CONSTRAINED_BY links
      3. Ingested dossier source from HermesDossier
      4. Verdict recorded on InventionPageMeta
      5. Objection claims with CHALLENGED_BY links
      6. Sync status update

    On failure: updates sync_status to "failed" and re-raises.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        claim_service: ClaimService,
        link_service: LinkService,
        run_integration_service: RunIntegrationService,
        ingest_service: IngestService,
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._claim_svc = claim_service
        self._link_svc = link_service
        self._run_svc = run_integration_service
        self._ingest_svc = ingest_service
        self._default_actor = default_actor

    async def ingest_pantheon_state(
        self,
        vault_id: EntityId,
        run_id: str,
        state: Any,
        invention_page_id: EntityId | None = None,
        workbook_id: EntityId | None = None,
    ) -> None:
        """Ingest Pantheon deliberation state into vault.

        Steps:
          1. Create KnowledgeRunRef (upstream_system="CouncilArtifactStore")
          2. Ingest AthenaCanon: constraint claims + CONSTRAINED_BY links
          3. Ingest HermesDossier: store as source for later compilation
          4. Record verdict on InventionPageMeta
          5. Ingest objections: claims + CHALLENGED_BY links
          6. Update sync status
        """
        # 1. Attach run
        ref = await self._run_svc.attach_run(
            vault_id=vault_id,
            run_id=run_id,
            run_type="pantheon",
            upstream_system="CouncilArtifactStore",
        )

        try:
            # We need a page_id for canon claims — use invention_page_id if given,
            # otherwise we create a temporary holding page for the claims.
            claim_page_id = invention_page_id

            # If no invention page, create a transient page to hold canon claims
            if claim_page_id is None:
                claim_page_id = await self._ensure_pantheon_claims_page(
                    vault_id, run_id, workbook_id,
                )

            # 2. Ingest AthenaCanon
            constraint_claim_ids = await self._ingest_canon(
                vault_id=vault_id,
                run_id=run_id,
                ref_id=ref.ref_id,
                state=state,
                claim_page_id=claim_page_id,
                invention_page_id=invention_page_id,
                workbook_id=workbook_id,
            )

            # 3. Ingest HermesDossier
            await self._ingest_dossier(
                vault_id=vault_id,
                run_id=run_id,
                ref_id=ref.ref_id,
                state=state,
            )

            # 4. Record verdict + update InventionPageMeta
            verdict_info = _extract_verdict(state)
            if invention_page_id is not None:
                await self._record_verdict(
                    invention_page_id=invention_page_id,
                    verdict_info=verdict_info,
                    state=state,
                )

            # 5. Ingest objections
            await self._ingest_objections(
                vault_id=vault_id,
                run_id=run_id,
                ref_id=ref.ref_id,
                state=state,
                claim_page_id=claim_page_id,
                invention_page_id=invention_page_id,
                workbook_id=workbook_id,
            )

            # 6. Sync status
            await self._update_sync_status(ref.ref_id, "synced")

        except Exception:
            await self._update_sync_status(ref.ref_id, "failed")
            raise

    # ------------------------------------------------------------------
    # Internal: ensure a page exists for holding pantheon claims
    # ------------------------------------------------------------------

    async def _ensure_pantheon_claims_page(
        self,
        vault_id: EntityId,
        run_id: str,
        workbook_id: EntityId | None,
    ) -> EntityId:
        """Create a transient MECHANISM page for standalone Pantheon claims.

        When Pantheon runs without an invention page, we still need a page to
        hold the canon constraint claims and objection claims.
        """
        from hephaestus.forgebase.domain.enums import PageType
        from hephaestus.forgebase.service.page_service import PageService

        page_svc = PageService(
            uow_factory=self._uow_factory,
            default_actor=self._default_actor,
        )
        page, _ = await page_svc.create_page(
            vault_id=vault_id,
            page_key=f"pantheon:claims:{run_id}",
            page_type=PageType.MECHANISM,
            title=f"Pantheon Deliberation Claims ({run_id})",
            content=b"# Pantheon Deliberation Claims\n\nAuto-generated claim container.",
            workbook_id=workbook_id,
        )
        return page.page_id

    # ------------------------------------------------------------------
    # Internal: canon ingestion
    # ------------------------------------------------------------------

    async def _ingest_canon(
        self,
        vault_id: EntityId,
        run_id: str,
        ref_id: EntityId,
        state: Any,
        claim_page_id: EntityId,
        invention_page_id: EntityId | None,
        workbook_id: EntityId | None,
    ) -> list[EntityId]:
        """Ingest AthenaCanon constraints as claims with CONSTRAINED_BY links.

        Returns list of created constraint claim IDs.
        """
        canon = _extract_canon(state)
        if canon is None:
            return []

        constraint_claim_ids: list[EntityId] = []

        # Mandatory constraints
        mandatory = canon.get("mandatory_constraints", [])
        if isinstance(mandatory, list):
            for constraint_text in mandatory:
                if not constraint_text:
                    continue
                claim, _cv = await self._claim_svc.create_claim(
                    vault_id=vault_id,
                    page_id=claim_page_id,
                    statement=str(constraint_text),
                    status=ClaimStatus.HYPOTHESIS,
                    support_type=SupportType.GENERATED,
                    confidence=canon.get("confidence", 0.5),
                    workbook_id=workbook_id,
                )
                constraint_claim_ids.append(claim.claim_id)

                # Record artifact
                idem_key = f"{run_id}:canon:constraint:{_content_hash(str(constraint_text).encode())}"
                await self._run_svc.record_artifact(
                    ref_id=ref_id,
                    entity_kind=EntityKind.CLAIM,
                    entity_id=claim.claim_id,
                    role="canon_constraint",
                    idempotency_key=idem_key,
                )

                # If invention page exists, create CONSTRAINED_BY link
                if invention_page_id is not None:
                    await self._link_svc.create_link(
                        vault_id=vault_id,
                        kind=LinkKind.CONSTRAINED_BY,
                        source_entity=invention_page_id,
                        target_entity=claim.claim_id,
                        label=f"Canon constraint: {str(constraint_text)[:80]}",
                        workbook_id=workbook_id,
                    )

        # Anti-goals as constraint claims
        anti_goals = canon.get("anti_goals", [])
        if isinstance(anti_goals, list):
            for anti_goal in anti_goals:
                if not anti_goal:
                    continue
                claim, _cv = await self._claim_svc.create_claim(
                    vault_id=vault_id,
                    page_id=claim_page_id,
                    statement=f"Anti-goal: {anti_goal}",
                    status=ClaimStatus.HYPOTHESIS,
                    support_type=SupportType.GENERATED,
                    confidence=canon.get("confidence", 0.5),
                    workbook_id=workbook_id,
                )
                constraint_claim_ids.append(claim.claim_id)

                idem_key = f"{run_id}:canon:antigoal:{_content_hash(str(anti_goal).encode())}"
                await self._run_svc.record_artifact(
                    ref_id=ref_id,
                    entity_kind=EntityKind.CLAIM,
                    entity_id=claim.claim_id,
                    role="canon_anti_goal",
                    idempotency_key=idem_key,
                )

                if invention_page_id is not None:
                    await self._link_svc.create_link(
                        vault_id=vault_id,
                        kind=LinkKind.CONSTRAINED_BY,
                        source_entity=invention_page_id,
                        target_entity=claim.claim_id,
                        label=f"Anti-goal: {str(anti_goal)[:80]}",
                        workbook_id=workbook_id,
                    )

        return constraint_claim_ids

    # ------------------------------------------------------------------
    # Internal: dossier ingestion
    # ------------------------------------------------------------------

    async def _ingest_dossier(
        self,
        vault_id: EntityId,
        run_id: str,
        ref_id: EntityId,
        state: Any,
    ) -> None:
        """Ingest HermesDossier as a HEPH_OUTPUT source for later compilation."""
        dossier = _extract_dossier(state)
        if dossier is None:
            return

        raw = _safe_bytes(dossier)
        content_hash = _content_hash(raw)
        idem_key = f"{run_id}:pantheon:dossier:{content_hash}"

        source, _version = await self._ingest_svc.ingest_source(
            vault_id=vault_id,
            raw_content=raw,
            format=SourceFormat.HEPH_OUTPUT,
            title=f"Pantheon dossier ({run_id})",
            idempotency_key=idem_key,
            metadata={
                "pantheon_run_id": run_id,
                "artifact_type": "hermes_dossier",
            },
        )

        await self._run_svc.record_artifact(
            ref_id=ref_id,
            entity_kind=EntityKind.SOURCE,
            entity_id=source.source_id,
            role="pantheon_dossier",
            idempotency_key=idem_key,
        )

    # ------------------------------------------------------------------
    # Internal: verdict recording
    # ------------------------------------------------------------------

    async def _record_verdict(
        self,
        invention_page_id: EntityId,
        verdict_info: dict,
        state: Any,
    ) -> None:
        """Record verdict on InventionPageMeta and update invention state."""
        final_verdict = verdict_info.get("final_verdict")
        outcome_tier = verdict_info.get("outcome_tier") or (final_verdict or "")
        consensus = verdict_info.get("consensus_achieved", False)

        # Count objections
        objections = _extract_objections(state)
        open_count = sum(1 for o in objections if o.get("status") == "OPEN")
        resolved_count = sum(1 for o in objections if o.get("status") == "RESOLVED")

        uow = self._uow_factory()
        async with uow:
            # Update pantheon fields on meta
            await uow.invention_meta.update_pantheon(
                page_id=invention_page_id,
                verdict=final_verdict or "",
                outcome_tier=outcome_tier,
                consensus=bool(consensus),
                objection_count_open=open_count,
                objection_count_resolved=resolved_count,
            )

            # Map verdict to epistemic state
            new_state = _VERDICT_TO_STATE.get(final_verdict or "")
            if new_state is not None:
                await uow.invention_meta.update_state(invention_page_id, new_state)

            await uow.commit()

    # ------------------------------------------------------------------
    # Internal: objection ingestion
    # ------------------------------------------------------------------

    async def _ingest_objections(
        self,
        vault_id: EntityId,
        run_id: str,
        ref_id: EntityId,
        state: Any,
        claim_page_id: EntityId,
        invention_page_id: EntityId | None,
        workbook_id: EntityId | None,
    ) -> None:
        """Ingest objections as claims with CHALLENGED_BY links.

        Each objection becomes a HYPOTHESIS claim.  Open objections
        get CHALLENGED_BY links to the invention page (if present).
        """
        objections = _extract_objections(state)
        if not objections:
            return

        for i, obj in enumerate(objections):
            statement = obj.get("statement", "")
            if not statement:
                continue

            status_str = obj.get("status", "UNKNOWN")
            severity = obj.get("severity", "UNKNOWN")

            # Create claim for the objection
            claim, _cv = await self._claim_svc.create_claim(
                vault_id=vault_id,
                page_id=claim_page_id,
                statement=statement,
                status=ClaimStatus.HYPOTHESIS,
                support_type=SupportType.GENERATED,
                confidence=0.5,  # Objections start at moderate confidence
                workbook_id=workbook_id,
            )

            # Record artifact
            idem_key = f"{run_id}:pantheon:objection:{i}:{_content_hash(statement.encode())}"
            await self._run_svc.record_artifact(
                ref_id=ref_id,
                entity_kind=EntityKind.CLAIM,
                entity_id=claim.claim_id,
                role=f"pantheon_objection_{severity.lower()}",
                idempotency_key=idem_key,
            )

            # Open objections get CHALLENGED_BY links to the invention page
            if status_str == "OPEN" and invention_page_id is not None:
                await self._link_svc.create_link(
                    vault_id=vault_id,
                    kind=LinkKind.CHALLENGED_BY,
                    source_entity=invention_page_id,
                    target_entity=claim.claim_id,
                    label=f"Objection ({severity}): {statement[:80]}",
                    workbook_id=workbook_id,
                )

    # ------------------------------------------------------------------
    # Internal: sync status
    # ------------------------------------------------------------------

    async def _update_sync_status(
        self, ref_id: EntityId, status: str
    ) -> None:
        """Update sync_status on the KnowledgeRunRef via a fresh UoW."""
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.run_refs.update_sync_status(ref_id, status)
                await uow.commit()
        except Exception:
            logger.exception(
                "Failed to update sync_status to %r for ref_id=%s", status, ref_id,
            )
