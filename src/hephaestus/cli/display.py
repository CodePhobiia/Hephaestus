"""
Rich Terminal Rendering for Hephaestus CLI.

Provides beautiful Rich-based display components:
- Spinning progress for each pipeline stage
- Full ⚒️ HEPHAESTUS invention report display
- Cost summary table
- Trace display
- Color scheme: gold/amber headers, cyan UI, green success, red errors
"""

from __future__ import annotations

import time
from typing import Any

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------

GOLD = "bold yellow"
AMBER = "yellow"
CYAN = "cyan"
CYAN_BOLD = "bold cyan"
GREEN = "bold green"
RED = "bold red"
DIM = "dim"
WHITE = "white"
BLUE = "blue"
MAGENTA = "magenta"


def make_console(quiet: bool = False) -> Console:
    """Create a Rich console configured for Hephaestus output."""
    return Console(highlight=False, stderr=False)


# ---------------------------------------------------------------------------
# Header / Banner
# ---------------------------------------------------------------------------


def print_banner(console: Console) -> None:
    """Print the ⚒️ HEPHAESTUS banner."""
    banner = Text()
    banner.append("⚒️  ", style="bold")
    banner.append("HEPHAESTUS", style=GOLD)
    banner.append(" — ", style=DIM)
    banner.append("The Invention Engine", style=AMBER)

    panel = Panel(
        banner,
        border_style="yellow",
        padding=(0, 2),
        expand=False,
    )
    console.print()
    console.print(panel)
    console.print()


# ---------------------------------------------------------------------------
# Stage progress display
# ---------------------------------------------------------------------------


class StageProgress:
    """
    Manages the progress display for the 5-stage Genesis pipeline.

    Usage::

        progress = StageProgress(console)
        with progress:
            progress.start_stage(1, "Decomposing problem structure...")
            # ... do work ...
            progress.complete_stage(1)
    """

    STAGES = [
        (1, "Decompose", "Extracting abstract structural form"),
        (2, "Search", "Scanning knowledge domains"),
        (3, "Score", "Evaluating candidates"),
        (4, "Translate", "Building structural bridge"),
        (5, "Verify", "Adversarial novelty verification"),
    ]

    def __init__(self, console: Console) -> None:
        self.console = console
        self._stage_times: dict[int, float] = {}
        self._current_stage: int = 0
        self._live: Live | None = None
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=CYAN),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._tasks: dict[int, Any] = {}

    def __enter__(self) -> "StageProgress":
        self._progress.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self._progress.stop()

    def start_stage(self, stage_num: int, message: str | None = None) -> None:
        """Start displaying a stage with a spinner."""
        self._current_stage = stage_num
        self._stage_times[stage_num] = time.monotonic()

        stage_info = self.STAGES[stage_num - 1] if stage_num <= len(self.STAGES) else (stage_num, f"Stage {stage_num}", message or "")
        _, stage_name, default_msg = stage_info
        display_msg = message or default_msg

        desc = f"[{CYAN_BOLD}]Stage {stage_num}/5[/] [{AMBER}]{stage_name}[/]  [dim]{display_msg}[/]"
        task_id = self._progress.add_task(desc, total=None)
        self._tasks[stage_num] = task_id

    def complete_stage(self, stage_num: int, result_msg: str = "") -> None:
        """Mark a stage as complete with a ✓ checkmark."""
        if stage_num not in self._tasks:
            return

        elapsed = time.monotonic() - self._stage_times.get(stage_num, time.monotonic())
        stage_info = self.STAGES[stage_num - 1] if stage_num <= len(self.STAGES) else (stage_num, f"Stage {stage_num}", "")
        _, stage_name, _ = stage_info

        suffix = f"  [dim]{result_msg}[/]" if result_msg else ""
        done_desc = (
            f"[{GREEN}]✓[/] [dim]Stage {stage_num}/5[/] [{AMBER}]{stage_name}[/]"
            f"  [{DIM}]{elapsed:.1f}s[/]{suffix}"
        )
        self._progress.update(self._tasks[stage_num], description=done_desc, completed=100, total=100)

    def fail_stage(self, stage_num: int, error_msg: str = "") -> None:
        """Mark a stage as failed with a ✗ marker."""
        if stage_num not in self._tasks:
            return

        stage_info = self.STAGES[stage_num - 1] if stage_num <= len(self.STAGES) else (stage_num, f"Stage {stage_num}", "")
        _, stage_name, _ = stage_info

        fail_desc = (
            f"[{RED}]✗[/] [dim]Stage {stage_num}/5[/] [{AMBER}]{stage_name}[/]"
            f"  [{RED}]{error_msg}[/]"
        )
        self._progress.update(self._tasks[stage_num], description=fail_desc, completed=100, total=100)


