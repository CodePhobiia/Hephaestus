"""Lint report repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import LintReport
from hephaestus.forgebase.domain.values import EntityId


class LintReportRepository(ABC):
    @abstractmethod
    async def create(self, report: LintReport) -> None: ...

    @abstractmethod
    async def get(self, report_id: EntityId) -> LintReport | None: ...

    @abstractmethod
    async def get_by_job(self, job_id: EntityId) -> LintReport | None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[LintReport]: ...
