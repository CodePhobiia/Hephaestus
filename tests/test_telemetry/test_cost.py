"""Tests for cost governance — BudgetPolicy, BudgetViolation, CostGovernor."""

from __future__ import annotations

import pytest

from hephaestus.telemetry.cost import BudgetPolicy, BudgetViolation


class TestBudgetPolicy:
    def test_defaults(self) -> None:
        policy = BudgetPolicy()
        assert policy.max_per_run_usd == 5.0
        assert policy.max_per_hour_usd == 20.0
        assert policy.max_per_day_usd == 100.0
        assert policy.max_global_per_hour_usd == 50.0

    def test_custom_values(self) -> None:
        policy = BudgetPolicy(max_per_run_usd=1.0, max_per_day_usd=10.0)
        assert policy.max_per_run_usd == 1.0
        assert policy.max_per_day_usd == 10.0

    def test_to_dict(self) -> None:
        policy = BudgetPolicy()
        d = policy.to_dict()
        assert d["max_per_run_usd"] == 5.0
        assert d["max_per_hour_usd"] == 20.0
        assert d["max_per_day_usd"] == 100.0
        assert d["max_global_per_hour_usd"] == 50.0
        assert len(d) == 4


class TestBudgetViolation:
    def test_attributes(self) -> None:
        exc = BudgetViolation(
            "over budget",
            limit_type="per_run",
            current=6.0,
            limit=5.0,
        )
        assert str(exc) == "over budget"
        assert exc.limit_type == "per_run"
        assert exc.current == 6.0
        assert exc.limit == 5.0

    def test_is_exception(self) -> None:
        exc = BudgetViolation("x", limit_type="t", current=0, limit=0)
        assert isinstance(exc, Exception)
