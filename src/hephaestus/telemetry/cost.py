"""Cost governance — per-user, per-tenant, and per-run spend controls."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BudgetPolicy:
    """Spend limits applied to runs."""

    max_per_run_usd: float = 5.0
    max_per_hour_usd: float = 20.0
    max_per_day_usd: float = 100.0
    max_global_per_hour_usd: float = 50.0

    def to_dict(self) -> dict[str, float]:
        return {
            "max_per_run_usd": self.max_per_run_usd,
            "max_per_hour_usd": self.max_per_hour_usd,
            "max_per_day_usd": self.max_per_day_usd,
            "max_global_per_hour_usd": self.max_global_per_hour_usd,
        }


class BudgetViolation(Exception): # noqa: N818
    """Raised when a budget limit would be exceeded."""

    def __init__(self, message: str, *, limit_type: str, current: float, limit: float) -> None:
        super().__init__(message)
        self.limit_type = limit_type
        self.current = current
        self.limit = limit


class CostGovernor:
    """Enforces spend limits at pre-flight and mid-flight checkpoints.

    Uses the RunStore for aggregate cost queries.
    """

    def __init__(self, policy: BudgetPolicy | None = None) -> None:
        self._policy = policy or BudgetPolicy()
        self._run_store: Any = None

    def set_run_store(self, store: Any) -> None:
        """Attach a RunStore for aggregate queries."""
        self._run_store = store

    @property
    def policy(self) -> BudgetPolicy:
        return self._policy

    async def preflight_check(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Check spend limits before starting a run. Raises BudgetViolation."""
        if self._run_store is None:
            return

        now = datetime.now(UTC)

        # Per-user hourly check
        if user_id:
            hourly = await self._run_store.aggregate_cost(
                user_id=user_id, since=now - timedelta(hours=1)
            )
            if hourly >= self._policy.max_per_hour_usd:
                raise BudgetViolation(
                    f"User hourly spend limit exceeded: ${hourly:.2f} >= ${self._policy.max_per_hour_usd:.2f}",
                    limit_type="user_hourly",
                    current=hourly,
                    limit=self._policy.max_per_hour_usd,
                )

        # Per-tenant daily check
        if tenant_id:
            daily = await self._run_store.aggregate_cost(
                tenant_id=tenant_id, since=now - timedelta(days=1)
            )
            if daily >= self._policy.max_per_day_usd:
                raise BudgetViolation(
                    f"Tenant daily spend limit exceeded: ${daily:.2f} >= ${self._policy.max_per_day_usd:.2f}",
                    limit_type="tenant_daily",
                    current=daily,
                    limit=self._policy.max_per_day_usd,
                )

        # Global hourly check
        global_hourly = await self._run_store.aggregate_cost(since=now - timedelta(hours=1))
        if global_hourly >= self._policy.max_global_per_hour_usd:
            raise BudgetViolation(
                f"Global hourly spend limit exceeded: "
                f"${global_hourly:.2f} >= ${self._policy.max_global_per_hour_usd:.2f}",
                limit_type="global_hourly",
                current=global_hourly,
                limit=self._policy.max_global_per_hour_usd,
            )

    def check_run_budget(self, run_cost_so_far: float) -> None:
        """Mid-flight check: raise if a single run is exceeding its budget."""
        if run_cost_so_far >= self._policy.max_per_run_usd:
            raise BudgetViolation(
                f"Run budget exceeded: ${run_cost_so_far:.2f} >= ${self._policy.max_per_run_usd:.2f}",
                limit_type="per_run",
                current=run_cost_so_far,
                limit=self._policy.max_per_run_usd,
            )


__all__ = [
    "BudgetPolicy",
    "BudgetViolation",
    "CostGovernor",
]
