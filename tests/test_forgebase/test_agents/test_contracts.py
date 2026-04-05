"""Tests for agent contracts — task model, roles, statuses."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.contracts.agent import (
    AgentRole,
    AgentRun,
    AgentTask,
    RunStatus,
    TaskStatus,
)
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


class TestAgentRole:
    def test_all_six_roles_exist(self):
        roles = {r.value for r in AgentRole}
        assert roles == {
            "scout", "compiler", "cartographer",
            "skeptic", "librarian", "reporter",
        }

    def test_role_is_str_enum(self):
        assert isinstance(AgentRole.SCOUT, str)
        assert AgentRole.SCOUT == "scout"

    def test_role_from_string(self):
        assert AgentRole("compiler") is AgentRole.COMPILER


class TestTaskStatus:
    def test_all_statuses(self):
        assert {s.value for s in TaskStatus} == {
            "pending", "running", "completed", "failed",
        }


class TestRunStatus:
    def test_all_statuses(self):
        assert {s.value for s in RunStatus} == {
            "pending", "running", "completed", "failed",
        }


class TestAgentTask:
    def test_create_task(self, id_gen: DeterministicIdGenerator):
        task = AgentTask(
            task_id=id_gen.generate("atsk"),
            role=AgentRole.SCOUT,
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
            objective="Find missing sources",
        )
        assert task.status == TaskStatus.PENDING
        assert task.role == AgentRole.SCOUT
        assert task.artifacts_created == []
        assert task.error is None
        assert task.constraints == []

    def test_task_with_constraints(self, id_gen: DeterministicIdGenerator):
        task = AgentTask(
            task_id=id_gen.generate("atsk"),
            role=AgentRole.SKEPTIC,
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
            objective="Check claims",
            constraints=["focus on contradictions", "ignore info findings"],
        )
        assert len(task.constraints) == 2

    def test_task_mutable_status(self, id_gen: DeterministicIdGenerator):
        task = AgentTask(
            task_id=id_gen.generate("atsk"),
            role=AgentRole.COMPILER,
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
            objective="Compile all",
        )
        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING
        task.status = TaskStatus.COMPLETED
        assert task.status == TaskStatus.COMPLETED


class TestAgentRun:
    def test_create_run(self, id_gen: DeterministicIdGenerator):
        run = AgentRun(
            run_id=id_gen.generate("arun"),
            vault_id=id_gen.vault_id(),
            workbook_id=id_gen.workbook_id(),
        )
        assert run.status == RunStatus.PENDING
        assert run.tasks == []
        assert run.completed_at is None

    def test_run_with_tasks(self, id_gen: DeterministicIdGenerator):
        vault_id = id_gen.vault_id()
        wb_id = id_gen.workbook_id()
        run = AgentRun(
            run_id=id_gen.generate("arun"),
            vault_id=vault_id,
            workbook_id=wb_id,
        )
        task = AgentTask(
            task_id=id_gen.generate("atsk"),
            role=AgentRole.SCOUT,
            vault_id=vault_id,
            workbook_id=wb_id,
            objective="Research",
        )
        run.tasks.append(task)
        assert len(run.tasks) == 1
        assert run.tasks[0].role == AgentRole.SCOUT
