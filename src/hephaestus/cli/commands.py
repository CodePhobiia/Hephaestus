"""Shared slash-command registry for the Hephaestus CLI.

Provides a centralised :class:`CommandRegistry` that the REPL, future TUI,
and API surfaces can all share.  The :func:`default_registry` helper returns
a pre-populated registry containing every existing REPL command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Command dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Command:
    """Metadata for a single slash command."""

    name: str
    """Canonical name without the leading ``/``."""

    aliases: list[str] = field(default_factory=list)
    """Short aliases (e.g. ``['h', '?']``)."""

    description: str = ""
    """One-line description shown in help."""

    usage: str = ""
    """Usage string, e.g. ``/refine <constraint>``."""

    category: str = "session"
    """Logical group: session, invention, config, navigation, export."""

    handler_name: str = ""
    """Method / function name on the REPL class (e.g. ``'_cmd_help'``)."""

    modes: list[str] = field(default_factory=lambda: ["all"])
    """Modes where this command is available: ``'repl'``, ``'agent'``, ``'all'``."""

    resume_safe: bool = True
    """Whether this command is safe to use during resumed sessions."""

    args_required: bool = False
    """Whether the command requires at least one argument."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SLASH_RE = re.compile(r"^/(\S+)(?:\s+(.*))?$", re.DOTALL)


class CommandRegistry:
    """Central store of :class:`Command` objects with lookup helpers."""

    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name

    # -- mutators -----------------------------------------------------------

    def register(self, command: Command) -> None:
        """Add *command* to the registry.

        Raises :class:`ValueError` on duplicate name or alias collision.
        """
        if command.name in self._commands:
            raise ValueError(f"Duplicate command name: {command.name!r}")
        if command.name in self._aliases:
            raise ValueError(
                f"Command name {command.name!r} conflicts with an existing alias"
            )

        for alias in command.aliases:
            if alias in self._aliases or alias in self._commands:
                raise ValueError(
                    f"Alias {alias!r} for command {command.name!r} "
                    "conflicts with an existing name or alias"
                )

        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    # -- queries ------------------------------------------------------------

    def get(self, name_or_alias: str) -> Optional[Command]:
        """Look up a command by its canonical *name* or any alias."""
        name_or_alias = name_or_alias.lower()
        if name_or_alias in self._commands:
            return self._commands[name_or_alias]
        canon = self._aliases.get(name_or_alias)
        if canon is not None:
            return self._commands[canon]
        return None

    def list_commands(
        self,
        mode: str = "all",
        category: Optional[str] = None,
    ) -> List[Command]:
        """Return commands filtered by *mode* and optional *category*.

        A command matches a mode if its ``modes`` list contains ``'all'`` or
        contains the requested *mode*.
        """
        out: list[Command] = []
        for cmd in self._commands.values():
            if mode != "all" and "all" not in cmd.modes and mode not in cmd.modes:
                continue
            if category is not None and cmd.category != category:
                continue
            out.append(cmd)
        return out

    def format_help(self, mode: str = "all") -> str:
        """Return Rich-markup help text grouped by category."""
        commands = self.list_commands(mode=mode)
        if not commands:
            return "[dim]No commands available.[/dim]"

        by_cat: Dict[str, list[Command]] = {}
        for cmd in commands:
            by_cat.setdefault(cmd.category, []).append(cmd)

        # Deterministic category order
        cat_order = ["session", "invention", "config", "context", "export"]
        ordered_cats = [c for c in cat_order if c in by_cat]
        ordered_cats += sorted(set(by_cat) - set(cat_order))

        lines: list[str] = []
        for cat in ordered_cats:
            lines.append(f"[bold yellow]{cat.title()}[/]")
            for cmd in sorted(by_cat[cat], key=lambda c: c.name):
                usage = cmd.usage or f"/{cmd.name}"
                desc = cmd.description
                lines.append(f"  [cyan]{usage:<26s}[/] {desc}")
            lines.append("")

        return "\n".join(lines).rstrip("\n")

    def completions(self, prefix: str, mode: str = "all") -> List[str]:
        """Return ``/name`` strings matching *prefix* (for tab-completion).

        *prefix* may or may not start with ``/``.
        """
        bare = prefix.lstrip("/").lower()
        hits: list[str] = []
        for cmd in self.list_commands(mode=mode):
            if cmd.name.startswith(bare):
                hits.append(f"/{cmd.name}")
            for alias in cmd.aliases:
                if alias.startswith(bare) and f"/{alias}" not in hits:
                    hits.append(f"/{alias}")
        return sorted(hits)

    def parse_command(self, raw: str) -> Tuple[Optional[Command], str]:
        """Parse a ``/cmd args`` string into ``(Command | None, args)``.

        Returns ``(None, '')`` for unparseable input.
        """
        raw = raw.strip()
        m = _SLASH_RE.match(raw)
        if not m:
            return None, ""
        cmd_name = m.group(1).lower()
        args = (m.group(2) or "").strip()
        return self.get(cmd_name), args


