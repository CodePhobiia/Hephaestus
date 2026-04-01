"""Default tool registry factory — pre-registers all built-in tools."""

from __future__ import annotations

import asyncio
import math
import operator
from typing import Any

from hephaestus.session.todos import TodoList
from hephaestus.tools.file_ops import (
    grep_search,
    list_directory,
    read_file,
    search_files,
    write_file,
)
from hephaestus.tools.registry import ToolDefinition, ToolRegistry
from hephaestus.tools.web_tools import web_fetch, web_search

# ── shared todo list for the session ────────────────────────────────

_session_todos = TodoList()

# ── calculator helpers ──────────────────────────────────────────────

_CALC_OPS: dict[str, Any] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
}

_CALC_ALLOWED_NAMES: set[str] = {
    "abs", "round", "min", "max", "sum",
    "int", "float", "pow",
    "True", "False",
}


def _safe_eval(expression: str) -> str:
    """Evaluate a simple arithmetic expression safely."""
    # Only allow digits, operators, parens, dots, whitespace, and a few builtins
    allowed_builtins = {k: __builtins__[k] for k in _CALC_ALLOWED_NAMES  # type: ignore[index]
                        if k in (__builtins__ if isinstance(__builtins__, dict) else vars(__builtins__))}
    allowed_builtins["math"] = math
    try:
        result = eval(expression, {"__builtins__": allowed_builtins}, {})  # noqa: S307
    except Exception as exc:
        return f"Calculation error: {exc}"
    return str(result)


# ── handler wrappers ────────────────────────────────────────────────


def _handle_read_file(params: dict[str, Any]) -> str:
    return read_file(
        path=params["path"],
        max_chars=params.get("max_chars", 20_000),
    )


def _handle_write_file(params: dict[str, Any]) -> str:
    return write_file(
        path=params["path"],
        content=params["content"],
    )


def _handle_list_directory(params: dict[str, Any]) -> str:
    return list_directory(
        path=params["path"],
        max_entries=params.get("max_entries", 100),
    )


def _handle_search_files(params: dict[str, Any]) -> str:
    return search_files(
        pattern=params["pattern"],
        directory=params["directory"],
        max_results=params.get("max_results", 50),
    )


def _handle_grep_search(params: dict[str, Any]) -> str:
    return grep_search(
        query=params["query"],
        directory=params["directory"],
        max_results=params.get("max_results", 50),
    )


def _handle_web_search(params: dict[str, Any]) -> str:
    return asyncio.run(web_search(
        query=params["query"],
        max_results=params.get("max_results", 5),
    ))


def _handle_web_fetch(params: dict[str, Any]) -> str:
    return asyncio.run(web_fetch(
        url=params["url"],
        max_chars=params.get("max_chars", 15_000),
    ))


def _handle_calculator(params: dict[str, Any]) -> str:
    return _safe_eval(params["expression"])


def _handle_todo_add(params: dict[str, Any]) -> str:
    item = _session_todos.add(
        title=params["title"],
        notes=params.get("notes", ""),
    )
    return f"Added todo {item.id}: {item.title}"


def _handle_todo_list(params: dict[str, Any]) -> str:
    return _session_todos.summary()


# ── tool definitions ────────────────────────────────────────────────

_TOOL_DEFS: list[ToolDefinition] = [
    ToolDefinition(
        name="read_file",
        description="Read a file and return its contents.",
        category="read",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 20000).",
                    "default": 20000,
                },
            },
            "required": ["path"],
        },
        handler=_handle_read_file,
    ),
    ToolDefinition(
        name="write_file",
        description="Write content to a file, creating directories as needed.",
        category="write",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to write to.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
        handler=_handle_write_file,
    ),
    ToolDefinition(
        name="list_directory",
        description="List entries in a directory.",
        category="read",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory to list.",
                },
                "max_entries": {
                    "type": "integer",
                    "description": "Maximum entries to return (default 100).",
                    "default": 100,
                },
            },
            "required": ["path"],
        },
        handler=_handle_list_directory,
    ),
    ToolDefinition(
        name="search_files",
        description="Find files matching a glob-like pattern under a directory.",
        category="read",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match file names against.",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory to search in.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 50).",
                    "default": 50,
                },
            },
            "required": ["pattern", "directory"],
        },
        handler=_handle_search_files,
    ),
    ToolDefinition(
        name="grep_search",
        description="Search file contents for a text query under a directory.",
        category="read",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for (case-insensitive).",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory to search in.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 50).",
                    "default": 50,
                },
            },
            "required": ["query", "directory"],
        },
        handler=_handle_grep_search,
    ),
    ToolDefinition(
        name="web_search",
        description="Search the web and return formatted results.",
        category="safe",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
        handler=_handle_web_search,
    ),
    ToolDefinition(
        name="web_fetch",
        description="Fetch a URL and return extracted text content.",
        category="safe",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 15000).",
                    "default": 15000,
                },
            },
            "required": ["url"],
        },
        handler=_handle_web_fetch,
    ),
    ToolDefinition(
        name="calculator",
        description="Evaluate a simple arithmetic expression.",
        category="safe",
        input_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate (e.g. '2 + 3 * 4').",
                },
            },
            "required": ["expression"],
        },
        handler=_handle_calculator,
    ),
    ToolDefinition(
        name="todo_add",
        description="Add an item to the session todo list.",
        category="safe",
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short description of the task.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional extra notes.",
                    "default": "",
                },
            },
            "required": ["title"],
        },
        handler=_handle_todo_add,
    ),
    ToolDefinition(
        name="todo_list",
        description="Show all items on the session todo list.",
        category="safe",
        input_schema={
            "type": "object",
            "properties": {},
        },
        handler=_handle_todo_list,
    ),
]

# ── public API ──────────────────────────────────────────────────────

EXPECTED_TOOLS: set[str] = {t.name for t in _TOOL_DEFS}


def create_default_registry() -> ToolRegistry:
    """Return a :class:`ToolRegistry` pre-loaded with all built-in tools."""
    registry = ToolRegistry()
    for tool in _TOOL_DEFS:
        registry.register(tool)
    return registry
