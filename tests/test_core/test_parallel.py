"""Tests for parallel execution utilities."""

from __future__ import annotations

import asyncio

import pytest

from hephaestus.core.parallel import (
    ParallelConfig,
    PipelineTimer,
    TimedResult,
    gather_with_semaphore,
)


class TestGatherWithSemaphore:
    @pytest.mark.asyncio
    async def test_basic_parallel(self):
        async def task(n):
            return n * 2
        results = await gather_with_semaphore([task(1), task(2), task(3)])
        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.value for r in results] == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_preserves_order(self):
        async def task(n):
            await asyncio.sleep(0.01 * (3 - n))  # reverse timing
            return n
        results = await gather_with_semaphore([task(1), task(2), task(3)])
        assert [r.value for r in results] == [1, 2, 3]  # original order

    @pytest.mark.asyncio
    async def test_handles_failure(self):
        async def good():
            return "ok"
        async def bad():
            raise ValueError("boom")
        results = await gather_with_semaphore([good(), bad(), good()])
        assert results[0].success
        assert not results[1].success
        assert "boom" in results[1].error
        assert results[2].success

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        active = []
        max_active = [0]
        async def task():
            active.append(1)
            if len(active) > max_active[0]:
                max_active[0] = len(active)
            await asyncio.sleep(0.02)
            active.pop()
            return True
        cfg = ParallelConfig(max_concurrent=2)
        results = await gather_with_semaphore([task() for _ in range(5)], cfg)
        assert all(r.success for r in results)
        assert max_active[0] <= 2

    @pytest.mark.asyncio
    async def test_timeout(self):
        async def slow():
            await asyncio.sleep(10)
        cfg = ParallelConfig(timeout_per_task=0.05)
        results = await gather_with_semaphore([slow()], cfg)
        assert not results[0].success

    @pytest.mark.asyncio
    async def test_empty_tasks(self):
        results = await gather_with_semaphore([])
        assert results == []

    @pytest.mark.asyncio
    async def test_timing(self):
        async def task():
            await asyncio.sleep(0.05)
            return True
        results = await gather_with_semaphore([task()])
        assert results[0].duration_seconds > 0.04


class TestPipelineTimer:
    def test_basic_timing(self):
        import time
        timer = PipelineTimer()
        timer.start("Decompose")
        time.sleep(0.05)
        elapsed = timer.stop("Decompose")
        assert elapsed > 0.04
        assert timer.get("Decompose") > 0.04

    def test_total(self):
        timer = PipelineTimer()
        timer._stages = {"A": 1.0, "B": 2.0, "C": 0.5}
        assert timer.total == 3.5

    def test_summary(self):
        timer = PipelineTimer()
        timer._stages = {"Decompose": 1.5, "Search": 3.0}
        s = timer.summary()
        assert s["Decompose"] == 1.5
        assert s["Search"] == 3.0

    def test_format_report(self):
        timer = PipelineTimer()
        timer._stages = {"Decompose": 1.0, "Search": 2.0}
        report = timer.format_report()
        assert "Decompose" in report
        assert "Total" in report

    def test_stop_unstarted(self):
        timer = PipelineTimer()
        assert timer.stop("unknown") == 0.0

    def test_get_missing(self):
        timer = PipelineTimer()
        assert timer.get("nope") == 0.0
