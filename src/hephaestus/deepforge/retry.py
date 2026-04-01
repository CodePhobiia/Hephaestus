"""Retry logic with exponential backoff for DeepForge API calls."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

_RETRYABLE_STRINGS = ("rate limit", "429", "timeout", "connection", "503", "502", "overloaded")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError, TimeoutError, OSError,
    )


def is_retryable(exc: Exception, config: RetryConfig | None = None) -> bool:
    """Check if an exception should trigger a retry."""
    cfg = config or RetryConfig()
    if isinstance(exc, cfg.retryable_exceptions):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in _RETRYABLE_STRINGS)


async def with_retry(
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    config: RetryConfig | None = None,
) -> Any:
    """Execute a coroutine with exponential backoff retry.

    Parameters
    ----------
    coro_factory:
        A callable that returns a new coroutine on each call.
    config:
        Retry configuration. Defaults to RetryConfig().

    Returns
    -------
    The result of the coroutine.

    Raises
    ------
    The last exception if all retries are exhausted.
    """
    cfg = config or RetryConfig()
    last_exc: Exception | None = None

    for attempt in range(cfg.max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt >= cfg.max_retries or not is_retryable(exc, cfg):
                raise
            delay = min(
                cfg.base_delay * (cfg.exponential_base ** attempt),
                cfg.max_delay,
            )
            logger.warning(
                "Attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1, cfg.max_retries + 1, exc, delay,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]  # unreachable but satisfies type checker


async def with_timeout(
    coro: Coroutine[Any, Any, Any],
    timeout_seconds: float = 120.0,
) -> Any:
    """Wrap a coroutine with a timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")


__all__ = ["RetryConfig", "is_retryable", "with_retry", "with_timeout"]
