"""ClaimService — claim creation, update, support, derivation, and invalidation."""
from __future__ import annotations

from typing import Callable

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    EntityKind,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    BranchClaimDerivationHead,
    BranchClaimHead,
    BranchClaimSupportHead,
    Claim,
    ClaimDerivation,
    ClaimSupport,
    ClaimVersion,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import ConflictError


class ClaimService:
    """Command service for claim lifecycle operations."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_claim(
        self,
        vault_id: EntityId,
        page_id: EntityId,
        statement: str,
        status: ClaimStatus,
        support_type: SupportType,
        confidence: float,
        workbook_id: EntityId | None = None,
    ) -> tuple[Claim, ClaimVersion]:
        """Create a new claim with an initial version."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            claim_id = uow.id_generator.claim_id()

            claim = Claim(
                claim_id=claim_id,
                vault_id=vault_id,
                page_id=page_id,
                created_at=now,
            )

            version = ClaimVersion(
                claim_id=claim_id,
                version=Version(1),
                statement=statement,
                status=status,
                support_type=support_type,
                confidence=confidence,
                validated_at=now,
                fresh_until=None,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claims.create(claim, version)

            # Set head
            if workbook_id is not None:
                await uow.workbooks.set_claim_head(
                    BranchClaimHead(
                        workbook_id=workbook_id,
                        claim_id=claim_id,
                        head_version=Version(1),
                        base_version=Version(1),  # born on branch
                    )
                )
            else:
                await uow.vaults.set_canonical_claim_head(
                    vault_id, claim_id, 1,
                )

            # Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.version_created",
                    aggregate_type="claim",
                    aggregate_id=claim_id,
                    aggregate_version=Version(1),
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "statement": statement,
                        "status": status.value,
                        "confidence": confidence,
                        "version": 1,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return claim, version

    async def update_claim(
        self,
        claim_id: EntityId,
        expected_version: Version,
        statement: str | None = None,
        status: ClaimStatus | None = None,
        confidence: float | None = None,
        workbook_id: EntityId | None = None,
    ) -> ClaimVersion:
        """Update a claim, creating a new version with optimistic concurrency."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            claim = await uow.claims.get(claim_id)
            if claim is None:
                raise ValueError(f"Claim not found: {claim_id}")

            current_head = await uow.claims.get_head_version(claim_id)
            if current_head is None:
                raise ValueError(f"No versions found for claim: {claim_id}")

            if current_head.version != expected_version:
                raise ConflictError(
                    entity_id=str(claim_id),
                    expected=expected_version.number,
                    actual=current_head.version.number,
                )

            new_version_num = expected_version.next()

            new_version = ClaimVersion(
                claim_id=claim_id,
                version=new_version_num,
                statement=statement if statement is not None else current_head.statement,
                status=status if status is not None else current_head.status,
                support_type=current_head.support_type,
                confidence=confidence if confidence is not None else current_head.confidence,
                validated_at=now,
                fresh_until=current_head.fresh_until,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claims.create_version(new_version)

            # Update head
            if workbook_id is not None:
                await uow.workbooks.set_claim_head(
                    BranchClaimHead(
                        workbook_id=workbook_id,
                        claim_id=claim_id,
                        head_version=new_version_num,
                        base_version=expected_version,
                    )
                )
            else:
                await uow.vaults.set_canonical_claim_head(
                    claim.vault_id, claim_id, new_version_num.number,
                )

            # Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.version_created",
                    aggregate_type="claim",
                    aggregate_id=claim_id,
                    aggregate_version=new_version_num,
                    vault_id=claim.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "statement": new_version.statement,
                        "status": new_version.status.value,
                        "confidence": new_version.confidence,
                        "version": new_version_num.number,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return new_version

    async def add_support(
        self,
        claim_id: EntityId,
        source_id: EntityId,
        source_segment: str | None = None,
        strength: float = 1.0,
        workbook_id: EntityId | None = None,
    ) -> ClaimSupport:
        """Add supporting evidence from a source to a claim."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            claim = await uow.claims.get(claim_id)
            if claim is None:
                raise ValueError(f"Claim not found: {claim_id}")

            support_id = uow.id_generator.support_id()

            support = ClaimSupport(
                support_id=support_id,
                claim_id=claim_id,
                source_id=source_id,
                source_segment=source_segment,
                strength=strength,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claim_supports.create(support)

            # Track on branch if applicable
            if workbook_id is not None:
                await uow.workbooks.set_claim_support_head(
                    BranchClaimSupportHead(
                        workbook_id=workbook_id,
                        support_id=support_id,
                        created_on_branch=True,
                    )
                )

            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.support_added",
                    aggregate_type="claim",
                    aggregate_id=claim_id,
                    vault_id=claim.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "support_id": str(support_id),
                        "source_id": str(source_id),
                        "strength": strength,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return support

    async def remove_support(
        self,
        support_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> None:
        """Remove supporting evidence from a claim."""
        uow = self._uow_factory()
        async with uow:
            support = await uow.claim_supports.get(support_id)
            if support is None:
                raise ValueError(f"ClaimSupport not found: {support_id}")

            claim = await uow.claims.get(support.claim_id)
            vault_id = claim.vault_id if claim else support.claim_id  # fallback

            await uow.claim_supports.delete(support_id)

            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.support_removed",
                    aggregate_type="claim",
                    aggregate_id=support.claim_id,
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={"support_id": str(support_id)},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

    async def add_derivation(
        self,
        claim_id: EntityId,
        parent_claim_id: EntityId,
        relationship: str,
        workbook_id: EntityId | None = None,
    ) -> ClaimDerivation:
        """Record that a claim is derived from a parent claim."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            claim = await uow.claims.get(claim_id)
            if claim is None:
                raise ValueError(f"Claim not found: {claim_id}")

            derivation_id = uow.id_generator.derivation_id()

            derivation = ClaimDerivation(
                derivation_id=derivation_id,
                claim_id=claim_id,
                parent_claim_id=parent_claim_id,
                relationship=relationship,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claim_derivations.create(derivation)

            # Track on branch if applicable
            if workbook_id is not None:
                await uow.workbooks.set_claim_derivation_head(
                    BranchClaimDerivationHead(
                        workbook_id=workbook_id,
                        derivation_id=derivation_id,
                        created_on_branch=True,
                    )
                )

            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.derivation_added",
                    aggregate_type="claim",
                    aggregate_id=claim_id,
                    vault_id=claim.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "derivation_id": str(derivation_id),
                        "parent_claim_id": str(parent_claim_id),
                        "relationship": relationship,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return derivation

    async def invalidate_claim(
        self,
        claim_id: EntityId,
        reason: str,
        workbook_id: EntityId | None = None,
    ) -> ClaimVersion:
        """Invalidate a claim by creating a new version with CONTESTED status.

        This does NOT use optimistic concurrency -- it always creates a new
        version on top of the current head to force-invalidate.
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            claim = await uow.claims.get(claim_id)
            if claim is None:
                raise ValueError(f"Claim not found: {claim_id}")

            current_head = await uow.claims.get_head_version(claim_id)
            if current_head is None:
                raise ValueError(f"No versions found for claim: {claim_id}")

            new_version_num = current_head.version.next()

            new_version = ClaimVersion(
                claim_id=claim_id,
                version=new_version_num,
                statement=current_head.statement,
                status=ClaimStatus.CONTESTED,
                support_type=current_head.support_type,
                confidence=0.0,
                validated_at=now,
                fresh_until=None,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.claims.create_version(new_version)

            # Update head
            if workbook_id is not None:
                await uow.workbooks.set_claim_head(
                    BranchClaimHead(
                        workbook_id=workbook_id,
                        claim_id=claim_id,
                        head_version=new_version_num,
                        base_version=current_head.version,
                    )
                )
            else:
                await uow.vaults.set_canonical_claim_head(
                    claim.vault_id, claim_id, new_version_num.number,
                )

            uow.record_event(
                uow.event_factory.create(
                    event_type="claim.invalidated",
                    aggregate_type="claim",
                    aggregate_id=claim_id,
                    aggregate_version=new_version_num,
                    vault_id=claim.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "reason": reason,
                        "previous_status": current_head.status.value,
                        "version": new_version_num.number,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return new_version
