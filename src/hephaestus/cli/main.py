"""
Hephaestus CLI — ``heph`` command.

Usage::

    heph "describe your problem here"
    heph --depth 5 --model opus --format json "my problem"
    heph --trace --cost "a complex distributed systems challenge"
    heph --raw "a raw deepforge prompt"

All options
-----------
  --depth INT          DeepForge depth / anti-training pressure rounds (default 3)
  --model TEXT         Model to use: opus | gpt5 | both (default both)
  --format TEXT        Output format: markdown | json | text (default markdown)
  --domain TEXT        Hint for problem domain
  --trace              Show full reasoning trace
  --raw                Run deepforge only, skip genesis pipeline
  --candidates INT     Number of search candidates (default 8)
  --output PATH        Save output to file
  --cost               Show cost breakdown
  --quiet              Minimal output (one-line result)
  --version            Show version and exit
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from hephaestus import __version__
from hephaestus.cli.display import (
    StageProgress,
    make_console,
    print_banner,
    print_cost_table,
    print_error,
    print_invention_report,
    print_quiet_result,
    print_success,
    print_trace,
    print_warning,
)

# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------


def _version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"hephaestus-ai v{__version__}")
    ctx.exit()


# ---------------------------------------------------------------------------
# Main CLI command
# ---------------------------------------------------------------------------


@click.command(
    name="heph",
    help=(
        "⚒️  HEPHAESTUS — The Invention Engine.\n\n"
        "Give it a problem. Get a genuinely novel solution derived from a distant"
        " knowledge domain, with structural mapping, architecture, and novelty proof.\n\n"
        "Example:\n\n"
        '  heph "I need a load balancer that handles unpredictable traffic spikes"\n\n'
        '  heph --depth 5 --model opus --trace "a complex routing problem"'
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("problem", required=False)
@click.option(
    "--depth",
    "-d",
    default=3,
    show_default=True,
    type=click.IntRange(1, 10),
    help="Anti-training pressure depth (rounds). Higher = more novel, more cost.",
)
@click.option(
    "--model",
    "-m",
    default="both",
    show_default=True,
    type=click.Choice(["opus", "gpt5", "both"], case_sensitive=False),
    help="Model(s) to use: opus (Claude Opus), gpt5 (GPT-5.4), or both.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    default="markdown",
    show_default=True,
    type=click.Choice(["markdown", "json", "text"], case_sensitive=False),
    help="Output format for the invention report.",
)
@click.option(
    "--domain",
    default=None,
    help="Hint for the target domain (e.g. 'distributed-systems', 'biology').",
)
@click.option(
    "--trace",
    is_flag=True,
    default=False,
    help="Show the full reasoning trace (interference injections, pressure rounds, etc.).",
)
@click.option(
    "--raw",
    is_flag=True,
    default=False,
    help="Run DeepForge directly on the prompt — skip the full Genesis pipeline.",
)
@click.option(
    "--candidates",
    "-c",
    default=8,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Number of cross-domain candidates to search.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(path_type=Path),
    help="Save the report to a file (format inferred from extension or --format).",
)
@click.option(
    "--cost",
    is_flag=True,
    default=False,
    help="Show a detailed cost breakdown table.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Minimal output — print only the invention name and key stats.",
)
@click.option(
    "--version",
    "-v",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_version_callback,
    help="Show version and exit.",
)
def cli(
    problem: str | None,
    depth: int,
    model: str,
    output_format: str,
    domain: str | None,
    trace: bool,
    raw: bool,
    candidates: int,
    output: Path | None,
    cost: bool,
    quiet: bool,
) -> None:
    """Main CLI entry point."""
    console = make_console(quiet=quiet)

    # ── Validate inputs ───────────────────────────────────────────────────────
    if not problem:
        if not quiet:
            print_banner(console)
        console.print(
            "  [yellow]Provide a problem description.[/]\n\n"
            "  Example:  [cyan]heph \"I need a load balancer for traffic spikes\"[/]\n\n"
            "  Run [cyan]heph --help[/] for all options."
        )
        sys.exit(0)

    # ── API key validation ────────────────────────────────────────────────────
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    model_lower = model.lower()
    if model_lower in ("opus", "both") and not anthropic_key:
        print_error(
            console,
            "ANTHROPIC_API_KEY environment variable is not set.",
            hint="export ANTHROPIC_API_KEY=sk-ant-...",
        )
        sys.exit(1)

    if model_lower in ("gpt5", "both") and not openai_key:
        print_error(
            console,
            "OPENAI_API_KEY environment variable is not set.",
            hint="export OPENAI_API_KEY=sk-...",
        )
        sys.exit(1)

    # ── Banner ────────────────────────────────────────────────────────────────
    if not quiet:
        print_banner(console)

    # ── Dispatch ─────────────────────────────────────────────────────────────
    try:
        if raw:
            asyncio.run(
                _run_raw(
                    console=console,
                    problem=problem,
                    model=model_lower,
                    depth=depth,
                    anthropic_key=anthropic_key,
                    openai_key=openai_key,
                    output=output,
                    quiet=quiet,
                )
            )
        else:
            asyncio.run(
                _run_genesis(
                    console=console,
                    problem=problem,
                    model=model_lower,
                    depth=depth,
                    output_format=output_format,
                    domain=domain,
                    trace=trace,
                    candidates=candidates,
                    output=output,
                    show_cost=cost,
                    quiet=quiet,
                    anthropic_key=anthropic_key,
                    openai_key=openai_key,
                )
            )
    except KeyboardInterrupt:
        console.print(f"\n  [dim]Interrupted by user.[/]")
        sys.exit(130)


# ---------------------------------------------------------------------------
# Genesis pipeline runner
# ---------------------------------------------------------------------------


async def _run_genesis(
    console: Console,
    problem: str,
    model: str,
    depth: int,
    output_format: str,
    domain: str | None,
    trace: bool,
    candidates: int,
    output: Path | None,
    show_cost: bool,
    quiet: bool,
    anthropic_key: str | None,
    openai_key: str | None,
) -> None:
    """Run the full Genesis invention pipeline."""
    from hephaestus.core.genesis import (
        Genesis,
        GenesisConfig,
        PipelineStage,
    )

    # ── Build config ──────────────────────────────────────────────────────────
    config = _build_genesis_config(
        model=model,
        depth=depth,
        candidates=candidates,
        domain=domain,
        anthropic_key=anthropic_key,
        openai_key=openai_key,
    )

    genesis = Genesis(config)

    # ── Streaming pipeline with stage progress ────────────────────────────────
    report: Any = None
    error_msg: str | None = None

    if not quiet:
        stage_progress = StageProgress(console)
        with stage_progress:
            async for update in genesis.invent_stream(problem):
                _handle_pipeline_update(update, stage_progress)
                if update.stage == PipelineStage.COMPLETE:
                    report = update.data
                elif update.stage == PipelineStage.FAILED:
                    error_msg = update.message
                    break
    else:
        # Quiet mode — just collect the final result
        async for update in genesis.invent_stream(problem):
            if update.stage == PipelineStage.COMPLETE:
                report = update.data
            elif update.stage == PipelineStage.FAILED:
                error_msg = update.message
                break

    # ── Handle failure ────────────────────────────────────────────────────────
    if error_msg or report is None:
        msg = error_msg or "Pipeline produced no results."
        print_error(
            console,
            msg,
            hint=_error_hint(msg),
        )
        sys.exit(1)

    # ── Display results ───────────────────────────────────────────────────────
    if quiet:
        print_quiet_result(console, report)
    else:
        if output_format == "json":
            _render_json(console, report)
        elif output_format == "text":
            _render_text(console, report)
        else:
            # Default: rich terminal rendering
            print_invention_report(
                console,
                report,
                show_trace=trace,
                show_cost=show_cost,
            )

    # ── Save to file ──────────────────────────────────────────────────────────
    if output:
        _save_report(console, report, output, output_format)


def _handle_pipeline_update(update: Any, stage_progress: StageProgress) -> None:
    """Translate pipeline updates into stage progress display events."""
    from hephaestus.core.genesis import PipelineStage

    stage_map = {
        PipelineStage.DECOMPOSING: 1,
        PipelineStage.SEARCHING: 2,
        PipelineStage.SCORING: 3,
        PipelineStage.TRANSLATING: 4,
        PipelineStage.VERIFYING: 5,
    }
    complete_map = {
        PipelineStage.DECOMPOSED: 1,
        PipelineStage.SEARCHED: 2,
        PipelineStage.SCORED: 3,
        PipelineStage.TRANSLATED: 4,
        PipelineStage.VERIFIED: 5,
    }

    if update.stage in stage_map:
        stage_num = stage_map[update.stage]
        # Extract meaningful part after "Stage N/5:"
        msg = update.message
        if ":" in msg:
            msg = msg.split(":", 1)[-1].strip()
        stage_progress.start_stage(stage_num, msg)

    elif update.stage in complete_map:
        stage_num = complete_map[update.stage]
        msg = update.message
        if ":" in msg:
            msg = msg.split(":", 1)[-1].strip()
        stage_progress.complete_stage(stage_num, msg)

    elif update.stage.name == "FAILED":
        # Mark current stage as failed
        current = getattr(stage_progress, "_current_stage", 0)
        if current > 0:
            stage_progress.fail_stage(current, update.message[:80])


# ---------------------------------------------------------------------------
# Raw deepforge runner
# ---------------------------------------------------------------------------


async def _run_raw(
    console: Console,
    problem: str,
    model: str,
    depth: int,
    anthropic_key: str | None,
    openai_key: str | None,
    output: Path | None,
    quiet: bool,
) -> None:
    """Run DeepForge directly on the prompt without the genesis pipeline."""
    from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig

    if not quiet:
        console.print(f"  [dim]Running DeepForge directly (depth={depth})...[/]\n")

    # Pick adapter
    adapter = _build_raw_adapter(model, depth, anthropic_key, openai_key)
    harness = DeepForgeHarness(
        adapter=adapter,
        config=HarnessConfig(
            use_interference=True,
            use_pruner=True,
            use_pressure=True,
            max_pressure_rounds=depth,
            max_tokens=4096,
            temperature=0.9,
        ),
    )

    try:
        result = await harness.forge(problem)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print_error(console, str(exc), hint="Check your API keys and network connection.")
        sys.exit(1)

    # Print output
    console.print()
    console.rule("[yellow]⚒️  DeepForge Output[/]", style="yellow")
    console.print()
    console.print(result.output)
    console.print()
    console.rule(style="dim yellow")
    console.print()

    if not quiet:
        trace = result.trace
        console.print(
            f"  [dim]Cost:[/] [green]${trace.total_cost_usd:.4f}[/]  "
            f"[dim]Tokens:[/] {trace.total_output_tokens:,}  "
            f"[dim]Attempts:[/] {trace.attempts}  "
            f"[dim]Pruner kills:[/] {trace.pruner_kills}"
        )
        console.print()

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.output, encoding="utf-8")
        if not quiet:
            print_success(console, f"Saved to [cyan]{output}[/]")


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_json(console: Console, report: Any) -> None:
    """Render report as JSON to stdout."""
    from hephaestus.output.formatter import OutputFormat, OutputFormatter

    formatter = OutputFormatter()
    # We need to bridge genesis InventionReport → formatter InventionReport
    fmt_report = _bridge_report(report)
    output = formatter.to_json(fmt_report)
    console.print(output)


def _render_text(console: Console, report: Any) -> None:
    """Render report as plain text to stdout."""
    from hephaestus.output.formatter import OutputFormat, OutputFormatter

    formatter = OutputFormatter()
    fmt_report = _bridge_report(report)
    output = formatter.to_plain(fmt_report)
    console.print(output)


def _save_report(console: Console, report: Any, path: Path, fmt: str) -> None:
    """Save the report to a file."""
    from hephaestus.output.formatter import OutputFormatter

    formatter = OutputFormatter()
    fmt_report = _bridge_report(report)

    # Infer format from extension if not specified
    ext = path.suffix.lower()
    if ext == ".json" or fmt == "json":
        content = formatter.to_json(fmt_report)
    elif ext == ".txt" or fmt == "text":
        content = formatter.to_plain(fmt_report)
    else:
        content = formatter.to_markdown(fmt_report)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print_success(console, f"Saved to [cyan]{path}[/]")


def _bridge_report(genesis_report: Any) -> Any:
    """
    Bridge a genesis.InventionReport to the formatter's InventionReport dataclass.

    This translation layer allows the OutputFormatter (used for file/JSON/text output)
    to consume the full pipeline report from Genesis.
    """
    from hephaestus.output.formatter import (
        AlternativeInvention,
        InventionReport as FmtReport,
    )

    top = genesis_report.top_invention
    if not top:
        # Minimal empty report
        return FmtReport(
            problem=genesis_report.problem,
            structural_form=str(getattr(genesis_report.structure, "mathematical_shape", "")),
            invention_name="No invention produced",
            source_domain="N/A",
            domain_distance=0.0,
            structural_fidelity=0.0,
            novelty_score=0.0,
            mechanism="N/A",
            translation="N/A",
            architecture="N/A",
            where_analogy_breaks="N/A",
            cost_usd=genesis_report.total_cost_usd,
        )

    trans = top.translation
    mapping_str = "\n".join(
        f"• {m.source_element} → {m.target_element}: {m.mechanism}"
        for m in getattr(trans, "mapping", [])
    )

    alternatives = [
        AlternativeInvention(
            rank=i + 2,
            invention_name=alt.invention_name,
            source_domain=alt.source_domain,
            domain_distance=getattr(alt.translation.source_candidate, "domain_distance", 0.0),
            structural_fidelity=getattr(alt.translation.source_candidate, "structural_fidelity", 0.0),
            novelty_score=alt.novelty_score,
            summary=getattr(alt.translation, "key_insight", ""),
        )
        for i, alt in enumerate(genesis_report.alternative_inventions)
    ]

    return FmtReport(
        problem=genesis_report.problem,
        structural_form=getattr(genesis_report.structure, "mathematical_shape", ""),
        invention_name=top.invention_name,
        source_domain=top.source_domain,
        domain_distance=getattr(trans.source_candidate, "domain_distance", 0.0),
        structural_fidelity=getattr(trans.source_candidate, "structural_fidelity", 0.0),
        novelty_score=top.novelty_score,
        mechanism=getattr(trans, "key_insight", ""),
        translation=mapping_str,
        architecture=getattr(trans, "architecture", ""),
        where_analogy_breaks="\n".join(getattr(trans, "limitations", [])),
        prior_art_report=getattr(top, "prior_art_report", None),
        alternatives=alternatives,
        cost_usd=genesis_report.total_cost_usd,
        models_used=list(set(genesis_report.model_config.values())),
        depth=3,
        wall_time_seconds=genesis_report.total_duration_seconds,
    )


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------


def _build_genesis_config(
    model: str,
    depth: int,
    candidates: int,
    domain: str | None,
    anthropic_key: str | None,
    openai_key: str | None,
) -> Any:
    """Build a GenesisConfig from CLI options."""
    from hephaestus.core.genesis import GenesisConfig

    # Model selection
    if model == "opus":
        decompose_model = "claude-opus-4-5"
        search_model = "claude-opus-4-5"
        score_model = "claude-opus-4-5"
        translate_model = "claude-opus-4-5"
        attack_model = "claude-opus-4-5"
        defend_model = "claude-opus-4-5"
    elif model == "gpt5":
        decompose_model = "gpt-4o"
        search_model = "gpt-4o"
        score_model = "gpt-4o-mini"
        translate_model = "gpt-4o"
        attack_model = "gpt-4o"
        defend_model = "gpt-4o"
    else:  # both (default)
        decompose_model = "claude-opus-4-5"
        search_model = "gpt-4o"
        score_model = "gpt-4o-mini"
        translate_model = "claude-opus-4-5"
        attack_model = "gpt-4o"
        defend_model = "claude-opus-4-5"

    return GenesisConfig(
        anthropic_api_key=anthropic_key,
        openai_api_key=openai_key,
        decompose_model=decompose_model,
        search_model=search_model,
        score_model=score_model,
        translate_model=translate_model,
        attack_model=attack_model,
        defend_model=defend_model,
        num_candidates=candidates,
        use_interference_in_translate=True,
    )


def _build_raw_adapter(
    model: str,
    depth: int,
    anthropic_key: str | None,
    openai_key: str | None,
) -> Any:
    """Build an adapter for raw deepforge mode."""
    if model in ("opus", "both"):
        from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(model="claude-opus-4-5", api_key=anthropic_key)
    else:
        from hephaestus.deepforge.adapters.openai import OpenAIAdapter
        return OpenAIAdapter(model="gpt-4o", api_key=openai_key)


# ---------------------------------------------------------------------------
# Error hints
# ---------------------------------------------------------------------------


def _error_hint(error_msg: str) -> str | None:
    """Return a helpful hint based on the error message."""
    msg = error_msg.lower()
    if "api key" in msg or "authentication" in msg or "unauthorized" in msg:
        return "Check that your ANTHROPIC_API_KEY and OPENAI_API_KEY are set correctly."
    if "decomposition failed" in msg:
        return "Try rephrasing your problem description. Make it more specific and concrete."
    if "no candidates found" in msg:
        return "Try --domain to hint the target domain, or rephrase as a structural challenge."
    if "all candidates filtered" in msg:
        return "Lower --depth or try --model opus for deeper search."
    if "lens library" in msg or "no such file" in msg:
        return "Run: pip install --upgrade hephaestus-ai"
    if "rate limit" in msg or "429" in msg:
        return "API rate limit hit. Wait a few seconds and try again."
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the heph CLI command."""
    cli()


if __name__ == "__main__":
    main()
