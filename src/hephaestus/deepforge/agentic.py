"""
Agentic DeepForge Harness — tool-augmented invention with deep reasoning.

The standard DeepForgeHarness treats the LLM as a text-in/text-out black box.
The AgenticHarness gives the LLM tools to explore the codebase, and enables
extended thinking so the model can reason deeply before and between tool calls.

This is Hephaestus as it should be: the god who forges, not the god who
writes memos about forging.

Usage::

    harness = AgenticHarness.for_workspace(
        adapter=claude_max_adapter,
        workspace_root=Path("/path/to/repo"),
        config=HarnessConfig(use_pressure=True),
    )
    result = await harness.forge("How do I solve X in this codebase?")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hephaestus.deepforge.adapters.base import BaseAdapter, ModelCapability
from hephaestus.deepforge.harness import (
    DeepForgeHarness,
    ForgeResult,
    ForgeTrace,
    HarnessConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions for repo exploration
# ---------------------------------------------------------------------------

_READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": (
        "Read the contents of a file in the repository. Use this to understand "
        "code structure, find patterns, and ground your reasoning in actual "
        "implementation details. You SHOULD read files proactively — don't "
        "guess at code structure when you can look."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to repo root.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Max characters to read (default 20000).",
                "default": 20000,
            },
        },
        "required": ["path"],
    },
}

_LIST_DIR_SCHEMA = {
    "name": "list_directory",
    "description": (
        "List files and subdirectories. Use this to explore repo structure "
        "and discover what exists before reading specific files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to repo root (default: root).",
                "default": ".",
            },
        },
    },
}

_GREP_SCHEMA = {
    "name": "grep_search",
    "description": (
        "Search file contents for a text pattern across the repository. "
        "Use this to find where specific functions, classes, patterns, or "
        "concepts are implemented."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text pattern to search for.",
            },
            "directory": {
                "type": "string",
                "description": "Subdirectory to search within (default: entire repo).",
                "default": ".",
            },
        },
        "required": ["query"],
    },
}

_SEARCH_FILES_SCHEMA = {
    "name": "search_files",
    "description": (
        "Find files matching a glob pattern (e.g. '*.py', 'test_*.rs'). "
        "Use this to discover files by naming convention."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match.",
            },
            "directory": {
                "type": "string",
                "description": "Directory to search in (default: repo root).",
                "default": ".",
            },
        },
        "required": ["pattern"],
    },
}

AGENTIC_TOOLS = [_READ_FILE_SCHEMA, _LIST_DIR_SCHEMA, _GREP_SCHEMA, _SEARCH_FILES_SCHEMA]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AgenticConfig:
    """Configuration specific to the agentic harness layer."""

    # Repo exploration
    workspace_root: Path | None = None

    # Reasoning
    enable_extended_thinking: bool = True
    thinking_budget_tokens: int = 16_000

    # Tool loop
    max_tool_rounds: int = 15
    tool_timeout_seconds: float = 10.0

    # Which tools to expose
    tools: list[dict[str, Any]] = field(default_factory=lambda: list(AGENTIC_TOOLS))


# ---------------------------------------------------------------------------
# Agentic system prompt supplement
# ---------------------------------------------------------------------------

_AGENTIC_SYSTEM_SUPPLEMENT = """\

--- AGENTIC MODE ACTIVE ---

You have tools to explore the repository you are working within.
USE THEM. Do not guess at code structure, imports, or implementations.
Read files. Search for patterns. Explore directories. Ground every claim
in actual code.

Before answering any question about the codebase:
1. Explore the relevant directory structure
2. Read the key files
3. Search for related patterns
4. THEN reason about the problem with full context

You are not writing a document about what you imagine the code does.
You are reading the code and reasoning about what it actually does.

