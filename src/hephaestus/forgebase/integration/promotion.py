"""PromotionService — promotes invention claims from HYPOTHESIS to SUPPORTED.

Claims are NEVER silently promoted. This service performs explicit checks
against the invention page's epistemic state, open objections, and
required support/derivation links before any status change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
)
from hephaestus.forgebase.domain.models import ClaimVersion, PromotionResult
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class PromotionService:
    """Promotes invention claims from HYPOTHESIS to SUPPORTED after verification.

    Claims are NEVER silently promoted. This service performs explicit checks:
    1. InventionPageMeta.invention_state must be VERIFIED
    2. No open CONTESTED objections on the page's claims
    3. Required ClaimSupport or ClaimDerivation links must exist
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def evaluate_promotion(
        self,
        page_id: EntityId,
        vault_id: EntityId,
    ) -> PromotionResult:
        """Check if an invention page's claims are eligible for promotion.

        Checks:
        1. InventionPageMeta.invention_state == VERIFIED
        2. No open CONTESTED objections on the page's claims
        3. Required ClaimSupport or ClaimDerivation links exist

        Returns PromotionResult with eligible_claims and blocked_claims.
        """
        uow = self._uow_factory()
        async with uow:
            # Check invention state
            meta = await uow.invention_meta.get(page_id)
            if meta is None:
                return PromotionResult(
                    page_id=page_id,
                    eligible_claims=[],
                    blocked_claims=[],
                    overall_eligible=False,
                )

            # Get all claims on this page
            claims = await uow.claims.list_by_page(page_id)

            if meta.invention_state != InventionEpistemicState.VERIFIED:
                # Not verified -- nothing eligible
                blocked = [
                    (
                        c.claim_id,
                        f"Invention state is {meta.invention_state.value}, not VERIFIED",
                    )
                    for c in claims
                ]
                return PromotionResult(
                    page_id=page_id,
                    eligible_claims=[],
                    blocked_claims=blocked,
                    overall_eligible=False,
                )

            eligible: list[EntityId] = []
            blocked: list[tuple[EntityId, str]] = []

            for claim in claims:
                head = await uow.claims.get_head_version(claim.claim_id)
                if head is None:
                    continue

                # Skip already-supported claims
                if head.status == ClaimStatus.SUPPORTED:
                    continue

                # Check for CONTESTED status (open objections)
                if head.status == ClaimStatus.CONTESTED:
                    blocked.append(
                        (
                            claim.claim_id,
                            "Claim is CONTESTED — open objections remain",
                        )
                    )
                    continue

                # Check for support/derivation links
                supports = await uow.claim_supports.list_by_claim(claim.claim_id)
                derivations = await uow.claim_derivations.list_by_claim(
                    claim.claim_id,
                )

                if not supports and not derivations:
                    blocked.append(
                        (
                            claim.claim_id,
                            "No ClaimSupport or ClaimDerivation links",
                        )
                    )
                    continue

                eligible.append(claim.claim_id)

            await uow.rollback()  # read-only operation

        return PromotionResult(
            page_id=page_id,
            eligible_claims=eligible,
            blocked_claims=blocked,
            overall_eligible=len(eligible) > 0,
        )

    async def promote_claims(
        self,
        page_id: EntityId,
        vault_id: EntityId,
        claim_ids: list[EntityId] | None = None,
    ) -> list[EntityId]:
        """Promote eligible claims from HYPOTHESIS to SUPPORTED.

        If claim_ids not provided, promotes all eligible.
        Returns list of promoted claim IDs.
        """
        # Evaluate first
        result = await self.evaluate_promotion(page_id, vault_id)

        targets = claim_ids if claim_ids else result.eligible_claims
        targets = [cid for cid in targets if cid in result.eligible_claims]

        if not targets:
            return []

        promoted: list[EntityId] = []
        uow = self._uow_factory()
        async with uow:
            for claim_id in targets:
                head = await uow.claims.get_head_version(claim_id)
                if head is None or head.status == ClaimStatus.SUPPORTED:
                    continue

                # Create new version with SUPPORTED status
                new_version = ClaimVersion(
                    claim_id=claim_id,
                    version=head.version.next(),
                    statement=head.statement,
                    status=ClaimStatus.SUPPORTED,
                    support_type=head.support_type,
                    confidence=head.confidence,
                    validated_at=uow.clock.now(),
                    fresh_until=head.fresh_until,
                    created_at=uow.clock.now(),
                    created_by=self._default_actor,
                )
                await uow.claims.create_version(new_version)
                await uow.vaults.set_canonical_claim_head(
                    vault_id,
                    claim_id,
                    new_version.version.number,
                )

                uow.record_event(
                    uow.event_factory.create(
                        event_type="invention.promoted",
                        aggregate_type="claim",
                        aggregate_id=claim_id,
                        vault_id=vault_id,
                        payload={
                            "page_id": str(page_id),
                            "from_status": head.status.value,
                            "to_status": "supported",
                        },
                        actor=self._default_actor,
                    )
                )
                promoted.append(claim_id)

            await uow.commit()

        return promoted
