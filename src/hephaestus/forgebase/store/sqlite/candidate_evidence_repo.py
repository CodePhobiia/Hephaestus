"""SQLite implementation of CandidateEvidenceRepository."""

from __future__ import annotations

from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.models import ConceptCandidateEvidence
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version
from hephaestus.forgebase.repository.candidate_evidence_repo import CandidateEvidenceRepository


class SqliteCandidateEvidenceRepository(CandidateEvidenceRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, evidence: ConceptCandidateEvidence) -> None:
        seg = evidence.segment_ref
        await self._db.execute(
            """INSERT INTO fb_candidate_evidence
            (evidence_id, candidate_id, seg_source_id, seg_source_version,
             seg_start, seg_end, seg_section_key, seg_preview_text, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(evidence.evidence_id),
                str(evidence.candidate_id),
                str(seg.source_id),
                seg.source_version.number,
                seg.segment_start,
                seg.segment_end,
                seg.section_key,
                seg.preview_text,
                evidence.role,
                evidence.created_at.isoformat(),
            ),
        )

    async def list_by_candidate(
        self,
        candidate_id: EntityId,
    ) -> list[ConceptCandidateEvidence]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_candidate_evidence WHERE candidate_id = ? ORDER BY created_at",
            (str(candidate_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_evidence(r) for r in rows]

    @staticmethod
    def _row_to_evidence(row: aiosqlite.Row) -> ConceptCandidateEvidence:
        return ConceptCandidateEvidence(
            evidence_id=EntityId(row["evidence_id"]),
            candidate_id=EntityId(row["candidate_id"]),
            segment_ref=EvidenceSegmentRef(
                source_id=EntityId(row["seg_source_id"]),
                source_version=Version(row["seg_source_version"]),
                segment_start=row["seg_start"],
                segment_end=row["seg_end"],
                section_key=row["seg_section_key"],
                preview_text=row["seg_preview_text"],
            ),
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
