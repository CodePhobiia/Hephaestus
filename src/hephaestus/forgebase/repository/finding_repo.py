"""Lint finding repository contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import FindingStatus
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId


class FindingRepository(ABC):
    @abstractmethod
    async def create(self, finding: LintFinding) -> None: ...

    @abstractmethod
    async def get(self, finding_id: EntityId) -> LintFinding | None: ...

    @abstractmethod
    async def list_by_job(self, job_id: EntityId) -> list[LintFinding]: ...

    @abstractmethod
    async def update_status(self, finding_id: EntityId, status: FindingStatus) -> None: ...
