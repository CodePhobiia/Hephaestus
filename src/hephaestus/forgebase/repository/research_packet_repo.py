"""Research packet repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import (
    ResearchPacket,
    ResearchPacketContradictionResult,
    ResearchPacketDiscoveredSource,
    ResearchPacketFreshnessResult,
    ResearchPacketIngestJob,
)
from hephaestus.forgebase.domain.values import EntityId


class ResearchPacketRepository(ABC):
    @abstractmethod
    async def create(self, packet: ResearchPacket) -> None: ...

    @abstractmethod
    async def get(self, packet_id: EntityId) -> ResearchPacket | None: ...

    @abstractmethod
    async def list_by_finding(self, finding_id: EntityId) -> list[ResearchPacket]: ...

    @abstractmethod
    async def add_discovered_source(self, source: ResearchPacketDiscoveredSource) -> None: ...

    @abstractmethod
    async def list_discovered_sources(
        self, packet_id: EntityId
    ) -> list[ResearchPacketDiscoveredSource]: ...

    @abstractmethod
    async def add_ingest_job(self, ingest: ResearchPacketIngestJob) -> None: ...

    @abstractmethod
    async def list_ingest_jobs(self, packet_id: EntityId) -> list[ResearchPacketIngestJob]: ...

    @abstractmethod
    async def set_contradiction_result(self, result: ResearchPacketContradictionResult) -> None: ...

    @abstractmethod
    async def get_contradiction_result(
        self, packet_id: EntityId
    ) -> ResearchPacketContradictionResult | None: ...

    @abstractmethod
    async def set_freshness_result(self, result: ResearchPacketFreshnessResult) -> None: ...

    @abstractmethod
    async def get_freshness_result(
        self, packet_id: EntityId
    ) -> ResearchPacketFreshnessResult | None: ...
