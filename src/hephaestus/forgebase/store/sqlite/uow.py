"""SQLite UnitOfWork implementation."""
from __future__ import annotations

import aiosqlite

from hephaestus.forgebase.domain.event_types import Clock, EventFactory
from hephaestus.forgebase.repository.content_store import StagedContentStore
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.forgebase.store.sqlite.candidate_evidence_repo import SqliteCandidateEvidenceRepository
from hephaestus.forgebase.store.sqlite.claim_derivation_repo import SqliteClaimDerivationRepository
from hephaestus.forgebase.store.sqlite.compile_manifest_repo import SqliteCompileManifestRepository
from hephaestus.forgebase.store.sqlite.concept_candidate_repo import SqliteConceptCandidateRepository
from hephaestus.forgebase.store.sqlite.dirty_marker_repo import SqliteDirtyMarkerRepository
from hephaestus.forgebase.store.sqlite.invention_meta_repo import SqliteInventionPageMetaRepository
from hephaestus.forgebase.store.sqlite.claim_repo import SqliteClaimRepository
from hephaestus.forgebase.store.sqlite.claim_support_repo import SqliteClaimSupportRepository
from hephaestus.forgebase.store.sqlite.event_repo import SqliteEventRepository
from hephaestus.forgebase.store.sqlite.finding_repo import SqliteFindingRepository
from hephaestus.forgebase.store.sqlite.job_repo import SqliteJobRepository
from hephaestus.forgebase.store.sqlite.link_repo import SqliteLinkRepository
from hephaestus.forgebase.store.sqlite.lint_report_repo import SqliteLintReportRepository
from hephaestus.forgebase.store.sqlite.merge_conflict_repo import SqliteMergeConflictRepository
from hephaestus.forgebase.store.sqlite.merge_proposal_repo import SqliteMergeProposalRepository
from hephaestus.forgebase.store.sqlite.page_repo import SqlitePageRepository
from hephaestus.forgebase.store.sqlite.repair_batch_repo import SqliteRepairBatchRepository
from hephaestus.forgebase.store.sqlite.research_packet_repo import SqliteResearchPacketRepository
from hephaestus.forgebase.store.sqlite.run_artifact_repo import SqliteRunArtifactRepository
from hephaestus.forgebase.store.sqlite.run_ref_repo import SqliteRunRefRepository
from hephaestus.forgebase.store.sqlite.source_repo import SqliteSourceRepository
from hephaestus.forgebase.store.sqlite.vault_repo import SqliteVaultRepository
from hephaestus.forgebase.store.sqlite.workbook_repo import SqliteWorkbookRepository


class SqliteUnitOfWork(AbstractUnitOfWork):
    """SQLite-backed UoW: single connection, single-writer."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        content: StagedContentStore,
        clock: Clock,
        id_generator: IdGenerator,
        consumer_names: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self.content = content
        self.clock = clock
        self.id_generator = id_generator
        self.event_factory = EventFactory(clock=clock, id_generator=id_generator)
        self._consumer_names = consumer_names or []
        self._event_repo = SqliteEventRepository(db)

        # Wire up repos
        self.vaults = SqliteVaultRepository(db)
        self.sources = SqliteSourceRepository(db)
        self.pages = SqlitePageRepository(db)
        self.claims = SqliteClaimRepository(db)
        self.claim_supports = SqliteClaimSupportRepository(db)
        self.claim_derivations = SqliteClaimDerivationRepository(db)
        self.links = SqliteLinkRepository(db)
        self.workbooks = SqliteWorkbookRepository(db)
        self.merge_proposals = SqliteMergeProposalRepository(db)
        self.merge_conflicts = SqliteMergeConflictRepository(db)
        self.jobs = SqliteJobRepository(db)
        self.findings = SqliteFindingRepository(db)
        self.research_packets = SqliteResearchPacketRepository(db)
        self.repair_batches = SqliteRepairBatchRepository(db)
        self.lint_reports = SqliteLintReportRepository(db)
        self.run_refs = SqliteRunRefRepository(db)
        self.run_artifacts = SqliteRunArtifactRepository(db)
        self.concept_candidates = SqliteConceptCandidateRepository(db)
        self.candidate_evidence = SqliteCandidateEvidenceRepository(db)
        self.compile_manifests = SqliteCompileManifestRepository(db)
        self.dirty_markers = SqliteDirtyMarkerRepository(db)
        self.invention_meta = SqliteInventionPageMetaRepository(db)

    async def begin(self) -> None:
        await self._db.execute("BEGIN")

    async def commit(self) -> None:
        # Flush events to outbox within the same transaction
        if self._event_buffer:
            await self._event_repo.flush_events(self._event_buffer, self._consumer_names)

        await self._db.commit()

        # Finalize content AFTER db commit succeeds
        await self.content.finalize()

        self._event_buffer.clear()

    async def rollback(self) -> None:
        await self._db.rollback()
        await self.content.abort()
        self._event_buffer.clear()
