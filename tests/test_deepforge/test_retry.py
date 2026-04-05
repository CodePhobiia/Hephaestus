"""Tests for retry logic."""

from __future__ import annotations

import asyncio
import time

import pytest

from hephaestus.deepforge.retry import RetryConfig, is_retryable, with_retry, with_timeout


class TestIsRetryable:
    def test_connection_error(self):
        assert is_retryable(ConnectionError("refused"))

    def test_timeout_error(self):
        assert is_retryable(TimeoutError("timed out"))

    def test_rate_limit_message(self):
        assert is_retryable(Exception("rate limit exceeded"))

    def test_429_message(self):
        assert is_retryable(Exception("HTTP 429"))

    def test_non_retryable(self):
        assert not is_retryable(ValueError("bad input"))

    def test_503_message(self):
        assert is_retryable(Exception("503 Service Unavailable"))


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        calls = []

        async def factory():
            calls.append(1)
            return "ok"

        result = await with_retry(factory)
        assert result == "ok"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        attempts = []

        async def factory():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("refused")
            return "recovered"

        cfg = RetryConfig(max_retries=3, base_delay=0.01)
        result = await with_retry(factory, cfg)
        assert result == "recovered"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        async def factory():
            raise ConnectionError("always fails")

        cfg = RetryConfig(max_retries=2, base_delay=0.01)
        with pytest.raises(ConnectionError):
            await with_retry(factory, cfg)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        calls = []

        async def factory():
            calls.append(1)
            raise ValueError("bad input")

        cfg = RetryConfig(max_retries=3, base_delay=0.01)
        with pytest.raises(ValueError):
            await with_retry(factory, cfg)
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        times = []

        async def factory():
            times.append(time.monotonic())
            if len(times) < 3:
                raise ConnectionError("fail")
            return "ok"

        cfg = RetryConfig(max_retries=3, base_delay=0.05, exponential_base=2.0)
        await with_retry(factory, cfg)
        assert len(times) == 3
        delay1 = times[1] - times[0]
        delay2 = times[2] - times[1]
        assert delay2 > delay1  # exponential increase

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        calls = []

        async def factory():
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("fail")
            return "ok"

        cfg = RetryConfig(max_retries=3, base_delay=100.0, max_delay=0.01)
        t0 = time.monotonic()
        await with_retry(factory, cfg)
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0  # max_delay capped it


class TestWithTimeout:
    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        async def fast():
            return "done"

        result = await with_timeout(fast(), timeout_seconds=5.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(TimeoutError, match="timed out"):
            await with_timeout(slow(), timeout_seconds=0.05)

    @pytest.mark.asyncio
    async def test_default_timeout(self):
        async def fast():
            return 42

        result = await with_timeout(fast())
        assert result == 42
