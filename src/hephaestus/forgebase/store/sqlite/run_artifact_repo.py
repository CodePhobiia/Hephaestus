"""SQLite implementation of KnowledgeRunArtifactRepository."""
from __future__ import annotations

import aiosqlite

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import KnowledgeRunArtifact
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.run_artifact_repo import KnowledgeRunArtifactRepository


class SqliteRunArtifactRepository(KnowledgeRunArtifactRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, artifact: KnowledgeRunArtifact) -> None:
        await self._db.execute(
            "INSERT INTO fb_run_artifacts (ref_id, entity_kind, entity_id, role) VALUES (?, ?, ?, ?)",
            (
                str(artifact.ref_id),
                artifact.entity_kind.value,
                str(artifact.entity_id),
                artifact.role,
            ),
        )

    async def list_by_ref(self, ref_id: EntityId) -> list[KnowledgeRunArtifact]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_run_artifacts WHERE ref_id = ?",
            (str(ref_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_artifact(r) for r in rows]

    @staticmethod
    def _row_to_artifact(row: aiosqlite.Row) -> KnowledgeRunArtifact:
        return KnowledgeRunArtifact(
            ref_id=EntityId(row["ref_id"]),
            entity_kind=EntityKind(row["entity_kind"]),
            entity_id=EntityId(row["entity_id"]),
            role=row["role"],
        )
