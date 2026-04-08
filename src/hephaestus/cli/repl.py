"""
Hephaestus Interactive REPL — Phases 1-4.

Provides a persistent invention session where users describe problems,
refine inventions, explore alternatives, and iterate — all within a
single running session that maintains context.

Phase 1 (Core REPL):
  - REPL loop with Rich console
  - Problem input -> pipeline -> result display
  - /help, /status, /quit, /model, /usage, /cost, /clear, /history
  - Numbered menu after invention
  - Backend auto-detection from config

Phase 2 (Refinement & Context):
  - /refine — re-run translation with constraints
  - /domain <hint> — bias search toward specific fields
  - /deeper <n> — increase anti-training pressure
  - /context add <text> — inject domain knowledge
  - /alternatives — show alternative inventions
  - /export — export invention
  - /trace — show reasoning trace

Phase 3 (Persistence & History):
  - Auto-save inventions to disk as JSON + markdown
  - /save [name] — explicit save
  - /load <name> — load from disk
  - /history — list inventions (session + disk) with search
  - /compare — side-by-side comparison
  - Session replay from JSON

Phase 4 (Onboarding & Polish):
  - First-run onboarding wizard (in config.py)
  - Tab completion for /commands
  - /export pdf — PDF export via weasyprint
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hephaestus.cli.commands import default_registry
from hephaestus.cli.config import (
    INVENTIONS_DIR,
    SESSIONS_DIR,
    HephaestusConfig,
    ensure_dirs,
    load_config,
    run_onboarding,
)
from hephaestus.cli.display import (
    AMBER,
    DIM,
    EMBER,
    GOLD,
    GREEN,
    RED,
    WHITE_HOT,
    StageProgress,
    print_banner,
    print_cost_table,
    print_error,
    print_invention_report,
    print_success,
    print_trace,
    print_warning,
)
from hephaestus.memory.transparency import (
    build_memory_report,
    format_context_report,
    format_memory_report,
)
from hephaestus.session.compact import compact_session, should_compact
from hephaestus.session.schema import (
    EntryType,
    Role,
    Session,
    SessionMeta,
)
from hephaestus.session.todos import TodoList

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class InventionEntry:
    """One invention produced during the session."""

    problem: str
    report: Any  # InventionReport
    timestamp: float = field(default_factory=time.time)
    label: str = ""  # short slug derived from problem
    refined: bool = False

    @property
    def slug(self) -> str:
        if self.label:
            return self.label
        words = self.problem.lower().split()[:4]
        return "-".join(w for w in words if w.isalnum())[:40] or "invention"


@dataclass
class SessionState:
    """Mutable state for one interactive session."""

    config: HephaestusConfig
    inventions: list[InventionEntry] = field(default_factory=list)
    current_idx: int = -1  # index into inventions
    context_items: list[str] = field(default_factory=list)
    pinned: list[int] = field(default_factory=list)  # indices into inventions
    start_time: float = field(default_factory=time.time)

    # Cumulative token/cost tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    last_auto_save_path: Path | None = None
    last_auto_save_error: str | None = None
    last_loaded_path: Path | None = None
    exit_reported: bool = False

    # Per-stage counters  {stage_name: (calls, input_tokens, output_tokens)}
    stage_usage: dict[str, list[int]] = field(
        default_factory=lambda: {
            "Decompose": [0, 0, 0],
            "Search": [0, 0, 0],
            "Score": [0, 0, 0],
            "Translate": [0, 0, 0],
            "Verify": [0, 0, 0],
            "Refine": [0, 0, 0],
        }
    )

    # Integration fields — typed session, todo list, layered config
    session: Any = field(default=None)  # Session from session.schema
    todo_list: Any = field(default=None)  # TodoList from session.todos
    layered_config: Any = field(default=None)  # LayeredConfig instance
    workspace_root: Any = field(default=None)  # Path if workspace mode active
    workspace_context: Any = field(default=None)  # WorkspaceContext

    # ForgeBase session state
    forgebase: Any = field(default=None)  # ForgeBase instance (lazy)
    current_vault_id: Any = field(default=None)  # EntityId | None
    current_workbook_id: Any = field(default=None)  # EntityId | None

    @property
    def current(self) -> InventionEntry | None:
        if 0 <= self.current_idx < len(self.inventions):
            return self.inventions[self.current_idx]
        return None

    @property
    def current_report(self) -> Any | None:
        entry = self.current
        return entry.report if entry else None

    @property
    def session_duration(self) -> float:
        return time.time() - self.start_time

    def add_invention(self, problem: str, report: Any) -> None:
        entry = InventionEntry(problem=problem, report=report)
        self.inventions.append(entry)
        self.current_idx = len(self.inventions) - 1
        self.total_cost_usd += report.total_cost_usd
        self.total_calls += 1

        trace = getattr(getattr(report, "top_invention", None), "trace", None)
        if trace is not None:
            self.total_input_tokens += int(getattr(trace, "total_input_tokens", 0) or 0)
            self.total_output_tokens += int(getattr(trace, "total_output_tokens", 0) or 0)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def _prompt_text(state: SessionState) -> str:
    """Build the REPL prompt string."""
    entry = state.current
    if entry:
        slug = entry.slug
        return f"[bold yellow]heph[/][dim][{slug}][/]> "
    return "[bold yellow]heph[/]> "


def _maybe_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Avoid MagicMock fabricating optional attributes that were never set."""
    if isinstance(obj, Mock):
        data = getattr(obj, "__dict__", {})
        if isinstance(data, dict) and name in data:
            return data[name]
        return default
    return getattr(obj, name, default)


def _repo_dossier_from_state(state: SessionState) -> Any | None:
    workspace_context = getattr(state, "workspace_context", None)
    if workspace_context is None:
        return None
    return getattr(workspace_context, "repo_dossier", None)


def _inject_workspace_context(problem: str, state: SessionState) -> str:
    """Augment a pipeline problem with repo/workspace context when available.

    Interactive mode detects when Hephaestus is running inside a codebase, but
    the normal invention prompt path still needs explicit injection of the
    scanned workspace context. This helper makes repo-aware invention the
    default while avoiding duplicated workspace blocks across refinements.
    """
    workspace_context = getattr(state, "workspace_context", None)
    if workspace_context is None:
        return problem

    marker = "=== WORKSPACE CONTEXT ==="
    if marker in problem:
        return problem

    try:
        prompt_text = workspace_context.to_prompt_text()
    except Exception as exc:
        logger.warning("Could not render workspace context for pipeline injection: %s", exc)
        return problem

    if not prompt_text.strip():
        return problem

    return f"{problem}\n\n{prompt_text}"


def _backend_status(config: HephaestusConfig) -> tuple[str, str]:
    """Return a short readiness label and hint for the configured backend."""
    backend = config.backend
    selected_model = str(getattr(config, "default_model", "") or "")
    if backend == "agent-sdk":
        ready = _detect_agent_sdk_available()
        return (
            "ready" if ready else "not ready",
            "Claude Agent SDK + Claude CLI detected."
            if ready
            else "Install: pip install claude-agent-sdk",
        )
    if backend == "claude-max":
        ready = _detect_claude_max_available()
        return (
            "ready" if ready else "not ready",
            "Uses your Claude Max login from ~/.openclaw."
            if ready
            else "Run Claude Max login on this machine first.",
        )
    if backend == "claude-cli":
        ready = _detect_claude_cli_available()
        return (
            "ready" if ready else "not ready",
            "`claude` is on PATH."
            if ready
            else "Install the Claude CLI or switch to /backend api.",
        )
    if backend == "codex-cli":
        ready = _detect_codex_cli_available()
        return (
            "ready" if ready else "not ready",
            "Uses your Codex/ChatGPT OAuth from ~/.codex."
            if ready
            else "Run `codex login` on this machine first.",
        )
    if backend == "openrouter":
        ready = bool(getattr(config, "openrouter_api_key", None))
        return (
            "ready" if ready else "not ready",
            "OPENROUTER_API_KEY detected."
            if ready
            else "Set OPENROUTER_API_KEY before running inventions.",
        )

    anthropic = bool(getattr(config, "anthropic_api_key", None))
    openai = bool(getattr(config, "openai_api_key", None))
    if selected_model == "both":
        if anthropic and openai:
            return "ready", "Both Anthropic and OpenAI keys detected for the mixed preset."
        return "not ready", "The 'both' preset needs both ANTHROPIC_API_KEY and OPENAI_API_KEY."
    if selected_model in {"opus"} or selected_model.startswith("claude"):
        return (
            ("ready", "Anthropic key detected.")
            if anthropic
            else ("not ready", "Set ANTHROPIC_API_KEY or switch to a GPT/OpenRouter backend.")
        )
    if selected_model in {"gpt5"} or selected_model.startswith(("gpt", "o3", "o4")):
        return (
            ("ready", "OpenAI key detected.")
            if openai
            else ("not ready", "Set OPENAI_API_KEY or switch to a Claude/OpenRouter backend.")
        )
    if anthropic or openai:
        providers = []
        if anthropic:
            providers.append("Anthropic")
        if openai:
            providers.append("OpenAI")
        return "ready", f"API keys detected: {', '.join(providers)}."
    return (
        "not ready",
        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or switch to /backend claude-max or /backend codex-cli.",
    )


def _detect_agent_sdk_available() -> bool:
    from hephaestus.cli.config import _detect_agent_sdk

    return _detect_agent_sdk()


def _detect_claude_max_available() -> bool:
    from hephaestus.cli.config import _detect_claude_max

    return _detect_claude_max()


def _detect_codex_cli_available() -> bool:
    from hephaestus.cli.config import _detect_codex_cli

    return _detect_codex_cli()


def _detect_claude_cli_available() -> bool:
    from hephaestus.cli.config import _detect_claude_cli

    return _detect_claude_cli()


def _safe_error_message(exc: Exception) -> str:
    """Trim exception text down to something user-facing."""
    message = str(exc).strip()
    return message or exc.__class__.__name__


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------


HELP_TEXT = """\
[bold yellow]Quick Start[/]
  Type a problem in plain English to run the invention pipeline.
  After each result, type [dark_orange]1-7[/] to use the menu or enter another problem immediately.
  Use [dark_orange]Ctrl+D[/] or [dark_orange]/quit[/] to leave the session. [dark_orange]Tab[/] completes slash commands.

[bold yellow]Session[/]
  [dark_orange]/help[/]              Show this help
  [dark_orange]/status[/]            Session info, backend readiness, and current defaults
  [dark_orange]/history[/] [search]  List session and saved inventions
  [dark_orange]/load[/] <name|path>  Load a saved invention or session replay
  [dark_orange]/save[/] [name]       Save the current invention now
  [dark_orange]/compare[/]           Compare recent inventions side by side
  [dark_orange]/model[/] [name]      Show or switch the active model for interactive runs
  [dark_orange]/backend[/] [name]    Show or switch backend (agent-sdk, claude-max, claude-cli, api, openrouter)
  [dark_orange]/usage[/]             Session runs, tokens, and cost summary
  [dark_orange]/cost[/]              Cost breakdown for the current invention
  [dark_orange]/clear[/]             Clear current context and prompt state
  [dark_orange]/quit[/] or [dark_orange]/exit[/]    Exit interactive mode

[bold yellow]Iteration[/]
  [dark_orange]/refine[/] [constraint]  Re-run the current invention with a constraint
  [dark_orange]/alternatives[/]         Show runner-up inventions from the last run
  [dark_orange]/deeper[/] [n]           Increase depth and retry the current problem
  [dark_orange]/domain[/] <hint>        Re-run with a source-domain hint
  [dark_orange]/candidates[/] [n]       Show or change candidate count (1-20)
  [dark_orange]/trace[/]                Show trace details from the last run
  [dark_orange]/export[/] [format]      Export as markdown, json, text, or pdf

[bold yellow]Context[/]
  [dark_orange]/context[/]              Show context carried into the next run
  [dark_orange]/context add[/] <text>   Add domain knowledge or constraints
  [dark_orange]/context clear[/]        Remove all added context

[bold yellow]Working Memory[/]
  [dark_orange]/todo[/]                Show current todo items
  [dark_orange]/todo add[/] <text>     Add a new todo
  [dark_orange]/todo start[/] <id>     Start working on a todo
  [dark_orange]/todo done[/] <id>      Mark a todo complete
  [dark_orange]/plan[/]                Alias for /todo

[bold yellow]Creativity Controls[/]
  [dark_orange]/intensity[/] [level]    STANDARD, AGGRESSIVE, or MAXIMUM
  [dark_orange]/mode[/] [mode]          MECHANISM, FRAMEWORK, NARRATIVE, SYSTEM, PROTOCOL, TAXONOMY, or INTERFACE

[bold yellow]ForgeBase[/]
  [dark_orange]/vault[/] [sub]           Manage vaults: create, list, use, info, compile, lint
  [dark_orange]/ask[/] <query>           Query within current vault context
  [dark_orange]/fuse[/] <id1> <id2>     Cross-vault fusion
  [dark_orange]/ingest[/] <path_or_url> Ingest source into current vault
  [dark_orange]/fb-lint[/]              Lint current vault
  [dark_orange]/fb-compile[/]           Compile current vault
  [dark_orange]/workbook[/] [sub]       Manage workbooks: open, list, diff, merge, abandon
  [dark_orange]/fb-export[/] [format]   Export current vault (markdown or obsidian)
"""

