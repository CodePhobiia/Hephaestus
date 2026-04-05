"""Telemetry event bus — in-process pub/sub for lifecycle events."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    STAGE_ENTERED = "stage_entered"
    STAGE_COMPLETED = "stage_completed"
    PROVIDER_CALL = "provider_call"
    TOOL_CALL = "tool_call"
    MCP_CALL = "mcp_call"
    COUNCIL_EVENT = "council_event"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    COST_UPDATED = "cost_updated"
    QUALITY_GATE = "quality_gate"
    RESEARCH_CALL = "research_call"


@dataclass
class TelemetryEvent:
    """A single telemetry event in the system."""

    event_type: EventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: uuid4().hex[:16])
    run_id: str = ""
    correlation_id: str = ""
    stage: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "stage": self.stage,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


EventHandler = Callable[[TelemetryEvent], None]


class EventBus:
    """In-process event bus with pluggable sinks."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._type_handlers: dict[EventType, list[EventHandler]] = {}

    def subscribe(self, handler: EventHandler, *, event_type: EventType | None = None) -> None:
        """Subscribe a handler to events. If event_type is None, subscribes to all."""
        if event_type is None:
            self._handlers.append(handler)
        else:
            self._type_handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: TelemetryEvent) -> None:
        """Emit an event to all matching handlers."""
        # Inject correlation context if available
        if not event.correlation_id:
            from hephaestus.telemetry.logging import get_correlation_id

            event.correlation_id = get_correlation_id()
        if not event.run_id:
            from hephaestus.telemetry.logging import get_run_id

            event.run_id = get_run_id()

        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler error for %s", event.event_type.value)

        for handler in self._type_handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler error for %s", event.event_type.value)

    def emit_simple(
        self,
        event_type: EventType,
        *,
        stage: str = "",
        duration_ms: float = 0.0,
        **metadata: Any,
    ) -> None:
        """Convenience method to emit an event without constructing the dataclass."""
        self.emit(
            TelemetryEvent(
                event_type=event_type,
                stage=stage,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )


class StageTimer:
    """Context manager for timing pipeline stages and emitting events."""

    def __init__(self, bus: EventBus, stage: str, **extra: Any) -> None:
        self._bus = bus
        self._stage = stage
        self._extra = extra
        self._start: float = 0.0

    def __enter__(self) -> StageTimer:
        self._start = time.monotonic()
        self._bus.emit_simple(EventType.STAGE_ENTERED, stage=self._stage, **self._extra)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        if exc_type is not None:
            self._bus.emit_simple(
                EventType.RUN_FAILED,
                stage=self._stage,
                duration_ms=elapsed_ms,
                error=str(exc_val),
                error_type=exc_type.__name__ if exc_type else "Unknown",
                **self._extra,
            )
        else:
            self._bus.emit_simple(
                EventType.STAGE_COMPLETED,
                stage=self._stage,
                duration_ms=elapsed_ms,
                **self._extra,
            )


# Global event bus singleton
_global_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the global event bus, creating it if needed."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


__all__ = [
    "EventBus",
    "EventType",
    "StageTimer",
    "TelemetryEvent",
    "get_event_bus",
]
