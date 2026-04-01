"""Tests for the conversation runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hephaestus.agent.runtime import ConversationRuntime, ToolCallRecord, TurnResult
from hephaestus.session.schema import EntryType, Role, Session
from hephaestus.tools.permissions import PermissionMode, PermissionPolicy
from hephaestus.tools.registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Mock adapter helpers
# ---------------------------------------------------------------------------

@dataclass
class MockToolCall:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockGenResult:
    text: str
    content_blocks: list[dict[str, Any]]
    tool_calls: list[MockToolCall]
    input_tokens: int = 10
    output_tokens: int = 20
    cost_usd: float = 0.0
    model: str = "mock"
    stop_reason: str = "end_turn"


def _text_result(text: str) -> MockGenResult:
    """Adapter returns text only, no tool calls."""
    return MockGenResult(
        text=text,
        content_blocks=[{"type": "text", "text": text}],
        tool_calls=[],
    )


def _tool_result(tool_calls: list[MockToolCall], text: str = "") -> MockGenResult:
    """Adapter requests tool calls."""
    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    for tc in tool_calls:
        blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
    return MockGenResult(text=text, content_blocks=blocks, tool_calls=tool_calls)


def _make_registry(*tools: tuple[str, str]) -> ToolRegistry:
    """Build a registry with named tools."""
    reg = ToolRegistry()
    for name, category in tools:
        reg.register(ToolDefinition(
            name=name,
            description=f"Tool {name}",
            input_schema={"type": "object", "properties": {}},
            category=category,
            handler=lambda **kw: f"result for {kw}",
        ))
    return reg


def _make_runtime(
    adapter: Any = None,
    registry: ToolRegistry | None = None,
    mode: PermissionMode = PermissionMode.FULL_ACCESS,
) -> ConversationRuntime:
    if adapter is None:
        adapter = AsyncMock()
    if registry is None:
        registry = _make_registry(("read_file", "read"), ("calculator", "safe"))
    policy = PermissionPolicy(mode)
    session = Session()
    return ConversationRuntime(adapter, registry, policy, session)


# ---------------------------------------------------------------------------
# TurnResult / ToolCallRecord
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_turn_result_defaults(self):
        tr = TurnResult(text="hi")
        assert tr.tool_calls == []
        assert tr.rounds == 0

    def test_tool_call_record(self):
        tcr = ToolCallRecord(
            tool_use_id="1", name="read_file", input={"path": "/a"}, output="ok",
        )
        assert tcr.is_error is False


# ---------------------------------------------------------------------------
# ConversationRuntime
# ---------------------------------------------------------------------------

class TestRuntimeTextOnly:
    async def test_simple_text_response(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(return_value=_text_result("Hello!"))
        rt = _make_runtime(adapter=adapter)
        result = await rt.run_turn("Hi")
        assert result == "Hello!"

    async def test_records_in_session(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(return_value=_text_result("Sure"))
        rt = _make_runtime(adapter=adapter)
        await rt.run_turn("Do something")
        entries = rt.session.transcript
        assert len(entries) == 2
        assert entries[0].role == Role.USER.value
        assert entries[1].role == Role.ASSISTANT.value


class TestRuntimeToolLoop:
    async def test_single_tool_call(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([MockToolCall(id="t1", name="calculator", input={})]),
            _text_result("Done"),
        ])
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="calculator",
            description="calc",
            input_schema={"type": "object", "properties": {}},
            category="safe",
            handler=lambda **kw: "42",
        ))
        rt = _make_runtime(adapter=adapter, registry=reg)
        result = await rt.run_turn("calc")
        assert result == "Done"
        assert adapter.generate_with_tools.call_count == 2

    async def test_tool_denied_by_permissions(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([MockToolCall(id="t1", name="web_search", input={"query": "test"})]),
            _text_result("Fallback"),
        ])
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="web_search",
            description="search",
            input_schema={"type": "object", "properties": {}},
            category="dangerous",
            handler=lambda **kw: "results",
        ))
        rt = _make_runtime(adapter=adapter, registry=reg, mode=PermissionMode.READ_ONLY)
        result = await rt.run_turn("search web")
        assert result == "Fallback"
        # The tool result should include denial
        tool_entries = [
            e for e in rt.session.transcript if e.entry_type == EntryType.TOOL_RESULT.value
        ]
        assert len(tool_entries) == 1
        assert "FULL_ACCESS" in tool_entries[0].content

    async def test_missing_handler(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([MockToolCall(id="t1", name="unknown_tool", input={})]),
            _text_result("OK"),
        ])
        rt = _make_runtime(adapter=adapter)
        result = await rt.run_turn("do thing")
        assert result == "OK"

    async def test_handler_exception(self):
        def bad_handler(**kw):
            raise RuntimeError("boom")

        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([MockToolCall(id="t1", name="calculator", input={})]),
            _text_result("recovered"),
        ])
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="calculator",
            description="calc",
            input_schema={"type": "object", "properties": {}},
            category="safe",
            handler=bad_handler,
        ))
        rt = _make_runtime(adapter=adapter, registry=reg)
        result = await rt.run_turn("calc")
        assert result == "recovered"
        tool_results = [
            e for e in rt.session.transcript if e.entry_type == EntryType.TOOL_RESULT.value
        ]
        assert any("boom" in e.content for e in tool_results)

    async def test_max_rounds_reached(self):
        """When tool calls never stop, runtime caps at max_rounds."""
        adapter = AsyncMock()
        # Always return a tool call, never text.
        adapter.generate_with_tools = AsyncMock(
            return_value=_tool_result([MockToolCall(id="t1", name="calculator", input={})]),
        )
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="calculator",
            description="calc",
            input_schema={"type": "object", "properties": {}},
            category="safe",
            handler=lambda **kw: "42",
        ))
        rt = _make_runtime(adapter=adapter, registry=reg)
        rt.max_rounds = 3
        result = await rt.run_turn("loop forever")
        assert "max tool rounds" in result.lower()
        assert adapter.generate_with_tools.call_count == 3

    async def test_async_handler(self):
        async def async_handler(**kw):
            return "async result"

        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([MockToolCall(id="t1", name="calculator", input={})]),
            _text_result("Final"),
        ])
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="calculator",
            description="calc",
            input_schema={"type": "object", "properties": {}},
            category="safe",
            handler=async_handler,
        ))
        rt = _make_runtime(adapter=adapter, registry=reg)
        result = await rt.run_turn("async")
        assert result == "Final"

    async def test_system_prompt_passed(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(return_value=_text_result("hi"))
        rt = _make_runtime(adapter=adapter)
        rt.system_prompt = "You are helpful."
        await rt.run_turn("test")
        call_kwargs = adapter.generate_with_tools.call_args
        assert call_kwargs.kwargs.get("system") == "You are helpful."

    async def test_multiple_tool_calls_in_one_round(self):
        adapter = AsyncMock()
        adapter.generate_with_tools = AsyncMock(side_effect=[
            _tool_result([
                MockToolCall(id="t1", name="calculator", input={}),
                MockToolCall(id="t2", name="calculator", input={}),
            ]),
            _text_result("Both done"),
        ])
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="calculator",
            description="calc",
            input_schema={"type": "object", "properties": {}},
            category="safe",
            handler=lambda **kw: "42",
        ))
        rt = _make_runtime(adapter=adapter, registry=reg)
        result = await rt.run_turn("two tools")
        assert result == "Both done"
        # Two tool_result entries in session
        tool_results = [
            e for e in rt.session.transcript if e.entry_type == EntryType.TOOL_RESULT.value
        ]
        assert len(tool_results) == 2