VALID_EXPORT_FORMATS = ("markdown", "json", "text", "pdf")


async def _cmd_help(console: Console, state: SessionState, args: str) -> None:
    console.print()
    console.print(
        Panel(HELP_TEXT, title="[bold yellow]Help[/]", border_style="yellow", padding=(0, 1))
    )


async def _cmd_status(console: Console, state: SessionState, args: str) -> None:
    console.print()
    dur = state.session_duration
    mins, secs = divmod(int(dur), 60)
    dur_str = f"{mins}m {secs:02d}s"

    num_inv = len(state.inventions)
    num_refined = sum(1 for e in state.inventions if e.refined)
    backend_ready, backend_hint = _backend_status(state.config)

    table = Table(box=box.ROUNDED, border_style="yellow", show_header=False, padding=(0, 2))
    table.add_column("Key", style=DIM, no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Backend", f"[dark_orange]{state.config.backend}[/]")
    table.add_row(
        "Backend status",
        f"[green]{backend_ready}[/]" if backend_ready == "ready" else f"[yellow]{backend_ready}[/]",
    )
    table.add_row("Model", f"[dark_orange]{state.config.default_model}[/]")
    table.add_row("Session duration", f"[dark_orange]{dur_str}[/]")
    table.add_row("Inventions", f"[dark_orange]{num_inv} generated, {num_refined} refined[/]")
    table.add_row("Cost (session)", f"[green]${state.total_cost_usd:.4f}[/]")
    table.add_row(
        "Tokens (session)",
        f"[dark_orange]{state.total_input_tokens:,} in / {state.total_output_tokens:,} out[/]",
    )
    table.add_row("Depth", f"[dark_orange]{state.config.depth}[/]")
    table.add_row("Search candidates", f"[dark_orange]{state.config.candidates}[/]")
    table.add_row(
        "Intensity", f"[dark_orange]{getattr(state.config, 'divergence_intensity', 'STANDARD')}[/]"
    )
    table.add_row("Output mode", f"[dark_orange]{getattr(state.config, 'output_mode', 'MECHANISM')}[/]")
    table.add_row("Context additions", f"[dark_orange]{len(state.context_items)} items[/]")
    table.add_row("Auto-save", f"[dark_orange]{'ON' if state.config.auto_save else 'OFF'}[/]")
    repo_dossier = _repo_dossier_from_state(state)
    if state.workspace_root:
        table.add_row("Workspace", f"[dark_orange]{state.workspace_root}[/]")
    if repo_dossier is not None:
        table.add_row(
            "Repo awareness",
            f"[dark_orange]{repo_dossier.component_count} components[/], "
            f"[dark_orange]{len(repo_dossier.commands)} commands[/], "
            f"[dark_orange]{len(repo_dossier.hotspots)} hotspots[/]",
        )
    if state.session is not None and getattr(state.session, "lens_engine_state", None) is not None:
        lens_state = state.session.lens_engine_state
        table.add_row("Lens engine", f"[dark_orange]{lens_state.summary()}[/]")

    console.print(Panel(table, title="[bold yellow]Session Status[/]", border_style="yellow"))
    console.print(f"  [dim]{backend_hint}[/]")

    # Memory transparency section
    config_ns = None
    if state.layered_config is not None:
        config_ns = SimpleNamespace(config_sources=state.layered_config.config_sources())
    mem_report = build_memory_report(state, config=config_ns)
    console.print()
    console.print(
        Panel(
            format_memory_report(mem_report),
            title="[bold yellow]Memory & Context[/]",
            border_style="dim yellow",
        )
    )
    if repo_dossier is not None:
        console.print()
        console.print(
            Panel(
                repo_dossier.format_status_text(),
                title="[bold yellow]Repo Awareness[/]",
                border_style="dim yellow",
            )
        )
    console.print()


VALID_MODELS = {
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "gpt-4o",
    "gpt-4o-mini",
    "o3",
    "o4-mini",
    "gpt-5.4",
    "gpt-5.4-mini",
    "opus",
    "gpt5",
    "codex",
    "both",
}


async def _cmd_model(console: Console, state: SessionState, args: str) -> None:
    if not args:
        console.print(f"  [dim]Current model:[/] [{EMBER}]{state.config.default_model}[/]")
        console.print(
            "  [dim]Use an exact model name or a preset like opus, gpt5, codex, or both.[/]"
        )
        console.print(f"  [dim]Available:[/] {', '.join(sorted(VALID_MODELS))}\n")
        return
    name = args.strip().lower()
    if name not in VALID_MODELS:
        console.print(
            f"  [{RED}]Unknown model '{args.strip()}'.[/] Available: {', '.join(sorted(VALID_MODELS))}\n"
        )
        return
    if name in {"opus", "gpt5", "codex", "both"} and state.config.backend in {
        "claude-max",
        "claude-cli",
        "codex-cli",
    }:
        state.config.backend = "api"
        console.print(
            "  [dim]Switched backend to [dark_orange]api[/] so the preset can use provider-specific stage models.[/]"
        )
    state.config.default_model = name
    console.print(f"  [{GREEN}]\u2713[/] Model set to [{EMBER}]{name}[/]")
    console.print("  [dim]Applies to the next invention run in this session.[/]\n")


async def _cmd_backend(console: Console, state: SessionState, args: str) -> None:
    from hephaestus.cli.config import VALID_BACKENDS

    if not args:
        readiness, hint = _backend_status(state.config)
        console.print(f"  [dim]Current backend:[/] [{EMBER}]{state.config.backend}[/]")
        console.print(f"  [dim]Status:[/] {readiness}")
        console.print(f"  [dim]{hint}[/]\n")
        return
    name = args.strip().lower()
    if name not in VALID_BACKENDS:
        console.print(f"  [{RED}]Invalid backend.[/] Choose from: {', '.join(VALID_BACKENDS)}\n")
        return
    state.config.backend = name
    if name in {"agent-sdk", "claude-max", "claude-cli"} and state.config.default_model in {
        "opus",
        "gpt5",
        "both",
    }:
        state.config.default_model = "claude-opus-4-6"
        console.print(
            "  [dim]Using [dark_orange]claude-opus-4-6[/] for subscription backends.[/]"
        )
    # Persist to disk so it survives restart
    from hephaestus.cli.config import save_config
    save_config(state.config)
    readiness, hint = _backend_status(state.config)
    console.print(f"  [{GREEN}]\u2713[/] Backend set to [{EMBER}]{name}[/] (saved)")
    console.print(f"  [dim]Status:[/] {readiness}")
    console.print(f"  [dim]{hint}[/]\n")


async def _cmd_usage(console: Console, state: SessionState, args: str) -> None:
    console.print()
    if state.total_calls == 0 and state.current_report is None:
        console.print("  [dim]No runs yet. Describe a problem to start the pipeline.[/]")
        console.print(
            "  [dim]Tip:[/] use [dark_orange]/context add <text>[/] to inject requirements before the next run.\n"
        )
        return

    summary = Table(
        title="Session Usage",
        box=box.SIMPLE_HEAD,
        border_style="yellow",
        padding=(0, 2),
    )
    summary.add_column("Metric", style=AMBER)
    summary.add_column("Value", justify="right", style="white")
    summary.add_row("Runs", str(state.total_calls))
    summary.add_row("Input tokens", f"{state.total_input_tokens:,}")
    summary.add_row("Output tokens", f"{state.total_output_tokens:,}")
    summary.add_row("Cost", f"[bold green]${state.total_cost_usd:.4f}[/]")
    console.print(summary)

    report = state.current_report
    if report is None or not hasattr(report, "cost_breakdown"):
        console.print()
        return

    table = Table(
        title="Current Invention Cost Breakdown",
        box=box.SIMPLE_HEAD,
        border_style="yellow",
        padding=(0, 2),
    )
    table.add_column("Stage", style=AMBER)
    table.add_column("Cost", justify="right", style=GREEN)

    cost = report.cost_breakdown
    stage_costs = [
        ("Decompose", getattr(cost, "decomposition_cost", 0.0)),
        ("Search", getattr(cost, "search_cost", 0.0)),
        ("Score", getattr(cost, "scoring_cost", 0.0)),
        ("Translate", getattr(cost, "translation_cost", 0.0)),
        ("Verify", getattr(cost, "verification_cost", 0.0)),
    ]
    for stage_name, value in stage_costs:
        if value > 0:
            table.add_row(stage_name, f"${value:.4f}")

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/]", f"[bold green]${getattr(cost, 'total', state.total_cost_usd):.4f}[/]"
    )

    console.print()
    console.print(table)
    console.print()


async def _cmd_cost(console: Console, state: SessionState, args: str) -> None:
    report = state.current_report
    if report:
        print_cost_table(console, report)
    elif state.total_cost_usd > 0:
        console.print(f"  [dim]Session cost so far:[/] [{GREEN}]${state.total_cost_usd:.4f}[/]\n")
    else:
        console.print("  [dim]No cost yet. Describe a problem to start inventing.[/]\n")


async def _cmd_clear(console: Console, state: SessionState, args: str) -> None:
    state.current_idx = -1
    state.context_items.clear()
    state.pinned.clear()
    console.print(f"  [{GREEN}]\u2713[/] Cleared the active prompt state.")
    console.print("  [dim]History is still available via /history.[/]\n")


async def _cmd_quit(console: Console, state: SessionState, args: str) -> None:
    dur = state.session_duration
    mins, secs = divmod(int(dur), 60)
    num = len(state.inventions)
    state.exit_reported = True
    console.print()
    if num > 0:
        if state.config.auto_save and not state.last_auto_save_error:
            save_note = (
                f"  [{GREEN}]\u2713[/] Auto-save is enabled. Saved inventions live in "
                f"[dark_orange]~/.hephaestus/inventions/[/]"
            )
        elif state.config.auto_save:
            save_note = f"  [{AMBER}]\u26a0[/] Auto-save failed for at least one run. Use [dark_orange]/save[/] if you need another copy."
        else:
            save_note = f"  [{AMBER}]\u26a0[/] {num} invention{'s' if num != 1 else ''} NOT saved (auto-save is off). Use /save before quitting."
        console.print(save_note)
    console.print(
        f"  [dim]Session:[/] "
        f"[dim]{num} inventions | ${state.total_cost_usd:.4f} | {mins}m {secs:02d}s[/]\n"
    )
    raise SystemExit(0)


async def _cmd_alternatives(console: Console, state: SessionState, args: str) -> None:
    report = state.current_report
    if not report:
        console.print("  [dim]No current invention. Describe a problem first.[/]\n")
        return
    alts = report.alternative_inventions
    if not alts:
        console.print("  [dim]No alternatives were recorded for the last run.[/]")
        console.print("  [dim]Try /deeper, /domain <hint>, or a fresh problem statement.[/]\n")
        return
    console.print()
    for i, alt in enumerate(alts, start=2):
        name = getattr(alt, "invention_name", "?")
        src = getattr(alt, "source_domain", "?")
        novelty = getattr(alt, "novelty_score", 0.0)
        feas = getattr(alt, "feasibility_rating", "?")
        console.print(f"  [{AMBER}]{i}.[/] [{WHITE_HOT}]{name}[/]  [dim](from {src})[/]")
        console.print(f"     Novelty: [{GOLD}]{novelty:.2f}[/]  Feasibility: [{EMBER}]{feas}[/]")
        console.print()


async def _cmd_trace(console: Console, state: SessionState, args: str) -> None:
    report = state.current_report
    if not report:
        console.print("  [dim]No current invention. Run a problem first.[/]\n")
        return
    print_trace(console, report)


async def _cmd_candidates(console: Console, state: SessionState, args: str) -> None:
    if not args:
        console.print(f"  [dim]Search candidates:[/] [{EMBER}]{state.config.candidates}[/]")
        console.print("  [dim]Higher values search more domains but cost more.[/]\n")
        return
    try:
        n = int(args.strip())
        if not 1 <= n <= 20:
            raise ValueError
    except ValueError:
        console.print(f"  [{RED}]Candidates must be 1\u201320.[/]\n")
        return
    state.config.candidates = n
    console.print(f"  [{GREEN}]\u2713[/] Candidates set to [{EMBER}]{n}[/]")
    console.print("  [dim]Applies to the next invention run in this session.[/]\n")


VALID_INTENSITIES = ("STANDARD", "AGGRESSIVE", "MAXIMUM")


async def _cmd_intensity(console: Console, state: SessionState, args: str) -> None:
    """Show or set divergence intensity."""
    current = getattr(state.config, "divergence_intensity", "STANDARD")
    if not args:
        console.print(f"  [dim]Divergence intensity:[/] [{EMBER}]{current}[/]")
        console.print(f"  [dim]Options:[/] {', '.join(VALID_INTENSITIES)}\n")
        return
    val = args.strip().upper()
    if val not in VALID_INTENSITIES:
        console.print(
            f"  [{RED}]Invalid intensity '{args.strip()}'.[/] Options: {', '.join(VALID_INTENSITIES)}\n"
        )
        return
    state.config.divergence_intensity = val
    console.print(f"  [{GREEN}]\u2713[/] Divergence intensity set to [{EMBER}]{val}[/]")
    console.print("  [dim]Applies to the next invention run in this session.[/]\n")


