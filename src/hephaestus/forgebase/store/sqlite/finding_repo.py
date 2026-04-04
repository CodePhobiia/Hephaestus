"""SQLite implementation of FindingRepository."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
    RemediationRoute,
    RemediationStatus,
    RouteSource,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.finding_repo import FindingRepository


class SqliteFindingRepository(FindingRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(self, finding: LintFinding) -> None:
        affected_ids_json = json.dumps([str(eid) for eid in finding.affected_entity_ids])
        await self._db.execute(
            """INSERT INTO fb_lint_findings
            (finding_id, job_id, vault_id, category, severity, page_id, claim_id,
             description, suggested_action, status, resolved_at,
             finding_fingerprint, remediation_status, disposition,
             remediation_route, route_source, detector_version, confidence,
             affected_entity_ids, research_job_id, repair_workbook_id,
             repair_batch_id, verification_job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                finding.finding_fingerprint,
                finding.remediation_status.value,
                finding.disposition.value,
                finding.remediation_route.value if finding.remediation_route else None,
                finding.route_source.value if finding.route_source else None,
                finding.detector_version,
                finding.confidence,
                affected_ids_json,
                str(finding.research_job_id) if finding.research_job_id else None,
                str(finding.repair_workbook_id) if finding.repair_workbook_id else None,
                str(finding.repair_batch_id) if finding.repair_batch_id else None,
                str(finding.verification_job_id) if finding.verification_job_id else None,
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
        resolved_at = datetime.now(UTC).isoformat() if status != FindingStatus.OPEN else None
        await self._db.execute(
            "UPDATE fb_lint_findings SET status = ?, resolved_at = ? WHERE finding_id = ?",
            (status.value, resolved_at, str(finding_id)),
        )

    async def update_remediation_status(
        self,
        finding_id: EntityId,
        status: RemediationStatus,
        route: RemediationRoute | None = None,
        route_source: RouteSource | None = None,
    ) -> None:
        if route is not None:
            await self._db.execute(
                """UPDATE fb_lint_findings
                SET remediation_status = ?, remediation_route = ?, route_source = ?
                WHERE finding_id = ?""",
                (
                    status.value,
                    route.value,
                    route_source.value if route_source else None,
                    str(finding_id),
                ),
            )
        else:
            await self._db.execute(
                "UPDATE fb_lint_findings SET remediation_status = ? WHERE finding_id = ?",
                (status.value, str(finding_id)),
            )

    async def update_disposition(
        self,
        finding_id: EntityId,
        disposition: FindingDisposition,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_lint_findings SET disposition = ? WHERE finding_id = ?",
            (disposition.value, str(finding_id)),
        )

    async def find_by_fingerprint(
        self,
        vault_id: EntityId,
        fingerprint: str,
    ) -> LintFinding | None:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE vault_id = ? AND finding_fingerprint = ?",
            (str(vault_id), fingerprint),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_finding(row)

    async def list_by_disposition(
        self,
        vault_id: EntityId,
        disposition: FindingDisposition,
    ) -> list[LintFinding]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE vault_id = ? AND disposition = ?",
            (str(vault_id), disposition.value),
        )
        rows = await cursor.fetchall()
        return [self._row_to_finding(r) for r in rows]

    async def list_by_remediation_status(
        self,
        vault_id: EntityId,
        status: RemediationStatus,
    ) -> list[LintFinding]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE vault_id = ? AND remediation_status = ?",
            (str(vault_id), status.value),
        )
        rows = await cursor.fetchall()
        return [self._row_to_finding(r) for r in rows]

    async def set_research_job_id(
        self,
        finding_id: EntityId,
        research_job_id: EntityId,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_lint_findings SET research_job_id = ? WHERE finding_id = ?",
            (str(research_job_id), str(finding_id)),
        )

    async def set_repair_workbook(
        self,
        finding_id: EntityId,
        repair_workbook_id: EntityId,
        repair_batch_id: EntityId,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_lint_findings SET repair_workbook_id = ?, repair_batch_id = ? WHERE finding_id = ?",
            (str(repair_workbook_id), str(repair_batch_id), str(finding_id)),
        )

    async def set_verification_job_id(
        self,
        finding_id: EntityId,
        verification_job_id: EntityId,
    ) -> None:
        await self._db.execute(
            "UPDATE fb_lint_findings SET verification_job_id = ? WHERE finding_id = ?",
            (str(verification_job_id), str(finding_id)),
        )

    async def list_by_vault(self, vault_id: EntityId) -> list[LintFinding]:
        cursor = await self._db.execute(
            "SELECT * FROM fb_lint_findings WHERE vault_id = ?",
            (str(vault_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_finding(r) for r in rows]

    @staticmethod
    def _row_to_finding(row: aiosqlite.Row) -> LintFinding:
        affected_raw = row["affected_entity_ids"]
        if affected_raw:
            affected_list = json.loads(affected_raw)
            affected_entity_ids = [EntityId(eid) for eid in affected_list] if affected_list else []
        else:
            affected_entity_ids = []

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
            finding_fingerprint=row["finding_fingerprint"],
            remediation_status=RemediationStatus(row["remediation_status"]),
            disposition=FindingDisposition(row["disposition"]),
            remediation_route=RemediationRoute(row["remediation_route"]) if row["remediation_route"] else None,
            route_source=RouteSource(row["route_source"]) if row["route_source"] else None,
            detector_version=row["detector_version"],
            confidence=row["confidence"],
            affected_entity_ids=affected_entity_ids,
            research_job_id=EntityId(row["research_job_id"]) if row["research_job_id"] else None,
            repair_workbook_id=EntityId(row["repair_workbook_id"]) if row["repair_workbook_id"] else None,
            repair_batch_id=EntityId(row["repair_batch_id"]) if row["repair_batch_id"] else None,
            verification_job_id=EntityId(row["verification_job_id"]) if row["verification_job_id"] else None,
        )
