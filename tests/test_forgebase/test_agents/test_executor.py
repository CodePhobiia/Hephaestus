"""Tests for AgentExecutor — routing and lifecycle."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.agents.executor import AgentExecutor
from hephaestus.forgebase.contracts.agent import (
    AgentRole,
    AgentTask,
    TaskStatus,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC))


@pytest.mark.asyncio
async def test_executor_routes_all_roles(id_gen, clock):
    """Every role has a registered handler in the executor."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    for role in AgentRole:
        assert role in executor._handlers, f"Missing handler for {role.value}"

    await fb.close()


@pytest.mark.asyncio
async def test_executor_sets_completed_timestamp(id_gen, clock):
    """Executor sets completed_at after handler returns."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="test-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_MAINTENANCE,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.REPORTER,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Generate a test report",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.completed_at is not None
    assert result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    await fb.close()


@pytest.mark.asyncio
async def test_executor_reporter_creates_artifact(id_gen, clock):
    """Reporter handler creates at least one page artifact."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="reporter-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_MAINTENANCE,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.REPORTER,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Report on vault state",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED
    assert len(result.artifacts_created) >= 1

    await fb.close()


@pytest.mark.asyncio
async def test_executor_scout_with_noop_augmentor(id_gen, clock):
    """Scout handler completes with NoOpAugmentor (no sources discovered)."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="scout-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_RESEARCH,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.SCOUT,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Find sources about quantum computing",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED
    # NoOpAugmentor returns no sources
    assert len(result.artifacts_created) == 0

    await fb.close()


@pytest.mark.asyncio
async def test_executor_skeptic_runs_lint(id_gen, clock):
    """Skeptic handler runs lint and records the report as artifact."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="skeptic-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_QUALITY,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.SKEPTIC,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Find contradictions",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED
    # Should have at least a report artifact
    assert len(result.artifacts_created) >= 1

    await fb.close()


@pytest.mark.asyncio
async def test_executor_librarian_runs_lint(id_gen, clock):
    """Librarian handler runs lint and records the report."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="librarian-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_QUALITY,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.LIBRARIAN,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Clean up structure",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED
    assert len(result.artifacts_created) >= 1

    await fb.close()


@pytest.mark.asyncio
async def test_executor_cartographer_on_empty_vault(id_gen, clock):
    """Cartographer completes on an empty vault (no pages to link)."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="carto-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_MAINTENANCE,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.CARTOGRAPHER,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Build concept map",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED
    # No pages means no links created
    assert len(result.artifacts_created) == 0

    await fb.close()


@pytest.mark.asyncio
async def test_executor_compiler_on_empty_vault(id_gen, clock):
    """Compiler completes on a vault with no normalized sources."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    executor = AgentExecutor(fb)

    vault = await fb.vaults.create_vault(name="compiler-vault")
    from hephaestus.forgebase.domain.enums import BranchPurpose

    wb = await fb.branches.create_workbook(
        vault.vault_id, "test-wb", BranchPurpose.AGENT_MAINTENANCE,
    )

    task = AgentTask(
        task_id=id_gen.generate("atsk"),
        role=AgentRole.COMPILER,
        vault_id=vault.vault_id,
        workbook_id=wb.workbook_id,
        objective="Compile all sources",
        created_at=datetime.now(UTC),
    )

    result = await executor.execute_task(task)
    assert result.status == TaskStatus.COMPLETED

    await fb.close()