VALID_MODES = ("MECHANISM", "FRAMEWORK", "NARRATIVE", "SYSTEM", "PROTOCOL", "TAXONOMY", "INTERFACE")


async def _cmd_mode(console: Console, state: SessionState, args: str) -> None:
    """Show or set output mode."""
    current = getattr(state.config, "output_mode", "MECHANISM")
    if not args:
        console.print(f"  [dim]Output mode:[/] [{EMBER}]{current}[/]")
        console.print(f"  [dim]Options:[/] {', '.join(VALID_MODES)}\n")
        return
    val = args.strip().upper()
    if val not in VALID_MODES:
        console.print(
            f"  [{RED}]Invalid mode '{args.strip()}'.[/] Options: {', '.join(VALID_MODES)}\n"
        )
        return
    state.config.output_mode = val
    console.print(f"  [{GREEN}]\u2713[/] Output mode set to [{EMBER}]{val}[/]")
    console.print("  [dim]Applies to the next invention run in this session.[/]\n")


# ---------------------------------------------------------------------------
# Working memory commands
# ---------------------------------------------------------------------------


def _resolve_todo_id(todo_list: TodoList, prefix: str) -> str:
    """Resolve a todo ID prefix to a full ID.

    Raises :class:`KeyError` if no item matches or the prefix is ambiguous.
    """
    matches = [item for item in todo_list.items if item.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        raise KeyError(f"Ambiguous prefix {prefix!r} — matches {len(matches)} items")
    raise KeyError(f"No todo item with id prefix {prefix!r}")


async def _cmd_todo(console: Console, state: SessionState, args: str) -> None:
    """Show or manage the working-memory todo list."""
    if state.todo_list is None:
        state.todo_list = TodoList()

    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""

    if sub == "add" and len(parts) > 1 and parts[1].strip():
        item = state.todo_list.add(parts[1].strip())
        console.print(f"  [{GREEN}]\u2713[/] Added: {item.title}  [dim](id: {item.id})[/]\n")
    elif sub == "add":
        console.print(f"  [{RED}]Usage: /todo add <text>[/]\n")
    elif sub == "start" and len(parts) > 1:
        try:
            resolved = _resolve_todo_id(state.todo_list, parts[1].strip())
            state.todo_list.start(resolved)
            console.print(f"  [{GREEN}]\u2713[/] Started: {resolved}\n")
        except (KeyError, ValueError) as exc:
            console.print(f"  [{RED}]{exc}[/]\n")
    elif sub == "done" and len(parts) > 1:
        try:
            resolved = _resolve_todo_id(state.todo_list, parts[1].strip())
            state.todo_list.complete(resolved)
            console.print(f"  [{GREEN}]\u2713[/] Completed: {resolved}\n")
        except (KeyError, ValueError) as exc:
            console.print(f"  [{RED}]{exc}[/]\n")
    elif not sub:
        console.print()
        console.print(state.todo_list.summary())
        console.print()
    else:
        console.print("  [dim]Usage: /todo [add <text> | start <id> | done <id>][/]\n")


# ---------------------------------------------------------------------------
# Workspace commands
# ---------------------------------------------------------------------------


async def _cmd_read(console: Console, state: SessionState, args: str) -> None:
    """Read a file from the workspace."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode. Run heph from a project directory.[/]\n")
        return
    path = args.strip()
    if not path:
        console.print(f"  [{RED}]Usage: /read <file_path>[/]\n")
        return
    from hephaestus.tools.file_ops import read_file

    full = state.workspace_root / path if not Path(path).is_absolute() else Path(path)
    content = read_file(str(full))
    console.print()
    console.print(content)
    console.print()


async def _cmd_tree(console: Console, state: SessionState, args: str) -> None:
    """Show the workspace directory tree."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode.[/]\n")
        return
    if state.workspace_context and state.workspace_context.summary.tree:
        console.print()
        for line in state.workspace_context.summary.tree.splitlines():
            console.print(f"  {line}")
        console.print()
    else:
        from hephaestus.tools.file_ops import list_directory

        console.print(list_directory(str(state.workspace_root)))


async def _cmd_grep(console: Console, state: SessionState, args: str) -> None:
    """Search file contents in the workspace."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode.[/]\n")
        return
    query = args.strip()
    if not query:
        console.print(f"  [{RED}]Usage: /grep <query>[/]\n")
        return
    from hephaestus.tools.file_ops import grep_search

    result = grep_search(query, str(state.workspace_root))
    console.print()
    console.print(result)
    console.print()


async def _cmd_find(console: Console, state: SessionState, args: str) -> None:
    """Find files by pattern in the workspace."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode.[/]\n")
        return
    pattern = args.strip() or "*.py"
    from hephaestus.tools.file_ops import search_files

    result = search_files(pattern, str(state.workspace_root))
    console.print()
    console.print(result)
    console.print()


async def _cmd_edit(console: Console, state: SessionState, args: str) -> None:
    """Edit a file — replace exact text."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode.[/]\n")
        return
    console.print("  [dim]Use the agent chat to make edits. Describe what to change.[/]\n")


async def _cmd_invent(console: Console, state: SessionState, args: str) -> None:
    """Analyze the codebase and invent improvements using the genesis pipeline."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode. Run heph from a project directory.[/]\n")
        return

    max_inventions = 3
    if args.strip().isdigit():
        max_inventions = min(int(args.strip()), 7)

    console.print("\n  [bold yellow]⚒️  Workspace Invention Mode[/]")
    console.print(
        f"  [dim]Analyzing {state.workspace_root.name}/ and inventing up to {max_inventions} improvements...[/]\n"
    )

    try:
        from hephaestus.workspace.inventor import WorkspaceInventor

        # Build an adapter from current config
        cfg = state.config
        adapter = _build_adapter_for_analysis(cfg)

        inventor = WorkspaceInventor(
            adapter=adapter,
            workspace_root=state.workspace_root,
            max_inventions=max_inventions,
            depth=cfg.depth,
            model=cfg.backend if cfg.backend != "api" else "both",
            intensity=cfg.divergence_intensity,
        )

        report = await inventor.analyze_and_invent(console=console)

        # Save report
        if report.inventions_succeeded > 0:
            report_text = inventor.format_report(report)
            save_path = state.workspace_root / ".hephaestus" / "inventions.md"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(report_text, encoding="utf-8")
            console.print(f"\n  [green]✓[/] Report saved to {save_path}")

        console.print(
            f"\n  [bold]Results:[/] {report.inventions_succeeded}/{report.inventions_attempted} "
            f"inventions succeeded\n"
        )
    except Exception as exc:
        console.print(f"  [red]Invention failed: {exc}[/]\n")


def _build_adapter_for_analysis(cfg: Any) -> Any:
    """Build an LLM adapter from the current session config for codebase analysis.

    Prefers Claude Max (OAT token, zero API cost) when available.
    """
    backend = cfg.backend

    if backend == "codex-cli":
        from hephaestus.deepforge.adapters.codex_oauth import CodexOAuthAdapter

        return CodexOAuthAdapter(
            model=cfg.default_model or "gpt-5.4",
            reasoning="xhigh",
            reasoning_effort="xhigh",
            reasoning_summary="auto",
        )

    # Always try Claude Max first — it's free (subscription)
    try:
        from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter

        return ClaudeMaxAdapter(model=cfg.default_model or "claude-sonnet-4-6")
    except Exception as exc:
        logger.warning("Claude Max adapter not available, trying fallbacks: %s", exc)

    if backend == "claude-cli":
        from hephaestus.deepforge.adapters.claude_cli import ClaudeCliAdapter

        return ClaudeCliAdapter(model=cfg.default_model or "claude-opus-4-6")

    # Fall back to API key adapters
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter(
            model=cfg.default_model or "claude-sonnet-4-20250514", api_key=anthropic_key
        )

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from hephaestus.deepforge.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(model="gpt-4o", api_key=openai_key)

    raise RuntimeError(
        "No LLM adapter available. Set up Claude Max, ANTHROPIC_API_KEY, or OPENAI_API_KEY."
    )


async def _cmd_ws(console: Console, state: SessionState, args: str) -> None:
    """Show workspace status."""
    if not state.workspace_root:
        console.print("  [dim]Not in workspace mode. Run heph from a project directory.[/]\n")
        return
    if state.workspace_context:
        console.print()
        console.print(f"  [{GOLD}]Workspace:[/] {state.workspace_root}")
        s = state.workspace_context.summary
        console.print(
            f"  [dim]Files:[/] {s.total_files} | [dim]Lines:[/] {s.total_lines:,} | [dim]Language:[/] {s.primary_language}"
        )
        if s.git:
            console.print(
                f"  [dim]Git:[/] {s.git.branch} {'(dirty)' if s.git.has_changes else '(clean)'}"
            )
        repo_dossier = _repo_dossier_from_state(state)
        if repo_dossier is not None:
            console.print(
                f"  [dim]Repo cache:[/] {repo_dossier.cache_state} @ {repo_dossier.cache_path}"
            )
            for note in repo_dossier.architecture_notes[:3]:
                console.print(f"  [dim]-[/] {note}")
            if repo_dossier.components:
                names = ", ".join(component.name for component in repo_dossier.components[:8])
                extra = len(repo_dossier.components) - min(len(repo_dossier.components), 8)
                if extra > 0:
                    names += f" (+{extra} more)"
                console.print(f"  [dim]Components:[/] {names}")
            if repo_dossier.commands:
                console.print(
                    "  [dim]Commands:[/] "
                    + "; ".join(command.command for command in repo_dossier.commands[:4])
                )
        console.print()


# ---------------------------------------------------------------------------
# Phase 2 commands
# ---------------------------------------------------------------------------


async def _cmd_refine(console: Console, state: SessionState, args: str) -> None:
    """Enter refinement mode — re-run translation with a user constraint."""
    report = state.current_report
    if not report:
        console.print("  [dim]No current invention to refine. Describe a problem first.[/]\n")
        return

    top = report.top_invention
    if not top:
        console.print("  [dim]No invention to refine.[/]\n")
        return

    console.print()
    console.print(
        f"  [dim]Refining:[/] [{WHITE_HOT}]{top.invention_name}[/]\n"
        f"  [dim]Add constraints, shift domain, narrow scope, or challenge weaknesses.[/]\n"
    )

    if args.strip():
        constraint = args.strip()
    else:
        try:
            constraint = console.input("  [bold yellow]refine[/]> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]Refinement cancelled.[/]\n")
            return

    if not constraint:
        console.print("  [dim]No constraint provided. Refinement cancelled.[/]\n")
        return

    # Build a refined problem: original problem + constraint + context
    original = report.problem
    refined_problem = (
        f"{original}\n\n"
        f"REFINEMENT CONSTRAINT: {constraint}\n\n"
        f"PREVIOUS INVENTION (refine this): {top.invention_name} from {top.source_domain}"
    )
    if state.context_items:
        refined_problem += "\n\nADDITIONAL CONTEXT:\n" + "\n".join(
            f"- {c}" for c in state.context_items
        )

    console.print("  [dim]Re-running pipeline with refinement constraint...[/]\n")
    await _run_pipeline(console, state, refined_problem, is_refinement=True)


async def _cmd_domain(console: Console, state: SessionState, args: str) -> None:
    """Re-run with a domain hint."""
    if not args.strip():
        console.print("  [dim]Usage:[/] /domain <hint>  (e.g. /domain biology)\n")
        return

    report = state.current_report
    if not report:
        console.print("  [dim]No current problem. Describe a problem first.[/]\n")
        return

    domain_hint = args.strip()
    problem = report.problem
    augmented = f"{problem}\n\nDOMAIN HINT: Focus on solutions from {domain_hint}."
    if state.context_items:
        augmented += "\n\nADDITIONAL CONTEXT:\n" + "\n".join(f"- {c}" for c in state.context_items)

    console.print(f"  [dim]Re-running with domain hint: {domain_hint}...[/]\n")
    await _run_pipeline(console, state, augmented)


async def _cmd_deeper(console: Console, state: SessionState, args: str) -> None:
    """Increase depth and re-run."""
    report = state.current_report
    if not report:
        console.print("  [dim]No current problem. Describe a problem first.[/]\n")
        return

    increment = 2
    if args.strip():
        try:
            increment = int(args.strip())
            if increment < 1 or increment > 10:
                console.print(f"  [{RED}]Increment must be 1–10. Using default (+2).[/]\n")
                increment = 2
        except ValueError:
            console.print(f"  [{RED}]Invalid number '{args.strip()}'. Using default (+2).[/]\n")

    old_depth = state.config.depth
    state.config.depth = min(10, old_depth + increment)
    console.print(
        f"  [{GREEN}]\u2713[/] Depth increased: {old_depth} \u2192 {state.config.depth}\n"
        f"  [dim]Re-running pipeline...[/]\n"
    )
    await _run_pipeline(console, state, report.problem)


