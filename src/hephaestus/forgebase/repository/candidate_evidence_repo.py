"""Repository contract for concept candidate evidence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import ConceptCandidateEvidence
from hephaestus.forgebase.domain.values import EntityId


class CandidateEvidenceRepository(ABC):
    @abstractmethod
    async def create(self, evidence: ConceptCandidateEvidence) -> None: ...

    @abstractmethod
    async def list_by_candidate(
        self,
        candidate_id: EntityId,
    ) -> list[ConceptCandidateEvidence]: ...