# ---------------------------------------------------------------------------
# Invention report display
# ---------------------------------------------------------------------------


def print_invention_report(console: Console, report: Any, show_trace: bool = False, show_cost: bool = True) -> None:
    """
    Print the full ⚒️ HEPHAESTUS invention report to the console.

    Parameters
    ----------
    console:
        Rich console to print to.
    report:
        InventionReport from the genesis pipeline.
    show_trace:
        Whether to show the full reasoning trace.
    show_cost:
        Whether to show the cost breakdown table.
    """
    top = report.top_invention
    if not top:
        print_warning(console, "No viable invention was produced for this run.")
        return

    console.print()
    console.rule(Text("⚒️  HEPHAESTUS — Invention Report", style=GOLD), style="yellow")
    console.print()

    # ── Problem ──────────────────────────────────────────────────────────────
    _print_section(console, "PROBLEM", report.problem)

    # ── Structural Form ──────────────────────────────────────────────────────
    structure = report.structure
    _print_section(
        console,
        "STRUCTURAL FORM",
        getattr(structure, "mathematical_shape", str(structure)),
    )
    if hasattr(structure, "native_domain"):
        console.print(f"  [dim]Native domain:[/] [{CYAN}]{structure.native_domain}[/]")
    console.print()

    # ── Invention header ─────────────────────────────────────────────────────
    console.rule(style="dim yellow")
    _print_invention_header(console, top)
    console.rule(style="dim yellow")
    console.print()

    # ── Translation details ──────────────────────────────────────────────────
    _print_translation(console, top)

    # ── Where analogy breaks ─────────────────────────────────────────────────
    if hasattr(top.translation, "limitations") and top.translation.limitations:
        _print_section(
            console,
            "WHERE THE ANALOGY BREAKS",
            "\n".join(f"  • {lim}" for lim in top.translation.limitations),
        )

    # ── Adversarial verdict ──────────────────────────────────────────────────
    _print_adversarial(console, top)

    # ── Alternative inventions ───────────────────────────────────────────────
    if report.alternative_inventions:
        console.rule(style="dim yellow")
        console.print(f"\n  [{AMBER}]ALTERNATIVE INVENTIONS[/]\n")
        for i, alt in enumerate(report.alternative_inventions, start=2):
            _print_alternative(console, alt, i)

    # ── Cost breakdown ───────────────────────────────────────────────────────
    if show_cost:
        console.rule(style="dim yellow")
        print_cost_table(console, report)

    # ── Trace ────────────────────────────────────────────────────────────────
    if show_trace:
        console.rule(style="dim yellow")
        print_trace(console, report)

    console.rule(style="yellow")
    console.print()


def _print_section(console: Console, title: str, content: str) -> None:
    """Print a labeled section."""
    text = _safe_text(content, fallback="Not available.")
    console.print(f"  [{GOLD}]{title}:[/]")
    console.print(f"  {text}")
    console.print()


