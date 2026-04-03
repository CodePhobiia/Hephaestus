"""UnitOfWork contract — the single atomic boundary for ForgeBase operations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from hephaestus.forgebase.domain.event_types import Clock, EventFactory
from hephaestus.forgebase.domain.models import DomainEvent
from hephaestus.forgebase.repository.claim_derivation_repo import ClaimDerivationRepository
from hephaestus.forgebase.repository.claim_repo import ClaimRepository
from hephaestus.forgebase.repository.claim_support_repo import ClaimSupportRepository
from hephaestus.forgebase.repository.content_store import StagedContentStore
from hephaestus.forgebase.repository.finding_repo import FindingRepository
from hephaestus.forgebase.repository.job_repo import JobRepository
from hephaestus.forgebase.repository.link_repo import LinkRepository
from hephaestus.forgebase.repository.merge_conflict_repo import MergeConflictRepository
from hephaestus.forgebase.repository.merge_proposal_repo import MergeProposalRepository
from hephaestus.forgebase.repository.page_repo import PageRepository
from hephaestus.forgebase.repository.run_artifact_repo import KnowledgeRunArtifactRepository
from hephaestus.forgebase.repository.run_ref_repo import KnowledgeRunRefRepository
from hephaestus.forgebase.repository.source_repo import SourceRepository
from hephaestus.forgebase.repository.vault_repo import VaultRepository
from hephaestus.forgebase.repository.workbook_repo import WorkbookRepository
from hephaestus.forgebase.service.id_generator import IdGenerator


class AbstractUnitOfWork(ABC):
    """Atomic transaction boundary: repos + outbox + content staging."""

    # Repository accessors — set by concrete implementations
    vaults: VaultRepository
    sources: SourceRepository
    pages: PageRepository
    claims: ClaimRepository
    claim_supports: ClaimSupportRepository
    claim_derivations: ClaimDerivationRepository
    links: LinkRepository
    workbooks: WorkbookRepository
    merge_proposals: MergeProposalRepository
    merge_conflicts: MergeConflictRepository
    jobs: JobRepository
    findings: FindingRepository
    run_refs: KnowledgeRunRefRepository
    run_artifacts: KnowledgeRunArtifactRepository
    content: StagedContentStore

    # Infrastructure — injected
    event_factory: EventFactory
    clock: Clock
    id_generator: IdGenerator

    def __init__(self) -> None:
        self._event_buffer: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        """Buffer a domain event. Flushed to outbox on commit."""
        self._event_buffer.append(event)

    @property
    def pending_events(self) -> list[DomainEvent]:
        return list(self._event_buffer)

    @abstractmethod
    async def begin(self) -> None: ...

    @abstractmethod
    async def commit(self) -> None:
        """Persist state + flush events to outbox + finalize content. Pure persistence."""

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back state + abort content + clear event buffer."""

    async def __aenter__(self) -> Self:
        await self.begin()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()
        elif self._event_buffer:
            # Auto-rollback if events were recorded but not committed
            await self.rollback()
