"""MCP health tracking — per-server latency, failure rate, and circuit breaker."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class MCPServerState(StrEnum):
    """Health state of an MCP server."""

    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"
    STOPPED = "stopped"


@dataclass
class ServerHealthRecord:
    """Health tracking data for a single MCP server."""

    server_name: str
    state: MCPServerState = MCPServerState.STARTING
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    total_latency_ms: float = 0.0
    last_call_at: float = 0.0
    last_failure_at: float = 0.0
    last_failure_error: str = ""
    restart_count: int = 0
    circuit_opened_at: float = 0.0

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "consecutive_failures": self.consecutive_failures,
            "failure_rate": round(self.failure_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "restart_count": self.restart_count,
        }


class MCPHealthTracker:
    """Tracks health and performance of all MCP servers.

    Implements circuit breaker pattern: after N consecutive failures,
    the server is marked circuit_open and calls are rejected until
    a cooldown period passes and a probe succeeds.
    """

    def __init__(
        self,
        *,
        circuit_breaker_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._threshold = circuit_breaker_threshold
        self._cooldown = cooldown_seconds
        self._records: dict[str, ServerHealthRecord] = {}

    def register(self, server_name: str) -> None:
        if server_name not in self._records:
            self._records[server_name] = ServerHealthRecord(server_name=server_name)

    def mark_ready(self, server_name: str) -> None:
        record = self._get_or_create(server_name)
        record.state = MCPServerState.READY
        record.consecutive_failures = 0
        logger.info("MCP server %s marked ready", server_name)

    def mark_stopped(self, server_name: str) -> None:
        record = self._get_or_create(server_name)
        record.state = MCPServerState.STOPPED

    def record_success(self, server_name: str, latency_ms: float) -> None:
        record = self._get_or_create(server_name)
        record.total_calls += 1
        record.successful_calls += 1
        record.total_latency_ms += latency_ms
        record.last_call_at = time.monotonic()
        record.consecutive_failures = 0

        if record.state == MCPServerState.CIRCUIT_OPEN:
            record.state = MCPServerState.READY
            logger.info("MCP server %s circuit closed after successful probe", server_name)
        elif record.state != MCPServerState.READY:
            record.state = MCPServerState.READY

    def record_failure(self, server_name: str, error: str) -> None:
        record = self._get_or_create(server_name)
        record.total_calls += 1
        record.failed_calls += 1
        record.consecutive_failures += 1
        record.last_failure_at = time.monotonic()
        record.last_failure_error = error

        if record.consecutive_failures >= self._threshold:
            record.state = MCPServerState.CIRCUIT_OPEN
            record.circuit_opened_at = time.monotonic()
            logger.warning(
                "MCP server %s circuit opened after %d consecutive failures",
                server_name,
                record.consecutive_failures,
            )
        elif record.consecutive_failures >= 2:
            record.state = MCPServerState.DEGRADED

    def record_restart(self, server_name: str) -> None:
        record = self._get_or_create(server_name)
        record.restart_count += 1
        record.state = MCPServerState.STARTING
        record.consecutive_failures = 0

    def is_available(self, server_name: str) -> bool:
        """Check if a server should accept calls."""
        record = self._records.get(server_name)
        if record is None:
            return True  # Unknown server, allow optimistically

        if record.state == MCPServerState.CIRCUIT_OPEN:
            elapsed = time.monotonic() - record.circuit_opened_at
            if elapsed >= self._cooldown:
                logger.info("MCP server %s cooldown elapsed, allowing probe", server_name)
                return True  # Allow a probe
            return False

        return record.state in (
            MCPServerState.READY,
            MCPServerState.STARTING,
            MCPServerState.DEGRADED,
        )

    def get_health(self, server_name: str) -> ServerHealthRecord | None:
        return self._records.get(server_name)

    def all_health(self) -> dict[str, dict[str, Any]]:
        return {name: record.to_dict() for name, record in self._records.items()}

    def _get_or_create(self, server_name: str) -> ServerHealthRecord:
        if server_name not in self._records:
            self._records[server_name] = ServerHealthRecord(server_name=server_name)
        return self._records[server_name]


__all__ = [
    "MCPHealthTracker",
    "MCPServerState",
    "ServerHealthRecord",
]
