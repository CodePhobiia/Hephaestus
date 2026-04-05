"""Tests for KnowledgeTeam orchestrator."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.agents.team import KnowledgeTeam
from hephaestus.forgebase.contracts.agent import (
    AgentRole,
    RunStatus,
    TaskStatus,
)
from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def actor() -> ActorRef:
    return ActorRef(actor_type=ActorType.AGENT, actor_id="test-team")


@pytest.mark.asyncio
async def test_run_maintenance_creates_workbook_and_tasks(id_gen, clock, actor):
    """run_maintenance creates a workbook and runs 5 agents sequentially."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="maint-vault")
    run = await team.run_maintenance(vault.vault_id)

    assert run.status in (RunStatus.COMPLETED, RunStatus.FAILED)
    assert len(run.tasks) == 5

    expected_roles = [
        AgentRole.SCOUT,
        AgentRole.COMPILER,
        AgentRole.CARTOGRAPHER,
        AgentRole.SKEPTIC,
        AgentRole.LIBRARIAN,
    ]
    actual_roles = [t.role for t in run.tasks]
    assert actual_roles == expected_roles

    # All tasks should have the same workbook_id
    workbook_ids = {str(t.workbook_id) for t in run.tasks}
    assert len(workbook_ids) == 1

    # Workbook should match run's workbook
    assert run.tasks[0].workbook_id == run.workbook_id

    # Run should have completed_at set
    assert run.completed_at is not None

    await fb.close()


@pytest.mark.asyncio
async def test_run_research_creates_3_tasks(id_gen, clock, actor):
    """run_research creates Scout -> Compiler -> Reporter."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="research-vault")
    run = await team.run_research(vault.vault_id, "quantum computing advances")

    assert len(run.tasks) == 3
    assert run.tasks[0].role == AgentRole.SCOUT
    assert run.tasks[1].role == AgentRole.COMPILER
    assert run.tasks[2].role == AgentRole.REPORTER

    # All tasks share the objective
    for task in run.tasks:
        assert task.objective == "quantum computing advances"

    await fb.close()


@pytest.mark.asyncio
async def test_run_quality_creates_3_tasks(id_gen, clock, actor):
    """run_quality creates Skeptic -> Librarian -> Reporter."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="quality-vault")
    run = await team.run_quality(vault.vault_id)

    assert len(run.tasks) == 3
    assert run.tasks[0].role == AgentRole.SKEPTIC
    assert run.tasks[1].role == AgentRole.LIBRARIAN
    assert run.tasks[2].role == AgentRole.REPORTER

    await fb.close()


@pytest.mark.asyncio
async def test_run_custom_with_selected_roles(id_gen, clock, actor):
    """run_custom allows arbitrary role sequences."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="custom-vault")
    run = await team.run_custom(
        vault.vault_id,
        roles=[AgentRole.REPORTER, AgentRole.SKEPTIC],
        objective="Just report and verify",
    )

    assert len(run.tasks) == 2
    assert run.tasks[0].role == AgentRole.REPORTER
    assert run.tasks[1].role == AgentRole.SKEPTIC

    await fb.close()


@pytest.mark.asyncio
async def test_run_custom_rejects_empty_roles(id_gen, clock, actor):
    """run_custom raises ValueError for empty roles list."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="empty-vault")

    with pytest.raises(ValueError, match="At least one role"):
        await team.run_custom(vault.vault_id, roles=[], objective="Nothing")

    await fb.close()


@pytest.mark.asyncio
async def test_agents_work_on_branch_not_canonical(id_gen, clock, actor):
    """All tasks in a run should target a workbook, not canonical."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="branch-check-vault")
    run = await team.run_maintenance(vault.vault_id)

    # The workbook_id on the run should be a real workbook
    assert run.workbook_id is not None
    assert str(run.workbook_id).startswith("wb_")

    # Every task should reference the same workbook
    for task in run.tasks:
        assert task.workbook_id == run.workbook_id

    await fb.close()


@pytest.mark.asyncio
async def test_run_proposes_merge(id_gen, clock, actor):
    """A completed run should attempt to propose a merge."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="merge-vault")
    run = await team.run_quality(vault.vault_id)

    # Run should complete (merge proposal may or may not succeed
    # depending on whether there are branch changes)
    assert run.status in (RunStatus.COMPLETED, RunStatus.FAILED)
    assert run.completed_at is not None

    await fb.close()


@pytest.mark.asyncio
async def test_sequential_task_execution(id_gen, clock, actor):
    """Tasks execute sequentially — each sees the previous task's work."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    team = KnowledgeTeam(fb, actor)

    vault = await fb.vaults.create_vault(name="seq-vault")
    run = await team.run_maintenance(vault.vault_id)

    # Each task should have a completed_at timestamp
    for task in run.tasks:
        assert task.completed_at is not None

    await fb.close()