async def _cmd_context(console: Console, state: SessionState, args: str) -> None:
    """Show, add, or clear context items."""
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else ""

    if sub == "add" and len(parts) > 1 and parts[1].strip():
        text = parts[1].strip()
        state.context_items.append(text)
        console.print(
            f"  [{GREEN}]\u2713[/] Context added ({len(state.context_items)} items total)\n"
        )
        return
    elif sub == "add":
        console.print(f"  [{RED}]Usage: /context add <text>[/]\n")
        return
    elif sub == "clear":
        state.context_items.clear()
        console.print(f"  [{GREEN}]\u2713[/] Context cleared.\n")
    else:
        if not state.context_items:
            console.print("  [dim]No context items yet.[/]")
            console.print(
                "  [dim]Example:[/] [dark_orange]/context add must work offline and tolerate node churn[/]\n"
            )
        else:
            console.print()
            for i, item in enumerate(state.context_items, 1):
                console.print(f"  [{EMBER}]{i}.[/] {item}")
            console.print()

        # Context transparency report
        config_ns = None
        if state.layered_config is not None:
            config_ns = SimpleNamespace(config_sources=state.layered_config.config_sources())
        mem_report = build_memory_report(state, config=config_ns)
        ctx_text = format_context_report(mem_report)
        console.print(
            Panel(
                ctx_text,
                title="[bold yellow]Context Details[/]",
                border_style="dim yellow",
            )
        )
        repo_dossier = _repo_dossier_from_state(state)
        if repo_dossier is not None:
            console.print()
            console.print(
                Panel(
                    repo_dossier.format_context_text(),
                    title="[bold yellow]Repo Dossier[/]",
                    border_style="dim yellow",
                )
            )
        console.print()


# ---------------------------------------------------------------------------
# Phase 3 commands: Persistence & History
# ---------------------------------------------------------------------------


async def _cmd_save(console: Console, state: SessionState, args: str) -> None:
    """Explicitly save current invention (and full session) to disk."""
    entry = state.current
    if not entry:
        console.print("  [dim]No current invention to save.[/]\n")
        return

    ensure_dirs()
    name = args.strip() if args.strip() else entry.slug
    # Sanitize name
    name = re.sub(r"[^a-z0-9_-]", "-", name.lower().strip())[:50].strip("-") or "invention"
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    base = f"{date_str}-{name}"

    # Find unique filename
    json_path = INVENTIONS_DIR / f"{base}.json"
    counter = 1
    while json_path.exists():
        json_path = INVENTIONS_DIR / f"{base}-{counter}.json"
        counter += 1

    report = entry.report
    try:
        data = report.to_dict()
        data["_meta"] = {
            "problem": entry.problem,
            "timestamp": entry.timestamp,
            "refined": entry.refined,
            "slug": entry.slug,
        }
        json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        md_path = json_path.with_suffix(".md")
        md_path.write_text(_invention_to_markdown(entry, report), encoding="utf-8")

        console.print(f"  [{GREEN}]\u2713[/] Saved to [dark_orange]{json_path}[/]")
        console.print(f"  [{GREEN}]\u2713[/] Markdown: [dark_orange]{md_path}[/]")
    except Exception:
        print_error(
            console,
            "Could not save the current invention.",
            hint="Check write permissions for ~/.hephaestus/inventions and try again.",
        )
        return

    # Save full session replay JSON
    session_path = _save_session_replay(state)
    if session_path:
        console.print(f"  [{GREEN}]\u2713[/] Session replay: [dark_orange]{session_path}[/]")

    # Save typed session transcript
    if state.session is not None:
        try:
            transcript_path = SESSIONS_DIR / f"{base}-transcript.json"
            state.session.save(transcript_path)
            console.print(f"  [{GREEN}]\u2713[/] Session transcript: [dark_orange]{transcript_path}[/]")
        except Exception as exc:
            logger.warning("Failed to save session transcript: %s", exc)
    console.print()


def _save_session_replay(state: SessionState) -> Path | None:
    """Save full session state as a replay JSON."""
    ensure_dirs()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    first_slug = state.inventions[0].slug if state.inventions else "session"
    session_path = SESSIONS_DIR / f"{date_str}-{first_slug}-session.json"
    counter = 1
    while session_path.exists():
        session_path = SESSIONS_DIR / f"{date_str}-{first_slug}-session-{counter}.json"
        counter += 1

    try:
        entries = []
        for inv in state.inventions:
            entries.append(
                {
                    "problem": inv.problem,
                    "timestamp": inv.timestamp,
                    "refined": inv.refined,
                    "slug": inv.slug,
                    "report": inv.report.to_dict(),
                }
            )

        data = {
            "session_start": state.start_time,
            "session_duration_s": state.session_duration,
            "backend": state.config.backend,
            "model": state.config.default_model,
            "depth": state.config.depth,
            "candidates": state.config.candidates,
            "total_cost_usd": state.total_cost_usd,
            "context_items": state.context_items,
            "inventions": entries,
        }
        session_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return session_path
    except Exception as exc:
        logger.warning("Failed to save session replay: %s", exc)
        return None


def _loaded_mapping_items(items: list[Any] | None) -> list[Any]:
    """Normalize saved mapping rows into attribute-accessible objects."""
    normalized: list[Any] = []
    for item in items or []:
        if isinstance(item, dict):
            normalized.append(
                SimpleNamespace(
                    source_element=item.get("source_element", ""),
                    target_element=item.get("target_element", ""),
                    mechanism=item.get("mechanism", ""),
                )
            )
        else:
            normalized.append(item)
    return normalized


def _loaded_cost_breakdown(cost_data: dict[str, Any] | None) -> Any:
    """Normalize cost breakdown data from a saved report."""
    payload = cost_data or {}
    decomposition = float(payload.get("decomposition", 0.0) or 0.0)
    search = float(payload.get("search", 0.0) or 0.0)
    score = float(payload.get("scoring", 0.0) or 0.0)
    translation = float(payload.get("translation", 0.0) or 0.0)
    verification = float(payload.get("verification", 0.0) or 0.0)
    total = float(
        payload.get("total", decomposition + search + score + translation + verification) or 0.0
    )
    return SimpleNamespace(
        decomposition_cost=decomposition,
        search_cost=search,
        scoring_cost=score,
        translation_cost=translation,
        verification_cost=verification,
        total=total,
    )


def _loaded_report(report_data: dict[str, Any], meta: dict[str, Any] | None = None) -> Any:
    """Rehydrate a saved invention report into the attribute shape used by the REPL."""
    payload = dict(report_data)
    top_data = payload.get("top_invention") or {}
    alternatives_data = payload.get("alternatives") or []
    cost_breakdown = _loaded_cost_breakdown(payload.get("cost_breakdown"))
    lens_engine_payload = payload.get("lens_engine")
    pantheon_payload = payload.get("pantheon")

    def _translation_from(data: dict[str, Any]) -> Any:
        return SimpleNamespace(
            architecture=data.get("architecture", ""),
            limitations=list(data.get("limitations", []) or []),
            key_insight=data.get("key_insight", ""),
            implementation_notes=data.get("implementation_notes", ""),
            mapping=_loaded_mapping_items(data.get("mapping")),
            source_candidate=SimpleNamespace(
                domain_distance=float(
                    data.get("domain_distance", data.get("novelty_score", 0.0) or 0.0) or 0.0
                ),
                structural_fidelity=float(data.get("structural_fidelity", 0.0) or 0.0),
            ),
        )

    top_translation = _translation_from(top_data)
    top_invention = None
    if top_data:
        top_invention = SimpleNamespace(
            invention_name=top_data.get("name", "Loaded invention"),
            source_domain=top_data.get("source_domain", "Unknown"),
            novelty_score=float(top_data.get("novelty_score", 0.0) or 0.0),
            structural_validity=float(top_data.get("structural_fidelity", 0.0) or 0.0),
            feasibility_rating=top_data.get("feasibility", "N/A"),
            verdict=top_data.get("verdict", "UNKNOWN"),
            translation=top_translation,
            adversarial_result=top_data.get("adversarial_critique"),
            validity_notes=top_data.get("validity_notes", ""),
            recommended_next_steps=list(top_data.get("recommended_next_steps", []) or []),
            trace=None,
        )

    alternatives: list[Any] = []
    for alt in alternatives_data:
        alt_translation = _translation_from(alt)
        alternatives.append(
            SimpleNamespace(
                invention_name=alt.get("name", "Alternative invention"),
                source_domain=alt.get("source_domain", "Unknown"),
                novelty_score=float(alt.get("novelty_score", 0.0) or 0.0),
                structural_validity=float(alt.get("structural_fidelity", 0.0) or 0.0),
                feasibility_rating=alt.get("feasibility", "N/A"),
                verdict=alt.get("verdict", "UNKNOWN"),
                translation=alt_translation,
                adversarial_result=alt.get("adversarial_critique"),
                validity_notes=alt.get("validity_notes", ""),
                recommended_next_steps=list(alt.get("recommended_next_steps", []) or []),
                trace=None,
            )
        )

    report = SimpleNamespace(
        problem=meta.get("problem", payload.get("problem", ""))
        if meta
        else payload.get("problem", ""),
        structure=SimpleNamespace(
            native_domain=payload.get("native_domain", "N/A"),
            mathematical_shape=payload.get("mathematical_shape", "Not available"),
        ),
        top_invention=top_invention,
        alternative_inventions=alternatives,
        verified_inventions=[inv for inv in [top_invention, *alternatives] if inv is not None],
        cost_breakdown=cost_breakdown,
        total_duration_seconds=float(payload.get("total_duration_seconds", 0.0) or 0.0),
        model_config=payload.get("models", {}) or {},
        total_cost_usd=cost_breakdown.total,
        lens_engine_state=(
            __import__(
                "hephaestus.lenses.state", fromlist=["LensEngineState"]
            ).LensEngineState.from_dict(lens_engine_payload)
            if isinstance(lens_engine_payload, dict)
            else None
        ),
        pantheon_state=(
            __import__(
                "hephaestus.pantheon.models", fromlist=["PantheonState"]
            ).PantheonState.from_dict(pantheon_payload)
            if isinstance(pantheon_payload, dict)
            else None
        ),
        to_dict=lambda: payload,
    )
    return report


def _loaded_entry(
    report_data: dict[str, Any], meta: dict[str, Any] | None = None
) -> InventionEntry:
    """Create an InventionEntry from saved JSON."""
    meta = meta or {}
    report = _loaded_report(report_data, meta=meta)
    return InventionEntry(
        problem=str(meta.get("problem", report.problem)),
        report=report,
        timestamp=float(meta.get("timestamp", time.time()) or time.time()),
        label=str(meta.get("slug", "")),
        refined=bool(meta.get("refined", False)),
    )


