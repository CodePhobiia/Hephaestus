"""Tests for the RunOrchestrator — admission, concurrency, lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.execution.models import (
    ExecutionClass,
    RunRecord,
    RunStatus,
)
from hephaestus.execution.orchestrator import OrchestratorConfig, RunOrchestrator


def _make_record(**overrides: Any) -> RunRecord:
    defaults = dict(
        problem="test",
        config_snapshot={"depth": 3},
        dedup_key="abc",
        execution_class=ExecutionClass.INTERACTIVE,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def _make_store() -> MagicMock:
    store = AsyncMock()
    store.initialize = AsyncMock()
    store.close = AsyncMock()
    store.create = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(return_value=_make_record())
    store.find_duplicate = AsyncMock(return_value=None)
    store.list_runs = AsyncMock(return_value=[])
    store.update_stage = AsyncMock()
    store.complete = AsyncMock()
    store.touch = AsyncMock()
    store.fail = AsyncMock()
    store.cancel = AsyncMock(return_value=True)
    store.cleanup_stale = AsyncMock(return_value=0)
    store.aggregate_cost = AsyncMock(return_value=0.0)
    return store


class TestOrchestratorConfig:
    def test_defaults(self) -> None:
        cfg = OrchestratorConfig()
        assert cfg.max_concurrent_interactive == 4
        assert cfg.max_concurrent_deep == 2
        assert cfg.max_concurrent_research == 1
        assert cfg.max_queue_depth == 50


@pytest.mark.asyncio
class TestSubmit:
    async def test_submit_creates_record(self) -> None:
        store = _make_store()
        orch = RunOrchestrator(store)
        await orch.start()

        record = await orch.submit(problem="hello", config={"depth": 3})
        assert record.problem == "hello"
        assert record.status == RunStatus.QUEUED
        store.create.assert_awaited_once()
        await orch.stop()

    async def test_submit_returns_existing_on_duplicate(self) -> None:
        existing = _make_record(run_id="dup-123")
        store = _make_store()
        store.find_duplicate = AsyncMock(return_value=existing)
        orch = RunOrchestrator(store)
        await orch.start()

        record = await orch.submit(problem="hello", config={"depth": 3})
        assert record.run_id == "dup-123"
        store.create.assert_not_awaited()
        await orch.stop()

    async def test_submit_rejects_when_queue_full(self) -> None:
        store = _make_store()
        store.list_runs = AsyncMock(return_value=[_make_record() for _ in range(50)])
        orch = RunOrchestrator(store)
        await orch.start()

        with pytest.raises(ValueError, match="Queue full"):
            await orch.submit(problem="hello", config={"depth": 3})
        await orch.stop()


@pytest.mark.asyncio
class TestExecute:
    async def test_execute_runs_pipeline(self) -> None:
        store = _make_store()
        record = _make_record(run_id="run-1")
        store.get = AsyncMock(return_value=record)
        orch = RunOrchestrator(store)
        await orch.start()

        async def pipeline(rec: RunRecord, cancel: asyncio.Event) -> str | None:
            return "result-ref"

        await orch.execute("run-1", pipeline)
        store.complete.assert_awaited_once()
        await orch.stop()

    async def test_execute_fails_on_pipeline_error(self) -> None:
        store = _make_store()
        record = _make_record(run_id="run-2")
        store.get = AsyncMock(return_value=record)
        orch = RunOrchestrator(store)
        await orch.start()

        async def bad_pipeline(rec: RunRecord, cancel: asyncio.Event) -> str | None:
            raise RuntimeError("boom")

        await orch.execute("run-2", bad_pipeline)
        store.fail.assert_awaited()
        assert store.fail.await_args.kwargs["source"] == "pipeline"
        await orch.stop()

    async def test_execute_returns_none_for_missing_run(self) -> None:
        store = _make_store()
        store.get = AsyncMock(return_value=None)
        orch = RunOrchestrator(store)
        await orch.start()

        async def pipeline(rec: RunRecord, cancel: asyncio.Event) -> str | None:
            return None

        result = await orch.execute("nonexistent", pipeline)
        assert result is None
        await orch.stop()

    async def test_execute_heartbeats_while_pipeline_runs(self) -> None:
        store = _make_store()
        record = _make_record(run_id="run-heartbeat")
        record.status = RunStatus.RUNNING
        store.get = AsyncMock(side_effect=lambda run_id: record)
        orch = RunOrchestrator(
            store,
            config=OrchestratorConfig(heartbeat_interval_seconds=0.01),
        )
        await orch.start()

        async def pipeline(rec: RunRecord, cancel: asyncio.Event) -> str | None:
            await asyncio.sleep(0.03)
            return "result-ref"

        await orch.execute("run-heartbeat", pipeline)

        assert store.touch.await_count >= 1
        await orch.stop()

    async def test_timeout_resolution_expands_for_long_running_configs(self) -> None:
        record = _make_record(
            config_snapshot={
                "depth": 3,
                "use_pantheon_mode": True,
                "agentic_mode": True,
                "olympus_enabled": True,
            }
        )
        assert RunOrchestrator._timeout_seconds_for_record(record) == 3600


@pytest.mark.asyncio
class TestQueueStats:
    async def test_queue_stats_structure(self) -> None:
        store = _make_store()
        orch = RunOrchestrator(store)
        await orch.start()

        stats = await orch.get_queue_stats()
        assert "active_tasks" in stats
        assert "semaphores" in stats
        assert "interactive" in stats["semaphores"]
        assert "max" in stats["semaphores"]["interactive"]
        assert "available" in stats["semaphores"]["interactive"]
        await orch.stop()

    async def test_semaphore_limits_match_config(self) -> None:
        store = _make_store()
        cfg = OrchestratorConfig(max_concurrent_interactive=8)
        orch = RunOrchestrator(store, config=cfg)
        await orch.start()

        stats = await orch.get_queue_stats()
        assert stats["semaphores"]["interactive"]["max"] == 8
        await orch.stop()


@pytest.mark.asyncio
class TestCancelRun:
    async def test_cancel_sets_store_status(self) -> None:
        store = _make_store()
        orch = RunOrchestrator(store)
        await orch.start()

        await orch.cancel_run("run-1")
        store.cancel.assert_awaited_once_with("run-1")
        await orch.stop()
