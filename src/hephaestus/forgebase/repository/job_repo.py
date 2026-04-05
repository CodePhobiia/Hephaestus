"""Job repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from hephaestus.forgebase.domain.enums import JobStatus
from hephaestus.forgebase.domain.models import Job
from hephaestus.forgebase.domain.values import EntityId


class JobRepository(ABC):
    @abstractmethod
    async def create(self, job: Job) -> None: ...

    @abstractmethod
    async def get(self, job_id: EntityId) -> Job | None: ...

    @abstractmethod
    async def find_by_idempotency_key(self, key: str) -> Job | None: ...

    @abstractmethod
    async def update_status(
        self,
        job_id: EntityId,
        status: JobStatus,
        *,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> None: ...

    @abstractmethod
    async def increment_attempt(
        self, job_id: EntityId, next_attempt_at: datetime | None = None
    ) -> None: ...
