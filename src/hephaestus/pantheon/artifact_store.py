"""Council artifact persistence — store and query Pantheon deliberation artifacts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heph_council_artifacts (
    artifact_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    candidate_id    TEXT,
    round_index     INTEGER,
    content         TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_council_run ON heph_council_artifacts(run_id);
"""


@dataclass
class CouncilArtifactRecord:
    """A persisted council deliberation artifact."""

    artifact_id: str = field(default_factory=lambda: uuid4().hex)
    run_id: str = ""
    artifact_type: str = ""  # canon, dossier, audit, vote, reforge, objection, explanation
    candidate_id: str = ""
    round_index: int = 0
    content: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "candidate_id": self.candidate_id,
            "round_index": self.round_index,
            "content": self.content,
            "created_at": self.created_at,
        }


class CouncilArtifactStore:
    """Persists Pantheon deliberation artifacts linked to pipeline runs.

    Stores Athena canons, Hermes dossiers, Apollo audits, reforge records,
    votes, objections, and final accounting for post-hoc inspection and
    explainability.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._db: Any = None

    async def initialize(self) -> None:
        import aiosqlite

        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("CouncilArtifactStore initialized at %s", self._db_path)

    async def store(self, record: CouncilArtifactRecord) -> None:
        assert self._db is not None
        await self._db.execute(
            """
            INSERT OR REPLACE INTO heph_council_artifacts
            (artifact_id, run_id, artifact_type, candidate_id, round_index, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.artifact_id,
                record.run_id,
                record.artifact_type,
                record.candidate_id,
                record.round_index,
                json.dumps(record.content),
                record.created_at,
            ),
        )
        await self._db.commit()

    async def store_many(self, records: list[CouncilArtifactRecord]) -> None:
        for record in records:
            await self.store(record)

    async def get_by_run(self, run_id: str) -> list[CouncilArtifactRecord]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM heph_council_artifacts WHERE run_id = ? ORDER BY round_index, created_at",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_type(self, run_id: str, artifact_type: str) -> list[CouncilArtifactRecord]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM heph_council_artifacts WHERE run_id = ? AND artifact_type = ?",
            (run_id, artifact_type),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def explain_decision(self, run_id: str) -> dict[str, Any]:
        """Generate a structured explanation of the council's decision for a run.

        Returns a report covering:
        - Athena's structural analysis (canon)
        - Hermes' reality assessment (dossier)
        - Apollo's audits
        - Objection history
        - Vote records
        - Reforge attempts
        - Final outcome with causal chain
        """
        artifacts = await self.get_by_run(run_id)
        if not artifacts:
            return {"run_id": run_id, "explanation": "No council artifacts found"}

        explanation: dict[str, Any] = {
            "run_id": run_id,
            "sections": {},
        }

        by_type: dict[str, list[CouncilArtifactRecord]] = {}
        for a in artifacts:
            by_type.setdefault(a.artifact_type, []).append(a)

        # Athena canon
        canons = by_type.get("canon", [])
        if canons:
            explanation["sections"]["structural_analysis"] = canons[0].content

        # Hermes dossier
        dossiers = by_type.get("dossier", [])
        if dossiers:
            explanation["sections"]["reality_assessment"] = dossiers[0].content

        # Apollo audits
        audits = by_type.get("audit", [])
        if audits:
            explanation["sections"]["adversarial_audits"] = [a.content for a in audits]

        # Objection history
        objections = by_type.get("objection", [])
        if objections:
            explanation["sections"]["objection_ledger"] = [o.content for o in objections]

        # Votes
        votes = by_type.get("vote", [])
        if votes:
            explanation["sections"]["vote_records"] = [v.content for v in votes]

        # Reforges
        reforges = by_type.get("reforge", [])
        if reforges:
            explanation["sections"]["reforge_attempts"] = [r.content for r in reforges]

        # Final explanation
        explanations = by_type.get("explanation", [])
        if explanations:
            explanation["sections"]["final_explanation"] = explanations[-1].content

        # Accounting
        accounting_records = by_type.get("accounting", [])
        if accounting_records:
            explanation["sections"]["accounting"] = accounting_records[-1].content

        explanation["artifact_count"] = len(artifacts)
        explanation["artifact_types"] = sorted(by_type.keys())

        return explanation

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @staticmethod
    def _row_to_record(row: Any) -> CouncilArtifactRecord:
        content = row["content"]
        if isinstance(content, str):
            content = json.loads(content)
        return CouncilArtifactRecord(
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            artifact_type=row["artifact_type"],
            candidate_id=row["candidate_id"] or "",
            round_index=int(row["round_index"] or 0),
            content=content,
            created_at=row["created_at"],
        )


__all__ = [
    "CouncilArtifactRecord",
    "CouncilArtifactStore",
]