async def _cmd_load(console: Console, state: SessionState, args: str) -> None:
    """Load a previously saved invention or session from disk."""
    if not args.strip():
        console.print(f"  [{AMBER}]Usage:[/] /load <name or path>\n")
        console.print("  [dim]Tip: use /history to see saved inventions.[/]\n")
        return

    query = args.strip()
    target = _find_saved_file(query)

    if not target:
        print_error(
            console,
            f"No saved invention matching '{query}'.",
            hint="Use /history to browse saved files.",
        )
        return

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        print_error(
            console,
            f"Could not read {target.name}.",
            hint="Make sure the file contains valid JSON.",
        )
        return

    # Detect typed Session transcript (has "meta" with "id" and "transcript")
    if "meta" in data and "transcript" in data and "id" in data.get("meta", {}):
        loaded_session = Session.from_dict(data)
        state.session = loaded_session
        state.context_items = list(loaded_session.pinned_context)
        state.last_loaded_path = target
        n_entries = len(loaded_session.transcript)
        n_inv = len(loaded_session.inventions)
        gate_summary = None
        if loaded_session.reference_lots:
            from hephaestus.session.reference_lots import (
                default_probe_factory,
                evaluate_resume_gate,
            )

            probe = default_probe_factory(
                workspace_root=str(state.workspace_root) if state.workspace_root else None,
                active_tools=set(loaded_session.active_tools),
                permission_checker=lambda tool_name: True,  # REPL resume check is advisory here
                lens_engine_state=loaded_session.lens_engine_state,
            )
            gate = evaluate_resume_gate(loaded_session.reference_lots, probe)
            gate_summary = gate.summary()
        console.print(
            f"  [{GREEN}]\u2713[/] Loaded session transcript"
            f" ({n_entries} entries) from [dark_orange]{target.name}[/]"
        )
        if n_inv:
            console.print(f"  [dim]{n_inv} invention snapshot(s) in session.[/]")
        if gate_summary:
            console.print(f"  [dim]{gate_summary}[/]")
        console.print()
        return

    # Detect if it's a session replay (has "inventions" list) or a single invention
    if "inventions" in data and isinstance(data["inventions"], list):
        count = len(data["inventions"])
        loaded_entries = [
            _loaded_entry(
                inv.get("report", {}),
                meta={
                    "problem": inv.get("problem", ""),
                    "timestamp": inv.get("timestamp", time.time()),
                    "refined": inv.get("refined", False),
                    "slug": inv.get("slug", ""),
                },
            )
            for inv in data["inventions"]
        ]

        state.inventions = loaded_entries
        state.current_idx = len(loaded_entries) - 1 if loaded_entries else -1
        state.start_time = time.time() - float(data.get("session_duration_s", 0.0) or 0.0)
        state.config.backend = data.get("backend", state.config.backend)
        state.config.default_model = data.get("model", state.config.default_model)
        state.config.depth = data.get("depth", state.config.depth)
        state.config.candidates = data.get("candidates", state.config.candidates)
        state.total_cost_usd = float(data.get("total_cost_usd", 0.0) or 0.0)
        state.context_items = list(data.get("context_items", []) or [])
        state.total_calls = len(loaded_entries)
        state.total_input_tokens = 0
        state.total_output_tokens = 0
        state.last_loaded_path = target

        console.print(
            f"  [{GREEN}]\u2713[/] Loaded session with {count} inventions from [dark_orange]{target.name}[/]"
        )
        if state.current and state.current.report.top_invention:
            name = state.current.report.top_invention.invention_name
            console.print(f"  [dim]Current invention:[/] [{AMBER}]{name}[/]")
        console.print(
            "  [dim]Use /history to browse, [dark_orange]1[/] for the active report, or /compare to review recent work.[/]"
        )
        console.print()
    else:
        meta = data.get("_meta", {})
        entry = _loaded_entry(data, meta=meta)
        state.inventions.append(entry)
        state.current_idx = len(state.inventions) - 1
        state.last_loaded_path = target

        top = entry.report.top_invention
        name = top.invention_name if top else "N/A"
        source = top.source_domain if top else "N/A"
        novelty = top.novelty_score if top else 0
        console.print(f"  [{GREEN}]\u2713[/] Loaded from [dark_orange]{target.name}[/]")
        console.print(f"  [{AMBER}]Invention:[/] {name}")
        console.print(
            f"  [dim]Source:[/] [{EMBER}]{source}[/]  [dim]Novelty:[/] [{GREEN}]{novelty}[/]"
        )
        console.print(f"  [dim]Problem:[/] {entry.problem[:80]}")
        console.print(
            "  [dim]It is now the active invention. Type [dark_orange]1[/] for the full report or /export to save a new copy.[/]"
        )
        console.print()


def _find_saved_file(query: str) -> Path | None:
    """Find a saved JSON file by name or fuzzy match within Hephaestus dirs."""
    explicit = Path(query).expanduser()
    if explicit.suffix == ".json" and explicit.exists() and explicit.is_file():
        return explicit

    sanitized = re.sub(r"[*?\[\]{}]", "", query).strip().replace("\\", "/")
    if not sanitized:
        return None

    # Try exact filename in inventions dir
    if INVENTIONS_DIR.exists():
        direct = INVENTIONS_DIR / sanitized
        if direct.exists() and direct.suffix == ".json":
            return direct
        candidate = INVENTIONS_DIR / f"{sanitized}.json"
        if candidate.exists():
            return candidate

        matches = sorted(INVENTIONS_DIR.glob(f"*{sanitized}*.json"), reverse=True)
        if matches:
            return matches[0]

    # Try sessions dir too
    if SESSIONS_DIR.exists():
        matches = sorted(SESSIONS_DIR.glob(f"*{sanitized}*.json"), reverse=True)
        if matches:
            return matches[0]

    return None


async def _cmd_history_v2(console: Console, state: SessionState, args: str) -> None:
    """List inventions: session first, then saved on disk, with optional search."""
    search_term = args.strip().lower()

    # Collect session inventions
    entries: list[dict[str, Any]] = []
    for i, inv in enumerate(state.inventions):
        top = inv.report.top_invention
        entries.append(
            {
                "idx": i + 1,
                "source": "session",
                "name": top.invention_name if top else "(no invention)",
                "domain": top.source_domain if top else "N/A",
                "novelty": top.novelty_score if top else 0.0,
                "cost": inv.report.total_cost_usd,
                "problem": inv.problem,
                "refined": inv.refined,
                "date": datetime.fromtimestamp(inv.timestamp, tz=UTC).strftime("%Y-%m-%d"),
                "active": i == state.current_idx,
            }
        )

    # Collect saved inventions from disk (only if no session inventions or searching)
    if INVENTIONS_DIR.exists():
        for f in sorted(INVENTIONS_DIR.glob("*.json"), reverse=True)[:20]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                top_inv = data.get("top_invention", {})
                meta = data.get("_meta", {})
                name = top_inv.get("name", "N/A") if top_inv else "N/A"
                # Skip if already in session (by name match)
                if any(e["name"] == name and e["source"] == "session" for e in entries):
                    continue
                entries.append(
                    {
                        "idx": None,
                        "source": "disk",
                        "name": name,
                        "domain": top_inv.get("source_domain", "N/A") if top_inv else "N/A",
                        "novelty": top_inv.get("novelty_score", 0) if top_inv else 0,
                        "cost": data.get("cost_breakdown", {}).get("total", 0),
                        "problem": meta.get("problem", data.get("problem", "")),
                        "refined": meta.get("refined", False),
                        "date": f.stem[:10],
                        "active": False,
                        "filename": f.name,
                    }
                )
            except (json.JSONDecodeError, OSError, KeyError) as exc:
                logger.warning("Skipping unreadable invention file %s: %s", f.name, exc)
                continue

    # Filter by search term
    if search_term:
        entries = [
            e
            for e in entries
            if search_term in e.get("name", "").lower()
            or search_term in e.get("domain", "").lower()
            or search_term in e.get("problem", "").lower()
        ]

    if not entries:
        if search_term:
            console.print(f"  [dim]No inventions matching '{search_term}'.[/]")
            console.print(
                "  [dim]Run [dark_orange]/history[/][dim] with no filter to browse everything.[/]\n"
            )
        else:
            console.print("  [dim]No inventions yet in this session or on disk.[/]")
            console.print(
                "  [dim]Type a problem to start, or use [dark_orange]/load <name|path>[/] to restore saved work.[/]\n"
            )
        return

    session_names = [
        str(entry["name"])
        for entry in entries
        if entry["source"] == "session" and entry.get("name")
    ]
    if session_names:
        console.print(f"  [dim]Session inventions:[/] {', '.join(session_names[:4])}")

    table = Table(box=box.SIMPLE_HEAD, padding=(0, 2), show_header=True)
    table.add_column("#", style=EMBER, width=4)
    table.add_column("Invention", style=AMBER, max_width=35)
    table.add_column("Source Domain", style=DIM, max_width=20)
    table.add_column("Novelty", style=GREEN, justify="right", width=8)
    table.add_column("Cost", style=DIM, justify="right", width=10)
    table.add_column("Date", style=DIM, width=10)
    table.add_column("", style=DIM, width=8)

    for e in entries:
        marker = "[bold green]>[/]" if e["active"] else ""
        idx_str = str(e["idx"]) if e["idx"] else "-"
        tag = "[dim](refined)[/]" if e["refined"] else ""
        if e["source"] == "disk":
            tag = "[dim](saved)[/]"

        table.add_row(
            f"{marker}{idx_str}",
            str(e["name"])[:35],
            str(e["domain"])[:20],
            f"{e['novelty']:.2f}" if isinstance(e["novelty"], (int, float)) else str(e["novelty"]),
            f"${e['cost']:.4f}" if isinstance(e["cost"], (int, float)) else str(e["cost"]),
            str(e["date"]),
            tag,
        )

    console.print()
    title = f"[{GOLD}]History[/]"
    if search_term:
        title += f"  [{DIM}](search: {search_term})[/]"
    console.print(Panel(table, title=title, border_style="yellow", expand=False))
    console.print()


async def _cmd_compare(console: Console, state: SessionState, args: str) -> None:
    """Side-by-side comparison of inventions in the current session."""
    if len(state.inventions) < 2:
        n = len(state.inventions)
        if n == 0:
            console.print(
                "  [dim]No inventions yet. Describe a problem to generate your first one.[/]"
            )
            console.print(
                "  [dim]You can also restore saved work with [dark_orange]/load <name|path>[/][dim].[/]\n"
            )
        else:
            console.print(
                "  [dim]Only 1 invention so far. Describe another problem to unlock comparison.[/]\n"
            )
        return

    # Compare last 4 inventions max
    recent = state.inventions[-4:]

    table = Table(
        box=box.ROUNDED,
        padding=(0, 2),
        show_header=True,
        border_style="yellow",
    )
    table.add_column("Attribute", style=AMBER, no_wrap=True)

    for i, inv in enumerate(recent, 1):
        top = inv.report.top_invention
        col_name = f"#{i} " + (top.invention_name[:20] if top else "N/A")
        table.add_column(col_name, style="white", max_width=28)

    # Build rows
    rows: list[tuple[str, ...]] = []

    # Problem
    row = ["Problem"]
    for inv in recent:
        row.append(inv.problem[:35] + ("..." if len(inv.problem) > 35 else ""))
    rows.append(tuple(row))

    # Source domain
    row = ["Source Domain"]
    for inv in recent:
        top = inv.report.top_invention
        row.append(f"[{EMBER}]{top.source_domain}[/]" if top else "N/A")
    rows.append(tuple(row))

    # Novelty
    row = ["Novelty"]
    for inv in recent:
        top = inv.report.top_invention
        score = top.novelty_score if top else 0
        row.append(f"[{GREEN}]{score:.2f}[/]")
    rows.append(tuple(row))

    # Feasibility
    row = ["Feasibility"]
    for inv in recent:
        top = inv.report.top_invention
        feas = top.feasibility_rating if top else "N/A"
        row.append(f"[{EMBER}]{feas}[/]")
    rows.append(tuple(row))

    # Verdict
    row = ["Verdict"]
    for inv in recent:
        top = inv.report.top_invention
        verdict = top.verdict if top else "N/A"
        color = GREEN if verdict == "NOVEL" else AMBER
        row.append(f"[{color}]{verdict}[/]")
    rows.append(tuple(row))

    # Cost
    row = ["Cost (USD)"]
    for inv in recent:
        row.append(f"${inv.report.total_cost_usd:.4f}")
    rows.append(tuple(row))

    # Duration
    row = ["Duration"]
    for inv in recent:
        row.append(f"{inv.report.total_duration_seconds:.1f}s")
    rows.append(tuple(row))

    # Key insight
    row = ["Key Insight"]
    for inv in recent:
        top = inv.report.top_invention
        insight = ""
        if top and hasattr(top.translation, "key_insight"):
            insight = top.translation.key_insight[:40]
            if len(top.translation.key_insight) > 40:
                insight += "..."
        row.append(f"[dim]{insight}[/]" if insight else "[dim]-[/]")
    rows.append(tuple(row))

    for r in rows:
        table.add_row(*r)

    console.print()
    console.print(Panel(table, title=f"[{GOLD}]Side-by-Side Comparison[/]", border_style="yellow"))
    console.print()


# ---------------------------------------------------------------------------
# Phase 4: /export pdf support
# ---------------------------------------------------------------------------


async def _cmd_export_v2(console: Console, state: SessionState, args: str) -> None:
    """Export current invention as markdown, json, text, or pdf."""
    report = state.current_report
    if not report:
        console.print("  [dim]No current invention to export.[/]\n")
        return

    fmt = args.strip().lower() or "markdown"
    if fmt not in VALID_EXPORT_FORMATS:
        console.print(f"  [{RED}]Unknown export format '{fmt}'.[/]")
        console.print(f"  [dim]Choose one of:[/] {', '.join(VALID_EXPORT_FORMATS)}\n")
        return
    entry = state.current
    if entry is None:
        console.print("  [dim]No current invention to export.[/]\n")
        return

    ensure_dirs()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    slug = entry.slug

    from hephaestus.cli.main import _bridge_report
    from hephaestus.output.formatter import OutputFormatter

    fmt_report = _bridge_report(report)
    formatter = OutputFormatter()

    try:
        if fmt == "json":
            content = formatter.to_json(fmt_report)
            path = INVENTIONS_DIR / f"{date_str}-{slug}.json"
            path.write_text(content, encoding="utf-8")
        elif fmt == "text":
            content = formatter.to_plain(fmt_report)
            path = INVENTIONS_DIR / f"{date_str}-{slug}.txt"
            path.write_text(content, encoding="utf-8")
        elif fmt == "pdf":
            md_content = formatter.to_markdown(fmt_report)
            path = INVENTIONS_DIR / f"{date_str}-{slug}.pdf"
            try:
                from weasyprint import HTML

                html_body = _md_to_simple_html(md_content)
                html_str = (
                    "<html><head><style>"
                    "body{font-family:sans-serif;max-width:700px;margin:auto;padding:40px;}"
                    "h1{color:#b8860b;}h2{color:#666;}h3{color:#888;}"
                    "pre{background:#f5f5f5;padding:12px;border-radius:4px;}"
                    "code{background:#f0f0f0;padding:2px 4px;}"
                    "li{margin:4px 0;}"
                    "</style></head><body>"
                    f"{html_body}</body></html>"
                )
                HTML(string=html_str).write_pdf(str(path))
            except ImportError:
                path = INVENTIONS_DIR / f"{date_str}-{slug}-export.md"
                path.write_text(md_content, encoding="utf-8")
                print_warning(
                    console,
                    "weasyprint not installed. Saved as markdown instead. Install with: pip install weasyprint",
                )
        else:
            content = formatter.to_markdown(fmt_report)
            path = INVENTIONS_DIR / f"{date_str}-{slug}.md"
            path.write_text(content, encoding="utf-8")
    except OSError:
        print_error(
            console, "Export failed.", hint="Check write permissions for ~/.hephaestus/inventions."
        )
        return

    print_success(console, f"Exported to [dark_orange]{path}[/]")


