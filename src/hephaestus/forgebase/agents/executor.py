"""AgentExecutor — routes agent tasks to role-specific handlers.

Each handler is a thin function that delegates to existing ForgeBase services.
The executor is the single dispatch point for all agent task execution.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentRole, AgentTask, TaskStatus

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)

# Handler type: async function (ForgeBase, AgentTask) -> AgentTask
HandlerFn = Callable[["ForgeBase", AgentTask], Awaitable[AgentTask]]


class AgentExecutor:
    """Executes agent tasks by delegating to ForgeBase services.

    Each role maps to a handler function that uses ForgeBase services
    to accomplish the task. The executor is responsible for:
    - Routing tasks to the correct handler
    - Setting timestamps on completion/failure
    - Logging task lifecycle events
    """

    def __init__(self, forgebase: ForgeBase) -> None:
        self._forgebase = forgebase
        self._handlers: dict[AgentRole, HandlerFn] = self._build_handler_map()

    @staticmethod
    def _build_handler_map() -> dict[AgentRole, HandlerFn]:
        """Lazily import and map role handlers."""
        from hephaestus.forgebase.agents.handlers.cartographer import execute_cartographer
        from hephaestus.forgebase.agents.handlers.compiler_agent import execute_compiler
        from hephaestus.forgebase.agents.handlers.librarian import execute_librarian
        from hephaestus.forgebase.agents.handlers.reporter import execute_reporter
        from hephaestus.forgebase.agents.handlers.scout import execute_scout
        from hephaestus.forgebase.agents.handlers.skeptic import execute_skeptic

        return {
            AgentRole.SCOUT: execute_scout,
            AgentRole.COMPILER: execute_compiler,
            AgentRole.CARTOGRAPHER: execute_cartographer,
            AgentRole.SKEPTIC: execute_skeptic,
            AgentRole.LIBRARIAN: execute_librarian,
            AgentRole.REPORTER: execute_reporter,
        }

    async def execute_task(self, task: AgentTask) -> AgentTask:
        """Route task to the appropriate role handler.

        Sets task status to RUNNING before dispatch and records
        completion timestamp after the handler returns.

        Returns the updated AgentTask (same object, mutated in place).
        """
        handler = self._handlers.get(task.role)
        if handler is None:
            task.status = TaskStatus.FAILED
            task.error = f"No handler registered for role: {task.role.value}"
            task.completed_at = datetime.now(UTC)
            return task

        logger.info(
            "Executing %s task %s on vault=%s workbook=%s",
            task.role.value,
            task.task_id,
            task.vault_id,
            task.workbook_id,
        )

        result = await handler(self._forgebase, task)

        result.completed_at = datetime.now(UTC)

        logger.info(
            "Task %s (%s) completed with status=%s, artifacts=%d",
            result.task_id,
            result.role.value,
            result.status.value,
            len(result.artifacts_created),
        )

        return result
