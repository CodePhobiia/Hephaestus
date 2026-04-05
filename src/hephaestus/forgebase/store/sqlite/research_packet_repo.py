"""SQLite implementation of ResearchPacketRepository."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import ResearchOutcome
from hephaestus.forgebase.domain.models import (
    ResearchPacket,
    ResearchPacketContradictionResult,
    ResearchPacketDiscoveredSource,
    ResearchPacketFreshnessResult,
    ResearchPacketIngestJob,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.research_packet_repo import ResearchPacketRepository


class SqliteResearchPacketRepository(ResearchPacketRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, packet: ResearchPacket) -> None:
        await self._db.execute(
            """INSERT INTO fb_research_packets
            (packet_id, finding_id, vault_id, augmentor_kind, outcome, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(packet.packet_id),
                str(packet.finding_id),
                str(packet.vault_id),
                packet.augmentor_kind,
                packet.outcome.value,
                packet.created_at.isoformat(),
            ),
        )

    async def get(self, packet_id: EntityId) -> ResearchPacket | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packets WHERE packet_id = ?",
            (str(packet_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_packet(row)

    async def list_by_finding(self, finding_id: EntityId) -> list[ResearchPacket]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packets WHERE finding_id = ?",
            (str(finding_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_packet(r) for r in rows]

    async def add_discovered_source(self, source: ResearchPacketDiscoveredSource) -> None:
        await self._db.execute(
            """INSERT INTO fb_research_packet_sources
            (id, packet_id, url, title, summary, relevance, trust_tier)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(source.id),
                str(source.packet_id),
                source.url,
                source.title,
                source.summary,
                source.relevance,
                source.trust_tier,
            ),
        )

    async def list_discovered_sources(
        self, packet_id: EntityId
    ) -> list[ResearchPacketDiscoveredSource]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packet_sources WHERE packet_id = ?",
            (str(packet_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_discovered_source(r) for r in rows]

    async def add_ingest_job(self, ingest: ResearchPacketIngestJob) -> None:
        await self._db.execute(
            "INSERT INTO fb_research_packet_ingest_jobs (packet_id, ingest_job_id) VALUES (?, ?)",
            (str(ingest.packet_id), str(ingest.ingest_job_id)),
        )

    async def list_ingest_jobs(self, packet_id: EntityId) -> list[ResearchPacketIngestJob]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packet_ingest_jobs WHERE packet_id = ?",
            (str(packet_id),),
        )
        rows = await cursor.fetchall()
        return [
            ResearchPacketIngestJob(
                packet_id=EntityId(r["packet_id"]),
                ingest_job_id=EntityId(r["ingest_job_id"]),
            )
            for r in rows
        ]

    async def set_contradiction_result(self, result: ResearchPacketContradictionResult) -> None:
        evidence_json = json.dumps(result.supporting_evidence)
        await self._db.execute(
            """INSERT OR REPLACE INTO fb_research_packet_contradiction_results
            (packet_id, summary, resolution, confidence, supporting_evidence)
            VALUES (?, ?, ?, ?, ?)""",
            (
                str(result.packet_id),
                result.summary,
                result.resolution,
                result.confidence,
                evidence_json,
            ),
        )

    async def get_contradiction_result(
        self, packet_id: EntityId
    ) -> ResearchPacketContradictionResult | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packet_contradiction_results WHERE packet_id = ?",
            (str(packet_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ResearchPacketContradictionResult(
            packet_id=EntityId(row["packet_id"]),
            summary=row["summary"],
            resolution=row["resolution"],
            confidence=row["confidence"],
            supporting_evidence=json.loads(row["supporting_evidence"]),
        )

    async def set_freshness_result(self, result: ResearchPacketFreshnessResult) -> None:
        evidence_json = json.dumps(result.newer_evidence)
        await self._db.execute(
            """INSERT OR REPLACE INTO fb_research_packet_freshness_results
            (packet_id, is_stale, reason, newer_evidence)
            VALUES (?, ?, ?, ?)""",
            (
                str(result.packet_id),
                1 if result.is_stale else 0,
                result.reason,
                evidence_json,
            ),
        )

    async def get_freshness_result(
        self, packet_id: EntityId
    ) -> ResearchPacketFreshnessResult | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_research_packet_freshness_results WHERE packet_id = ?",
            (str(packet_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ResearchPacketFreshnessResult(
            packet_id=EntityId(row["packet_id"]),
            is_stale=bool(row["is_stale"]),
            reason=row["reason"],
            newer_evidence=json.loads(row["newer_evidence"]),
        )

    @staticmethod
    def _row_to_packet(row: aiosqlite.Row) -> ResearchPacket:
        return ResearchPacket(
            packet_id=EntityId(row["packet_id"]),
            finding_id=EntityId(row["finding_id"]),
            vault_id=EntityId(row["vault_id"]),
            augmentor_kind=row["augmentor_kind"],
            outcome=ResearchOutcome(row["outcome"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_discovered_source(row: aiosqlite.Row) -> ResearchPacketDiscoveredSource:
        return ResearchPacketDiscoveredSource(
            id=EntityId(row["id"]),
            packet_id=EntityId(row["packet_id"]),
            url=row["url"],
            title=row["title"],
            summary=row["summary"],
            relevance=row["relevance"],
            trust_tier=row["trust_tier"],
        )
