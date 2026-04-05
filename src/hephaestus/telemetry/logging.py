"""Structured JSON logging with correlation IDs."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

# Context variable for correlation ID propagation
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="")


def set_correlation_id(cid: str | None = None) -> str:
    """Set or generate a correlation ID for the current context."""
    cid = cid or uuid4().hex
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_run_id(rid: str) -> None:
    run_id_var.set(rid)


def get_run_id() -> str:
    return run_id_var.get()


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        output: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Inject correlation context
        cid = correlation_id_var.get("")
        if cid:
            output["correlation_id"] = cid
        rid = run_id_var.get("")
        if rid:
            output["run_id"] = rid

        # Include extra fields
        if hasattr(record, "extra_data") and record.extra_data:
            output["data"] = record.extra_data

        # Include exception info
        if record.exc_info and record.exc_info[1] is not None:
            output["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
            output["traceback"] = self.formatException(record.exc_info)

        # Source location for debug
        if record.levelno >= logging.WARNING:
            output["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(output, default=str, ensure_ascii=False)


def configure_logging(
    *,
    level: str = "INFO",
    json_output: bool = True,
    stream: Any = None,
) -> None:
    """Configure stdlib logging with structured JSON output and correlation IDs.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, format as JSON. If False, use standard formatting.
        stream: Output stream. Defaults to sys.stderr.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to prevent duplicates
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stderr)

    if json_output:
        handler.setFormatter(StructuredJSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


__all__ = [
    "StructuredJSONFormatter",
    "configure_logging",
    "correlation_id_var",
    "get_correlation_id",
    "get_run_id",
    "run_id_var",
    "set_correlation_id",
    "set_run_id",
]
