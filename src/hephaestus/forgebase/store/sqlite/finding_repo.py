"""SQLite implementation of FindingRepository."""
from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.finding_repo import FindingRepository


class SqliteFindingRepository(FindingRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, finding: LintFinding) -> None:
        await self._db.execute(
            "INSERT INTO fb_lint_findings (finding_id, job_id, vault_id, category, severity, page_id, claim_id, description, suggested_action, status, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(finding.finding_id),
                str(finding.job_id),
                str(finding.vault_id),
                finding.category.value,
                finding.severity.value,
                str(finding.page_id) if finding.page_id else None,
                str(finding.claim_id) if finding.claim_id else None,
                finding.description,
                finding.suggested_action,
                finding.status.value,
                finding.resolved_at.isoformat() if finding.resolved_at else None,
            ),
        )

    async def get(self, finding_id: EntityId) -> LintFinding | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE finding_id = ?",
            (str(finding_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_finding(row)

    async def list_by_job(self, job_id: EntityId) -> list[LintFinding]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE job_id = ?",
            (str(job_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_finding(r) for r in rows]

    async def update_status(self, finding_id: EntityId, status: FindingStatus) -> None:
        # Set resolved_at for any status that is not OPEN
        resolved_at = datetime.now(UTC).isoformat() if status != FindingStatus.OPEN else None
        await self._db.execute(
            "UPDATE fb_lint_findings SET status = ?, resolved_at = ? WHERE finding_id = ?",
            (status.value, resolved_at, str(finding_id)),
        )

    @staticmethod
    def _row_to_finding(row: aiosqlite.Row) -> LintFinding:
        return LintFinding(
            finding_id=EntityId(row["finding_id"]),
            job_id=EntityId(row["job_id"]),
            vault_id=EntityId(row["vault_id"]),
            category=FindingCategory(row["category"]),
            severity=FindingSeverity(row["severity"]),
            page_id=EntityId(row["page_id"]) if row["page_id"] else None,
            claim_id=EntityId(row["claim_id"]) if row["claim_id"] else None,
            description=row["description"],
            suggested_action=row["suggested_action"],
            status=FindingStatus(row["status"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )
