"""RepairWorkbookJob — create a workbook branch with proposed fixes for findings."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    ClaimStatus,
    FindingCategory,
    LinkKind,
    PageType,
    RemediationStatus,
    ResearchOutcome,
)
from hephaestus.forgebase.domain.models import (
    RepairBatch,
    ResearchPacket,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.branch_service import BranchService
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.lint_service import LintService
from hephaestus.forgebase.service.page_service import PageService


class RepairWorkbookJob:
    """Durable job: create a repair workbook for a batch of findings.

    All repairs happen on a workbook branch, never canonical.

    Steps:
      1. Create workbook with purpose=LINT_REPAIR
      2. For each finding, apply category-specific repair on branch
      3. Update findings: status -> REPAIR_WORKBOOK_CREATED
      4. Return workbook_id
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        branch_service: BranchService,
        page_service: PageService,
        claim_service: ClaimService,
        link_service: LinkService,
        lint_service: LintService,
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._branch_service = branch_service
        self._page_service = page_service
        self._claim_service = claim_service
        self._link_service = link_service
        self._lint_service = lint_service
        self._default_actor = default_actor

    async def execute(
        self,
        batch: RepairBatch,
        vault_id: EntityId,
        research_packets: dict[EntityId, ResearchPacket] | None = None,
    ) -> EntityId:
        """Create repair workbook for a finding batch.

        Returns the workbook_id.
        """
        research_packets = research_packets or {}

        # -- 1. Create workbook -------------------------------------------
        workbook = await self._branch_service.create_workbook(
            vault_id=vault_id,
            name=f"lint-repair-{batch.batch_id}",
            purpose=BranchPurpose.LINT_REPAIR,
        )
        workbook_id = workbook.workbook_id

        # -- 2. Read each finding and apply category-specific repair ------
        for finding_id in batch.finding_ids:
            uow = self._uow_factory()
            async with uow:
                finding = await uow.findings.get(finding_id)
                await uow.rollback()

            if finding is None:
                continue

            packet = research_packets.get(finding_id)

            await self._apply_repair(
                finding_category=finding.category,
                finding=finding,
                workbook_id=workbook_id,
                vault_id=vault_id,
                research_packet=packet,
            )

        # -- 3. Update findings: remediation_status -> REPAIR_WORKBOOK_CREATED
        for finding_id in batch.finding_ids:
            await self._lint_service.update_finding_remediation(
                finding_id,
                RemediationStatus.REPAIR_WORKBOOK_CREATED,
            )
            await self._lint_service.set_finding_repair_workbook(
                finding_id,
                workbook_id,
                batch.batch_id,
            )

        # -- 4. Return workbook_id ----------------------------------------
        return workbook_id

    async def _apply_repair(
        self,
        finding_category: FindingCategory,
        finding: object,
        workbook_id: EntityId,
        vault_id: EntityId,
        research_packet: ResearchPacket | None,
    ) -> None:
        """Apply category-specific repair on the workbook branch."""

        if finding_category == FindingCategory.DUPLICATE_PAGE:
            await self._repair_duplicate_page(finding, workbook_id)

        elif finding_category == FindingCategory.ORPHANED_PAGE:
            await self._repair_orphaned_page(finding, workbook_id, vault_id)

        elif finding_category == FindingCategory.BROKEN_REFERENCE:
            await self._repair_broken_reference(finding, workbook_id)

        elif finding_category == FindingCategory.CONTRADICTORY_CLAIM:
            await self._repair_contradictory_claim(
                finding,
                workbook_id,
                vault_id,
                research_packet,
            )

        elif finding_category == FindingCategory.UNSUPPORTED_CLAIM:
            await self._repair_unsupported_claim(finding, workbook_id)

        elif finding_category == FindingCategory.STALE_EVIDENCE:
            await self._repair_stale_evidence(finding, workbook_id)

    # -----------------------------------------------------------------
    # Category-specific repair methods
    # -----------------------------------------------------------------

    async def _repair_duplicate_page(
        self,
        finding: object,
        workbook_id: EntityId,
    ) -> None:
        """DUPLICATE_PAGE: keep the first page, tombstone the rest on branch."""
        affected = getattr(finding, "affected_entity_ids", [])
        if len(affected) < 2:
            return
        # Keep the first, tombstone the rest
        for page_id in affected[1:]:
            await self._page_service.delete_page(page_id, workbook_id)

    async def _repair_orphaned_page(
        self,
        finding: object,
        workbook_id: EntityId,
        vault_id: EntityId,
    ) -> None:
        """ORPHANED_PAGE: create a backlink to the orphaned page on the branch."""
        affected = getattr(finding, "affected_entity_ids", [])
        if not affected:
            return

        orphan_page_id = affected[0]

        # Read all pages to find a suitable source page for the backlink
        uow = self._uow_factory()
        async with uow:
            pages = await uow.pages.list_by_vault(vault_id)
            await uow.rollback()

        # Find a page that is not the orphan to link from
        source_page_id: EntityId | None = None
        for page in pages:
            if page.page_id != orphan_page_id:
                source_page_id = page.page_id
                break

        if source_page_id is not None:
            await self._link_service.create_link(
                vault_id=vault_id,
                kind=LinkKind.BACKLINK,
                source_entity=source_page_id,
                target_entity=orphan_page_id,
                label="auto-backlink from repair",
                workbook_id=workbook_id,
            )
        else:
            # No other page to link from -- tombstone the orphan
            await self._page_service.delete_page(orphan_page_id, workbook_id)

    async def _repair_broken_reference(
        self,
        finding: object,
        workbook_id: EntityId,
    ) -> None:
        """BROKEN_REFERENCE: delete broken link on branch."""
        affected = getattr(finding, "affected_entity_ids", [])
        for link_id in affected:
            await self._link_service.delete_link(link_id, workbook_id)

    async def _repair_contradictory_claim(
        self,
        finding: object,
        workbook_id: EntityId,
        vault_id: EntityId,
        research_packet: ResearchPacket | None,
    ) -> None:
        """CONTRADICTORY_CLAIM: update claim if research resolved, otherwise
        create an open-question page. NEVER silently resolve a contradiction."""

        research_resolved = (
            research_packet is not None
            and research_packet.outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR
        )

        if research_resolved:
            # Research settled it -- update the claim status on the branch.
            # We mark the first affected claim as CONTESTED (acknowledging
            # the resolution), which is the best we can do without knowing
            # which claim the research favored.
            affected = getattr(finding, "affected_entity_ids", [])
            for claim_id in affected:
                await self._claim_service.invalidate_claim(
                    claim_id=claim_id,
                    reason="Contradiction resolved by research",
                    workbook_id=workbook_id,
                )
        else:
            # Research insufficient or absent -- create an OPEN_QUESTION page
            # on the branch. This preserves uncertainty.
            description = getattr(finding, "description", "Unresolved contradiction")
            await self._page_service.create_page(
                vault_id=vault_id,
                page_key=f"open-question-{getattr(finding, 'finding_id', 'unknown')}",
                page_type=PageType.OPEN_QUESTION,
                title=f"Open Question: {description[:80]}",
                content=(
                    f"# Open Question\n\n{description}\n\n"
                    "This contradiction has not been resolved by research."
                ).encode(),
                workbook_id=workbook_id,
                summary="Auto-generated open question for unresolved contradiction",
            )

    async def _repair_unsupported_claim(
        self,
        finding: object,
        workbook_id: EntityId,
    ) -> None:
        """UNSUPPORTED_CLAIM: downgrade claim status to HYPOTHESIS on branch."""
        claim_id = getattr(finding, "claim_id", None)
        if claim_id is None:
            return

        # Read current version to get expected_version
        uow = self._uow_factory()
        async with uow:
            head = await uow.claims.get_head_version(claim_id)
            await uow.rollback()

        if head is None:
            return

        await self._claim_service.update_claim(
            claim_id=claim_id,
            expected_version=head.version,
            status=ClaimStatus.HYPOTHESIS,
            workbook_id=workbook_id,
        )

    async def _repair_stale_evidence(
        self,
        finding: object,
        workbook_id: EntityId,
    ) -> None:
        """STALE_EVIDENCE: mark claims as STALE on branch."""
        affected = getattr(finding, "affected_entity_ids", [])
        for claim_id in affected:
            uow = self._uow_factory()
            async with uow:
                head = await uow.claims.get_head_version(claim_id)
                await uow.rollback()

            if head is None:
                continue

            await self._claim_service.update_claim(
                claim_id=claim_id,
                expected_version=head.version,
                status=ClaimStatus.STALE,
                workbook_id=workbook_id,
            )