Think deeply. Use extended reasoning when available. The quality of your
thinking matters more than the speed of your response.
"""


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class RepoToolExecutor:
    """Executes file-system tools against a workspace root."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string."""
        try:
            if tool_name == "read_file":
                return self._read_file(
                    tool_input["path"],
                    max_chars=tool_input.get("max_chars", 20000),
                )
            elif tool_name == "list_directory":
                return self._list_directory(tool_input.get("path", "."))
            elif tool_name == "grep_search":
                return self._grep_search(
                    tool_input["query"],
                    directory=tool_input.get("directory", "."),
                )
            elif tool_name == "search_files":
                return self._search_files(
                    tool_input["pattern"],
                    directory=tool_input.get("directory", "."),
                )
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as exc:
            return f"Tool error ({tool_name}): {exc}"

    def _read_file(self, path: str, max_chars: int = 20000) -> str:
        full = self._safe_path(path)
        if full is None:
            return f"Error: path '{path}' is outside the workspace"
        if not full.is_file():
            return f"Error: file not found: {path}"
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                return content[:max_chars] + f"\n\n... [truncated at {max_chars} chars, {len(content)} total]"
            return content
        except OSError as exc:
            return f"Error reading {path}: {exc}"

    def _list_directory(self, path: str = ".") -> str:
        full = self._safe_path(path)
        if full is None:
            return f"Error: path '{path}' is outside the workspace"
        if not full.is_dir():
            return f"Error: not a directory: {path}"

        entries = []
        try:
            for item in sorted(full.iterdir()):
                if item.name.startswith(".") and item.name in {
                    ".git", "__pycache__", ".venv", "node_modules",
                }:
                    continue
                rel = item.relative_to(self._root)
                suffix = "/" if item.is_dir() else ""
                entries.append(f"{rel}{suffix}")
        except OSError as exc:
            return f"Error listing {path}: {exc}"

        if not entries:
            return f"(empty directory: {path})"
        return "\n".join(entries[:200])

    def _grep_search(self, query: str, directory: str = ".") -> str:
        full = self._safe_path(directory)
        if full is None:
            return f"Error: path '{directory}' is outside the workspace"

        results = []
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".hg"}
        binary_exts = {".pyc", ".so", ".dll", ".png", ".jpg", ".zip", ".gz", ".db"}

        for file_path in self._walk_files(full, skip_dirs, binary_exts, max_files=5000):
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if query.lower() in line.lower():
                        rel = file_path.relative_to(self._root)
                        results.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n... [truncated at 50 matches]"
            except OSError:
                continue

        if not results:
            return f"No matches found for '{query}' in {directory}"
        return "\n".join(results)

    def _search_files(self, pattern: str, directory: str = ".") -> str:
        full = self._safe_path(directory)
        if full is None:
            return f"Error: path '{directory}' is outside the workspace"

        matches = []
        try:
            for match in sorted(full.rglob(pattern)):
                if any(part.startswith(".") or part in {"__pycache__", "node_modules"}
                       for part in match.parts):
                    continue
                rel = match.relative_to(self._root)
                matches.append(str(rel))
                if len(matches) >= 100:
                    break
        except OSError:
            pass

        if not matches:
            return f"No files matching '{pattern}' in {directory}"
        return "\n".join(matches)

    def _safe_path(self, path: str) -> Path | None:
        """Resolve path and verify it's within workspace."""
        if Path(path).is_absolute():
            resolved = Path(path).resolve()
        else:
            resolved = (self._root / path).resolve()
        try:
            resolved.relative_to(self._root)
            return resolved
        except ValueError:
            return None

    @staticmethod
    def _walk_files(
        root: Path,
        skip_dirs: set[str],
        binary_exts: set[str],
        max_files: int = 5000,
    ) -> list[Path]:
        """Walk directory tree, skipping junk, returning code files."""
        files = []
        for item in root.rglob("*"):
            if any(part in skip_dirs for part in item.parts):
                continue
            if item.is_file() and item.suffix not in binary_exts:
                files.append(item)
                if len(files) >= max_files:
                    break
        return files


# ---------------------------------------------------------------------------
# Agentic Harness
# ---------------------------------------------------------------------------

