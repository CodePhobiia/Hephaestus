"""View contracts — read models for CLI and web UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hephaestus.forgebase.domain.values import EntityId


@dataclass
class VaultSummary:
    """Summary read model for vault overview (CLI/web)."""

    vault_id: EntityId
    name: str
    description: str
    health_score: float
    page_count: int
    claim_count: int
    source_count: int
    finding_count: int
    last_compiled_at: datetime | None
    last_linted_at: datetime | None


@dataclass
class WorkbookDiffView:
    """Read model showing workbook changes relative to canonical."""

    workbook_id: EntityId
    vault_id: EntityId
    workbook_name: str
    pages_added: int
    pages_modified: int
    pages_deleted: int
    claims_added: int
    claims_modified: int
    claims_deleted: int
    links_added: int
    links_deleted: int


@dataclass
class LintReportView:
    """Read model for lint report display."""

    report_id: EntityId
    vault_id: EntityId
    job_id: EntityId
    finding_count: int
    findings_by_category: dict[str, int]
    findings_by_severity: dict[str, int]
    debt_score: float
    created_at: datetime
