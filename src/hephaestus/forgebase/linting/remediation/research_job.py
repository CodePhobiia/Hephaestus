"""FindingResearchJob — orchestrate research for a single lint finding."""
from __future__ import annotations

from typing import Callable

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    RemediationStatus,
    ResearchOutcome,
)
from hephaestus.forgebase.domain.models import (
    LintFinding,
    ResearchPacket,
    ResearchPacketContradictionResult,
    ResearchPacketDiscoveredSource,
    ResearchPacketFreshnessResult,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.research.augmentor import (
    ContradictionResolution,
    DiscoveredSource,
    FreshnessCheck,
    ResearchAugmentor,
)
from hephaestus.forgebase.service.lint_service import LintService

# Categories that dispatch to find_supporting_evidence
_EVIDENCE_SEARCH_CATEGORIES = frozenset({
    FindingCategory.SOURCE_GAP,
    FindingCategory.RESOLVABLE_BY_SEARCH,
    FindingCategory.UNSUPPORTED_CLAIM,
})

# Relevance threshold for classifying sources as sufficient
_RELEVANCE_THRESHOLD = 0.5

# Confidence threshold for contradiction resolution
_CONTRADICTION_CONFIDENCE_THRESHOLD = 0.7


class FindingResearchJob:
    """Durable job: research a finding via the ResearchAugmentor.

    Steps:
      1. Read finding + affected entities
      2. Dispatch to augmentor by category
      3. Create ResearchPacket + child records
      4. Classify outcome
      5. If new sources discovered: schedule ingest jobs (follow-on)
      6. Update finding: remediation_status -> RESEARCH_COMPLETED
      7. Emit events
      8. Return packet
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        augmentor: ResearchAugmentor,
        lint_service: LintService,
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._augmentor = augmentor
        self._lint_service = lint_service
        self._default_actor = default_actor

    async def execute(
        self,
        finding_id: EntityId,
        vault_id: EntityId,
    ) -> ResearchPacket:
        """Execute research for a finding and return the created packet."""

        # -- 1. Read finding -----------------------------------------------
        uow = self._uow_factory()
        async with uow:
            finding = await uow.findings.get(finding_id)
            if finding is None:
                raise ValueError(f"Finding not found: {finding_id}")
            await uow.rollback()

        # -- 2. Dispatch to augmentor by category -------------------------
        discovered_sources: list[DiscoveredSource] = []
        contradiction_result: ContradictionResolution | None = None
        freshness_result: FreshnessCheck | None = None

        if finding.category == FindingCategory.CONTRADICTORY_CLAIM:
            contradiction_result = await self._augmentor.resolve_contradiction(
                claim_a=finding.description,
                claim_b="",  # We pass description as context
                context=finding.suggested_action or "",
            )

        elif finding.category == FindingCategory.STALE_EVIDENCE:
            uow2 = self._uow_factory()
            async with uow2:
                # Get the claim's validated_at for freshness check
                validated_at = uow2.clock.now()
                if finding.claim_id is not None:
                    claim_head = await uow2.claims.get_head_version(finding.claim_id)
                    if claim_head is not None:
                        validated_at = claim_head.validated_at
                await uow2.rollback()

            freshness_result = await self._augmentor.check_freshness(
                claim=finding.description,
                last_validated=validated_at,
            )

        elif finding.category in _EVIDENCE_SEARCH_CATEGORIES:
            discovered_sources = await self._augmentor.find_supporting_evidence(
                concept=finding.description,
                evidence_gaps=[finding.suggested_action or "missing evidence"],
            )

        # -- 3. Classify outcome ------------------------------------------
        outcome = self._classify_outcome(
            discovered_sources=discovered_sources,
            contradiction_result=contradiction_result,
            freshness_result=freshness_result,
        )

        # -- 4. Create packet + child records -----------------------------
        uow3 = self._uow_factory()
        async with uow3:
            now = uow3.clock.now()
            packet_id = uow3.id_generator.packet_id()

            packet = ResearchPacket(
                packet_id=packet_id,
                finding_id=finding_id,
                vault_id=vault_id,
                augmentor_kind=type(self._augmentor).__name__,
                outcome=outcome,
                created_at=now,
            )
            await uow3.research_packets.create(packet)

            # Persist discovered sources as child records
            for src in discovered_sources:
                child_id = uow3.id_generator.generate("rsrc")
                child = ResearchPacketDiscoveredSource(
                    id=child_id,
                    packet_id=packet_id,
                    url=src.url,
                    title=src.title,
                    summary=src.summary,
                    relevance=src.relevance,
                    trust_tier=src.trust_tier,
                )
                await uow3.research_packets.add_discovered_source(child)

            # Persist contradiction result
            if contradiction_result is not None:
                cr = ResearchPacketContradictionResult(
                    packet_id=packet_id,
                    summary=contradiction_result.summary,
                    resolution=contradiction_result.resolution,
                    confidence=contradiction_result.confidence,
                    supporting_evidence=contradiction_result.supporting_evidence,
                )
                await uow3.research_packets.set_contradiction_result(cr)

            # Persist freshness result
            if freshness_result is not None:
                fr = ResearchPacketFreshnessResult(
                    packet_id=packet_id,
                    is_stale=freshness_result.is_stale,
                    reason=freshness_result.reason,
                    newer_evidence=freshness_result.newer_evidence,
                )
                await uow3.research_packets.set_freshness_result(fr)

            # Emit research.packet_created
            uow3.record_event(
                uow3.event_factory.create(
                    event_type="research.packet_created",
                    aggregate_type="finding",
                    aggregate_id=finding_id,
                    vault_id=vault_id,
                    payload={
                        "packet_id": str(packet_id),
                        "outcome": outcome.value,
                        "augmentor_kind": packet.augmentor_kind,
                        "discovered_source_count": len(discovered_sources),
                    },
                    actor=self._default_actor,
                )
            )

            await uow3.commit()

        # -- 5. Schedule ingest jobs for new sources (follow-on) ----------
        # We record the intent but do not inline-ingest. The follow-on
        # job scheduling is done here as metadata only; actual ingest is
        # triggered by consumers of the research.packet_created event.

        # -- 6. Update finding remediation status -------------------------
        await self._lint_service.update_finding_remediation(
            finding_id,
            RemediationStatus.RESEARCH_COMPLETED,
        )

        return packet

    @staticmethod
    def _classify_outcome(
        *,
        discovered_sources: list[DiscoveredSource],
        contradiction_result: ContradictionResolution | None,
        freshness_result: FreshnessCheck | None,
    ) -> ResearchOutcome:
        """Classify research outcome per spec rules.

        - Sources with relevance > 0.5 -> SUFFICIENT_FOR_REPAIR
        - Contradiction confidence > 0.7 -> SUFFICIENT_FOR_REPAIR
        - Freshness check found newer evidence -> SUFFICIENT_FOR_REPAIR
        - Sources returned but none above threshold -> NEW_SOURCES_PENDING
        - Augmentor returned empty results -> NO_ACTIONABLE_RESULT
        - Otherwise -> INSUFFICIENT_EVIDENCE
        """
        # Contradiction resolution check
        if contradiction_result is not None:
            if contradiction_result.confidence > _CONTRADICTION_CONFIDENCE_THRESHOLD:
                return ResearchOutcome.SUFFICIENT_FOR_REPAIR
            if contradiction_result.resolution == "insufficient_evidence":
                return ResearchOutcome.INSUFFICIENT_EVIDENCE
            return ResearchOutcome.INSUFFICIENT_EVIDENCE

        # Freshness check
        if freshness_result is not None:
            if freshness_result.is_stale and freshness_result.newer_evidence:
                return ResearchOutcome.SUFFICIENT_FOR_REPAIR
            if not freshness_result.is_stale:
                return ResearchOutcome.NO_ACTIONABLE_RESULT
            return ResearchOutcome.INSUFFICIENT_EVIDENCE

        # Evidence search check
        if not discovered_sources:
            return ResearchOutcome.NO_ACTIONABLE_RESULT

        has_sufficient = any(
            src.relevance > _RELEVANCE_THRESHOLD for src in discovered_sources
        )
        if has_sufficient:
            return ResearchOutcome.SUFFICIENT_FOR_REPAIR

        return ResearchOutcome.NEW_SOURCES_PENDING
