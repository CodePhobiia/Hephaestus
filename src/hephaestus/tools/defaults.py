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
from hephaestus.tools.invocation import ToolContext
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
    "abs",
    "round",
    "min",
    "max",
    "sum",
    "int",
    "float",
    "pow",
    "True",
    "False",
}


_MAX_EXPR_LEN = 500
_MAX_AST_DEPTH = 10

_AST_ALLOWED_CALLS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "int": int,
    "float": float,
    "pow": pow,
    "sqrt": math.sqrt,
}


def _ast_eval_node(node: Any, depth: int = 0) -> Any:
    """Recursively evaluate an AST node — only safe arithmetic."""
    import ast

    if depth > _MAX_AST_DEPTH:
        raise ValueError("Expression too deeply nested")

    # Numeric literal
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    # Boolean literal (True/False are valid in arithmetic context)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value

    # Unary operators: +x, -x
    if isinstance(node, ast.UnaryOp):
        operand = _ast_eval_node(node.operand, depth + 1)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    # Binary operators: +, -, *, /, //, %, **
    if isinstance(node, ast.BinOp):
        left = _ast_eval_node(node.left, depth + 1)
        right = _ast_eval_node(node.right, depth + 1)
        op_map = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        op_func = op_map.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        # Guard against absurd exponents
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Exponent too large")
        return op_func(left, right)

    # Whitelisted function calls: abs(x), sqrt(x), min(a, b), etc.
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed (no methods or attributes)")
        func_name = node.func.id
        if func_name not in _AST_ALLOWED_CALLS:
            raise ValueError(f"Function not allowed: {func_name}")
        args = [_ast_eval_node(arg, depth + 1) for arg in node.args]
        if node.keywords:
            raise ValueError("Keyword arguments not allowed in calculator")
        return _AST_ALLOWED_CALLS[func_name](*args)

    # Name lookup — only True/False
    if isinstance(node, ast.Name):
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        raise ValueError(f"Name not allowed: {node.id}")

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def _safe_eval(expression: str) -> str:
    """Evaluate a simple arithmetic expression using AST parsing — no eval()."""
    import ast

    if len(expression) > _MAX_EXPR_LEN:
        return (
            f"Calculation error: expression too long ({len(expression)} chars, max {_MAX_EXPR_LEN})"
        )
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _ast_eval_node(tree.body)
    except Exception as exc:
        return f"Calculation error: {exc}"
    return str(result)


# ── handler wrappers ────────────────────────────────────────────────


def _handle_read_file(context: ToolContext, **kwargs: Any) -> str:
    return read_file(
        path=kwargs["path"],
        max_chars=kwargs.get("max_chars", 20_000),
    )


def _handle_write_file(context: ToolContext, **kwargs: Any) -> str:
    return write_file(
        path=kwargs["path"],
        content=kwargs["content"],
    )


def _handle_list_directory(context: ToolContext, **kwargs: Any) -> str:
    return list_directory(
        path=kwargs["path"],
        max_entries=kwargs.get("max_entries", 100),
    )


def _handle_search_files(context: ToolContext, **kwargs: Any) -> str:
    return search_files(
        pattern=kwargs["pattern"],
        directory=kwargs["directory"],
        max_results=kwargs.get("max_results", 50),
    )


def _handle_grep_search(context: ToolContext, **kwargs: Any) -> str:
    return grep_search(
        query=kwargs["query"],
        directory=kwargs["directory"],
        max_results=kwargs.get("max_results", 50),
    )


def _handle_web_search(context: ToolContext, **kwargs: Any) -> str:
    return asyncio.run(
        web_search(
            query=kwargs["query"],
            max_results=kwargs.get("max_results", 5),
        )
    )


def _handle_web_fetch(context: ToolContext, **kwargs: Any) -> str:
    return asyncio.run(
        web_fetch(
            url=kwargs["url"],
            max_chars=kwargs.get("max_chars", 15_000),
        )
    )


def _handle_calculator(context: ToolContext, **kwargs: Any) -> str:
    return _safe_eval(kwargs["expression"])


def _handle_todo_add(context: ToolContext, **kwargs: Any) -> str:
    item = _session_todos.add(
        title=kwargs["title"],
        notes=kwargs.get("notes", ""),
    )
    return f"Added todo {item.id}: {item.title}"


def _handle_todo_list(context: ToolContext, **kwargs: Any) -> str:
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
        category="dangerous",
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
        category="dangerous",
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
