"""Repository contract for concept candidates."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import CandidateStatus
from hephaestus.forgebase.domain.models import ConceptCandidate
from hephaestus.forgebase.domain.values import EntityId, Version


class ConceptCandidateRepository(ABC):
    @abstractmethod
    async def create(self, candidate: ConceptCandidate) -> None: ...

    @abstractmethod
    async def get(self, candidate_id: EntityId) -> ConceptCandidate | None: ...

    @abstractmethod
    async def list_active(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> list[ConceptCandidate]: ...

    @abstractmethod
    async def list_by_source(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> list[ConceptCandidate]: ...

    @abstractmethod
    async def list_by_normalized_name(
        self,
        vault_id: EntityId,
        normalized_name: str,
        workbook_id: EntityId | None = None,
    ) -> list[ConceptCandidate]: ...

    @abstractmethod
    async def update_status(
        self,
        candidate_id: EntityId,
        status: CandidateStatus,
        resolved_page_id: EntityId | None = None,
    ) -> None: ...

    @abstractmethod
    async def supersede_by_source(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> int:
        """Mark all candidates from a prior compile of this source as SUPERSEDED. Returns count."""