def _print_invention_header(console: Console, top: Any) -> None:
    """Print the primary invention's score card."""
    console.print()

    name_text = Text()
    name_text.append("  INVENTION: ", style=GOLD)
    name_text.append(top.invention_name, style=f"bold {AMBER}")
    console.print(name_text)

    src_text = Text()
    src_text.append("  SOURCE DOMAIN: ", style=GOLD)
    src_text.append(top.source_domain, style=CYAN)
    console.print(src_text)

    # Score grid
    score_table = Table.grid(padding=(0, 3))
    score_table.add_column(style=DIM)
    score_table.add_column(style=WHITE)

    dd = getattr(top.translation.source_candidate, "domain_distance", top.novelty_score)
    sf = getattr(top.translation.source_candidate, "structural_fidelity", top.structural_validity)

    score_table.add_row("  DOMAIN DISTANCE:", f"[{GREEN}]{dd:.2f}[/]")
    score_table.add_row("  STRUCTURAL FIDELITY:", f"[{GREEN}]{sf:.2f}[/]")
    score_table.add_row("  NOVELTY SCORE:", f"[{GOLD}]{top.novelty_score:.2f}[/]")
    score_table.add_row("  FEASIBILITY:", f"[{CYAN}]{top.feasibility_rating}[/]")
    score_table.add_row("  VERDICT:", _verdict_style(top.verdict))

    console.print()
    console.print(score_table)
    console.print()


def _verdict_style(verdict: str) -> str:
    """Return Rich markup for a verdict string."""
    verdict = _safe_text(verdict, fallback="UNKNOWN")
    colors = {
        "NOVEL": GREEN,
        "QUESTIONABLE": AMBER,
        "DERIVATIVE": "yellow",
        "INVALID": RED,
    }
    color = colors.get(verdict.upper(), WHITE)
    return f"[{color}]{verdict}[/]"


def _print_translation(console: Console, top: Any) -> None:
    """Print mechanism, translation mapping, and architecture."""
    trans = getattr(top, "translation", None)
    if not trans:
        print_warning(console, "Translation details were not available for this invention.")
        return

    # Key insight
    if hasattr(trans, "key_insight") and trans.key_insight:
        console.print(f"  [{GOLD}]KEY INSIGHT:[/]")
        console.print(Panel(trans.key_insight, border_style="dim yellow", padding=(0, 2)))
        console.print()

    # Architecture
    arch = getattr(trans, "architecture", None)
    if arch:
        if isinstance(arch, dict):
            import json
            arch = json.dumps(arch, indent=2)
        elif not isinstance(arch, str):
            arch = str(arch)
        console.print(f"  [{GOLD}]ARCHITECTURE:[/]")
        console.print()
        for para in arch.split("\n\n"):
            if para.strip():
                console.print(f"  {para.strip()}")
                console.print()

    # Element mapping
    if hasattr(trans, "mapping") and trans.mapping:
        console.print(f"  [{GOLD}]STRUCTURAL MAPPING:[/]")
        console.print()
        map_table = Table(box=box.SIMPLE, padding=(0, 1), show_header=True)
        map_table.add_column("Source Element", style=CYAN, no_wrap=False)
        map_table.add_column("→", style=DIM, width=3)
        map_table.add_column("Target Element", style=AMBER, no_wrap=False)
        map_table.add_column("Mechanism", style=DIM, no_wrap=False)
        for elem in trans.mapping[:8]:  # cap at 8 rows
            map_table.add_row(
                _safe_text(getattr(elem, "source_element", "")),
                "→",
                _safe_text(getattr(elem, "target_element", "")),
                _safe_text(getattr(elem, "mechanism", "")),
            )
        console.print(map_table)
        console.print()
    else:
        console.print(f"  [{DIM}]No structural mapping details were returned.[/]\n")


