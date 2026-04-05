"""Batch invention mode — process multiple problems from a file."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for a batch invention run."""

    input_file: Path
    output_dir: Path
    format: str = "markdown"
    depth: int = 3
    model: str = "both"
    intensity: str = "STANDARD"
    output_mode: str = "MECHANISM"
    max_concurrent: int = 1


@dataclass
class BatchResultEntry:
    """Result of a single problem in a batch."""

    index: int
    problem: str
    invention_name: str = ""
    status: str = "pending"  # pending, success, failed
    error: str = ""
    output_path: str = ""
    duration_seconds: float = 0.0


@dataclass
class BatchResult:
    """Aggregate results of a batch run."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[BatchResultEntry] = field(default_factory=list)
    total_duration: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total if self.total > 0 else 0.0


def parse_problems(input_file: Path) -> list[str]:
    """Parse problems from a file — one per line, skip blanks and # comments."""
    if not input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    problems: list[str] = []
    for line in input_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        problems.append(stripped)
    return problems


async def run_batch(config: BatchConfig, console: Console) -> BatchResult:
    """Run the invention pipeline on each problem in the input file."""
    problems = parse_problems(config.input_file)
    if not problems:
        console.print("  [yellow]No problems found in input file.[/]")
        return BatchResult()

    config.output_dir.mkdir(parents=True, exist_ok=True)

    result = BatchResult(total=len(problems))
    start = time.monotonic()

    console.print(f"\n  [bold yellow]Batch run:[/] {len(problems)} problems from {config.input_file}")
    console.print(f"  [dim]Output: {config.output_dir} | Format: {config.format}[/]\n")

    for i, problem in enumerate(problems, 1):
        entry = BatchResultEntry(index=i, problem=problem)
        t0 = time.monotonic()

        console.print(f"  [{i}/{len(problems)}] {problem[:80]}{'...' if len(problem) > 80 else ''}")

        try:
            report = await _run_single(problem, config)
            entry.invention_name = getattr(report, "top_invention", None)
            if entry.invention_name and hasattr(entry.invention_name, "invention_name"):
                entry.invention_name = entry.invention_name.invention_name
            else:
                entry.invention_name = "Unknown"

            # Export
            ext = {"json": ".json", "text": ".txt"}.get(config.format, ".md")
            out_path = config.output_dir / f"invention_{i:03d}{ext}"
            _export_report(report, out_path, config.format)
            entry.output_path = str(out_path)
            entry.status = "success"
            result.succeeded += 1

            console.print(f"        [green]✓[/] {entry.invention_name}")
        except Exception as exc:
            entry.status = "failed"
            entry.error = str(exc)[:200]
            result.failed += 1
            console.print(f"        [red]✗[/] {entry.error[:80]}")

        entry.duration_seconds = time.monotonic() - t0
        result.results.append(entry)

    result.total_duration = time.monotonic() - start

    # Summary table
    _print_summary(console, result)
    return result


async def _run_single(problem: str, config: BatchConfig) -> Any:
    """Run genesis pipeline for a single problem."""
    import os

    from hephaestus.cli.main import _build_genesis_config
    from hephaestus.core.genesis import Genesis

    genesis_config = _build_genesis_config(
        model=config.model,
        depth=config.depth,
        candidates=8,
        domain=None,
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
        openai_key=os.environ.get("OPENAI_API_KEY"),
        divergence_intensity=config.intensity,
        output_mode=config.output_mode,
    )
    genesis = Genesis(genesis_config)
    return await genesis.invent(problem)


def _export_report(report: Any, path: Path, fmt: str) -> None:
    """Export an invention report to file."""
    from hephaestus.export.markdown import export_to_file

    # Bridge genesis report to formatter if needed
    try:
        from hephaestus.cli.main import _bridge_report

        fmt_report = _bridge_report(report)
    except Exception as exc:
        logger.warning("Report bridging failed, using raw report: %s", exc)
        fmt_report = report

    export_to_file(fmt_report, path)


def _print_summary(console: Console, result: BatchResult) -> None:
    """Print batch run summary table."""
    console.print()
    console.rule("[bold yellow]Batch Summary[/]", style="yellow")
    console.print()

    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("#", width=4)
    table.add_column("Problem", max_width=50)
    table.add_column("Invention", max_width=30)
    table.add_column("Status", width=8)
    table.add_column("Time", width=8, justify="right")

    for entry in result.results:
        status_str = "[green]✓[/]" if entry.status == "success" else "[red]✗[/]"
        table.add_row(
            str(entry.index),
            entry.problem[:50],
            entry.invention_name[:30] if entry.invention_name else "-",
            status_str,
            f"{entry.duration_seconds:.1f}s",
        )

    console.print(table)
    console.print()
    console.print(
        f"  [bold]Total:[/] {result.total} | "
        f"[green]Succeeded:[/] {result.succeeded} | "
        f"[red]Failed:[/] {result.failed} | "
        f"[dim]Time:[/] {result.total_duration:.1f}s | "
        f"[dim]Rate:[/] {result.success_rate:.0%}"
    )
    console.print()


__all__ = ["BatchConfig", "BatchResult", "BatchResultEntry", "parse_problems", "run_batch"]
