"""Tests for contract view models."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


class TestVaultSummary:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.contracts.views import VaultSummary

        summary = VaultSummary(
            vault_id=id_gen.vault_id(),
            name="Battery Materials",
            description="Research on battery chemistry",
            health_score=85.0,
            page_count=42,
            claim_count=120,
            source_count=15,
            finding_count=3,
            last_compiled_at=_now(),
            last_linted_at=_now(),
        )

        assert summary.name == "Battery Materials"
        assert summary.health_score == 85.0
        assert summary.page_count == 42
        assert summary.finding_count == 3

    def test_construction_minimal(self, id_gen):
        from hephaestus.forgebase.contracts.views import VaultSummary

        summary = VaultSummary(
            vault_id=id_gen.vault_id(),
            name="Empty Vault",
            description="",
            health_score=100.0,
            page_count=0,
            claim_count=0,
            source_count=0,
            finding_count=0,
            last_compiled_at=None,
            last_linted_at=None,
        )

        assert summary.last_compiled_at is None
        assert summary.last_linted_at is None


class TestWorkbookDiffView:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.contracts.views import WorkbookDiffView

        view = WorkbookDiffView(
            workbook_id=id_gen.workbook_id(),
            vault_id=id_gen.vault_id(),
            workbook_name="repair-stale-evidence",
            pages_added=3,
            pages_modified=2,
            pages_deleted=0,
            claims_added=10,
            claims_modified=5,
            claims_deleted=1,
            links_added=4,
            links_deleted=0,
        )

        assert view.workbook_name == "repair-stale-evidence"
        assert view.pages_added == 3
        assert view.claims_modified == 5


class TestLintReportView:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.contracts.views import LintReportView

        view = LintReportView(
            report_id=id_gen.report_id(),
            vault_id=id_gen.vault_id(),
            job_id=id_gen.job_id(),
            finding_count=15,
            findings_by_category={"stale_evidence": 5, "orphaned_page": 10},
            findings_by_severity={"warning": 10, "info": 5},
            debt_score=42.5,
            created_at=_now(),
        )

        assert view.finding_count == 15
        assert view.debt_score == 42.5
        assert view.findings_by_severity == {"warning": 10, "info": 5}


class TestQueryStubs:
    def test_vault_query(self, id_gen):
        from hephaestus.forgebase.contracts.query import QueryScope, VaultQuery

        q = VaultQuery(
            vault_id=id_gen.vault_id(),
            query_text="battery cathode materials",
            scope=QueryScope.ALL,
            max_results=10,
        )

        assert q.query_text == "battery cathode materials"
        assert q.scope == QueryScope.ALL
        assert q.max_results == 10

    def test_query_result(self, id_gen):
        from hephaestus.forgebase.contracts.query import QueryResult

        result = QueryResult(
            query_id=id_gen.generate("qry"),
            vault_id=id_gen.vault_id(),
            matches=[],
            total_count=0,
        )

        assert result.total_count == 0
        assert result.matches == []


class TestAgentStubs:
    def test_agent_role(self):
        from hephaestus.forgebase.contracts.agent import AgentRole

        assert AgentRole.SCOUT.value == "scout"
        assert AgentRole.COMPILER.value == "compiler"
        assert AgentRole.SKEPTIC.value == "skeptic"

    def test_agent_task(self, id_gen):
        from hephaestus.forgebase.contracts.agent import AgentRole, AgentTask

        task = AgentTask(
            task_id=id_gen.generate("task"),
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
            role=AgentRole.SCOUT,
            objective="Research battery cathode materials",
            config={},
        )

        assert task.role == AgentRole.SCOUT
        assert task.objective == "Research battery cathode materials"

    def test_agent_run(self, id_gen):
        from hephaestus.forgebase.contracts.agent import AgentRun, RunStatus

        run = AgentRun(
            run_id=id_gen.generate("arun"),
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
            status=RunStatus.PENDING,
            created_at=_now(),
            completed_at=None,
        )

        assert run.status == RunStatus.PENDING
        assert run.completed_at is None


class TestFusionRunModel:
    def test_construction(self, id_gen):
        from hephaestus.forgebase.domain.enums import FusionMode
        from hephaestus.forgebase.domain.models import FusionRun

        run = FusionRun(
            fusion_run_id=id_gen.generate("frun"),
            vault_ids=[id_gen.vault_id(), id_gen.vault_id()],
            problem="Improve battery longevity",
            fusion_mode=FusionMode.STRICT,
            status="pending",
            bridge_count=0,
            transfer_count=0,
            manifest_id=None,
            policy_version="1.0.0",
            created_at=_now(),
            completed_at=None,
        )

        assert run.fusion_run_id.prefix == "frun"
        assert len(run.vault_ids) == 2
        assert run.problem == "Improve battery longevity"
        assert run.fusion_mode == FusionMode.STRICT
        assert run.status == "pending"
        assert run.completed_at is None

    def test_construction_completed(self, id_gen):
        from hephaestus.forgebase.domain.enums import FusionMode
        from hephaestus.forgebase.domain.models import FusionRun

        run = FusionRun(
            fusion_run_id=id_gen.generate("frun"),
            vault_ids=[id_gen.vault_id(), id_gen.vault_id()],
            problem=None,
            fusion_mode=FusionMode.EXPLORATORY,
            status="completed",
            bridge_count=5,
            transfer_count=3,
            manifest_id=id_gen.generate("mfst"),
            policy_version="1.0.0",
            created_at=_now(),
            completed_at=_now(),
        )

        assert run.status == "completed"
        assert run.bridge_count == 5
        assert run.manifest_id is not None


class TestFusionEvents:
    def test_fusion_events_in_taxonomy(self):
        from hephaestus.forgebase.domain.event_types import EVENT_TAXONOMY

        fusion_events = [
            "fusion.requested",
            "fusion.candidates_generated",
            "fusion.analysis_completed",
            "fusion.synthesis_completed",
            "fusion.completed",
            "fusion.failed",
            "fusion.partial_completed",
            "fusion.persisted",
        ]

        for event in fusion_events:
            assert event in EVENT_TAXONOMY, f"{event} missing from EVENT_TAXONOMY"