def _print_adversarial(console: Console, top: Any) -> None:
    """Print adversarial verification results."""
    adv = getattr(top, "adversarial_result", None)

    console.print(f"  [{GOLD}]ADVERSARIAL VERIFICATION:[/]")
    console.print()

    if isinstance(adv, str):
        console.print(f"  {adv}")
        console.print()
        return

    if adv is None:
        console.print(f"  [{DIM}]No adversarial verification details were returned.[/]\n")
        return

    fatal_flaws = list(getattr(adv, "fatal_flaws", []) or [])
    if fatal_flaws:
        console.print(f"  [{RED}]Fatal flaws:[/]")
        for flaw in fatal_flaws:
            console.print(f"  [{RED}]  ✗[/] {flaw}")
        console.print()
    else:
        console.print(f"  [{GREEN}]  ✓ No fatal flaws found[/]")
        console.print()

    structural_weaknesses = list(getattr(adv, "structural_weaknesses", []) or [])
    if structural_weaknesses:
        console.print(f"  [{AMBER}]Structural weaknesses:[/]")
        for w in structural_weaknesses:
            console.print(f"  [{AMBER}]  ⚠[/] {w}")
        console.print()

    if top.validity_notes:
        _print_section(console, "VALIDITY NOTES", top.validity_notes)

    if top.recommended_next_steps:
        console.print(f"  [{GOLD}]RECOMMENDED NEXT STEPS:[/]")
        for step in top.recommended_next_steps:
            console.print(f"  [{CYAN}]  ▸[/] {step}")
        console.print()


def _print_alternative(console: Console, alt: Any, rank: int) -> None:
    """Print a summary of an alternative invention."""
    inv_name = getattr(alt, "invention_name", "Unknown")
    src_domain = getattr(alt, "source_domain", "Unknown")
    novelty = getattr(alt, "novelty_score", 0.0)
    feasibility = getattr(alt, "feasibility_rating", "?")

    console.print(
        f"  [{AMBER}]{rank}.[/] [{CYAN_BOLD}]{inv_name}[/]  "
        f"[dim](from {src_domain})[/]"
    )
    console.print(
        f"     Novelty: [{GOLD}]{novelty:.2f}[/]  "
        f"Feasibility: [{CYAN}]{feasibility}[/]"
    )
    key_insight = getattr(alt.translation, "key_insight", "") if hasattr(alt, "translation") else ""
    if key_insight:
        console.print(f"     [dim]{key_insight[:120]}…[/]" if len(key_insight) > 120 else f"     [dim]{key_insight}[/]")
    console.print()


# ---------------------------------------------------------------------------
# Cost table
# ---------------------------------------------------------------------------


def print_cost_table(console: Console, report: Any) -> None:
    """Print a cost breakdown table."""
    console.print()
    console.print(f"  [{GOLD}]COST BREAKDOWN[/]")
    console.print()

    cost = getattr(report, "cost_breakdown", None)
    if cost is None:
        console.print(f"  [{DIM}]No cost breakdown available for this run.[/]\n")
        return

    table = Table(box=box.SIMPLE_HEAD, padding=(0, 2), show_header=True)
    table.add_column("Stage", style=AMBER, no_wrap=True)
    table.add_column("Cost (USD)", style=GREEN, justify="right")

    stage_costs = [
        ("Decompose", cost.decomposition_cost),
        ("Search", cost.search_cost),
        ("Score", cost.scoring_cost),
        ("Translate", cost.translation_cost),
        ("Verify", cost.verification_cost),
    ]

    for name, c in stage_costs:
        if c > 0:
            table.add_row(name, f"${c:.4f}")

    table.add_section()
    table.add_row("[bold]TOTAL[/]", f"[bold green]${cost.total:.4f}[/]")

    console.print(table)

    # Footer stats
    models = getattr(report, "model_config", {}) or {}
    model_str = " + ".join(sorted(set(models.values()))) if models else "N/A"
    elapsed = float(getattr(report, "total_duration_seconds", 0.0))
    console.print()
    console.print(
        f"  [dim]Models:[/] [{CYAN}]{model_str}[/]  "
        f"[dim]Time:[/] [{CYAN}]{elapsed:.1f}s[/]"
    )
    console.print()


