"""Tests for ForgeBase tool definitions."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.tools.definitions import (
    build_forgebase_tools,
    register_forgebase_tools,
)
from hephaestus.tools.registry import ToolDefinition, ToolRegistry


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC))


@pytest.mark.asyncio
async def test_build_forgebase_tools_returns_definitions(id_gen, clock):
    """build_forgebase_tools returns a list of ToolDefinition objects."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    tools = build_forgebase_tools(fb)
    assert isinstance(tools, list)
    assert len(tools) >= 6

    for tool in tools:
        assert isinstance(tool, ToolDefinition)
        assert tool.name
        assert tool.description
        assert tool.input_schema

    await fb.close()


@pytest.mark.asyncio
async def test_expected_tool_names(id_gen, clock):
    """All expected ForgeBase tools are present."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    tools = build_forgebase_tools(fb)
    names = {t.name for t in tools}

    expected = {
        "vault_create",
        "vault_ingest",
        "vault_compile",
        "vault_lint",
        "vault_fuse",
        "vault_team",
    }
    assert expected.issubset(names)

    await fb.close()


@pytest.mark.asyncio
async def test_register_forgebase_tools(id_gen, clock):
    """register_forgebase_tools adds tools to a ToolRegistry."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    registry = ToolRegistry()

    register_forgebase_tools(registry, fb)

    # All tools should be in the registry
    registered = registry.list_tools()
    assert len(registered) >= 6

    # Each tool should be retrievable by name
    assert registry.get("vault_create") is not None
    assert registry.get("vault_ingest") is not None
    assert registry.get("vault_compile") is not None
    assert registry.get("vault_lint") is not None
    assert registry.get("vault_fuse") is not None
    assert registry.get("vault_team") is not None

    await fb.close()


@pytest.mark.asyncio
async def test_tool_api_schema_generation(id_gen, clock):
    """Tools generate valid API schema for the model."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)
    registry = ToolRegistry()

    register_forgebase_tools(registry, fb)

    schema = registry.to_api_schema()
    assert isinstance(schema, list)
    assert len(schema) >= 6

    for entry in schema:
        assert "name" in entry
        assert "description" in entry
        assert "input_schema" in entry
        assert entry["input_schema"]["type"] == "object"

    await fb.close()


@pytest.mark.asyncio
async def test_tool_categories(id_gen, clock):
    """Tools have appropriate categories set."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    tools = build_forgebase_tools(fb)
    by_name = {t.name: t for t in tools}

    # vault_lint is read-only
    assert by_name["vault_lint"].category == "read"

    # vault_create, vault_ingest are write
    assert by_name["vault_create"].category == "write"
    assert by_name["vault_ingest"].category == "write"

    await fb.close()


@pytest.mark.asyncio
async def test_vault_create_tool_has_required_fields(id_gen, clock):
    """vault_create tool requires 'name' parameter."""
    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    tools = build_forgebase_tools(fb)
    create_tool = next(t for t in tools if t.name == "vault_create")

    assert "name" in create_tool.input_schema.get("required", [])

    await fb.close()
