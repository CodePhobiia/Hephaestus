"""KnowledgeTeam — orchestrates a team of agents working on a vault.

The team creates a workbook (branch), executes agents sequentially
so each sees the previous agent's work, then proposes a merge.
Agents ALWAYS work on branches -- never on canonical.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hephaestus.forgebase.agents.executor import AgentExecutor
from hephaestus.forgebase.contracts.agent import (
    AgentRole,
    AgentRun,
    AgentTask,
    RunStatus,
    TaskStatus,
)
from hephaestus.forgebase.domain.enums import BranchPurpose
from hephaestus.forgebase.domain.values import ActorRef, EntityId

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase
    from hephaestus.forgebase.service.id_generator import IdGenerator

logger = logging.getLogger(__name__)


class KnowledgeTeam:
    """Orchestrates a team of agents working on a vault.

    All team runs follow the same pattern:
    1. Create a workbook (branch) for the run
    2. Execute agents sequentially on the workbook
    3. Propose merge when done

    Parameters
    ----------
    forgebase:
        The fully wired ForgeBase instance providing all services.
    default_actor:
        Actor reference for audit trail.
    """

    def __init__(
        self,
        forgebase: ForgeBase,
        default_actor: ActorRef,
    ) -> None:
        self._forgebase = forgebase
        self._actor = default_actor
        self._executor = AgentExecutor(forgebase)

    async def run_maintenance(self, vault_id: EntityId) -> AgentRun:
        """Standard maintenance pass: Scout -> Compiler -> Cartographer -> Skeptic -> Librarian.

        Runs the full suite of structural agents to keep a vault healthy.
        Scouts for missing sources, compiles them, links everything together,
        checks for quality issues, and cleans up structure.
        """
        return await self._execute_run(
            vault_id=vault_id,
            roles=[
                AgentRole.SCOUT,
                AgentRole.COMPILER,
                AgentRole.CARTOGRAPHER,
                AgentRole.SKEPTIC,
                AgentRole.LIBRARIAN,
            ],
            objective="Vault maintenance: discover, compile, link, verify, clean",
            branch_purpose=BranchPurpose.AGENT_MAINTENANCE,
            branch_name="agent/maintenance",
        )

    async def run_research(
        self,
        vault_id: EntityId,
        query: str,
    ) -> AgentRun:
        """Research-focused run: Scout -> Compiler -> Reporter.

        Discovers sources for a specific query, compiles them,
        and produces a summary report.
        """
        return await self._execute_run(
            vault_id=vault_id,
            roles=[
                AgentRole.SCOUT,
                AgentRole.COMPILER,
                AgentRole.REPORTER,
            ],
            objective=query,
            branch_purpose=BranchPurpose.AGENT_RESEARCH,
            branch_name="agent/research",
        )

    async def run_quality(self, vault_id: EntityId) -> AgentRun:
        """Quality-focused run: Skeptic -> Librarian -> Reporter.

        Checks the vault for quality and structural issues, then
        produces a quality report.
        """
        return await self._execute_run(
            vault_id=vault_id,
            roles=[
                AgentRole.SKEPTIC,
                AgentRole.LIBRARIAN,
                AgentRole.REPORTER,
            ],
            objective="Quality audit: verify claims, fix structure, report findings",
            branch_purpose=BranchPurpose.AGENT_QUALITY,
            branch_name="agent/quality",
        )

    async def run_custom(
        self,
        vault_id: EntityId,
        roles: list[AgentRole],
        objective: str,
    ) -> AgentRun:
        """Custom agent sequence with user-specified roles and objective."""
        if not roles:
            raise ValueError("At least one role must be specified")

        return await self._execute_run(
            vault_id=vault_id,
            roles=roles,
            objective=objective,
            branch_purpose=BranchPurpose.AGENT_CUSTOM,
            branch_name="agent/custom",
        )

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    async def _execute_run(
        self,
        vault_id: EntityId,
        roles: list[AgentRole],
        objective: str,
        branch_purpose: BranchPurpose,
        branch_name: str,
    ) -> AgentRun:
        """Core run execution: create branch, run tasks, propose merge."""
        id_gen = self._get_id_generator()

        # Create the run record
        run = AgentRun(
            run_id=id_gen.generate("arun"),
            vault_id=vault_id,
            workbook_id=EntityId("wb_00000000000000000000000000"),  # placeholder
            status=RunStatus.RUNNING,
            created_at=datetime.now(UTC),
        )

        try:
            # Step 1: Create workbook for this run
            workbook = await self._forgebase.branches.create_workbook(
                vault_id=vault_id,
                name=branch_name,
                purpose=branch_purpose,
                actor=self._actor,
            )
            run.workbook_id = workbook.workbook_id

            logger.info(
                "KnowledgeTeam started run %s on vault=%s workbook=%s with %d agents",
                run.run_id,
                vault_id,
                workbook.workbook_id,
                len(roles),
            )

            # Step 2: Create and execute tasks sequentially
            for role in roles:
                task = AgentTask(
                    task_id=id_gen.generate("atsk"),
                    role=role,
                    vault_id=vault_id,
                    workbook_id=workbook.workbook_id,
                    objective=objective,
                    created_at=datetime.now(UTC),
                )
                run.tasks.append(task)

                result = await self._executor.execute_task(task)

                # If a task fails, mark the run as failed but continue
                # to let remaining agents attempt their work
                if result.status == TaskStatus.FAILED:
                    logger.warning(
                        "Task %s (%s) failed in run %s: %s",
                        result.task_id,
                        result.role.value,
                        run.run_id,
                        result.error,
                    )

            # Step 3: Propose merge
            try:
                proposal = await self._forgebase.merge.propose_merge(
                    workbook_id=workbook.workbook_id,
                    actor=self._actor,
                )
                logger.info(
                    "Run %s merge proposed: verdict=%s",
                    run.run_id,
                    proposal.verdict.value,
                )
            except Exception as exc:
                logger.warning(
                    "Run %s merge proposal failed: %s",
                    run.run_id,
                    exc,
                )

            # Determine overall run status
            failed_tasks = [t for t in run.tasks if t.status == TaskStatus.FAILED]
            if len(failed_tasks) == len(run.tasks):
                run.status = RunStatus.FAILED
            else:
                run.status = RunStatus.COMPLETED

        except Exception as exc:
            logger.error("Run %s failed: %s", run.run_id, exc)
            run.status = RunStatus.FAILED

        run.completed_at = datetime.now(UTC)
        return run

    def _get_id_generator(self) -> IdGenerator:
        """Get the ID generator from the UoW factory."""
        uow = self._forgebase.uow_factory()
        return uow.id_generator