# ---------------------------------------------------------------------------
# Trace display
# ---------------------------------------------------------------------------


def print_trace(console: Console, report: Any) -> None:
    """Print the full reasoning trace (for --trace flag)."""
    console.print()
    console.print(f"  [{GOLD}]REASONING TRACE[/]")
    console.print()

    top = report.top_invention
    if not top:
        console.print("  [dim]No trace available.[/]")
        return

    if hasattr(top, "trace") and top.trace:
        trace = top.trace
        console.print(f"  [dim]Attempts:[/] {getattr(trace, 'attempts', '?')}")
        console.print(f"  [dim]Pruner kills:[/] {getattr(trace, 'pruner_kills', 0)}")
        mechanisms = list(getattr(trace, "mechanisms_used", []) or [])
        console.print(f"  [dim]Mechanisms:[/] {', '.join(mechanisms) if mechanisms else 'N/A'}")
        console.print(f"  [dim]Input tokens:[/] {int(getattr(trace, 'total_input_tokens', 0)):,}")
        console.print(f"  [dim]Output tokens:[/] {int(getattr(trace, 'total_output_tokens', 0)):,}")
        console.print(f"  [dim]Wall time:[/] {float(getattr(trace, 'wall_time_seconds', 0)):.2f}s")
        console.print()

        # Interference injections
        injections = getattr(trace, "interference_injections", [])
        if injections:
            console.print(f"  [{AMBER}]Interference Injections ({len(injections)}):[/]")
            for i, inj in enumerate(injections, 1):
                lens_name = getattr(inj, "lens_name", "unknown")
                console.print(f"  [{CYAN}]  [{i}][/] [dim]Lens:[/] {lens_name}")
            console.print()

        # Pressure trace
        pressure = getattr(trace, "pressure_trace", None)
        if pressure:
            rounds = getattr(pressure, "rounds_completed", 0)
            blocked = getattr(pressure, "blocked_paths", [])
            console.print(f"  [{AMBER}]Anti-Training Pressure:[/]")
            console.print(f"  [dim]Rounds completed:[/] {rounds}")
            console.print(f"  [dim]Paths blocked:[/] {len(blocked)}")
            console.print()
    else:
        console.print("  [dim]No detailed trace available.[/]")


# ---------------------------------------------------------------------------
# Error display
# ---------------------------------------------------------------------------


def print_error(console: Console, error: str, hint: str | None = None) -> None:
    """Print a user-friendly error message."""
    text = _safe_text(error, fallback="Something went wrong.")
    console.print()
    console.print(Panel(
        Text(text, style=RED),
        title="[bold red]Error[/]",
        border_style="red",
        padding=(0, 2),
    ))
    if hint:
        console.print(f"\n  [dim]Hint:[/] {hint}")
    console.print()


def print_warning(console: Console, message: str) -> None:
    """Print a warning message."""
    console.print(f"\n  [{AMBER}]⚠[/] [dim]{message}[/]\n")


def print_success(console: Console, message: str) -> None:
    """Print a success message."""
    console.print(f"\n  [{GREEN}]✓[/] {message}\n")


# ---------------------------------------------------------------------------
# Minimal / quiet output
# ---------------------------------------------------------------------------


def print_quiet_result(console: Console, report: Any) -> None:
    """Print a minimal one-line result for --quiet mode."""
    top = report.top_invention
    if top:
        console.print(
            f"[{GOLD}]{top.invention_name}[/] "
            f"[dim](from {top.source_domain})[/] "
            f"novelty=[{GREEN}]{top.novelty_score:.2f}[/] "
            f"cost=[dim]${report.total_cost_usd:.4f}[/]"
        )
    else:
        console.print(f"[{RED}]No viable invention produced.[/]")


def _safe_text(value: Any, fallback: str = "") -> str:
    """Render a value as a readable string for terminal output."""
    if value is None:
        return fallback
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or fallback
    return str(value)
