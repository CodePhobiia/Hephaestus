"""Parallel execution utilities for pipeline stages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TimedResult:
    """A result with timing information."""

    value: Any
    duration_seconds: float
    index: int = 0
    error: str = ""
    success: bool = True


@dataclass
class ParallelConfig:
    """Configuration for parallel execution."""

    max_concurrent: int = 4
    timeout_per_task: float = 120.0
    fail_fast: bool = False  # stop all on first failure


async def gather_with_semaphore(
    tasks: list[Coroutine[Any, Any, T]],
    config: ParallelConfig | None = None,
) -> list[TimedResult]:
    """Run coroutines in parallel with a concurrency semaphore.

    Returns a TimedResult for each task (in order), including failures.
    """
    cfg = config or ParallelConfig()
    semaphore = asyncio.Semaphore(cfg.max_concurrent)
    results: list[TimedResult] = [
        TimedResult(value=None, duration_seconds=0.0, index=i, success=False)
        for i in range(len(tasks))
    ]

    async def _run(idx: int, coro: Coroutine) -> None:
        async with semaphore:
            t0 = time.monotonic()
            try:
                if cfg.timeout_per_task > 0:
                    value = await asyncio.wait_for(coro, timeout=cfg.timeout_per_task)
                else:
                    value = await coro
                results[idx] = TimedResult(
                    value=value,
                    duration_seconds=time.monotonic() - t0,
                    index=idx,
                    success=True,
                )
            except Exception as exc:
                results[idx] = TimedResult(
                    value=None,
                    duration_seconds=time.monotonic() - t0,
                    index=idx,
                    error=str(exc),
                    success=False,
                )
                if cfg.fail_fast:
                    raise

    await asyncio.gather(
        *(_run(i, t) for i, t in enumerate(tasks)),
        return_exceptions=not cfg.fail_fast,
    )

    return results


@dataclass
class PipelineTimer:
    """Tracks timing for each pipeline stage."""

    _stages: dict[str, float] = field(default_factory=dict)
    _starts: dict[str, float] = field(default_factory=dict)

    def start(self, stage: str) -> None:
        self._starts[stage] = time.monotonic()

    def stop(self, stage: str) -> float:
        if stage not in self._starts:
            return 0.0
        elapsed = time.monotonic() - self._starts[stage]
        self._stages[stage] = elapsed
        del self._starts[stage]
        return elapsed

    def get(self, stage: str) -> float:
        return self._stages.get(stage, 0.0)

    @property
    def total(self) -> float:
        return sum(self._stages.values())

    def summary(self) -> dict[str, float]:
        return dict(self._stages)

    def format_report(self) -> str:
        lines = []
        for stage, elapsed in self._stages.items():
            pct = (elapsed / self.total * 100) if self.total > 0 else 0
            lines.append(f"  {stage}: {elapsed:.2f}s ({pct:.0f}%)")
        lines.append(f"  Total: {self.total:.2f}s")
        return "\n".join(lines)


__all__ = [
    "TimedResult",
    "ParallelConfig",
    "gather_with_semaphore",
    "PipelineTimer",
]
