"""Permission system for tool execution."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class PermissionMode(str, Enum):
    """Access level for tool execution."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    FULL_ACCESS = "full_access"


# Tool categories by permission level required.
READ_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "search_files",
    "grep_search",
    "list_inventions",
    "compare_inventions",
    "calculator",
    "calculate",
})

WRITE_TOOLS = frozenset({
    "write_file",
    "write_notes",
    "save_note",
    "export_invention",
    "export",
})

DANGEROUS_TOOLS = frozenset({
    "web_search",
    "web_fetch",
    "execute_command",
    "shell",
})

# "safe" tools are always allowed regardless of mode.
SAFE_TOOLS = frozenset({
    "calculator",
    "calculate",
    "list_inventions",
    "compare_inventions",
})


def _tool_category(tool_name: str) -> str:
    """Return the category string for a tool name."""
    if tool_name in READ_TOOLS:
        return "read"
    if tool_name in WRITE_TOOLS:
        return "write"
    if tool_name in DANGEROUS_TOOLS:
        return "dangerous"
    return "safe"


class PermissionPolicy:
    """Decides whether a tool action is allowed under the current mode."""

    def __init__(
        self,
        mode: PermissionMode,
        workspace_root: Path | None = None,
    ) -> None:
        self.mode = mode
        self.workspace_root = workspace_root.resolve() if workspace_root else None

    def check(self, tool_name: str, action: str = "") -> bool:
        """Return whether *tool_name* (with optional *action*) is allowed."""
        cat = _tool_category(tool_name)

        if cat == "safe":
            return True
        if cat == "read":
            return True  # read tools always allowed
        if cat == "write":
            return self.mode in (
                PermissionMode.WORKSPACE_WRITE,
                PermissionMode.FULL_ACCESS,
            )
        if cat == "dangerous":
            return self.mode == PermissionMode.FULL_ACCESS
        return False  # pragma: no cover

    def explain_denial(self, tool_name: str) -> str:
        """Return a human-readable reason the tool is denied."""
        cat = _tool_category(tool_name)
        if cat == "write":
            return (
                f"Tool '{tool_name}' requires at least WORKSPACE_WRITE mode. "
                f"Current mode: {self.mode.value}."
            )
        if cat == "dangerous":
            return (
                f"Tool '{tool_name}' requires FULL_ACCESS mode. "
                f"Current mode: {self.mode.value}."
            )
        return f"Tool '{tool_name}' is not allowed under current policy."
