"""Tests for execution models — RunRecord, RunStatus, ExecutionClass."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.execution.models import (
    ExecutionClass,
    RunRecord,
    RunStatus,
    _config_hash,
)


class TestRunStatus:
    def test_values(self) -> None:
        assert RunStatus.QUEUED == "queued"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"


class TestExecutionClass:
    def test_interactive_for_shallow(self) -> None:
        assert ExecutionClass.from_config(1) == ExecutionClass.INTERACTIVE
        assert ExecutionClass.from_config(3) == ExecutionClass.INTERACTIVE

    def test_deep_for_depth_above_3(self) -> None:
        assert ExecutionClass.from_config(4) == ExecutionClass.DEEP
        assert ExecutionClass.from_config(10) == ExecutionClass.DEEP

    def test_research_overrides_depth(self) -> None:
        assert ExecutionClass.from_config(1, research=True) == ExecutionClass.RESEARCH
        assert ExecutionClass.from_config(10, research=True) == ExecutionClass.RESEARCH

    def test_timeout_seconds(self) -> None:
        assert ExecutionClass.INTERACTIVE.timeout_seconds == 120
        assert ExecutionClass.DEEP.timeout_seconds == 600
        assert ExecutionClass.RESEARCH.timeout_seconds == 900


class TestConfigHash:
    def test_deterministic(self) -> None:
        h1 = _config_hash("problem", {"depth": 3})
        h2 = _config_hash("problem", {"depth": 3})
        assert h1 == h2

    def test_different_problems(self) -> None:
        h1 = _config_hash("problem A", {"depth": 3})
        h2 = _config_hash("problem B", {"depth": 3})
        assert h1 != h2

    def test_different_config(self) -> None:
        h1 = _config_hash("problem", {"depth": 3})
        h2 = _config_hash("problem", {"depth": 5})
        assert h1 != h2

    def test_key_order_independent(self) -> None:
        h1 = _config_hash("p", {"a": 1, "b": 2})
        h2 = _config_hash("p", {"b": 2, "a": 1})
        assert h1 == h2

    def test_returns_32_char_hex(self) -> None:
        h = _config_hash("p", {})
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)


class TestRunRecord:
    def test_defaults(self) -> None:
        record = RunRecord(
            problem="test problem",
            config_snapshot={"depth": 3},
            dedup_key="abc123",
            execution_class=ExecutionClass.INTERACTIVE,
        )
        assert record.status == RunStatus.QUEUED
        assert record.run_id  # non-empty UUID
        assert record.user_id is None
        assert record.tenant_id is None
        assert record.cost_usd == 0.0
        assert record.stage_history == []
        assert record.error is None
        assert record.result_ref is None

    def test_created_at_is_utc(self) -> None:
        record = RunRecord(
            problem="p",
            config_snapshot={},
            dedup_key="k",
            execution_class=ExecutionClass.DEEP,
        )
        assert record.created_at.tzinfo is not None
