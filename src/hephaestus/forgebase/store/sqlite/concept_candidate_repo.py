"""SQLite implementation of ConceptCandidateRepository."""
from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import CandidateKind, CandidateStatus
from hephaestus.forgebase.domain.models import ConceptCandidate
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.repository.concept_candidate_repo import ConceptCandidateRepository


class SqliteConceptCandidateRepository(ConceptCandidateRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, candidate: ConceptCandidate) -> None:
        await self._db.execute(
            """INSERT INTO fb_concept_candidates
            (candidate_id, vault_id, workbook_id, source_id, source_version,
             source_compile_job_id, name, normalized_name, aliases,
             candidate_kind, confidence, salience, status, resolved_page_id,
             compiler_policy_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(candidate.candidate_id),
                str(candidate.vault_id),
                str(candidate.workbook_id) if candidate.workbook_id else None,
                str(candidate.source_id),
                candidate.source_version.number,
                str(candidate.source_compile_job_id),
                candidate.name,
                candidate.normalized_name,
                json.dumps(candidate.aliases),
                candidate.candidate_kind.value,
                candidate.confidence,
                candidate.salience,
                candidate.status.value,
                str(candidate.resolved_page_id) if candidate.resolved_page_id else None,
                candidate.compiler_policy_version,
                candidate.created_at.isoformat(),
            ),
        )

    async def get(self, candidate_id: EntityId) -> ConceptCandidate | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_concept_candidates WHERE candidate_id = ?",
            (str(candidate_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_candidate(row)

    async def list_active(
        self,
        vault_id: EntityId,
        workbook_id: EntityId | None = None,
    ) -> list[ConceptCandidate]:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND workbook_id = ? AND status = ? ORDER BY created_at",
                (str(vault_id), str(workbook_id), CandidateStatus.ACTIVE.value),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND workbook_id IS NULL AND status = ? ORDER BY created_at",
                (str(vault_id), CandidateStatus.ACTIVE.value),
            )
        rows = await cursor.fetchall()
        return [self._row_to_candidate(r) for r in rows]

    async def list_by_source(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> list[ConceptCandidate]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_concept_candidates WHERE source_id = ? AND source_version = ? ORDER BY created_at",
            (str(source_id), source_version.number),
        )
        rows = await cursor.fetchall()
        return [self._row_to_candidate(r) for r in rows]

    async def list_by_normalized_name(
        self,
        vault_id: EntityId,
        normalized_name: str,
        workbook_id: EntityId | None = None,
    ) -> list[ConceptCandidate]:
        if workbook_id is not None:
            cursor = await self._db.execute(
                "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND normalized_name = ? AND workbook_id = ? ORDER BY created_at",
                (str(vault_id), normalized_name, str(workbook_id)),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM fb_concept_candidates WHERE vault_id = ? AND normalized_name = ? AND workbook_id IS NULL ORDER BY created_at",
                (str(vault_id), normalized_name),
            )
        rows = await cursor.fetchall()
        return [self._row_to_candidate(r) for r in rows]

    async def update_status(
        self,
        candidate_id: EntityId,
        status: CandidateStatus,
        resolved_page_id: EntityId | None = None,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_concept_candidates SET status = ?, resolved_page_id = ? WHERE candidate_id = ?",
            (
                status.value,
                str(resolved_page_id) if resolved_page_id else None,
                str(candidate_id),
            ),
        )

    async def supersede_by_source(
        self,
        source_id: EntityId,
        source_version: Version,
    ) -> int:
        cursor = await self._db.execute(
            "UPDATE fb_concept_candidates SET status = ? WHERE source_id = ? AND source_version = ? AND status = ?",
            (
                CandidateStatus.SUPERSEDED.value,
                str(source_id),
                source_version.number,
                CandidateStatus.ACTIVE.value,
            ),
        )
        return cursor.rowcount

    @staticmethod
    def _row_to_candidate(row: aiosqlite.Row) -> ConceptCandidate:
        return ConceptCandidate(
            candidate_id=EntityId(row["candidate_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            source_id=EntityId(row["source_id"]),
            source_version=Version(row["source_version"]),
            source_compile_job_id=EntityId(row["source_compile_job_id"]),
            name=row["name"],
            normalized_name=row["normalized_name"],
            aliases=json.loads(row["aliases"]),
            candidate_kind=CandidateKind(row["candidate_kind"]),
            confidence=row["confidence"],
            salience=row["salience"],
            status=CandidateStatus(row["status"]),
            resolved_page_id=EntityId(row["resolved_page_id"]) if row["resolved_page_id"] else None,
            compiler_policy_version=row["compiler_policy_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
