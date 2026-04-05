"""Workspace mode — the agentic coding mode for Hephaestus.

Combines invention capabilities with codebase understanding.
The model can read, understand, and modify files in a workspace
while applying cross-domain structural insights.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hephaestus.agent.runtime import ConversationRuntime
from hephaestus.session.schema import Session, SessionMeta
from hephaestus.tools.permissions import PermissionMode, PermissionPolicy
from hephaestus.tools.registry import ToolDefinition, ToolRegistry
from hephaestus.workspace.context import WorkspaceContext

logger = logging.getLogger(__name__)

_WORKSPACE_SYSTEM_PROMPT = """\
You are Hephaestus, an invention engine that also works directly on codebases.

You have access to a workspace at: {root}

{workspace_context}

You can:
- READ files to understand the codebase
- SEARCH for patterns across files
- WRITE and EDIT files to implement changes
- LIST directories to explore structure
- Use your cross-domain invention capabilities to propose novel architectural solutions

When working on the codebase:
1. First understand the existing structure before making changes
2. Explain what you're going to do before doing it
3. Make minimal, focused changes
4. Preserve existing code style and conventions
5. Consider edge cases and error handling

You can also invent — if asked to solve a hard problem, use structural transfer
from distant domains to propose novel solutions, then implement them directly.
"""


@dataclass
class WorkspaceConfig:
    """Configuration for workspace mode."""

    root: Path
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE
    context_budget: int = 24_000
    auto_scan: bool = True


class WorkspaceMode:
    """Agentic workspace mode — read, understand, and modify codebases.

    Usage::

        mode = WorkspaceMode.create(
            root=Path("/path/to/repo"),
            adapter=my_adapter,
        )
        response = await mode.chat("What does this codebase do?")
        response = await mode.chat("Add error handling to the API routes")
    """

    def __init__(
        self,
        runtime: ConversationRuntime,
        workspace_context: WorkspaceContext,
        config: WorkspaceConfig,
    ) -> None:
        self.runtime = runtime
        self.context = workspace_context
        self.config = config
        self._initialized = False

    @classmethod
    def create(
        cls,
        root: Path | str,
        adapter: Any,
        *,
        permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        context_budget: int = 24_000,
    ) -> WorkspaceMode:
        """Create a workspace mode for a directory.

        Parameters
        ----------
        root:
            Path to the codebase root.
        adapter:
            LLM adapter (must support generate_with_tools).
        permission_mode:
            File access permissions.
        context_budget:
            Max chars for workspace context in prompts.
        """
        root = Path(root).resolve()
        config = WorkspaceConfig(
            root=root,
            permission_mode=permission_mode,
            context_budget=context_budget,
        )

        # Build context
        ws_context = WorkspaceContext.from_directory(root, budget_chars=context_budget)

        # Build tool registry with workspace-aware tools
        registry = _build_workspace_registry(root)

        # Build permission policy
        policy = PermissionPolicy(permission_mode, workspace_root=root, registry=registry)

        # Build session
        session = Session(
            meta=SessionMeta(
                name=f"workspace:{root.name}",
                model=getattr(adapter, "model", "unknown"),
            )
        )
        session.bind_reference_lot(
            kind="workspace",
            subject_key=root.name,
            op_id=0,
            exact={"root": str(root)},
            dependents=[0],
        )

        # Build system prompt
        system_prompt = _WORKSPACE_SYSTEM_PROMPT.format(
            root=root,
            workspace_context=ws_context.to_prompt_text(),
        )

        # Build runtime
        runtime = ConversationRuntime(
            adapter=adapter,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            system_prompt=system_prompt,
        )

        return cls(runtime=runtime, workspace_context=ws_context, config=config)

    async def chat(self, message: str) -> str:
        """Send a message and get a response, with tool execution."""
        return await self.runtime.run_turn(message)

    def get_summary(self) -> str:
        """Get the workspace summary."""
        return self.context.summary.format_summary()

    def get_tree(self) -> str:
        """Get the directory tree."""
        return self.context.summary.tree

    def rescan(self) -> None:
        """Re-scan the workspace (after external changes)."""
        self.context = WorkspaceContext.from_directory(
            self.config.root,
            budget_chars=self.config.context_budget,
        )


def _build_workspace_registry(root: Path) -> ToolRegistry:
    """Build a tool registry with workspace-aware file operations."""
    from hephaestus.tools.file_ops import (
        grep_search,
        list_directory,
        read_file,
        search_files,
        write_file,
    )

    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read the contents of a file in the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (relative to workspace root or absolute).",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Max characters to read.",
                        "default": 20000,
                    },
                },
                "required": ["path"],
            },
            category="read",
            handler=lambda path, max_chars=20000: read_file(
                str(root / path) if not Path(path).is_absolute() else path,
                max_chars=max_chars,
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write content to a file in the workspace. Creates parent directories if needed.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (relative to workspace root).",
                    },
                    "content": {"type": "string", "description": "Content to write."},
                },
                "required": ["path", "content"],
            },
            category="write",
            handler=lambda path, content: write_file(
                str(root / path) if not Path(path).is_absolute() else path,
                content,
                workspace_root=str(root),
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="edit_file",
            description="Replace a specific text pattern in a file. Use for precise edits.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace.",
                    },
                    "new_text": {"type": "string", "description": "Replacement text."},
                },
                "required": ["path", "old_text", "new_text"],
            },
            category="write",
            handler=lambda path, old_text, new_text: _edit_file(root, path, old_text, new_text),
        )
    )

    registry.register(
        ToolDefinition(
            name="list_directory",
            description="List files and subdirectories in a directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path.", "default": "."},
                    "max_entries": {"type": "integer", "default": 100},
                },
            },
            category="read",
            handler=lambda path=".", max_entries=100: list_directory(
                str(root / path) if not Path(path).is_absolute() else path,
                max_entries=max_entries,
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="search_files",
            description="Find files matching a glob pattern in the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '*.py', 'test_*.js').",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search.",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
            category="read",
            handler=lambda pattern, directory=".": search_files(
                pattern,
                str(root / directory) if not Path(directory).is_absolute() else directory,
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="grep_search",
            description="Search file contents for a text pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for."},
                    "directory": {
                        "type": "string",
                        "description": "Directory to search.",
                        "default": ".",
                    },
                },
                "required": ["query"],
            },
            category="read",
            handler=lambda query, directory=".": grep_search(
                query,
                str(root / directory) if not Path(directory).is_absolute() else directory,
            ),
        )
    )

    return registry


def _edit_file(root: Path, path: str, old_text: str, new_text: str) -> str:
    """Replace old_text with new_text in a file."""
    full = root / path if not Path(path).is_absolute() else Path(path)
    full = full.resolve()

    # Validate within workspace
    try:
        full.relative_to(root)
    except ValueError:
        return f"Error: path {full} is outside workspace root {root}"

    if not full.is_file():
        return f"Error: file not found: {full}"

    try:
        content = full.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading {full}: {exc}"

    if old_text not in content:
        return f"Error: old_text not found in {path}. Make sure it matches exactly."

    count = content.count(old_text)
    if count > 1:
        return f"Error: old_text appears {count} times in {path}. Make it more specific."

    new_content = content.replace(old_text, new_text, 1)

    try:
        full.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return f"Error writing {full}: {exc}"

    return f"Edited {path}: replaced {len(old_text)} chars with {len(new_text)} chars"


__all__ = ["WorkspaceConfig", "WorkspaceMode"]
