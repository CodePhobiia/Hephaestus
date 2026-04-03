"""Research artifact persistence — SQLite-backed store linked to run IDs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heph_research_artifacts (
    artifact_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,
    source_url      TEXT,
    content         TEXT,
    trust_tier      TEXT DEFAULT 'STANDARD',
    citation_quality REAL DEFAULT 0.0,
    created_at      TEXT NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_research_run ON heph_research_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_research_type ON heph_research_artifacts(artifact_type);
"""


@dataclass
class ResearchArtifactRecord:
    """A persisted research artifact."""

    artifact_id: str = field(default_factory=lambda: uuid4().hex)
    run_id: str = ""
    artifact_type: str = ""  # baseline_dossier, prior_art, grounding, workspace_dossier, benchmark
    source_url: str = ""
    content: str = ""
    trust_tier: str = "STANDARD"
    citation_quality: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "source_url": self.source_url,
            "trust_tier": self.trust_tier,
            "citation_quality": self.citation_quality,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class ResearchArtifactStore:
    """Persists research artifacts linked to pipeline runs.

    Uses aiosqlite for local/dev. Shares the same DB pattern as RunStore
    for production Postgres deployments.
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
        logger.info("ResearchArtifactStore initialized at %s", self._db_path)

    async def store(self, record: ResearchArtifactRecord) -> None:
        """Persist a single research artifact."""
        assert self._db is not None
        await self._db.execute(
            """
            INSERT OR REPLACE INTO heph_research_artifacts
            (artifact_id, run_id, artifact_type, source_url, content,
             trust_tier, citation_quality, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.artifact_id, record.run_id, record.artifact_type,
                record.source_url, record.content, record.trust_tier,
                record.citation_quality, record.created_at,
                json.dumps(record.metadata),
            ),
        )
        await self._db.commit()

    async def store_many(self, records: list[ResearchArtifactRecord]) -> None:
        """Persist multiple artifacts."""
        for record in records:
            await self.store(record)

    async def get_by_run(self, run_id: str) -> list[ResearchArtifactRecord]:
        """Retrieve all artifacts for a specific run."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM heph_research_artifacts WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_by_type(self, run_id: str, artifact_type: str) -> list[ResearchArtifactRecord]:
        """Retrieve artifacts of a specific type for a run."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM heph_research_artifacts WHERE run_id = ? AND artifact_type = ?",
            (run_id, artifact_type),
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def source_manifest(self, run_id: str) -> list[dict[str, Any]]:
        """Return a summary of all sources consulted for a run."""
        artifacts = await self.get_by_run(run_id)
        return [
            {
                "artifact_type": a.artifact_type,
                "source_url": a.source_url,
                "trust_tier": a.trust_tier,
                "citation_quality": a.citation_quality,
            }
            for a in artifacts
            if a.source_url
        ]

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @staticmethod
    def _row_to_record(row: Any) -> ResearchArtifactRecord:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return ResearchArtifactRecord(
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            artifact_type=row["artifact_type"],
            source_url=row["source_url"] or "",
            content=row["content"] or "",
            trust_tier=row["trust_tier"] or "STANDARD",
            citation_quality=float(row["citation_quality"] or 0.0),
            created_at=row["created_at"],
            metadata=metadata,
        )


__all__ = [
    "ResearchArtifactRecord",
    "ResearchArtifactStore",
]
