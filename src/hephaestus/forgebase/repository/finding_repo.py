"""Lint finding repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.enums import (
    FindingDisposition,
    FindingStatus,
    RemediationRoute,
    RemediationStatus,
    RouteSource,
)
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

    @abstractmethod
    async def update_remediation_status(
        self,
        finding_id: EntityId,
        status: RemediationStatus,
        route: RemediationRoute | None = None,
        route_source: RouteSource | None = None,
    ) -> None: ...

    @abstractmethod
    async def update_disposition(
        self,
        finding_id: EntityId,
        disposition: FindingDisposition,
    ) -> None: ...

    @abstractmethod
    async def find_by_fingerprint(
        self,
        vault_id: EntityId,
        fingerprint: str,
    ) -> LintFinding | None: ...

    @abstractmethod
    async def list_by_disposition(
        self,
        vault_id: EntityId,
        disposition: FindingDisposition,
    ) -> list[LintFinding]: ...

    @abstractmethod
    async def list_by_remediation_status(
        self,
        vault_id: EntityId,
        status: RemediationStatus,
    ) -> list[LintFinding]: ...

    @abstractmethod
    async def set_research_job_id(
        self,
        finding_id: EntityId,
        research_job_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def set_repair_workbook(
        self,
        finding_id: EntityId,
        repair_workbook_id: EntityId,
        repair_batch_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def set_verification_job_id(
        self,
        finding_id: EntityId,
        verification_job_id: EntityId,
    ) -> None: ...

    @abstractmethod
    async def list_by_vault(self, vault_id: EntityId) -> list[LintFinding]: ...
