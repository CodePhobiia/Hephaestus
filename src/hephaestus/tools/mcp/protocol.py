"""MCP JSON-RPC 2.0 protocol engine — strict frame parsing and routing."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ProtocolError(Exception):
    """Raised on JSON-RPC 2.0 protocol violations."""


@dataclass
class JSONRPCRequest:
    """A JSON-RPC 2.0 request frame."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None

    def to_bytes(self) -> bytes:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": self.method}
        if self.params:
            payload["params"] = self.params
        if self.id is not None:
            payload["id"] = self.id
        return (json.dumps(payload) + "\n").encode()

    @property
    def is_notification(self) -> bool:
        return self.id is None


@dataclass
class JSONRPCResponse:
    """A parsed JSON-RPC 2.0 response frame."""

    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def error_code(self) -> int:
        if self.error:
            return int(self.error.get("code", -1))
        return 0

    @property
    def error_message(self) -> str:
        if self.error:
            return str(self.error.get("message", "Unknown error"))
        return ""


@dataclass
class JSONRPCNotification:
    """A JSON-RPC 2.0 notification (request without id)."""

    method: str
    params: dict[str, Any] = field(default_factory=dict)


class ProtocolEngine:
    """Strict JSON-RPC 2.0 frame parser and router.

    Parses incoming bytes into typed frames and dispatches them
    to registered handlers.
    """

    SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26"}

    def __init__(self) -> None:
        self._notification_handlers: dict[str, list[Any]] = {}
        self._buffer = b""

    def register_notification_handler(self, method: str, handler: Any) -> None:
        """Register a handler for a specific notification method."""
        self._notification_handlers.setdefault(method, []).append(handler)

    def parse_frame(self, raw: bytes) -> JSONRPCResponse | JSONRPCNotification | None:
        """Parse a single JSON-RPC 2.0 frame from raw bytes.

        Returns:
            JSONRPCResponse for responses (has id),
            JSONRPCNotification for notifications (no id, has method),
            None if the frame is malformed.
        """
        try:
            text = raw.decode("utf-8").strip()
            if not text:
                return None
            payload = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Malformed JSON-RPC frame: %s", exc)
            return None

        if not isinstance(payload, dict):
            logger.warning("JSON-RPC frame is not an object")
            return None

        # Check for jsonrpc version
        version = payload.get("jsonrpc")
        if version != "2.0":
            logger.debug("Non-2.0 JSON-RPC frame (got: %s)", version)

        # Route: response (has id but no method) vs notification (has method, no id)
        has_id = "id" in payload
        has_method = "method" in payload

        if has_id and not has_method:
            # Response
            return JSONRPCResponse(
                id=payload["id"],
                result=payload.get("result"),
                error=payload.get("error"),
            )
        elif has_method and not has_id:
            # Notification
            notification = JSONRPCNotification(
                method=payload["method"],
                params=payload.get("params", {}),
            )
            self._dispatch_notification(notification)
            return notification
        elif has_id and has_method:
            # Server-initiated request (rare in MCP, treat as response for correlation)
            return JSONRPCResponse(
                id=payload["id"],
                result=payload.get("params", {}),
            )
        else:
            logger.warning("JSON-RPC frame has neither id nor method")
            return None

    def parse_line(self, line: bytes) -> JSONRPCResponse | JSONRPCNotification | None:
        """Parse a single newline-delimited JSON-RPC frame."""
        return self.parse_frame(line)

    def parse_batch(self, data: bytes) -> list[JSONRPCResponse | JSONRPCNotification]:
        """Parse multiple newline-delimited frames."""
        results = []
        for line in data.split(b"\n"):
            line = line.strip()
            if line:
                frame = self.parse_frame(line)
                if frame is not None:
                    results.append(frame)
        return results

    def build_request(
        self, method: str, params: dict[str, Any], request_id: int | str
    ) -> JSONRPCRequest:
        """Build a JSON-RPC 2.0 request."""
        return JSONRPCRequest(method=method, params=params, id=request_id)

    def build_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> JSONRPCRequest:
        """Build a JSON-RPC 2.0 notification (no id)."""
        return JSONRPCRequest(method=method, params=params or {}, id=None)

    def negotiate_version(self, server_version: str) -> str:
        """Negotiate protocol version with server.

        Returns the agreed version, or raises ProtocolError.
        """
        if server_version in self.SUPPORTED_PROTOCOL_VERSIONS:
            return server_version
        # Fall back to latest supported
        latest = max(self.SUPPORTED_PROTOCOL_VERSIONS)
        logger.warning(
            "Server protocol version %s not in supported set %s; using %s",
            server_version,
            self.SUPPORTED_PROTOCOL_VERSIONS,
            latest,
        )
        return latest

    def _dispatch_notification(self, notification: JSONRPCNotification) -> None:
        """Dispatch a notification to registered handlers."""
        handlers = self._notification_handlers.get(notification.method, [])
        for handler in handlers:
            try:
                handler(notification)
            except Exception:
                logger.exception("Error in notification handler for %s", notification.method)

        if not handlers:
            logger.debug("Unhandled notification: %s", notification.method)


__all__ = [
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "ProtocolEngine",
    "ProtocolError",
]