def _md_to_simple_html(md: str) -> str:
    """Minimal markdown to HTML (no external dependency needed)."""
    import html as html_mod

    lines = md.split("\n")
    html_lines: list[str] = []
    in_code = False
    in_list = False

    for line in lines:
        if line.startswith("```"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_code:
                html_lines.append("</pre>")
            else:
                html_lines.append("<pre>")
            in_code = not in_code
            continue
        if in_code:
            html_lines.append(html_mod.escape(line))
            continue
        if line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{html_mod.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html_mod.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{html_mod.escape(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html_mod.escape(line[2:])}</li>")
        elif line.strip():
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{html_mod.escape(line)}</p>")
        elif in_list:
            html_lines.append("</ul>")
            in_list = False

    if in_code:
        html_lines.append("</pre>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


# ---------------------------------------------------------------------------
# Phase 4: Tab completion
# ---------------------------------------------------------------------------

ALL_COMMANDS = [
    "/help",
    "/status",
    "/quit",
    "/exit",
    "/clear",
    "/model",
    "/backend",
    "/usage",
    "/cost",
    "/refine",
    "/alternatives",
    "/deeper",
    "/domain",
    "/candidates",
    "/trace",
    "/export",
    "/context",
    "/save",
    "/load",
    "/history",
    "/compare",
    "/intensity",
    "/mode",
    "/todo",
    "/plan",
    # ForgeBase
    "/vault",
    "/ask",
    "/fuse",
    "/ingest",
    "/fb-lint",
    "/fb-compile",
    "/workbook",
    "/fb-export",
]


class _CommandCompleter:
    """Simple readline-based tab completer for /commands."""

    def __init__(self, commands: list[str]) -> None:
        self._commands = sorted(commands)
        self._matches: list[str] = []

    def complete(self, text: str, state_idx: int) -> str | None:
        if state_idx == 0:
            if text.startswith("/"):
                self._matches = [c for c in self._commands if c.startswith(text)]
            else:
                self._matches = []
        return self._matches[state_idx] if state_idx < len(self._matches) else None


def _setup_readline() -> None:
    """Install readline tab completion for /commands."""
    try:
        import readline
    except ImportError:
        return
    completer = _CommandCompleter(ALL_COMMANDS)
    readline.set_completer(completer.complete)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" \t\n")


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------


def _closest_command(name: str) -> str | None:
    """Return the closest command name by edit distance, or None if too distant."""
    from difflib import get_close_matches

    # Collect all known names and aliases from the registry
    all_names: list[str] = []
    for cmd in _registry.list_commands():
        all_names.append(cmd.name)
        all_names.extend(cmd.aliases)
    matches = get_close_matches(name, all_names, n=1, cutoff=0.5)
    return matches[0] if matches else None


COMMANDS: dict[str, Any] = {
    "help": _cmd_help,
    "status": _cmd_status,
    "history": _cmd_history_v2,
    "model": _cmd_model,
    "backend": _cmd_backend,
    "usage": _cmd_usage,
    "cost": _cmd_cost,
    "clear": _cmd_clear,
    "quit": _cmd_quit,
    "exit": _cmd_quit,
    "alternatives": _cmd_alternatives,
    "trace": _cmd_trace,
    "export": _cmd_export_v2,
    "candidates": _cmd_candidates,
    "refine": _cmd_refine,
    "domain": _cmd_domain,
    "deeper": _cmd_deeper,
    "context": _cmd_context,
    # Phase 3
    "save": _cmd_save,
    "load": _cmd_load,
    "compare": _cmd_compare,
    # V2 controls
    "intensity": _cmd_intensity,
    "mode": _cmd_mode,
    # Working memory
    "todo": _cmd_todo,
    # Workspace commands
    "read": _cmd_read,
    "tree": _cmd_tree,
    "grep": _cmd_grep,
    "find": _cmd_find,
    "edit": _cmd_edit,
    "ws": _cmd_ws,
    "workspace": _cmd_ws,
    "invent": _cmd_invent,
    # ForgeBase commands (lazy-imported handlers)
    "vault": None,  # set below
    "ask": None,
    "fuse": None,
    "ingest": None,
    "fb-lint": None,
    "fb-compile": None,
    "workbook": None,
    "fb-export": None,
}


# Wire ForgeBase handlers — lazy import to avoid pulling ForgeBase at REPL startup
def _init_forgebase_handlers() -> None:
    from hephaestus.cli.forgebase_commands import (
        _cmd_ask,
        _cmd_compile,
        _cmd_fb_export,
        _cmd_fuse,
        _cmd_ingest,
        _cmd_lint,
        _cmd_vault,
        _cmd_workbook,
    )

    COMMANDS["vault"] = _cmd_vault
    COMMANDS["ask"] = _cmd_ask
    COMMANDS["fuse"] = _cmd_fuse
    COMMANDS["ingest"] = _cmd_ingest
    COMMANDS["fb-lint"] = _cmd_lint
    COMMANDS["fb-compile"] = _cmd_compile
    COMMANDS["workbook"] = _cmd_workbook
    COMMANDS["fb-export"] = _cmd_fb_export
    # Aliases
    COMMANDS["v"] = _cmd_vault
    COMMANDS["wb"] = _cmd_workbook


_init_forgebase_handlers()

# Canonical command registry (shared with commands.py)
_registry = default_registry()


# ---------------------------------------------------------------------------
# Pipeline runner (reused from main.py internals)
# ---------------------------------------------------------------------------


def _build_genesis_config_from_session(state: SessionState) -> Any:
    """Build a GenesisConfig from the current session state."""
    from hephaestus.core.genesis import GenesisConfig

    cfg = state.config
    backend = cfg.backend
    selected_model = cfg.default_model  # User's /model choice

    # For subscription backends: use the selected model for ALL stages
    if backend in ("agent-sdk", "claude-max", "claude-cli", "codex-cli"):
        return GenesisConfig(
            decompose_model=selected_model,
            search_model=selected_model,
            score_model=selected_model,
            translate_model=selected_model,
            attack_model=selected_model,
            defend_model=selected_model,
            depth=cfg.depth,
            domain_hint=getattr(cfg, "domain", None) or getattr(cfg, "domain_hint", None),
            exploration_mode=getattr(cfg, "exploration_mode", "standard").lower(),
            pressure_translate_enabled=getattr(cfg, "pressure_translate_enabled", True),
            pressure_search_mode=getattr(cfg, "pressure_search_mode", "adaptive").lower(),
            use_claude_max=(backend == "claude-max"),
            use_claude_cli=(backend == "claude-cli"),
            use_codex_cli=(backend == "codex-cli"),
            use_agent_sdk=(backend == "agent-sdk"),
            num_candidates=cfg.candidates,
            use_interference_in_translate=True,
            divergence_intensity=getattr(cfg, "divergence_intensity", "STANDARD"),
            output_mode=getattr(cfg, "output_mode", "MECHANISM"),
            use_branchgenome_v1=getattr(cfg, "use_branchgenome_v1", False),
            use_adaptive_lens_engine=getattr(cfg, "use_adaptive_lens_engine", True),
            allow_lens_bundle_fallback=getattr(cfg, "allow_lens_bundle_fallback", True),
            enable_derived_lens_composites=getattr(cfg, "enable_derived_lens_composites", True),
            use_pantheon_mode=getattr(cfg, "use_pantheon_mode", False),
            pantheon_max_rounds=getattr(cfg, "pantheon_max_rounds", 4),
            pantheon_require_unanimity=getattr(cfg, "pantheon_require_unanimity", True),
            pantheon_allow_fail_closed=getattr(cfg, "pantheon_allow_fail_closed", True),
            pantheon_resolution_mode=getattr(cfg, "pantheon_resolution_mode", "TASK_SENSITIVE"),
            pantheon_max_survivors_to_council=getattr(cfg, "pantheon_max_survivors_to_council", 2),
            pantheon_athena_model=getattr(cfg, "pantheon_athena_model", None),
            pantheon_hermes_model=getattr(cfg, "pantheon_hermes_model", None),
            pantheon_apollo_model=getattr(cfg, "pantheon_apollo_model", None),
            transliminality_enabled=getattr(cfg, "transliminality_enabled", False),
            olympus_enabled=getattr(cfg, "olympus_enabled", True),
            agentic_mode=getattr(cfg, "agentic_mode", True),
            agentic_thinking_budget=getattr(cfg, "agentic_thinking_budget", 16_000),
            agentic_max_tool_rounds=getattr(cfg, "agentic_max_tool_rounds", 15),
        )

    if selected_model in {"opus", "gpt5", "codex", "both"}:
        from hephaestus.core.cross_model import get_model_preset

        preset_key = {"opus": "opus", "gpt5": "gpt", "codex": "codex"}.get(selected_model, "both")
        models = get_model_preset(preset_key)
        return GenesisConfig(
            anthropic_api_key=getattr(cfg, "anthropic_api_key", None),
            openai_api_key=getattr(cfg, "openai_api_key", None),
            openrouter_api_key=getattr(cfg, "openrouter_api_key", None)
            if backend == "openrouter"
            else None,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            depth=cfg.depth,
            domain_hint=getattr(cfg, "domain", None) or getattr(cfg, "domain_hint", None),
            exploration_mode=getattr(cfg, "exploration_mode", "standard").lower(),
            pressure_translate_enabled=getattr(cfg, "pressure_translate_enabled", True),
            pressure_search_mode=getattr(cfg, "pressure_search_mode", "adaptive").lower(),
            num_candidates=cfg.candidates,
            use_interference_in_translate=True,
            divergence_intensity=getattr(cfg, "divergence_intensity", "STANDARD"),
            output_mode=getattr(cfg, "output_mode", "MECHANISM"),
            use_branchgenome_v1=getattr(cfg, "use_branchgenome_v1", False),
            use_adaptive_lens_engine=getattr(cfg, "use_adaptive_lens_engine", True),
            allow_lens_bundle_fallback=getattr(cfg, "allow_lens_bundle_fallback", True),
            enable_derived_lens_composites=getattr(cfg, "enable_derived_lens_composites", True),
            use_pantheon_mode=getattr(cfg, "use_pantheon_mode", False),
            pantheon_max_rounds=getattr(cfg, "pantheon_max_rounds", 4),
            pantheon_require_unanimity=getattr(cfg, "pantheon_require_unanimity", True),
            pantheon_allow_fail_closed=getattr(cfg, "pantheon_allow_fail_closed", True),
            pantheon_resolution_mode=getattr(cfg, "pantheon_resolution_mode", "TASK_SENSITIVE"),
            pantheon_max_survivors_to_council=getattr(cfg, "pantheon_max_survivors_to_council", 2),
            pantheon_athena_model=getattr(cfg, "pantheon_athena_model", None),
            pantheon_hermes_model=getattr(cfg, "pantheon_hermes_model", None),
            pantheon_apollo_model=getattr(cfg, "pantheon_apollo_model", None),
            transliminality_enabled=getattr(cfg, "transliminality_enabled", False),
            olympus_enabled=getattr(cfg, "olympus_enabled", True),
            agentic_mode=getattr(cfg, "agentic_mode", True),
            agentic_thinking_budget=getattr(cfg, "agentic_thinking_budget", 16_000),
            agentic_max_tool_rounds=getattr(cfg, "agentic_max_tool_rounds", 15),
        )

    return GenesisConfig(
        anthropic_api_key=getattr(cfg, "anthropic_api_key", None),
        openai_api_key=getattr(cfg, "openai_api_key", None),
        openrouter_api_key=getattr(cfg, "openrouter_api_key", None)
        if backend == "openrouter"
        else None,
        decompose_model=selected_model,
        search_model=selected_model,
        score_model=selected_model,
        translate_model=selected_model,
        attack_model=selected_model,
        defend_model=selected_model,
        depth=cfg.depth,
        domain_hint=getattr(cfg, "domain", None) or getattr(cfg, "domain_hint", None),
        exploration_mode=getattr(cfg, "exploration_mode", "standard").lower(),
        pressure_translate_enabled=getattr(cfg, "pressure_translate_enabled", True),
        pressure_search_mode=getattr(cfg, "pressure_search_mode", "adaptive").lower(),
        num_candidates=cfg.candidates,
        use_interference_in_translate=True,
        divergence_intensity=getattr(cfg, "divergence_intensity", "STANDARD"),
        output_mode=getattr(cfg, "output_mode", "MECHANISM"),
        use_branchgenome_v1=getattr(cfg, "use_branchgenome_v1", False),
        use_adaptive_lens_engine=getattr(cfg, "use_adaptive_lens_engine", True),
        allow_lens_bundle_fallback=getattr(cfg, "allow_lens_bundle_fallback", True),
        enable_derived_lens_composites=getattr(cfg, "enable_derived_lens_composites", True),
        use_pantheon_mode=getattr(cfg, "use_pantheon_mode", False),
        pantheon_max_rounds=getattr(cfg, "pantheon_max_rounds", 4),
        pantheon_require_unanimity=getattr(cfg, "pantheon_require_unanimity", True),
        pantheon_allow_fail_closed=getattr(cfg, "pantheon_allow_fail_closed", True),
        pantheon_resolution_mode=getattr(cfg, "pantheon_resolution_mode", "TASK_SENSITIVE"),
        pantheon_max_survivors_to_council=getattr(cfg, "pantheon_max_survivors_to_council", 2),
        pantheon_athena_model=getattr(cfg, "pantheon_athena_model", None),
        pantheon_hermes_model=getattr(cfg, "pantheon_hermes_model", None),
        pantheon_apollo_model=getattr(cfg, "pantheon_apollo_model", None),
        transliminality_enabled=getattr(cfg, "transliminality_enabled", False),
            olympus_enabled=getattr(cfg, "olympus_enabled", True),
            agentic_mode=getattr(cfg, "agentic_mode", True),
            agentic_thinking_budget=getattr(cfg, "agentic_thinking_budget", 16_000),
            agentic_max_tool_rounds=getattr(cfg, "agentic_max_tool_rounds", 15),
    )


async def _run_pipeline(
    console: Console,
    state: SessionState,
    problem: str,
    *,
    is_refinement: bool = False,
) -> None:
    """Run the Genesis pipeline and store the result in session state."""
    from hephaestus.core.genesis import Genesis, PipelineStage

    problem = _inject_workspace_context(problem, state)

    try:
        genesis_config = _build_genesis_config_from_session(state)

        # Initialize ForgeBase for transliminality + knowledge features
        _fb = getattr(state, "forgebase", None)
        if _fb is None and genesis_config.transliminality_enabled:
            try:
                from hephaestus.cli.forgebase_commands import _ensure_forgebase

                _fb = await _ensure_forgebase(state)
            except Exception as fb_exc:
                import logging as _log

                _log.getLogger(__name__).warning("ForgeBase init skipped: %s", fb_exc)

        genesis = Genesis(genesis_config, forgebase=_fb)
    except Exception as exc:
        msg = str(exc).lower()
        hint = "Check /status to verify your backend and model settings."
        if "api key" in msg or "key" in msg or "auth" in msg:
            hint = "Check your API keys: run /status or set ANTHROPIC_API_KEY / OPENAI_API_KEY."
        elif "import" in msg or "module" in msg:
            hint = "A required package may be missing. Try: pip install --upgrade hephaestus-ai"
        print_error(console, "Failed to initialize the pipeline.", hint=hint)
        return

    report: Any = None
    error_msg: str | None = None

    try:
        stage_progress = StageProgress(console)
        with stage_progress:
            async for update in genesis.invent_stream(problem):
                from hephaestus.cli.main import _handle_pipeline_update

                _handle_pipeline_update(update, stage_progress)
                if update.stage == PipelineStage.COMPLETE:
                    report = update.data
                elif update.stage == PipelineStage.FAILED:
                    error_msg = update.message
                    break
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        from hephaestus.cli.main import _error_hint

        print_error(
            console,
            "The pipeline stopped before completion.",
            hint=_error_hint(_safe_error_message(exc))
            or "Check /status, your backend credentials, and network access.",
        )
        return

    if error_msg or report is None:
        msg = error_msg or "Pipeline produced no results."
        from hephaestus.cli.main import _error_hint

        print_error(console, msg, hint=_error_hint(msg))
        return

    state.add_invention(problem, report)
    if is_refinement and state.current:
        state.current.refined = True

    # Auto-save
    if state.config.auto_save:
        path = _auto_save_invention(state)
        state.last_auto_save_path = path
        state.last_auto_save_error = None if path else "Auto-save failed."
        if path is None:
            print_warning(
                console, "Auto-save failed. You can still keep working and use /save to retry."
            )
    else:
        state.last_auto_save_path = None
        state.last_auto_save_error = None

    # Display the result
    _display_invention_result(console, state)

    # Record invention in session transcript and check auto-compaction
    if state.session is not None:
        previous_lens_state = getattr(state.session, "lens_engine_state", None)
        try:
            from hephaestus.lenses.state import LensEngineState

            report.lens_engine_state = LensEngineState.from_report(
                report,
                previous_state=previous_lens_state,
            )
            state.session.apply_lens_engine_state(report.lens_engine_state)
        except Exception as exc:
            logger.warning("Could not attach lens-engine session state: %s", exc)

        deliberation_graph = getattr(report, "deliberation_graph", None)
        if deliberation_graph is not None:
            try:
                state.session.add_deliberation_graph(deliberation_graph)
            except Exception as exc:
                logger.warning("Could not attach deliberation graph to session: %s", exc)

        inv_name = report.top_invention.invention_name if report.top_invention else "N/A"
        pantheon_state = getattr(report, "pantheon_state", None)
        pantheon_payload = (
            pantheon_state.to_dict()
            if hasattr(pantheon_state, "to_dict")
            else pantheon_state
            if isinstance(pantheon_state, dict)
            else None
        )
        state.session.add_invention(
            invention_name=inv_name,
            source_domain=(
                report.top_invention.source_domain if report.top_invention is not None else ""
            ),
            architecture=(
                getattr(getattr(report.top_invention, "translation", None), "architecture", "")
                if report.top_invention is not None
                else ""
            ),
            key_insight=(
                getattr(getattr(report.top_invention, "translation", None), "key_insight", "")
                if report.top_invention is not None
                else ""
            ),
            mapping_summary=(
                "\n".join(
                    f"{m.source_element} -> {m.target_element}"
                    for m in getattr(
                        getattr(report.top_invention, "translation", None), "mapping", []
                    )[:6]
                )
                if report.top_invention is not None
                else ""
            ),
            score=float(getattr(report.top_invention, "novelty_score", 0.0) or 0.0),
            pantheon_state=pantheon_payload if isinstance(pantheon_payload, dict) else None,
            pantheon_consensus_achieved=bool(getattr(pantheon_state, "consensus_achieved", False)),
            pantheon_final_verdict=str(getattr(pantheon_state, "final_verdict", "") or ""),
            pantheon_outcome_tier=str(getattr(pantheon_state, "outcome_tier", "") or ""),
            pantheon_resolution_mode=str(getattr(pantheon_state, "resolution_mode", "") or ""),
            pantheon_rounds=len(getattr(pantheon_state, "rounds", []) or []),
            pantheon_winning_candidate_id=str(
                getattr(pantheon_state, "winning_candidate_id", "") or ""
            ),
            deliberation_graph_id=str(getattr(deliberation_graph, "graph_id", "") or ""),
            runtime_accounting=(
                deliberation_graph.accounting.to_dict()
                if getattr(deliberation_graph, "accounting", None) is not None
                and hasattr(deliberation_graph.accounting, "to_dict")
                else None
            ),
        )
        state.session.append_entry(
            Role.ASSISTANT.value,
            f"Invention: {inv_name}",
            entry_type=EntryType.INVENTION.value,
            metadata=(
                {
                    "pantheon_consensus_achieved": bool(
                        getattr(pantheon_state, "consensus_achieved", False)
                    ),
                    "pantheon_final_verdict": str(
                        getattr(pantheon_state, "final_verdict", "") or ""
                    ),
                    "pantheon_outcome_tier": str(getattr(pantheon_state, "outcome_tier", "") or ""),
                    "pantheon_resolution_mode": str(
                        getattr(pantheon_state, "resolution_mode", "") or ""
                    ),
                    "pantheon_rounds": len(getattr(pantheon_state, "rounds", []) or []),
                }
                if pantheon_state is not None
                else {}
            ),
        )
        if should_compact(state.session):
            summary = compact_session(state.session)
            if summary.removed_entries > 0:
                console.print(
                    f"  [dim]Session compacted: {summary.removed_entries}"
                    f" older entries archived.[/]"
                )


def _auto_save_invention(state: SessionState) -> Path | None:
    """Save the current invention to ~/.hephaestus/inventions/ as JSON + markdown."""
    entry = state.current
    if not entry:
        return None
    ensure_dirs()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    slug = entry.slug

    # Find a unique filename
    json_path = INVENTIONS_DIR / f"{date_str}-{slug}.json"
    counter = 1
    while json_path.exists():
        json_path = INVENTIONS_DIR / f"{date_str}-{slug}-{counter}.json"
        counter += 1

    report = entry.report
    try:
        data = report.to_dict()
        # Add extra metadata for reload
        data["_meta"] = {
            "problem": entry.problem,
            "timestamp": entry.timestamp,
            "refined": entry.refined,
            "slug": entry.slug,
        }
        json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        # Save markdown alongside
        md_path = json_path.with_suffix(".md")
        md_content = _invention_to_markdown(entry, report)
        md_path.write_text(md_content, encoding="utf-8")

        return json_path
    except Exception as exc:
        logger.warning("Failed to save invention: %s", exc)
        return None


def _invention_to_markdown(entry: InventionEntry, report: Any) -> str:
    """Generate a markdown summary for a saved invention."""
    top = report.top_invention
    lines = [
        f"# {top.invention_name if top else 'Invention'}",
        "",
        f"**Problem:** {entry.problem}",
        f"**Source Domain:** {top.source_domain if top else 'N/A'}",
        f"**Novelty Score:** {top.novelty_score:.2f}" if top else "",
        f"**Feasibility:** {top.feasibility_rating if top else 'N/A'}",
        f"**Cost:** ${report.total_cost_usd:.4f}",
        f"**Duration:** {report.total_duration_seconds:.1f}s",
        f"**Date:** {datetime.fromtimestamp(entry.timestamp, tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if top and hasattr(top.translation, "key_insight") and top.translation.key_insight:
        lines.extend(
            [
                "## Key Insight",
                "",
                top.translation.key_insight,
                "",
            ]
        )
    if top and hasattr(top.translation, "architecture") and top.translation.architecture:
        _arch = top.translation.architecture
        if isinstance(_arch, dict):
            import json as _j

            _arch = _j.dumps(_arch, indent=2)
        elif not isinstance(_arch, str):
            _arch = str(_arch)
        lines.extend(
            [
                "## Architecture",
                "",
                _arch,
                "",
            ]
        )
    if top and hasattr(top.translation, "limitations") and top.translation.limitations:
        lines.extend(["## Limitations", ""])
        for lim in top.translation.limitations:
            lines.append(f"- {lim}")
        lines.append("")
    if top and hasattr(top, "recommended_next_steps") and top.recommended_next_steps:
        lines.extend(["## Recommended Next Steps", ""])
        for step in top.recommended_next_steps:
            lines.append(f"- {step}")
        lines.append("")
    lens_state = _maybe_attr(report, "lens_engine_state", None)
    if lens_state is not None:
        lines.extend(
            [
                "## Lens Engine",
                "",
                str(lens_state.summary()),
                "",
            ]
        )
        active_bundle = _maybe_attr(lens_state, "active_bundle", None)
        if active_bundle is not None:
            lines.append(
                f"- Active bundle: {active_bundle.bundle_id} "
                f"({active_bundle.bundle_kind}, {active_bundle.proof_status})"
            )
            lines.append(f"- Members: {', '.join(active_bundle.member_ids)}")
        for composite in _maybe_attr(lens_state, "active_composites", [])[:3]:
            lines.append(
                f"- Composite: {composite.composite_id} "
                f"(v{composite.version}) from {', '.join(composite.component_lens_ids)}"
            )
        for item in _maybe_attr(lens_state, "pending_invalidations", [])[:4]:
            lines.append(f"- Invalidation: {item.summary}")
        for item in _maybe_attr(lens_state, "recompositions", [])[-3:]:
            lines.append(f"- Recomposition: {item.summary}")
        lines.append("")
    pantheon_state = _maybe_attr(report, "pantheon_state", None)
    if pantheon_state is not None:
        lines.extend(
            [
                "## Pantheon Mode",
                "",
                f"- Resolution mode: {_maybe_attr(pantheon_state, 'resolution_mode', 'TASK_SENSITIVE')}",
                f"- Outcome tier: {_maybe_attr(pantheon_state, 'outcome_tier', 'PENDING')}",
                f"- Consensus achieved: {bool(_maybe_attr(pantheon_state, 'consensus_achieved', False))}",
                f"- Final verdict: {_maybe_attr(pantheon_state, 'final_verdict', 'UNKNOWN')}",
            ]
        )
        winning_candidate_id = _maybe_attr(pantheon_state, "winning_candidate_id", "")
        if winning_candidate_id:
            lines.append(f"- Winning candidate: {winning_candidate_id}")
        lines.append(f"- Council rounds: {len(_maybe_attr(pantheon_state, 'rounds', []) or [])}")
        for screening in _maybe_attr(pantheon_state, "screenings", [])[:4]:
            lines.append(
                f"- Pre-council screening: {screening.candidate_id} "
                f"survived={screening.survived} score={screening.priority_score:.2f}"
            )
        unresolved = _maybe_attr(pantheon_state, "unresolved_vetoes", []) or []
        for item in unresolved[:4]:
            lines.append(f"- Unresolved veto: {item}")
        caveats = _maybe_attr(pantheon_state, "caveats", []) or []
        for item in caveats[:4]:
            lines.append(f"- Caveat: {item}")
        lines.append("")
    return "\n".join(lines)


def _display_invention_result(console: Console, state: SessionState) -> None:
    """Display the invention result and post-invention menu."""
    report = state.current_report
    if not report:
        return

    top = report.top_invention
    if not top:
        console.print(f"  [{RED}]No inventions produced.[/]\n")
        return

    # Header summary
    console.print()
    console.print(f"  \u2692\ufe0f  [{GOLD}]{top.invention_name}[/]")
    console.print(f"  [dim]Source:[/] [{EMBER}]{top.source_domain}[/]")

    feas = getattr(top, "feasibility_rating", "?")
    cost = report.total_cost_usd
    dur = report.total_duration_seconds

    console.print(
        f"  [dim]Novelty:[/] [{GOLD}]{top.novelty_score:.2f}[/]  "
        f"[dim]Feasibility:[/] [{EMBER}]{feas}[/]  "
        f"[dim]Cost:[/] [{GREEN}]${cost:.4f}[/]  "
        f"[dim]Time:[/] [{EMBER}]{dur:.0f}s[/]"
    )
    lens_state = _maybe_attr(report, "lens_engine_state", None)
    if lens_state is not None:
        console.print(f"  [dim]Lens engine:[/] [dark_orange]{lens_state.summary()}[/]")
    pantheon_state = _maybe_attr(report, "pantheon_state", None)
    if pantheon_state is not None:
        console.print(
            f"  [dim]Pantheon:[/] [dark_orange]tier={_maybe_attr(pantheon_state, 'outcome_tier', 'PENDING')} "
            f"consensus={bool(_maybe_attr(pantheon_state, 'consensus_achieved', False))} "
            f"verdict={_maybe_attr(pantheon_state, 'final_verdict', 'UNKNOWN')} "
            f"rounds={len(_maybe_attr(pantheon_state, 'rounds', []) or [])}[/]"
        )
    if state.last_auto_save_path is not None:
        console.print(f"  [dim]Saved snapshot:[/] [dark_orange]{state.last_auto_save_path.name}[/]")
    console.print()

    # Post-invention menu
    console.print(f"  [{DIM}]What next?[/]")
    console.print(
        f"  [{AMBER}][1][/] View full report          [{AMBER}][4][/] Try different problem"
    )
    console.print(
        f"  [{AMBER}][2][/] Explore alternatives      [{AMBER}][5][/] Export (markdown/json/text/pdf)"
    )
    console.print(
        f"  [{AMBER}][3][/] Refine this invention     [{AMBER}][6][/] Re-run from this source domain"
    )
    console.print(f"  [{AMBER}][7][/] Agent chat about this invention")
    console.print(f"  [{DIM}]Or type a new problem to invent something else.[/]")
    console.print()


async def _handle_menu_choice(
    console: Console,
    state: SessionState,
    choice: str,
) -> bool:
    """Handle a numbered menu choice. Returns True if handled."""
    choice = choice.strip()
    if choice == "1":
        report = state.current_report
        if report:
            print_invention_report(console, report, show_trace=False, show_cost=True)
        return True
    elif choice == "2":
        await _cmd_alternatives(console, state, "")
        return True
    elif choice == "3":
        await _cmd_refine(console, state, "")
        return True
    elif choice == "4":
        state.current_idx = -1
        state.context_items.clear()
        console.print(f"  [{GREEN}]\u2713[/] Ready for a new problem.")
        console.print("  [dim]Session history is still available via /history.[/]\n")
        return True
    elif choice == "5":
        console.print(
            f"  [{DIM}]Format:[/] [dark_orange]markdown[/] | [dark_orange]json[/] | [dark_orange]text[/] | [dark_orange]pdf[/]  [{DIM}](default: markdown)[/]"
        )
        try:
            fmt = console.input(f"  [{AMBER}]export>[/] ").strip().lower() or "markdown"
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]Export cancelled.[/]\n")
            return True
        await _cmd_export_v2(console, state, fmt)
        return True
    elif choice == "6":
        report = state.current_report
        if report and report.top_invention:
            domain = report.top_invention.source_domain
            await _cmd_domain(console, state, domain)
        else:
            console.print("  [dim]No current invention.[/]\n")
        return True
    elif choice == "7":
        await _chat_about_invention(console, state)
        return True
    return False


async def _chat_about_invention(console: Console, state: SessionState) -> None:
    """Launch the tool-enabled invention chat."""
    from hephaestus.cli.agent_chat import AgentChat

    await AgentChat(console, state).run()


# ---------------------------------------------------------------------------
# Main REPL loop
# ---------------------------------------------------------------------------


async def _repl_loop(console: Console, state: SessionState) -> None:
    """The core read-eval-print loop."""
    backend_str = f"[dark_orange]{state.config.backend}[/]"
    model_str = f"[dark_orange]{state.config.default_model}[/]"
    console.print(f"  [dim]Backend:[/] {backend_str}  [dim]Model:[/] {model_str}")
    readiness, hint = _backend_status(state.config)
    if readiness != "ready":
        console.print(f"  [yellow]Backend not ready:[/] {hint}")
    console.print()
    console.print(
        "  [dim]Type a problem, and Hephaestus will search distant domains for a transferable mechanism.[/]"
    )
    console.print()
    console.print(
        "  [dim]Example:[/] [white]I need a load balancer that handles unpredictable traffic spikes[/]"
    )
    console.print(
        "  [dim]Shortcuts:[/] [dark_orange]/help[/] [dim]|[/] [dark_orange]/status[/] [dim]|[/] [dark_orange]/history[/] [dim]|[/] [dark_orange]/quit[/]"
    )
    console.print("  [dim]Use Ctrl+C to cancel a running request and Ctrl+D to leave the REPL.[/]")
    console.print()

    while True:
        try:
            prompt = _prompt_text(state)
            raw = console.input(prompt).strip()
        except EOFError:
            await _cmd_quit(console, state, "")
        except KeyboardInterrupt:
            console.print()  # newline after ^C
            continue

        if not raw:
            continue

        # Record user input in session transcript
        if state.session is not None:
            state.session.append_entry(Role.USER.value, raw)

        # ── Slash commands (via CommandRegistry) ──────────────────────
        if raw.startswith("/"):
            cmd, cmd_args = _registry.parse_command(raw)
            if cmd:
                handler = COMMANDS.get(cmd.name)
                if handler:
                    try:
                        await handler(console, state, cmd_args)
                    except SystemExit:
                        raise
                    except Exception as exc:
                        print_error(console, "That command failed.", hint=_safe_error_message(exc))
            else:
                parts = raw[1:].split(None, 1)
                cmd_name = parts[0].lower() if parts else ""
                suggestion = _closest_command(cmd_name)
                hint = (
                    f"  [dim]Did you mean[/] [dark_orange]/{suggestion}[/][dim]?[/]"
                    if suggestion
                    else "  [dim]Try /help for commands.[/]"
                )
                console.print(f"  [{RED}]Unknown command:[/] /{cmd_name}")
                console.print(f"{hint}\n")
            continue

        # ── Numbered menu choices (1-7) ────────────────────────────────
        if raw in ("1", "2", "3", "4", "5", "6", "7") and state.current is not None:
            handled = await _handle_menu_choice(console, state, raw)
            if handled:
                continue

        # ── Problem description ────────────────────────────────────────
        problem = raw
        if state.context_items:
            problem += "\n\nADDITIONAL CONTEXT:\n" + "\n".join(
                f"- {c}" for c in state.context_items
            )

        console.print()
        try:
            await _run_pipeline(console, state, problem)
        except KeyboardInterrupt:
            console.print("\n  [dim]Interrupted.[/]\n")
        except Exception as exc:
            print_error(console, "The REPL run failed.", hint=_safe_error_message(exc))


def _auto_save_session_on_exit(state: SessionState) -> None:
    """Auto-save session replay and typed transcript on exit."""
    if state.inventions:
        try:
            _save_session_replay(state)
        except Exception as exc:
            logger.warning("Auto-save session replay failed on exit: %s", exc)
    if state.session is not None:
        try:
            ensure_dirs()
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            sid = state.session.meta.id[:8]
            session_path = SESSIONS_DIR / f"{date_str}-session-{sid}.json"
            state.session.save(session_path)
        except Exception as exc:
            logger.warning("Auto-save session transcript failed on exit: %s", exc)


def run_interactive(
    console: Console,
    *,
    model: str | None = None,
    depth: int | None = None,
    candidates: int | None = None,
    layered_config: Any = None,
    workspace_root: Any = None,
) -> None:
    """
    Entry point for interactive mode.

    Called from ``main.py`` when no problem argument is given.
    Handles onboarding, config loading, and launches the async REPL loop.

    Parameters
    ----------
    workspace_root:
        If set, enables workspace mode with file read/write/edit tools
        scoped to this directory.
    """
    print_banner(console)

    # Show agent activity during pipeline runs
    import logging as _logging

    _logging.basicConfig(level=_logging.WARNING, format="  %(message)s")
    _logging.getLogger("hephaestus.deepforge.adapters.agent_sdk").setLevel(_logging.INFO)
    _logging.getLogger("hephaestus.core.genesis").setLevel(_logging.INFO)

    # Load config via LayeredConfig (if provided) or fallback
    from hephaestus.cli.config import CONFIG_PATH, _resolve_keys

    if layered_config is not None and CONFIG_PATH.exists():
        cfg = layered_config.resolve()
        _resolve_keys(cfg)
    else:
        cfg = load_config()
        if cfg is None:
            cfg = run_onboarding(console)
        else:
            _resolve_keys(cfg)

    # Apply CLI overrides (only real model names, not backend keywords)
    if model:
        model = model.lower()
        if model == "agent-sdk":
            cfg.backend = "agent-sdk"
        elif model == "claude-max":
            cfg.backend = "claude-max"
        elif model == "claude-cli":
            cfg.backend = "claude-cli"
        elif model == "codex":
            cfg.backend = "codex-cli"
            cfg.default_model = "gpt-5.4"
        elif model in {"opus", "gpt5", "both"}:
            cfg.default_model = model
            cfg.backend = "api"
        else:
            cfg.default_model = model
    if depth:
        cfg.depth = depth
    if candidates:
        cfg.candidates = candidates

    # Create typed session, todo list, and session state
    ws_name = f"workspace:{workspace_root.name}" if workspace_root else None
    session = Session(
        meta=SessionMeta(
            model=cfg.default_model,
            backend=cfg.backend,
            name=ws_name or "",
        )
    )

    # Build workspace context if workspace mode
    ws_context = None
    if workspace_root:
        try:
            from hephaestus.workspace.context import WorkspaceContext

            ws_context = WorkspaceContext.from_directory(workspace_root)
            console.print("  [dim]Workspace tools enabled: read, write, edit, search, grep[/]")
            console.print()
        except Exception as exc:
            console.print(f"  [dim yellow]⚠ Could not load workspace context: {exc}[/]")

    state = SessionState(
        config=cfg,
        session=session,
        todo_list=TodoList(),
        layered_config=layered_config,
        workspace_root=workspace_root,
        workspace_context=ws_context,
    )

    # Phase 4: Tab completion for /commands
    _setup_readline()

    try:
        asyncio.run(_repl_loop(console, state))
    except SystemExit:
        _auto_save_session_on_exit(state)
        if not state.exit_reported:
            _print_session_footer(console, state)
    except KeyboardInterrupt:
        _auto_save_session_on_exit(state)
        _print_session_footer(console, state)
    except Exception as exc:
        print_error(console, "Interactive mode crashed.", hint=_safe_error_message(exc))
        _auto_save_session_on_exit(state)
        _print_session_footer(console, state)


def _print_session_footer(console: Console, state: SessionState) -> None:
    """Print one final session summary on REPL exit."""
    dur = state.session_duration
    mins, secs = divmod(int(dur), 60)
    num = len(state.inventions)
    console.print()
    if num > 0 and state.config.auto_save:
        if state.last_auto_save_error:
            console.print(
                f"  [{AMBER}]\u26a0[/] Auto-save failed for at least one run. Use [dark_orange]/save[/] if you need another copy."
            )
        else:
            console.print(
                f"  [{GREEN}]\u2713[/] Auto-save is enabled. Saved inventions live in [dark_orange]~/.hephaestus/inventions/[/]"
            )
    console.print(
        f"  [dim]Session:[/] "
        f"[dim]{num} inventions | "
        f"${state.total_cost_usd:.4f} | {mins}m {secs:02d}s[/]\n"
    )
