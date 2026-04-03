"""Tool registry: definitions, profiles, and API schema generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDefinition:
    """Metadata and handler for a single tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    category: str = "safe"  # read | write | dangerous | safe
    handler: Callable[..., Any] | Any | None = None


@dataclass
class ToolProfile:
    """Named subset of tools available for a particular workflow."""

    name: str
    allowed_tools: set[str] = field(default_factory=set)


# Built-in profiles mapping profile name -> set of allowed tool names.
BUILTIN_PROFILES: dict[str, set[str]] = {
    "invent": {
        "read_file",
        "list_directory",
        "search_files",
        "grep_search",
        "calculator",
        "calculate",
        "list_inventions",
        "compare_inventions",
    },
    "research": {
        "read_file",
        "list_directory",
        "search_files",
        "grep_search",
        "calculator",
        "calculate",
        "list_inventions",
        "compare_inventions",
        "web_search",
        "web_fetch",
    },
    "code_readonly": {
        "read_file",
        "list_directory",
        "search_files",
        "grep_search",
        "calculator",
        "calculate",
        "list_inventions",
        "compare_inventions",
    },
    "code_write": {
        "read_file",
        "list_directory",
        "search_files",
        "grep_search",
        "calculator",
        "calculate",
        "list_inventions",
        "compare_inventions",
        "write_file",
        "write_notes",
        "save_note",
        "export_invention",
        "export",
        "web_search",
        "web_fetch",
        "execute_command",
        "shell",
    },
    "export_only": {
        "read_file",
        "list_directory",
        "list_inventions",
        "compare_inventions",
        "export_invention",
        "export",
    },
}


class ToolRegistry:
    """Central registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._active_profile: str | None = None

    def register(self, tool: ToolDefinition) -> None:
        """Add a tool to the registry. The handler is automatically wrapped in the ToolInvocation ABI if it isn't already."""
        from hephaestus.tools.invocation import ToolInvocation
        if tool.handler is not None and not isinstance(tool.handler, ToolInvocation):
            tool.handler = ToolInvocation(name=tool.name, handler=tool.handler)
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Look up a tool by name, respecting the active profile filter."""
        tool = self._tools.get(name)
        if tool is None:
            return None
        if self._active_profile is not None:
            allowed = BUILTIN_PROFILES.get(self._active_profile, set())
            if tool.name not in allowed:
                return None
        return tool

    def list_tools(self, profile: str | None = None) -> list[ToolDefinition]:
        """Return tools, optionally filtered by *profile*."""
        pname = profile or self._active_profile
        if pname is not None:
            allowed = BUILTIN_PROFILES.get(pname, set())
            return [t for t in self._tools.values() if t.name in allowed]
        return list(self._tools.values())

    def apply_profile(self, profile_name: str) -> None:
        """Restrict visible tools to those in the named profile."""
        if profile_name not in BUILTIN_PROFILES:
            raise ValueError(
                f"Unknown profile '{profile_name}'. "
                f"Available: {sorted(BUILTIN_PROFILES)}"
            )
        self._active_profile = profile_name

    def clear_profile(self) -> None:
        """Remove any active profile filter."""
        self._active_profile = None

    def to_api_schema(self) -> list[dict[str, Any]]:
        """Format visible tools for the model's API (Anthropic native schema)."""
        tools = self.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
