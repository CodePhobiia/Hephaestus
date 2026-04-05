"""MCP stdio client — JSON-RPC 2.0 over stdin/stdout subprocess communication."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from hephaestus.tools.mcp.health import MCPHealthTracker
from hephaestus.tools.mcp.protocol import ProtocolEngine

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server subprocess."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30


@dataclass
class MCPTool:
    """A tool discovered from an MCP server."""

    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]

    @property
    def qualified_name(self) -> str:
        return f"{self.server_name}.{self.tool_name}"


class MCPError(Exception):
    """Error from MCP server or protocol."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(message)


class MCPClientState(StrEnum):
    """Lifecycle state of an MCP client connection."""

    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPED = "stopped"


import contextlib  # noqa: E402
import os  # noqa: E402


class MCPClient:
    """Communicates with a single MCP server over stdio using JSON-RPC 2.0."""

    def __init__(
        self,
        config: MCPServerConfig,
        *,
        health_tracker: MCPHealthTracker | None = None,
        heartbeat_interval: float = 30.0,
    ) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[Any] | None = None
        self._stderr_task: asyncio.Task[Any] | None = None
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._protocol = ProtocolEngine()
        self._health = health_tracker
        self._heartbeat_interval = heartbeat_interval
        self._state = MCPClientState.STOPPED
        self._notification_handlers: dict[str, list[Any]] = {}

    @property
    def state(self) -> MCPClientState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def on_notification(self, method: str, handler: Any) -> None:
        """Register a handler for server notifications."""
        self._notification_handlers.setdefault(method, []).append(handler)
        self._protocol.register_notification_handler(method, handler)

    async def start(self) -> None:
        """Spawn the server subprocess and send the initialize handshake."""
        self._state = MCPClientState.STARTING
        if self._health:
            self._health.register(self.config.name)

        # Filter secrets from the inherited environment to avoid leaking API keys
        # to MCP server subprocesses. Only pass through non-sensitive vars.
        secret_patterns = {"API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL"}
        env = {
            k: v for k, v in os.environ.items()
            if not any(pat in k.upper() for pat in secret_patterns)
        }
        # Explicitly merge any env vars declared in the MCP server config
        if self.config.env:
            env.update(self.config.env)

        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._reader_task = asyncio.create_task(self._read_pump())
        self._stderr_task = asyncio.create_task(self._stderr_pump())

        result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hephaestus", "version": "0.1.0"},
            },
        )

        # Negotiate version if server provides one
        server_version = result.get("protocolVersion", "2024-11-05")
        self._protocol.negotiate_version(server_version)

        self._state = MCPClientState.READY
        if self._health:
            self._health.mark_ready(self.config.name)

        # Start heartbeat
        if self._heartbeat_interval > 0:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("MCP server %s ready (protocol: %s)", self.config.name, server_version)

    async def discover_tools(self) -> list[MCPTool]:
        """Request the server's tool list and return parsed MCPTool objects."""
        result = await self._send_request("tools/list", {})
        tools: list[MCPTool] = []
        for entry in result.get("tools", []):
            tools.append(
                MCPTool(
                    server_name=self.config.name,
                    tool_name=entry["name"],
                    description=entry.get("description", ""),
                    input_schema=entry.get("inputSchema", {}),
                )
            )
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool on the server and return the text result."""
        start = time.monotonic()
        try:
            result = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                },
            )
            latency_ms = (time.monotonic() - start) * 1000
            if self._health:
                self._health.record_success(self.config.name, latency_ms)

            content = result.get("content", [])
            parts: list[str] = []
            for block in content:
                if block.get("type") == "text":
                    parts.append(block["text"])
            return "\n".join(parts) if parts else json.dumps(result)
        except Exception as exc:
            if self._health:
                self._health.record_failure(self.config.name, str(exc))
            raise

    async def shutdown(self) -> None:
        """Send shutdown request and terminate the subprocess."""
        self._state = MCPClientState.STOPPED
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        if self._process is None:
            return
        try:
            if self.is_running:
                await self._send_request("shutdown", {})
        except (TimeoutError, MCPError, OSError, RuntimeError):
            pass
        finally:
            if self._reader_task:
                self._reader_task.cancel()
            if self._stderr_task:
                self._stderr_task.cancel()

            if self._process.stdin:
                self._process.stdin.close()

            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError, OSError):
                with contextlib.suppress(OSError):
                    self._process.kill()
            self._process = None

            if self._health:
                self._health.mark_stopped(self.config.name)

            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("MCP server shutting down"))
            self._pending_requests.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _stderr_pump(self) -> None:
        """Drain stderr to prevent blocking."""
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
        except (asyncio.CancelledError, OSError):
            pass

    async def _read_pump(self) -> None:
        """Continuously read stdout and route JSON-RPC frames via the protocol engine."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break

                frame = self._protocol.parse_line(line)
                if frame is None:
                    continue

                # Notifications are auto-dispatched by the protocol engine.
                # Responses need to be correlated to pending futures.
                from hephaestus.tools.mcp.protocol import JSONRPCResponse

                if isinstance(frame, JSONRPCResponse) and frame.id is not None:
                    req_id = frame.id
                    if req_id in self._pending_requests:
                        # Re-wrap into the dict format expected by _send_request
                        payload: dict[str, Any] = {"id": frame.id}
                        if frame.error:
                            payload["error"] = frame.error
                        else:
                            payload["result"] = frame.result or {}
                        self._pending_requests[req_id].set_result(payload)

        except (asyncio.CancelledError, OSError):
            pass
        finally:
            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("MCP server stdout closed unexpectedly"))

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and wait for the matching response."""
        if not self.is_running:
            raise RuntimeError("MCP server process is not running")

        assert self._process is not None
        assert self._process.stdin is not None

        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        try:
            line = json.dumps(request) + "\n"
            self._process.stdin.write(line.encode())
            await self._process.stdin.drain()

            response = await asyncio.wait_for(future, timeout=self.config.timeout_seconds)

            if "error" in response:
                err = response["error"]
                raise MCPError(err.get("code", -1), err.get("message", "Unknown error"))

            return response.get("result", {})
        finally:
            self._pending_requests.pop(req_id, None)

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to detect server liveness."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if not self.is_running:
                    logger.warning(
                        "MCP server %s process died, stopping heartbeat", self.config.name
                    )
                    self._state = MCPClientState.STOPPED
                    if self._health:
                        self._health.mark_stopped(self.config.name)
                    break
                try:
                    await asyncio.wait_for(
                        self._send_request("ping", {}),
                        timeout=min(10.0, self._heartbeat_interval / 2),
                    )
                except (TimeoutError, MCPError):
                    self._state = MCPClientState.DEGRADED
                    logger.warning("MCP server %s heartbeat failed", self.config.name)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("MCP heartbeat error for %s", self.config.name)
