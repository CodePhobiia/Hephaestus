"""
Memory Transparency — surfaces what memory, instructions, and anti-memory are active.

Provides dataclasses and formatters so /status and /context commands can show
users exactly what the anti-memory system filtered, what instructions were
loaded, and what context is pinned in the current session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryReport:
    """Snapshot of all active memory state for transparency display."""

    anti_memory_hits: list[dict[str, Any]] = field(default_factory=list)
    """Each dict has keys: pattern (str), count (int), last_hit_time (float|None)."""

    loaded_instructions: list[str] = field(default_factory=list)
    """File paths of instruction files that were loaded."""

    pinned_context: list[str] = field(default_factory=list)
    """User-supplied context items pinned for the current session."""

    compaction_summaries: list[str] = field(default_factory=list)
    """Summaries produced when context was compacted."""

    active_config_sources: dict[str, str] = field(default_factory=dict)
    """Mapping of config key -> source (e.g. 'backend' -> '~/.hephaestus/config.yaml')."""

    @property
    def total_anti_memory_hits(self) -> int:
        return sum(h.get("count", 0) for h in self.anti_memory_hits)

    @property
    def has_activity(self) -> bool:
        return bool(
            self.anti_memory_hits
            or self.loaded_instructions
            or self.pinned_context
            or self.compaction_summaries
        )


def build_memory_report(
    session_state: Any,
    anti_memory: Any | None = None,
    config: Any | None = None,
) -> MemoryReport:
    """
    Collect transparency data from the session state and anti-memory system.

    Parameters
    ----------
    session_state:
        The REPL ``SessionState`` (or any object with ``context_items``,
        ``pinned``, and ``config`` attributes).  May also carry
        ``anti_memory_hits`` and ``compaction_summaries`` lists if the
        pipeline has populated them.
    anti_memory:
        An ``AntiMemory`` instance (optional).  Currently used for
        future extensions; hit data is read from *session_state*.
    config:
        Optional config object.  Falls back to ``session_state.config``.
    """
    cfg = config or getattr(session_state, "config", None)

    # -- Anti-memory hits ---------------------------------------------------
    anti_memory_hits: list[dict[str, Any]] = list(getattr(session_state, "anti_memory_hits", []))

    # -- Loaded instructions ------------------------------------------------
    loaded_instructions: list[str] = list(getattr(session_state, "loaded_instructions", []))

    # -- Pinned context -----------------------------------------------------
    pinned_context: list[str] = list(getattr(session_state, "context_items", []))

    # -- Compaction summaries -----------------------------------------------
    compaction_summaries: list[str] = list(getattr(session_state, "compaction_summaries", []))

    # -- Config sources -----------------------------------------------------
    active_config_sources: dict[str, str] = {}
    if cfg is not None:
        config_sources = getattr(cfg, "config_sources", None)
        if isinstance(config_sources, dict):
            active_config_sources = dict(config_sources)
        else:
            # Derive a minimal source map from what we can observe
            config_file = getattr(cfg, "_config_file", None)
            source_label = str(config_file) if config_file else "defaults"
            for key in ("backend", "default_model", "depth", "candidates"):
                val = getattr(cfg, key, None)
                if val is not None:
                    active_config_sources[key] = source_label

    return MemoryReport(
        anti_memory_hits=anti_memory_hits,
        loaded_instructions=loaded_instructions,
        pinned_context=pinned_context,
        compaction_summaries=compaction_summaries,
        active_config_sources=active_config_sources,
    )


def format_memory_report(report: MemoryReport) -> str:
    """
    Return a Rich-renderable string summarising active memory state.

    Intended for the ``/status`` command — compact, high-level overview.
    """
    lines: list[str] = []

    # -- Anti-memory --------------------------------------------------------
    n_patterns = len(report.anti_memory_hits)
    total_hits = report.total_anti_memory_hits
    if n_patterns:
        lines.append(f"[bold]Anti-Memory[/]  {n_patterns} pattern(s), {total_hits} total hit(s)")
    else:
        lines.append("[bold]Anti-Memory[/]  [dim]no patterns active[/]")

    # -- Instructions -------------------------------------------------------
    if report.loaded_instructions:
        lines.append(f"[bold]Instructions[/]  {len(report.loaded_instructions)} file(s) loaded")
    else:
        lines.append("[bold]Instructions[/]  [dim]none loaded[/]")

    # -- Pinned context -----------------------------------------------------
    if report.pinned_context:
        lines.append(f"[bold]Pinned Context[/]  {len(report.pinned_context)} item(s)")
    else:
        lines.append("[bold]Pinned Context[/]  [dim]none[/]")

    # -- Compaction ---------------------------------------------------------
    if report.compaction_summaries:
        lines.append(f"[bold]Compaction[/]  {len(report.compaction_summaries)} summary(ies)")
    else:
        lines.append("[bold]Compaction[/]  [dim]not triggered[/]")

    # -- Config sources -----------------------------------------------------
    if report.active_config_sources:
        sources = sorted(set(report.active_config_sources.values()))
        lines.append(f"[bold]Config Sources[/]  {', '.join(sources)}")

    return "\n".join(lines)


def format_context_report(report: MemoryReport) -> str:
    """
    Return a Rich-renderable string with detailed context / anti-memory info.

    Intended for the ``/context`` command — full detail view.
    """
    sections: list[str] = []

    # -- Anti-memory detail -------------------------------------------------
    sections.append("[bold underline]Anti-Memory Exclusions[/]")
    if report.anti_memory_hits:
        for hit in report.anti_memory_hits:
            pattern = hit.get("pattern", "???")
            count = hit.get("count", 0)
            last_time = hit.get("last_hit_time")
            time_str = _format_timestamp(last_time) if last_time else "n/a"
            sections.append(f"  [dark_orange]{pattern}[/]  hits={count}  last={time_str}")
    else:
        sections.append("  [dim]No anti-memory patterns matched this session.[/]")

    # -- Loaded instructions ------------------------------------------------
    sections.append("")
    sections.append("[bold underline]Loaded Instructions[/]")
    if report.loaded_instructions:
        for path in report.loaded_instructions:
            sections.append(f"  [green]{path}[/]")
    else:
        sections.append("  [dim]No instruction files loaded.[/]")

    # -- Pinned context -----------------------------------------------------
    sections.append("")
    sections.append("[bold underline]Pinned Context[/]")
    if report.pinned_context:
        for i, item in enumerate(report.pinned_context, 1):
            sections.append(f"  [dark_orange]{i}.[/] {item}")
    else:
        sections.append("  [dim]No context items pinned.[/]")

    # -- Compaction summaries -----------------------------------------------
    sections.append("")
    sections.append("[bold underline]Compaction History[/]")
    if report.compaction_summaries:
        for i, summary in enumerate(report.compaction_summaries, 1):
            sections.append(f"  {i}. {summary}")
    else:
        sections.append("  [dim]No compaction has occurred.[/]")

    # -- Config sources -----------------------------------------------------
    if report.active_config_sources:
        sections.append("")
        sections.append("[bold underline]Active Config Sources[/]")
        for key in sorted(report.active_config_sources):
            sections.append(f"  {key}: [dim]{report.active_config_sources[key]}[/]")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_timestamp(ts: float) -> str:
    """Format an epoch timestamp as a short human-readable string."""
    import datetime

    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
