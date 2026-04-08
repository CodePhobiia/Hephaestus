"""Durable execution models for Hephaestus run lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class RunStatus(StrEnum):
    """Lifecycle status of a pipeline run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionClass(StrEnum):
    """Execution tier determining timeout and resource allocation."""

    INTERACTIVE = "interactive"  # depth ≤ 3, timeout 120s
    DEEP = "deep"  # any depth, timeout 600s
    RESEARCH = "research"  # research-heavy, timeout 900s

    @classmethod
    def from_config(cls, depth: int, *, research: bool = False) -> ExecutionClass:
        if research:
            return cls.RESEARCH
        if depth <= 3:
            return cls.INTERACTIVE
        return cls.DEEP

    @property
    def timeout_seconds(self) -> int:
        return {
            ExecutionClass.INTERACTIVE: 120,
            ExecutionClass.DEEP: 600,
            ExecutionClass.RESEARCH: 900,
        }[self]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _config_hash(problem: str, config: dict[str, Any]) -> str:
    """Content-addressable deduplication key."""
    canonical = json.dumps({"problem": problem, **config}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class RunRecord:
    """Persistent record of a single pipeline run."""

    run_id: str = field(default_factory=lambda: uuid4().hex)
    status: RunStatus = RunStatus.QUEUED
    execution_class: ExecutionClass = ExecutionClass.INTERACTIVE
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Request
    problem: str = ""
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    dedup_key: str = ""

    # Progress
    current_stage: str = ""
    stage_history: list[dict[str, Any]] = field(default_factory=list)

    # Result
    result_ref: str | None = None  # path or key to result artifact
    cost_usd: float = 0.0
    token_count: int = 0
    error: str | None = None
    error_stage: str | None = None
    error_source: str | None = None

    # Correlation
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    user_id: str | None = None
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "execution_class": self.execution_class.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "problem": self.problem,
            "config_snapshot": self.config_snapshot,
            "dedup_key": self.dedup_key,
            "current_stage": self.current_stage,
            "stage_history": self.stage_history,
            "result_ref": self.result_ref,
            "cost_usd": self.cost_usd,
            "token_count": self.token_count,
            "error": self.error,
            "error_stage": self.error_stage,
            "error_source": self.error_source,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=str(data.get("run_id", uuid4().hex)),
            status=RunStatus(data.get("status", "queued")),
            execution_class=ExecutionClass(data.get("execution_class", "interactive")),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else _utc_now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else _utc_now(),
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at")
            else None,
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None,
            problem=str(data.get("problem", "")),
            config_snapshot=dict(data.get("config_snapshot", {})),
            dedup_key=str(data.get("dedup_key", "")),
            current_stage=str(data.get("current_stage", "")),
            stage_history=list(data.get("stage_history", [])),
            result_ref=data.get("result_ref"),
            cost_usd=float(data.get("cost_usd", 0.0)),
            token_count=int(data.get("token_count", 0)),
            error=data.get("error"),
            error_stage=data.get("error_stage"),
            error_source=data.get("error_source"),
            correlation_id=str(data.get("correlation_id", uuid4().hex)),
            user_id=data.get("user_id"),
            tenant_id=data.get("tenant_id"),
        )


__all__ = [
    "ExecutionClass",
    "RunRecord",
    "RunStatus",
    "_config_hash",
]