# ---------------------------------------------------------------------------
# Default registry (mirrors repl.py COMMANDS dict)
# ---------------------------------------------------------------------------

def default_registry() -> CommandRegistry:
    """Return a :class:`CommandRegistry` pre-populated with all REPL commands."""
    reg = CommandRegistry()

    # -- Session ------------------------------------------------------------
    reg.register(Command(
        name="help",
        aliases=["h", "?"],
        description="Show this help",
        usage="/help",
        category="session",
        handler_name="_cmd_help",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="status",
        aliases=[],
        description="Session info, backend readiness, and current defaults",
        usage="/status",
        category="session",
        handler_name="_cmd_status",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="quit",
        aliases=["exit", "q"],
        description="Exit interactive mode",
        usage="/quit",
        category="session",
        handler_name="_cmd_quit",
        modes=["repl"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="clear",
        aliases=[],
        description="Clear current context and prompt state",
        usage="/clear",
        category="session",
        handler_name="_cmd_clear",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="history",
        aliases=[],
        description="List session and saved inventions",
        usage="/history [search]",
        category="session",
        handler_name="_cmd_history_v2",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="compare",
        aliases=[],
        description="Compare recent inventions side by side",
        usage="/compare",
        category="session",
        handler_name="_cmd_compare",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="usage",
        aliases=[],
        description="Session runs, tokens, and cost summary",
        usage="/usage",
        category="session",
        handler_name="_cmd_usage",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="cost",
        aliases=[],
        description="Cost breakdown for the current invention",
        usage="/cost",
        category="session",
        handler_name="_cmd_cost",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))

    # -- Invention / Iteration ----------------------------------------------
    reg.register(Command(
        name="refine",
        aliases=[],
        description="Re-run the current invention with a constraint",
        usage="/refine [constraint]",
        category="invention",
        handler_name="_cmd_refine",
        modes=["all"],
        resume_safe=False,
        args_required=False,
    ))
    reg.register(Command(
        name="alternatives",
        aliases=["alt"],
        description="Show runner-up inventions from the last run",
        usage="/alternatives",
        category="invention",
        handler_name="_cmd_alternatives",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="deeper",
        aliases=[],
        description="Increase depth and retry the current problem",
        usage="/deeper [n]",
        category="invention",
        handler_name="_cmd_deeper",
        modes=["all"],
        resume_safe=False,
        args_required=False,
    ))
    reg.register(Command(
        name="domain",
        aliases=[],
        description="Re-run with a source-domain hint",
        usage="/domain <hint>",
        category="invention",
        handler_name="_cmd_domain",
        modes=["all"],
        resume_safe=False,
        args_required=True,
    ))
    reg.register(Command(
        name="trace",
        aliases=[],
        description="Show trace details from the last run",
        usage="/trace",
        category="invention",
        handler_name="_cmd_trace",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="candidates",
        aliases=[],
        description="Show or change candidate count (1-20)",
        usage="/candidates [n]",
        category="invention",
        handler_name="_cmd_candidates",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))

    # -- Config -------------------------------------------------------------
    reg.register(Command(
        name="model",
        aliases=[],
        description="Show or switch the active model",
        usage="/model [name]",
        category="config",
        handler_name="_cmd_model",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="backend",
        aliases=[],
        description="Show or switch backend",
        usage="/backend [name]",
        category="config",
        handler_name="_cmd_backend",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="intensity",
        aliases=[],
        description="Show or set divergence intensity",
        usage="/intensity [level]",
        category="config",
        handler_name="_cmd_intensity",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="mode",
        aliases=[],
        description="Show or set output mode",
        usage="/mode [mode]",
        category="config",
        handler_name="_cmd_mode",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))

    # -- Context ------------------------------------------------------------
    reg.register(Command(
        name="context",
        aliases=["ctx"],
        description="Show, add, or clear context items",
        usage="/context [add <text> | clear]",
        category="context",
        handler_name="_cmd_context",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))

    # -- Session (working memory) -------------------------------------------
    reg.register(Command(
        name="todo",
        aliases=["plan"],
        description="Show or manage the working-memory todo list",
        usage="/todo [add <text> | start <id> | done <id>]",
        category="session",
        handler_name="_cmd_todo",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))

    # -- Export / Persistence -----------------------------------------------
    reg.register(Command(
        name="export",
        aliases=[],
        description="Export as markdown, json, text, or pdf",
        usage="/export [format]",
        category="export",
        handler_name="_cmd_export_v2",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="save",
        aliases=[],
        description="Save the current invention now",
        usage="/save [name]",
        category="export",
        handler_name="_cmd_save",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="load",
        aliases=[],
        description="Load a saved invention or session replay",
        usage="/load <name|path>",
        category="export",
        handler_name="_cmd_load",
        modes=["all"],
        resume_safe=True,
        args_required=True,
    ))

    # ── Workspace commands ──────────────────────────────────────────
    reg.register(Command(
        name="read",
        aliases=["cat"],
        description="Read a file from the workspace",
        usage="/read <file_path>",
        category="workspace",
        handler_name="_cmd_read",
        modes=["repl"],
        resume_safe=True,
        args_required=True,
    ))
    reg.register(Command(
        name="tree",
        aliases=[],
        description="Show workspace directory tree",
        usage="/tree",
        category="workspace",
        handler_name="_cmd_tree",
        modes=["repl"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="grep",
        aliases=[],
        description="Search file contents in the workspace",
        usage="/grep <query>",
        category="workspace",
        handler_name="_cmd_grep",
        modes=["repl"],
        resume_safe=True,
        args_required=True,
    ))
    reg.register(Command(
        name="find",
        aliases=[],
        description="Find files by glob pattern",
        usage="/find <pattern>",
        category="workspace",
        handler_name="_cmd_find",
        modes=["repl"],
        resume_safe=True,
        args_required=False,
    ))
    reg.register(Command(
        name="edit",
        aliases=[],
        description="Edit a file (use agent chat for complex edits)",
        usage="/edit",
        category="workspace",
        handler_name="_cmd_edit",
        modes=["repl"],
        resume_safe=False,
        args_required=False,
    ))
    reg.register(Command(
        name="invent",
        aliases=["improve", "analyze"],
        description="Analyze the codebase and invent improvements",
        usage="/invent [max_count]",
        category="workspace",
        handler_name="_cmd_invent",
        modes=["repl"],
        resume_safe=False,
        args_required=False,
    ))
    reg.register(Command(
        name="ws",
        aliases=["workspace"],
        description="Show workspace status and info",
        usage="/ws",
        category="workspace",
        handler_name="_cmd_ws",
        modes=["repl"],
        resume_safe=True,
        args_required=False,
    ))

    return reg
