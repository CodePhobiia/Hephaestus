"""Tests for the default tool registry factory."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hephaestus.tools.defaults import (
    EXPECTED_TOOLS,
    _session_todos,
    create_default_registry,
)
from hephaestus.tools.registry import BUILTIN_PROFILES, ToolDefinition, ToolRegistry


class TestCreateDefaultRegistry:
    """create_default_registry returns a fully populated ToolRegistry."""

    def test_returns_tool_registry(self):
        reg = create_default_registry()
        assert isinstance(reg, ToolRegistry)

    def test_registry_is_not_empty(self):
        reg = create_default_registry()
        assert len(reg.list_tools()) > 0

    def test_all_expected_tools_registered(self):
        reg = create_default_registry()
        names = {t.name for t in reg.list_tools()}
        assert names == EXPECTED_TOOLS

    def test_each_tool_is_tool_definition(self):
        reg = create_default_registry()
        for tool in reg.list_tools():
            assert isinstance(tool, ToolDefinition)


class TestToolSchemas:
    """Each tool has a valid input_schema in JSON Schema format."""

    @pytest.fixture()
    def registry(self):
        return create_default_registry()

    def test_all_schemas_are_dicts(self, registry):
        for tool in registry.list_tools():
            assert isinstance(tool.input_schema, dict), f"{tool.name} schema not a dict"

    def test_all_schemas_have_type_object(self, registry):
        for tool in registry.list_tools():
            assert tool.input_schema.get("type") == "object", (
                f"{tool.name} schema missing type: object"
            )

    def test_all_schemas_have_properties(self, registry):
        for tool in registry.list_tools():
            assert "properties" in tool.input_schema, f"{tool.name} schema missing 'properties'"

    def test_required_fields_are_lists(self, registry):
        for tool in registry.list_tools():
            req = tool.input_schema.get("required")
            if req is not None:
                assert isinstance(req, list), f"{tool.name} required not a list"

    def test_read_file_schema(self, registry):
        tool = registry.get("read_file")
        assert tool is not None
        props = tool.input_schema["properties"]
        assert "path" in props
        assert "max_chars" in props
        assert "path" in tool.input_schema["required"]

    def test_write_file_schema(self, registry):
        tool = registry.get("write_file")
        assert tool is not None
        assert set(tool.input_schema["required"]) == {"path", "content"}

    def test_web_search_schema(self, registry):
        tool = registry.get("web_search")
        assert tool is not None
        props = tool.input_schema["properties"]
        assert "query" in props
        assert "max_results" in props

    def test_web_fetch_schema(self, registry):
        tool = registry.get("web_fetch")
        assert tool is not None
        assert "url" in tool.input_schema["properties"]

    def test_calculator_schema(self, registry):
        tool = registry.get("calculator")
        assert tool is not None
        assert "expression" in tool.input_schema["properties"]


class TestToolHandlers:
    """Each tool has a callable handler."""

    @pytest.fixture()
    def registry(self):
        return create_default_registry()

    def test_all_handlers_are_callable(self, registry):
        for tool in registry.list_tools():
            assert callable(tool.handler), f"{tool.name} handler not callable"

    def test_read_file_handler(self, registry):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            f.flush()
            tool = registry.get("read_file")
            result = tool.handler({"path": f.name})
            assert "hello world" in result

    def test_write_file_handler(self, registry):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.txt")
            tool = registry.get("write_file")
            result = tool.handler({"path": path, "content": "test content"})
            assert "Wrote" in result
            assert Path(path).read_text() == "test content"

    def test_list_directory_handler(self, registry):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "file_a.txt").touch()
            tool = registry.get("list_directory")
            result = tool.handler({"path": d})
            assert "file_a.txt" in result

    def test_calculator_handler(self, registry):
        tool = registry.get("calculator")
        assert tool.handler({"expression": "2 + 3"}) == "5"
        assert tool.handler({"expression": "10 * 2"}) == "20"

    def test_calculator_error(self, registry):
        tool = registry.get("calculator")
        result = tool.handler({"expression": "1 / 0"})
        assert "error" in result.lower()

    def test_todo_add_handler(self, registry):
        _session_todos.items.clear()
        tool = registry.get("todo_add")
        result = tool.handler({"title": "Test task"})
        assert "Added todo" in result
        assert "Test task" in result

    def test_todo_list_handler(self, registry):
        _session_todos.items.clear()
        _session_todos.add("Item one")
        tool = registry.get("todo_list")
        result = tool.handler({})
        assert "Item one" in result


class TestToolCategories:
    """Tools have correct category assignments."""

    @pytest.fixture()
    def registry(self):
        return create_default_registry()

    def test_read_tools_have_read_category(self, registry):
        for name in ("read_file", "list_directory", "search_files", "grep_search"):
            tool = registry.get(name)
            assert tool.category == "read", f"{name} should be category 'read'"

    def test_write_tools_have_write_category(self, registry):
        tool = registry.get("write_file")
        assert tool.category == "write"

    def test_safe_tools_have_safe_category(self, registry):
        for name in ("web_search", "web_fetch", "calculator", "todo_add", "todo_list"):
            tool = registry.get(name)
            assert tool.category == "safe", f"{name} should be category 'safe'"


class TestProfileCoverage:
    """Built-in profiles reference tools that exist in the default registry."""

    def test_invent_profile_tools_registered(self):
        reg = create_default_registry()
        registered = {t.name for t in reg.list_tools()}
        profile_tools = BUILTIN_PROFILES["invent"]
        overlap = profile_tools & registered
        # At least the core tools should be present
        assert overlap >= {
            "read_file",
            "list_directory",
            "search_files",
            "grep_search",
            "calculator",
        }

    def test_research_profile_tools_registered(self):
        reg = create_default_registry()
        registered = {t.name for t in reg.list_tools()}
        profile_tools = BUILTIN_PROFILES["research"]
        overlap = profile_tools & registered
        assert overlap >= {"web_search", "web_fetch", "read_file", "calculator"}

    def test_api_schema_valid(self):
        reg = create_default_registry()
        schema = reg.to_api_schema()
        assert isinstance(schema, list)
        assert len(schema) == len(EXPECTED_TOOLS)
        for entry in schema:
            assert "name" in entry
            assert "description" in entry
            assert "input_schema" in entry
