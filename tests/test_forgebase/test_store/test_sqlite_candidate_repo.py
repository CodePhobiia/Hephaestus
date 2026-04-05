"""Tests for SQLite concept candidate and evidence repositories."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import CandidateKind, CandidateStatus
from hephaestus.forgebase.domain.models import ConceptCandidate, ConceptCandidateEvidence
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version
from hephaestus.forgebase.store.sqlite.candidate_evidence_repo import (
    SqliteCandidateEvidenceRepository,
)
from hephaestus.forgebase.store.sqlite.concept_candidate_repo import (
    SqliteConceptCandidateRepository,
)


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


def _candidate(
    id_gen,
    vault_id: EntityId,
    *,
    name: str = "Solid Electrolyte Interphase",
    normalized_name: str = "solid electrolyte interphase",
    source_id: EntityId | None = None,
    source_version: Version | None = None,
    status: CandidateStatus = CandidateStatus.ACTIVE,
    workbook_id: EntityId | None = None,
) -> ConceptCandidate:
    return ConceptCandidate(
        candidate_id=id_gen.generate("cand"),
        vault_id=vault_id,
        workbook_id=workbook_id,
        source_id=source_id or id_gen.generate("source"),
        source_version=source_version or Version(1),
        source_compile_job_id=id_gen.generate("job"),
        name=name,
        normalized_name=normalized_name,
        aliases=["SEI"],
        candidate_kind=CandidateKind.MECHANISM,
        confidence=0.92,
        salience=0.85,
        status=status,
        resolved_page_id=None,
        compiler_policy_version="1.0.0",
        created_at=_now(),
    )


@pytest.mark.asyncio
class TestSqliteConceptCandidateRepository:
    async def test_create_and_get(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        c = _candidate(id_gen, vault_id)

        await repo.create(c)
        await sqlite_db.commit()

        got = await repo.get(c.candidate_id)
        assert got is not None
        assert got.name == "Solid Electrolyte Interphase"
        assert got.status == CandidateStatus.ACTIVE
        assert got.aliases == ["SEI"]

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        assert await repo.get(id_gen.generate("cand")) is None

    async def test_list_active(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        c1 = _candidate(id_gen, vault_id, name="C1", normalized_name="c1")
        c2 = _candidate(
            id_gen, vault_id, name="C2", normalized_name="c2", status=CandidateStatus.SUPERSEDED
        )
        c3 = _candidate(id_gen, vault_id, name="C3", normalized_name="c3")

        for c in [c1, c2, c3]:
            await repo.create(c)
        await sqlite_db.commit()

        active = await repo.list_active(vault_id)
        assert len(active) == 2
        assert all(c.status == CandidateStatus.ACTIVE for c in active)

    async def test_list_by_source(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        source_id = id_gen.generate("source")

        c1 = _candidate(
            id_gen,
            vault_id,
            name="C1",
            normalized_name="c1",
            source_id=source_id,
            source_version=Version(1),
        )
        c2 = _candidate(
            id_gen,
            vault_id,
            name="C2",
            normalized_name="c2",
            source_id=source_id,
            source_version=Version(1),
        )
        c3 = _candidate(id_gen, vault_id, name="C3", normalized_name="c3")  # different source

        for c in [c1, c2, c3]:
            await repo.create(c)
        await sqlite_db.commit()

        results = await repo.list_by_source(source_id, Version(1))
        assert len(results) == 2

    async def test_list_by_normalized_name(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        c1 = _candidate(id_gen, vault_id, name="SEI", normalized_name="sei")
        c2 = _candidate(id_gen, vault_id, name="SEI Layer", normalized_name="sei")
        c3 = _candidate(id_gen, vault_id, name="Other", normalized_name="other")

        for c in [c1, c2, c3]:
            await repo.create(c)
        await sqlite_db.commit()

        results = await repo.list_by_normalized_name(vault_id, "sei")
        assert len(results) == 2

    async def test_update_status(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        c = _candidate(id_gen, vault_id)

        await repo.create(c)
        await sqlite_db.commit()

        page_id = id_gen.generate("page")
        await repo.update_status(c.candidate_id, CandidateStatus.PROMOTED, resolved_page_id=page_id)
        await sqlite_db.commit()

        got = await repo.get(c.candidate_id)
        assert got is not None
        assert got.status == CandidateStatus.PROMOTED
        assert got.resolved_page_id == page_id

    async def test_supersede_by_source(self, sqlite_db, id_gen):
        repo = SqliteConceptCandidateRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        source_id = id_gen.generate("source")

        c1 = _candidate(
            id_gen,
            vault_id,
            name="C1",
            normalized_name="c1",
            source_id=source_id,
            source_version=Version(1),
        )
        c2 = _candidate(
            id_gen,
            vault_id,
            name="C2",
            normalized_name="c2",
            source_id=source_id,
            source_version=Version(1),
        )
        c3 = _candidate(
            id_gen,
            vault_id,
            name="C3",
            normalized_name="c3",
            source_id=source_id,
            source_version=Version(1),
            status=CandidateStatus.PROMOTED,
        )

        for c in [c1, c2, c3]:
            await repo.create(c)
        await sqlite_db.commit()

        count = await repo.supersede_by_source(source_id, Version(1))
        await sqlite_db.commit()

        # Only 2 ACTIVE candidates should have been superseded (not the PROMOTED one)
        assert count == 2

        got = await repo.get(c3.candidate_id)
        assert got is not None
        assert got.status == CandidateStatus.PROMOTED  # unchanged


@pytest.mark.asyncio
class TestSqliteCandidateEvidenceRepository:
    async def test_create_and_list(self, sqlite_db, id_gen):
        cand_repo = SqliteConceptCandidateRepository(sqlite_db)
        ev_repo = SqliteCandidateEvidenceRepository(sqlite_db)

        vault_id = id_gen.vault_id()
        c = _candidate(id_gen, vault_id)
        await cand_repo.create(c)

        seg = EvidenceSegmentRef(
            source_id=c.source_id,
            source_version=Version(1),
            segment_start=100,
            segment_end=300,
            section_key="3.2",
            preview_text="The SEI layer...",
        )
        ev = ConceptCandidateEvidence(
            evidence_id=id_gen.generate("cevd"),
            candidate_id=c.candidate_id,
            segment_ref=seg,
            role="DEFINITION",
            created_at=_now(),
        )

        await ev_repo.create(ev)
        await sqlite_db.commit()

        results = await ev_repo.list_by_candidate(c.candidate_id)
        assert len(results) == 1
        assert results[0].role == "DEFINITION"
        assert results[0].segment_ref.segment_start == 100
        assert results[0].segment_ref.section_key == "3.2"

    async def test_list_empty(self, sqlite_db, id_gen):
        ev_repo = SqliteCandidateEvidenceRepository(sqlite_db)
        results = await ev_repo.list_by_candidate(id_gen.generate("cand"))
        assert results == []
