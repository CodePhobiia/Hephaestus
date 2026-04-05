"""Tests for SQLite LintReportRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.models import LintReport
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.lint_report_repo import SqliteLintReportRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteLintReportRepository(sqlite_db)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


class TestLintReportCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo, id_gen, sqlite_db):
        report = LintReport(
            report_id=id_gen.report_id(),
            vault_id=id_gen.vault_id(),
            workbook_id=None,
            job_id=id_gen.job_id(),
            finding_count=15,
            findings_by_category={"stale_evidence": 5, "orphaned_page": 10},
            findings_by_severity={"warning": 10, "info": 5},
            debt_score=42.5,
            debt_policy_version="1.0.0",
            raw_counts={"stale_evidence:warning": 5},
            created_at=_now(),
        )
        await repo.create(report)
        await sqlite_db.commit()

        result = await repo.get(report.report_id)
        assert result is not None
        assert result.finding_count == 15
        assert result.debt_score == 42.5
        assert result.findings_by_category == {"stale_evidence": 5, "orphaned_page": 10}

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get(id_gen.report_id())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_job(self, repo, id_gen, sqlite_db):
        job_id = id_gen.job_id()
        report = LintReport(
            report_id=id_gen.report_id(),
            vault_id=id_gen.vault_id(),
            workbook_id=None,
            job_id=job_id,
            finding_count=3,
            findings_by_category={},
            findings_by_severity={},
            debt_score=10.0,
            debt_policy_version="1.0.0",
            raw_counts={},
            created_at=_now(),
        )
        await repo.create(report)
        await sqlite_db.commit()

        result = await repo.get_by_job(job_id)
        assert result is not None
        assert result.report_id == report.report_id

    @pytest.mark.asyncio
    async def test_list_by_vault(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        other_vault = id_gen.vault_id()

        r1 = LintReport(
            report_id=id_gen.report_id(),
            vault_id=vault_id,
            workbook_id=None,
            job_id=id_gen.job_id(),
            finding_count=5,
            findings_by_category={},
            findings_by_severity={},
            debt_score=20.0,
            debt_policy_version="1.0.0",
            raw_counts={},
            created_at=_now(),
        )
        r2 = LintReport(
            report_id=id_gen.report_id(),
            vault_id=vault_id,
            workbook_id=None,
            job_id=id_gen.job_id(),
            finding_count=10,
            findings_by_category={},
            findings_by_severity={},
            debt_score=35.0,
            debt_policy_version="1.0.0",
            raw_counts={},
            created_at=_now(),
        )
        r3 = LintReport(
            report_id=id_gen.report_id(),
            vault_id=other_vault,
            workbook_id=None,
            job_id=id_gen.job_id(),
            finding_count=1,
            findings_by_category={},
            findings_by_severity={},
            debt_score=5.0,
            debt_policy_version="1.0.0",
            raw_counts={},
            created_at=_now(),
        )
        await repo.create(r1)
        await repo.create(r2)
        await repo.create(r3)
        await sqlite_db.commit()

        results = await repo.list_by_vault(vault_id)
        assert len(results) == 2
