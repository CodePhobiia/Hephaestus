"""Tests for SQLite ResearchPacketRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ResearchOutcome
from hephaestus.forgebase.domain.models import (
    ResearchPacket,
    ResearchPacketContradictionResult,
    ResearchPacketDiscoveredSource,
    ResearchPacketFreshnessResult,
    ResearchPacketIngestJob,
)
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.research_packet_repo import SqliteResearchPacketRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteResearchPacketRepository(sqlite_db)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


class TestResearchPacketCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo, id_gen, sqlite_db):
        packet = ResearchPacket(
            packet_id=id_gen.packet_id(),
            finding_id=id_gen.finding_id(),
            vault_id=id_gen.vault_id(),
            augmentor_kind="perplexity",
            outcome=ResearchOutcome.SUFFICIENT_FOR_REPAIR,
            created_at=_now(),
        )
        await repo.create(packet)
        await sqlite_db.commit()

        result = await repo.get(packet.packet_id)
        assert result is not None
        assert result.augmentor_kind == "perplexity"
        assert result.outcome == ResearchOutcome.SUFFICIENT_FOR_REPAIR

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get(id_gen.packet_id())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_finding(self, repo, id_gen, sqlite_db):
        finding_id = id_gen.finding_id()
        vault_id = id_gen.vault_id()

        p1 = ResearchPacket(
            packet_id=id_gen.packet_id(),
            finding_id=finding_id,
            vault_id=vault_id,
            augmentor_kind="perplexity",
            outcome=ResearchOutcome.INSUFFICIENT_EVIDENCE,
            created_at=_now(),
        )
        p2 = ResearchPacket(
            packet_id=id_gen.packet_id(),
            finding_id=finding_id,
            vault_id=vault_id,
            augmentor_kind="noop",
            outcome=ResearchOutcome.SUFFICIENT_FOR_REPAIR,
            created_at=_now(),
        )
        # Different finding
        p3 = ResearchPacket(
            packet_id=id_gen.packet_id(),
            finding_id=id_gen.finding_id(),
            vault_id=vault_id,
            augmentor_kind="noop",
            outcome=ResearchOutcome.NO_ACTIONABLE_RESULT,
            created_at=_now(),
        )
        await repo.create(p1)
        await repo.create(p2)
        await repo.create(p3)
        await sqlite_db.commit()

        results = await repo.list_by_finding(finding_id)
        assert len(results) == 2


class TestDiscoveredSources:
    @pytest.mark.asyncio
    async def test_add_and_list(self, repo, id_gen, sqlite_db):
        packet_id = id_gen.packet_id()
        # Create parent packet first
        packet = ResearchPacket(
            packet_id=packet_id,
            finding_id=id_gen.finding_id(),
            vault_id=id_gen.vault_id(),
            augmentor_kind="perplexity",
            outcome=ResearchOutcome.SUFFICIENT_FOR_REPAIR,
            created_at=_now(),
        )
        await repo.create(packet)

        src = ResearchPacketDiscoveredSource(
            id=id_gen.generate("rds"),
            packet_id=packet_id,
            url="https://example.com/paper",
            title="New Paper",
            summary="Important findings",
            relevance=0.92,
            trust_tier="standard",
        )
        await repo.add_discovered_source(src)
        await sqlite_db.commit()

        sources = await repo.list_discovered_sources(packet_id)
        assert len(sources) == 1
        assert sources[0].url == "https://example.com/paper"
        assert sources[0].relevance == 0.92


class TestIngestJobs:
    @pytest.mark.asyncio
    async def test_add_and_list(self, repo, id_gen, sqlite_db):
        packet_id = id_gen.packet_id()
        packet = ResearchPacket(
            packet_id=packet_id,
            finding_id=id_gen.finding_id(),
            vault_id=id_gen.vault_id(),
            augmentor_kind="noop",
            outcome=ResearchOutcome.NEW_SOURCES_PENDING,
            created_at=_now(),
        )
        await repo.create(packet)

        ij = ResearchPacketIngestJob(
            packet_id=packet_id,
            ingest_job_id=id_gen.job_id(),
        )
        await repo.add_ingest_job(ij)
        await sqlite_db.commit()

        jobs = await repo.list_ingest_jobs(packet_id)
        assert len(jobs) == 1
        assert jobs[0].ingest_job_id == ij.ingest_job_id


class TestContradictionResult:
    @pytest.mark.asyncio
    async def test_set_and_get(self, repo, id_gen, sqlite_db):
        packet_id = id_gen.packet_id()
        packet = ResearchPacket(
            packet_id=packet_id,
            finding_id=id_gen.finding_id(),
            vault_id=id_gen.vault_id(),
            augmentor_kind="perplexity",
            outcome=ResearchOutcome.SUFFICIENT_FOR_REPAIR,
            created_at=_now(),
        )
        await repo.create(packet)

        cr = ResearchPacketContradictionResult(
            packet_id=packet_id,
            summary="Claims contradict",
            resolution="claim_a_stronger",
            confidence=0.85,
            supporting_evidence=["Evidence A", "Evidence B"],
        )
        await repo.set_contradiction_result(cr)
        await sqlite_db.commit()

        result = await repo.get_contradiction_result(packet_id)
        assert result is not None
        assert result.resolution == "claim_a_stronger"
        assert result.confidence == 0.85
        assert len(result.supporting_evidence) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get_contradiction_result(id_gen.packet_id())
        assert result is None


class TestFreshnessResult:
    @pytest.mark.asyncio
    async def test_set_and_get(self, repo, id_gen, sqlite_db):
        packet_id = id_gen.packet_id()
        packet = ResearchPacket(
            packet_id=packet_id,
            finding_id=id_gen.finding_id(),
            vault_id=id_gen.vault_id(),
            augmentor_kind="perplexity",
            outcome=ResearchOutcome.SUFFICIENT_FOR_REPAIR,
            created_at=_now(),
        )
        await repo.create(packet)

        fr = ResearchPacketFreshnessResult(
            packet_id=packet_id,
            is_stale=True,
            reason="Source updated since last validation",
            newer_evidence=["https://newer.com/v2"],
        )
        await repo.set_freshness_result(fr)
        await sqlite_db.commit()

        result = await repo.get_freshness_result(packet_id)
        assert result is not None
        assert result.is_stale is True
        assert result.reason == "Source updated since last validation"
        assert len(result.newer_evidence) == 1

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get_freshness_result(id_gen.packet_id())
        assert result is None
