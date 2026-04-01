"""MCP stdio client — JSON-RPC 2.0 over stdin/stdout subprocess communication."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any


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


class MCPClient:
    """Communicates with a single MCP server over stdio using JSON-RPC 2.0."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Spawn the server subprocess and send the initialize handshake."""
        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.env or None,
        )
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hephaestus", "version": "0.1.0"},
        })

    async def discover_tools(self) -> list[MCPTool]:
        """Request the server's tool list and return parsed MCPTool objects."""
        result = await self._send_request("tools/list", {})
        tools: list[MCPTool] = []
        for entry in result.get("tools", []):
            tools.append(MCPTool(
                server_name=self.config.name,
                tool_name=entry["name"],
                description=entry.get("description", ""),
                input_schema=entry.get("inputSchema", {}),
            ))
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool on the server and return the text result."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        # MCP tools/call returns content blocks; concatenate text ones.
        content = result.get("content", [])
        parts: list[str] = []
        for block in content:
            if block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts) if parts else json.dumps(result)

    async def shutdown(self) -> None:
        """Send shutdown request and terminate the subprocess."""
        if self._process is None:
            return
        try:
            if self.is_running:
                await self._send_request("shutdown", {})
        except (MCPError, asyncio.TimeoutError, OSError):
            pass
        finally:
            if self._process.stdin:
                self._process.stdin.close()
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
            self._process = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and wait for the matching response."""
        if not self.is_running:
            raise RuntimeError("MCP server process is not running")

        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        raw = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=self.config.timeout_seconds,
        )
        if not raw:
            raise RuntimeError("MCP server closed stdout unexpectedly")

        response = json.loads(raw.decode())
        if "error" in response:
            err = response["error"]
            raise MCPError(err.get("code", -1), err.get("message", "Unknown error"))

        return response.get("result", {})
