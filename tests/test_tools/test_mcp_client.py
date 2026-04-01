"""Tests for the MCP stdio client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.tools.mcp.client import MCPClient, MCPError, MCPServerConfig, MCPTool


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> MCPServerConfig:
    defaults = dict(name="test-server", command="/usr/bin/echo")
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


def _jsonrpc_response(req_id: int, result: dict) -> bytes:
    return (json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n").encode()


def _jsonrpc_error(req_id: int, code: int, message: str) -> bytes:
    return (json.dumps({
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": code, "message": message},
    }) + "\n").encode()


def _mock_process(responses: list[bytes]):
    """Create a mock process whose stdout yields *responses* in order."""
    proc = AsyncMock()
    proc.returncode = None
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=responses)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ---------------------------------------------------------------------------
# MCPServerConfig
# ---------------------------------------------------------------------------

class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="s", command="cmd")
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.timeout_seconds == 30

    def test_custom_values(self):
        cfg = MCPServerConfig(
            name="s", command="node", args=["server.js"],
            env={"KEY": "val"}, timeout_seconds=10,
        )
        assert cfg.args == ["server.js"]
        assert cfg.env["KEY"] == "val"
        assert cfg.timeout_seconds == 10


# ---------------------------------------------------------------------------
# MCPTool
# ---------------------------------------------------------------------------

class TestMCPTool:
    def test_qualified_name(self):
        tool = MCPTool(
            server_name="fs", tool_name="read",
            description="Read a file", input_schema={},
        )
        assert tool.qualified_name == "fs.read"

    def test_fields(self):
        tool = MCPTool(
            server_name="db", tool_name="query",
            description="Run SQL", input_schema={"type": "object"},
        )
        assert tool.description == "Run SQL"
        assert tool.input_schema == {"type": "object"}


# ---------------------------------------------------------------------------
# MCPClient — lifecycle
# ---------------------------------------------------------------------------

class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_start_sends_initialize(self):
        init_resp = _jsonrpc_response(1, {"protocolVersion": "2024-11-05"})
        proc = _mock_process([init_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()

        assert client.is_running
        # Verify initialize request was written
        written = proc.stdin.write.call_args[0][0]
        req = json.loads(written.decode())
        assert req["method"] == "initialize"
        assert req["id"] == 1

    @pytest.mark.asyncio
    async def test_shutdown_sends_request_and_terminates(self):
        init_resp = _jsonrpc_response(1, {})
        shutdown_resp = _jsonrpc_response(2, {})
        proc = _mock_process([init_resp, shutdown_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            await client.shutdown()

        assert not client.is_running
        proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_running_false_before_start(self):
        client = MCPClient(_make_config())
        assert not client.is_running

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self):
        client = MCPClient(_make_config())
        await client.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# MCPClient — discover_tools
# ---------------------------------------------------------------------------

class TestDiscoverTools:
    @pytest.mark.asyncio
    async def test_parses_tools_list(self):
        init_resp = _jsonrpc_response(1, {})
        tools_resp = _jsonrpc_response(2, {"tools": [
            {"name": "read", "description": "Read file",
             "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
            {"name": "write", "description": "Write file", "inputSchema": {}},
        ]})
        proc = _mock_process([init_resp, tools_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            tools = await client.discover_tools()

        assert len(tools) == 2
        assert tools[0].tool_name == "read"
        assert tools[0].qualified_name == "test-server.read"
        assert tools[1].description == "Write file"

    @pytest.mark.asyncio
    async def test_empty_tools_list(self):
        init_resp = _jsonrpc_response(1, {})
        tools_resp = _jsonrpc_response(2, {"tools": []})
        proc = _mock_process([init_resp, tools_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            tools = await client.discover_tools()

        assert tools == []


# ---------------------------------------------------------------------------
# MCPClient — call_tool
# ---------------------------------------------------------------------------

class TestCallTool:
    @pytest.mark.asyncio
    async def test_call_returns_text_content(self):
        init_resp = _jsonrpc_response(1, {})
        call_resp = _jsonrpc_response(2, {
            "content": [{"type": "text", "text": "hello world"}],
        })
        proc = _mock_process([init_resp, call_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            result = await client.call_tool("greet", {"name": "test"})

        assert result == "hello world"
        # Verify the request payload
        calls = proc.stdin.write.call_args_list
        call_req = json.loads(calls[-1][0][0].decode())
        assert call_req["method"] == "tools/call"
        assert call_req["params"]["name"] == "greet"

    @pytest.mark.asyncio
    async def test_call_concatenates_multiple_text_blocks(self):
        init_resp = _jsonrpc_response(1, {})
        call_resp = _jsonrpc_response(2, {
            "content": [
                {"type": "text", "text": "line1"},
                {"type": "image", "data": "..."},
                {"type": "text", "text": "line2"},
            ],
        })
        proc = _mock_process([init_resp, call_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            result = await client.call_tool("multi", {})

        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_call_fallback_json_when_no_text(self):
        init_resp = _jsonrpc_response(1, {})
        call_resp = _jsonrpc_response(2, {"value": 42})
        proc = _mock_process([init_resp, call_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            result = await client.call_tool("calc", {})

        assert json.loads(result) == {"value": 42}


# ---------------------------------------------------------------------------
# MCPClient — error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_error_response_raises_mcp_error(self):
        init_resp = _jsonrpc_response(1, {})
        err_resp = _jsonrpc_error(2, -32601, "Method not found")
        proc = _mock_process([init_resp, err_resp])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            with pytest.raises(MCPError, match="Method not found") as exc_info:
                await client.call_tool("bad", {})
            assert exc_info.value.code == -32601

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        init_resp = _jsonrpc_response(1, {})
        proc = _mock_process([init_resp])
        # Make the second readline hang forever
        proc.stdout.readline = AsyncMock(side_effect=[
            init_resp,
            asyncio.TimeoutError(),
        ])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config(timeout_seconds=1))
            await client.start()
            with pytest.raises(asyncio.TimeoutError):
                await client.call_tool("slow", {})

    @pytest.mark.asyncio
    async def test_closed_stdout_raises(self):
        init_resp = _jsonrpc_response(1, {})
        proc = _mock_process([init_resp, b""])

        with patch("hephaestus.tools.mcp.client.asyncio.create_subprocess_exec",
                    return_value=proc):
            client = MCPClient(_make_config())
            await client.start()
            with pytest.raises(RuntimeError, match="closed stdout"):
                await client.call_tool("gone", {})

    @pytest.mark.asyncio
    async def test_send_request_when_not_running(self):
        client = MCPClient(_make_config())
        with pytest.raises(RuntimeError, match="not running"):
            await client._send_request("test", {})
