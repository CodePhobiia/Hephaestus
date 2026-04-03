"""Knowledge run artifact repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import KnowledgeRunArtifact
from hephaestus.forgebase.domain.values import EntityId


class KnowledgeRunArtifactRepository(ABC):
    @abstractmethod
    async def create(self, artifact: KnowledgeRunArtifact) -> None: ...

    @abstractmethod
    async def list_by_ref(self, ref_id: EntityId) -> list[KnowledgeRunArtifact]: ...