class AgenticHarness:
    """Tool-augmented DeepForge harness with deep reasoning.

    Wraps the standard DeepForgeHarness but adds:
    - Tool use (read_file, grep_search, list_directory, search_files)
    - Extended thinking (when the model supports it)
    - A tool execution loop that lets the model explore before answering

    The forge() method is a drop-in replacement for DeepForgeHarness.forge().
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        harness_config: HarnessConfig | None = None,
        agentic_config: AgenticConfig | None = None,
    ) -> None:
        self._adapter = adapter
        self._harness_config = harness_config or HarnessConfig()
        self._agentic_config = agentic_config or AgenticConfig()

        # Tool executor
        self._executor: RepoToolExecutor | None = None
        if self._agentic_config.workspace_root is not None:
            self._executor = RepoToolExecutor(self._agentic_config.workspace_root)

        # Underlying standard harness (for pressure/pruner/interference)
        self._standard_harness = DeepForgeHarness(adapter, harness_config)

        logger.info(
            "AgenticHarness initialized | model=%s workspace=%s tools=%d thinking=%s",
            adapter.model_name,
            self._agentic_config.workspace_root or "(none)",
            len(self._agentic_config.tools) if self._executor else 0,
            self._agentic_config.enable_extended_thinking,
        )

    @classmethod
    def for_workspace(
        cls,
        adapter: BaseAdapter,
        workspace_root: Path,
        config: HarnessConfig | None = None,
        *,
        enable_thinking: bool = True,
        thinking_budget: int = 16_000,
        max_tool_rounds: int = 15,
    ) -> AgenticHarness:
        """Convenience constructor for workspace-bound agentic mode."""
        return cls(
            adapter=adapter,
            harness_config=config,
            agentic_config=AgenticConfig(
                workspace_root=workspace_root,
                enable_extended_thinking=enable_thinking,
                thinking_budget_tokens=thinking_budget,
                max_tool_rounds=max_tool_rounds,
            ),
        )

    async def forge(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> ForgeResult:
        """Run the agentic forge pipeline.

        If we have a workspace and tools, runs a tool loop first so the
        model can explore the codebase. Then feeds the exploration context
        into the standard DeepForge pipeline for interference/pressure/pruning.

        If no workspace is set, falls through to the standard harness.
        """
        if self._executor is None:
            # No workspace — fall back to standard harness
            return await self._standard_harness.forge(
                prompt, system=system, max_tokens=max_tokens,
                temperature=temperature, extra_context=extra_context,
            )

        t_start = time.monotonic()
        cfg = self._agentic_config
        h_cfg = self._harness_config

        effective_system = system or h_cfg.system_prompt or ""
        effective_system = effective_system + _AGENTIC_SYSTEM_SUPPLEMENT
        effective_max_tokens = max_tokens or h_cfg.max_tokens
        effective_temp = temperature if temperature is not None else h_cfg.temperature

        # ── Phase 1: Agentic exploration (tool loop) ──────────────────
        exploration_output, exploration_trace = await self._exploration_loop(
            prompt=prompt,
            system=effective_system,
            max_tokens=effective_max_tokens,
            temperature=effective_temp,
        )

        logger.info(
            "Agentic exploration complete | rounds=%d tool_calls=%d chars=%d (%.1fs)",
            exploration_trace["rounds"],
            exploration_trace["tool_calls"],
            len(exploration_output),
            time.monotonic() - t_start,
        )

        # ── Phase 2: Feed exploration into standard harness ───────────
        # The exploration output becomes additional context for the
        # interference/pressure/pruner pipeline
        enriched_prompt = (
            f"{prompt}\n\n"
            f"--- CODEBASE EXPLORATION (from agentic analysis) ---\n"
            f"{exploration_output}\n"
            f"--- END EXPLORATION ---\n\n"
            f"Now produce your final invention, grounded in the actual "
            f"codebase you just explored. Reference specific files, "
            f"functions, and patterns."
        )

        result = await self._standard_harness.forge(
            enriched_prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            extra_context={
                **(extra_context or {}),
                "agentic_exploration": {
                    "rounds": exploration_trace["rounds"],
                    "tool_calls": exploration_trace["tool_calls"],
                    "exploration_chars": len(exploration_output),
                    "exploration_seconds": time.monotonic() - t_start,
                },
            },
        )

        # Update trace timing
        result.trace.wall_time_seconds = time.monotonic() - t_start
        result.trace.total_input_tokens += exploration_trace["input_tokens"]
        result.trace.total_output_tokens += exploration_trace["output_tokens"]
        result.trace.mechanisms_used.insert(0, "agentic_exploration")

        return result

    async def _exploration_loop(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, dict[str, Any]]:
        """Run the tool-augmented exploration loop.

        The model gets the problem + tools and explores the codebase.
        Returns the model's exploration output and trace metadata.
        """
        cfg = self._agentic_config
        assert self._executor is not None

        # Build API-format tools
        tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in cfg.tools
        ]

        # Build the initial messages
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        # Build kwargs for extended thinking if supported
        extra_kwargs: dict[str, Any] = {}
        if (
            cfg.enable_extended_thinking
            and self._adapter.config.supports(ModelCapability.EXTENDED_THINKING)
        ):
            extra_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": cfg.thinking_budget_tokens,
            }
            logger.info(
                "Extended thinking enabled | budget=%d tokens",
                cfg.thinking_budget_tokens,
            )

        trace: dict[str, Any] = {
            "rounds": 0,
            "tool_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

        final_text = ""

        for round_idx in range(cfg.max_tool_rounds):
            trace["rounds"] = round_idx + 1

            # Call the model with tools
            gen = await self._adapter.generate_with_tools(
                messages,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                **extra_kwargs,
            )

            trace["input_tokens"] += gen.input_tokens
            trace["output_tokens"] += gen.output_tokens

            # If no tool calls, we're done — model has finished exploring
            if not gen.tool_calls:
                final_text = gen.text
                logger.info(
                    "Exploration finished (no more tool calls) | round=%d",
                    round_idx + 1,
                )
                break

            # Append assistant message with content blocks
            messages.append({"role": "assistant", "content": gen.content_blocks})

            # Execute tool calls
            tool_results: list[dict[str, Any]] = []
            for tc in gen.tool_calls:
                trace["tool_calls"] += 1
                result_text = self._executor.execute(tc.name, tc.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_text[:10000],  # Cap individual tool output
                })
                logger.debug(
                    "Tool: %s(%s) → %d chars",
                    tc.name,
                    ", ".join(f"{k}={v!r}" for k, v in tc.input.items()),
                    len(result_text),
                )

            # Feed results back
            messages.append({"role": "user", "content": tool_results})

            # Capture any text from this round as partial output
            if gen.text:
                final_text = gen.text

        else:
            logger.warning(
                "Exploration hit max rounds (%d) — model may not be done",
                cfg.max_tool_rounds,
            )

        return final_text, trace

    # ------------------------------------------------------------------
    # Expose standard harness properties for compatibility
    # ------------------------------------------------------------------

    @property
    def adapter(self) -> BaseAdapter:
        return self._adapter

    @property
    def config(self) -> HarnessConfig:
        return self._harness_config

    @property
    def agentic_config(self) -> AgenticConfig:
        return self._agentic_config


__all__ = [
    "AgenticConfig",
    "AgenticHarness",
    "AGENTIC_TOOLS",
    "RepoToolExecutor",
]
