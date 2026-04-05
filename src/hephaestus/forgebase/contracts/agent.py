"""Agent contracts — typed models for sub-project 5c (multi-agent knowledge team)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from hephaestus.forgebase.domain.values import EntityId


class AgentRole(StrEnum):
    """Roles in the knowledge team."""

    SCOUT = "scout"
    COMPILER = "compiler"
    CARTOGRAPHER = "cartographer"
    SKEPTIC = "skeptic"
    LIBRARIAN = "librarian"
    REPORTER = "reporter"


class TaskStatus(StrEnum):
    """Lifecycle status of an agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(StrEnum):
    """Lifecycle status of an agent run (multi-task)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentTask:
    """A discrete task assignable to a knowledge agent."""

    task_id: EntityId
    role: AgentRole
    vault_id: EntityId
    workbook_id: EntityId
    objective: str
    constraints: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    artifacts_created: list[EntityId] = field(default_factory=list)
    error: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRun:
    """Record of a multi-agent run on a vault branch."""

    run_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId
    tasks: list[AgentTask] = field(default_factory=list)
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
