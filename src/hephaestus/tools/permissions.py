"""Permission system for tool execution."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class PermissionMode(str, Enum):
    """Access level for tool execution."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    FULL_ACCESS = "full_access"


def _tool_category(tool_name: str, registry: Any = None) -> str:
    """Return the category string for a tool name by querying the registry if available."""
    if registry:
        tool_def = registry.get(tool_name)
        if tool_def:
            return tool_def.category
    # Default-deny if no registry or tool not found
    return "unknown"


class PermissionPolicy:
    """Decides whether a tool action is allowed under the current mode."""

    def __init__(
        self,
        mode: PermissionMode,
        workspace_root: Path | None = None,
        registry: Any = None,
    ) -> None:
        self.mode = mode
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.registry = registry

    def check(self, tool_name: str, action: str = "") -> bool:
        """Return whether *tool_name* (with optional *action*) is allowed."""
        cat = _tool_category(tool_name, self.registry)

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
        if cat == "unknown":
            return False
        return False  # pragma: no cover

    def explain_denial(self, tool_name: str) -> str:
        """Return a human-readable reason the tool is denied."""
        cat = _tool_category(tool_name, self.registry)
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
        if cat == "unknown":
            return f"Tool '{tool_name}' is not registered and is explicitly denied."
        return f"Tool '{tool_name}' is not allowed under current policy."
