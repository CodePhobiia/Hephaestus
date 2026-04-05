"""Hephaestus telemetry — structured logging, metrics, tracing, and cost governance."""

from hephaestus.telemetry.cost import BudgetPolicy, BudgetViolation, CostGovernor
from hephaestus.telemetry.events import (
    EventBus,
    EventType,
    StageTimer,
    TelemetryEvent,
    get_event_bus,
)
from hephaestus.telemetry.logging import (
    configure_logging,
    get_correlation_id,
    get_run_id,
    set_correlation_id,
    set_run_id,
)
from hephaestus.telemetry.metrics import MetricsCollector, get_metrics
from hephaestus.telemetry.tracing import configure_tracing, get_tracer, shutdown_tracing

__all__ = [
    "BudgetPolicy",
    "BudgetViolation",
    "CostGovernor",
    "EventBus",
    "EventType",
    "MetricsCollector",
    "StageTimer",
    "TelemetryEvent",
    "configure_logging",
    "configure_tracing",
    "get_correlation_id",
    "get_event_bus",
    "get_metrics",
    "get_run_id",
    "get_tracer",
    "set_correlation_id",
    "set_run_id",
    "shutdown_tracing",
]
