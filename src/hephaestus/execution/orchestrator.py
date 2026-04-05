"""Run orchestrator — admission control, concurrency, and lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from hephaestus.execution.models import (
    ExecutionClass,
    RunRecord,
    RunStatus,
    _config_hash,
)
from hephaestus.execution.run_store import RunStore

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the run orchestrator."""

    max_concurrent_interactive: int = 4
    max_concurrent_deep: int = 2
    max_concurrent_research: int = 1
    max_queue_depth: int = 50
    dedup_ttl_seconds: int = 300
    stale_cleanup_interval_seconds: int = 600
    retry_max_per_stage: int = 2
    retry_backoff_base: float = 1.0


class RunOrchestrator:
    """Manages run lifecycle: admission, concurrency, execution, and cleanup."""

    def __init__(self, store: RunStore, config: OrchestratorConfig | None = None) -> None:
        self._store = store
        self._config = config or OrchestratorConfig()
        self._semaphore_limits: dict[ExecutionClass, int] = {
            ExecutionClass.INTERACTIVE: self._config.max_concurrent_interactive,
            ExecutionClass.DEEP: self._config.max_concurrent_deep,
            ExecutionClass.RESEARCH: self._config.max_concurrent_research,
        }
        self._semaphores: dict[ExecutionClass, asyncio.Semaphore] = {
            ec: asyncio.Semaphore(limit) for ec, limit in self._semaphore_limits.items()
        }
        self._active_runs: dict[str, asyncio.Task[Any]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._dispatcher_task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Initialize the store and start background cleanup."""
        await self._store.initialize()
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("RunOrchestrator started")

    async def start_dispatcher(
        self, pipeline_fn: Callable[[RunRecord, asyncio.Event], Awaitable[str | None]]
    ) -> None:
        """Start the background poll-and-dispatch loop."""
        if self._dispatcher_task is not None:
            return
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop(pipeline_fn))
        logger.info("RunOrchestrator dispatcher started")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher_task

        for run_id, task in list(self._active_runs.items()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            await self._store.fail(run_id, error="Orchestrator shutdown", stage="shutdown")

        await self._store.close()
        logger.info("RunOrchestrator stopped")

    async def submit(
        self,
        *,
        problem: str,
        config: dict[str, Any],
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> RunRecord:
        """Submit a new run. Returns immediately with the queued record.

        Raises ValueError if queue is full or duplicate is detected.
        """
        dedup_key = _config_hash(problem, config)

        # Idempotency check
        existing = await self._store.find_duplicate(
            dedup_key, ttl_seconds=self._config.dedup_ttl_seconds
        )
        if existing is not None:
            logger.info("Duplicate run detected: %s → %s", dedup_key, existing.run_id)
            return existing

        # Queue depth check
        queued = await self._store.list_runs(
            status=RunStatus.QUEUED, limit=self._config.max_queue_depth + 1
        )
        if len(queued) >= self._config.max_queue_depth:
            raise ValueError(f"Queue full ({self._config.max_queue_depth} pending runs)")

        depth = int(config.get("depth", 3))
        research = bool(config.get("use_perplexity_research", False))
        exec_class = ExecutionClass.from_config(depth, research=research)

        record = RunRecord(
            problem=problem,
            config_snapshot=config,
            dedup_key=dedup_key,
            execution_class=exec_class,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        record = await self._store.create(record)
        logger.info("Run %s queued (%s)", record.run_id, exec_class.value)
        return record

    async def execute(
        self,
        run_id: str,
        pipeline_fn: Callable[[RunRecord, asyncio.Event], Awaitable[str | None]],
    ) -> RunRecord | None:
        """Execute a run through its pipeline function within concurrency limits.

        The pipeline_fn receives the RunRecord and a cancel Event.
        It should check the event periodically and return a result_ref or None.
        """
        record = await self._store.get(run_id)
        if record is None:
            logger.error("Run %s not found", run_id)
            return None

        if record.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
            logger.warning("Run %s in terminal state %s, skipping", run_id, record.status.value)
            return record

        cancel_event = asyncio.Event()
        self._cancel_events[run_id] = cancel_event
        sem = self._semaphores[record.execution_class]

        current = asyncio.current_task()
        if current is not None:
            self._active_runs.setdefault(run_id, current)

        try:
            async with sem:
                await self._store.update_stage(run_id, "STARTING")
                try:
                    result_ref = await asyncio.wait_for(
                        pipeline_fn(record, cancel_event),
                        timeout=record.execution_class.timeout_seconds,
                    )
                    if cancel_event.is_set():
                        await self._store.cancel(run_id)
                    else:
                        await self._store.complete(run_id, result_ref=result_ref)
                except TimeoutError:
                    await self._store.fail(
                        run_id,
                        error=f"Execution timed out after {record.execution_class.timeout_seconds}s",
                        stage=record.current_stage or "unknown",
                    )
                except asyncio.CancelledError:
                    await self._store.cancel(run_id)
                except Exception as exc:
                    await self._store.fail(
                        run_id, error=str(exc), stage=record.current_stage or "unknown"
                    )
                    logger.exception("Run %s failed", run_id)
        finally:
            self._cancel_events.pop(run_id, None)
            self._active_runs.pop(run_id, None)

        return await self._store.get(run_id)

    async def cancel_run(self, run_id: str) -> bool:
        """Request cancellation of a run."""
        event = self._cancel_events.get(run_id)
        if event is not None:
            event.set()
            logger.info("Cancellation signal sent for run %s", run_id)

        task = self._active_runs.get(run_id)
        if task is not None and not task.done():
            task.cancel()

        return await self._store.cancel(run_id)

    async def get_run(self, run_id: str) -> RunRecord | None:
        return await self._store.get(run_id)

    async def list_runs(self, **kwargs: Any) -> list[RunRecord]:
        return await self._store.list_runs(**kwargs)

    async def get_queue_stats(self) -> dict[str, Any]:
        """Return operational stats for admin views."""
        queued = await self._store.list_runs(status=RunStatus.QUEUED, limit=1000)
        running = await self._store.list_runs(status=RunStatus.RUNNING, limit=1000)
        return {
            "queued_count": len(queued),
            "running_count": len(running),
            "active_tasks": len(self._active_runs),
            "semaphores": {
                ec.value: {
                    "max": self._semaphore_limits[ec],
                    "available": self._semaphore_limits[ec]
                    - len([r for r in running if r.execution_class == ec]),
                }
                for ec in ExecutionClass
            },
        }

    async def _periodic_cleanup(self) -> None:
        """Background task cleaning up stale runs."""
        while True:
            try:
                await asyncio.sleep(self._config.stale_cleanup_interval_seconds)
                cleaned = await self._store.cleanup_stale()
                if cleaned:
                    logger.info("Cleaned %d stale runs", cleaned)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in periodic cleanup")

    async def _dispatcher_loop(
        self, pipeline_fn: Callable[[RunRecord, asyncio.Event], Awaitable[str | None]]
    ) -> None:
        """Continuously pulls queued runs and dispatches them."""
        while True:
            try:
                queued = await self._store.list_runs(status=RunStatus.QUEUED, limit=10)
                for record in queued:
                    if record.run_id not in self._active_runs:
                        # Dispatch in a background task
                        task = asyncio.create_task(self.execute(record.run_id, pipeline_fn))
                        self._active_runs[record.run_id] = task

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in dispatcher loop")
                await asyncio.sleep(5.0)


__all__ = [
    "OrchestratorConfig",
    "RunOrchestrator",
]
