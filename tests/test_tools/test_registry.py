"""Tests for the tool registry."""

import pytest

from hephaestus.tools.registry import (
    BUILTIN_PROFILES,
    ToolDefinition,
    ToolProfile,
    ToolRegistry,
)


def _dummy_handler(**kwargs):
    return "ok"


def _make_tool(name: str, category: str = "safe") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Test tool: {name}",
        input_schema={"type": "object", "properties": {}},
        category=category,
        handler=_dummy_handler,
    )


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_defaults(self):
        td = ToolDefinition(name="t", description="d", input_schema={})
        assert td.category == "safe"
        assert td.handler is None

    def test_with_handler(self):
        td = _make_tool("foo")
        assert td.handler is _dummy_handler


# ---------------------------------------------------------------------------
# ToolProfile
# ---------------------------------------------------------------------------


class TestToolProfile:
    def test_defaults(self):
        tp = ToolProfile(name="custom")
        assert tp.allowed_tools == set()

    def test_with_tools(self):
        tp = ToolProfile(name="custom", allowed_tools={"a", "b"})
        assert "a" in tp.allowed_tools


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestRegistryBasics:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = _make_tool("read_file", "read")
        reg.register(tool)
        assert reg.get("read_file") is tool

    def test_get_missing(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_list_tools_all(self):
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        assert len(reg.list_tools()) == 2

    def test_register_overwrites(self):
        reg = ToolRegistry()
        reg.register(_make_tool("x"))
        new = _make_tool("x")
        new = ToolDefinition(
            name="x",
            description="updated",
            input_schema={},
            handler=_dummy_handler,
        )
        reg.register(new)
        assert reg.get("x").description == "updated"


class TestRegistryProfiles:
    @pytest.fixture()
    def registry(self):
        reg = ToolRegistry()
        for name in ("read_file", "list_directory", "calculator", "write_file", "web_search"):
            reg.register(_make_tool(name))
        return reg

    def test_apply_profile_filters(self, registry):
        registry.apply_profile("invent")
        tools = registry.list_tools()
        names = {t.name for t in tools}
        assert "read_file" in names
        assert "calculator" in names
        assert "web_search" not in names

    def test_apply_profile_get_filtered(self, registry):
        registry.apply_profile("invent")
        assert registry.get("web_search") is None
        assert registry.get("read_file") is not None

    def test_clear_profile(self, registry):
        registry.apply_profile("invent")
        registry.clear_profile()
        assert registry.get("web_search") is not None

    def test_unknown_profile_raises(self, registry):
        with pytest.raises(ValueError, match="Unknown profile"):
            registry.apply_profile("nonexistent_profile")

    def test_list_with_explicit_profile(self, registry):
        tools = registry.list_tools(profile="export_only")
        names = {t.name for t in tools}
        assert "read_file" in names
        assert "web_search" not in names

    def test_research_includes_web(self, registry):
        registry.apply_profile("research")
        assert registry.get("web_search") is not None


class TestApiSchema:
    def test_to_api_schema_format(self):
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(
                name="my_tool",
                description="Does stuff",
                input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
        )
        schema = reg.to_api_schema()
        assert len(schema) == 1
        assert schema[0]["name"] == "my_tool"
        assert schema[0]["description"] == "Does stuff"
        assert "properties" in schema[0]["input_schema"]

    def test_schema_respects_profile(self):
        reg = ToolRegistry()
        reg.register(_make_tool("read_file", "read"))
        reg.register(_make_tool("web_search", "dangerous"))
        reg.apply_profile("invent")
        schema = reg.to_api_schema()
        names = {s["name"] for s in schema}
        assert "read_file" in names
        assert "web_search" not in names


class TestBuiltinProfiles:
    def test_all_profiles_exist(self):
        expected = {"invent", "research", "code_readonly", "code_write", "export_only"}
        assert expected == set(BUILTIN_PROFILES.keys())

    def test_code_write_superset(self):
        """code_write should include all tools from invent."""
        assert BUILTIN_PROFILES["invent"] <= BUILTIN_PROFILES["code_write"]
