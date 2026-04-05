"""SQLite implementation of LintReportRepository."""

from __future__ import annotations

import json
from datetime import datetime

import aiosqlite

from hephaestus.forgebase.domain.models import LintReport
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.lint_report_repo import LintReportRepository


class SqliteLintReportRepository(LintReportRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, report: LintReport) -> None:
        await self._db.execute(
            """INSERT INTO fb_lint_reports
            (report_id, vault_id, workbook_id, job_id, finding_count,
             findings_by_category, findings_by_severity, debt_score,
             debt_policy_version, raw_counts, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(report.report_id),
                str(report.vault_id),
                str(report.workbook_id) if report.workbook_id else None,
                str(report.job_id),
                report.finding_count,
                json.dumps(report.findings_by_category),
                json.dumps(report.findings_by_severity),
                report.debt_score,
                report.debt_policy_version,
                json.dumps(report.raw_counts),
                report.created_at.isoformat(),
            ),
        )

    async def get(self, report_id: EntityId) -> LintReport | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_reports WHERE report_id = ?",
            (str(report_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_report(row)

    async def get_by_job(self, job_id: EntityId) -> LintReport | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_reports WHERE job_id = ?",
            (str(job_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_report(row)

    async def list_by_vault(self, vault_id: EntityId) -> list[LintReport]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_reports WHERE vault_id = ? ORDER BY created_at DESC",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_report(r) for r in rows]

    @staticmethod
    def _row_to_report(row: aiosqlite.Row) -> LintReport:
        return LintReport(
            report_id=EntityId(row["report_id"]),
            vault_id=EntityId(row["vault_id"]),
            workbook_id=EntityId(row["workbook_id"]) if row["workbook_id"] else None,
            job_id=EntityId(row["job_id"]),
            finding_count=row["finding_count"],
            findings_by_category=json.loads(row["findings_by_category"]),
            findings_by_severity=json.loads(row["findings_by_severity"]),
            debt_score=row["debt_score"],
            debt_policy_version=row["debt_policy_version"],
            raw_counts=json.loads(row["raw_counts"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
