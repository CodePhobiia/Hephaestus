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
import logging
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
    print_error,
    print_invention_report,
    print_quiet_result,
    print_success,
)

logger = logging.getLogger(__name__)

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
        "Describe a hard problem. Hephaestus will search distant domains, map the"
        " structure back, and return a concrete invention report.\n\n"
        "Run without a problem to open the interactive REPL.\n\n"
        "Example:\n\n"
        '  heph "I need a load balancer that handles unpredictable traffic spikes"\n\n'
        '  heph --depth 5 --model opus --trace "a complex routing problem"\n\n'
        "Interactive:\n\n"
        "  heph --interactive"
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
    type=click.Choice(
        ["claude-max", "claude-cli", "codex", "opus", "gpt5", "both"], case_sensitive=False
    ),
    help="Backend/model preset to use: claude-max, claude-cli, codex, opus, gpt5, or both.",
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
    help="Hint for the target domain (soft bias on lens routing).",
)
@click.option(
    "--exploration-mode",
    default="standard",
    show_default=True,
    type=click.Choice(["standard", "forge"], case_sensitive=False),
    help="Exploration mechanism mode.",
)
@click.option(
    "--pressure-translate/--no-pressure-translate",
    default=True,
    show_default=True,
    help="Enable pressure rounds exclusively for Translate mechanisms.",
)
@click.option(
    "--pressure-search-mode",
    default="adaptive",
    show_default=True,
    type=click.Choice(["off", "adaptive", "always"], case_sensitive=False),
    help="Pressure behavior applied to the Search phase.",
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
    "--intensity",
    default="STANDARD",
    show_default=True,
    type=click.Choice(["STANDARD", "AGGRESSIVE", "MAXIMUM"], case_sensitive=False),
    help="Divergence intensity — how far from consensus.",
)
@click.option(
    "--output-mode",
    default="MECHANISM",
    show_default=True,
    type=click.Choice(
        ["MECHANISM", "FRAMEWORK", "NARRATIVE", "SYSTEM", "PROTOCOL", "TAXONOMY", "INTERFACE"],
        case_sensitive=False,
    ),
    help="Output structure shape (e.g. MECHANISM, FRAMEWORK, SYSTEM).",
)
@click.option(
    "--research/--no-research",
    "use_research",
    default=True,
    show_default=True,
    help="Enable Perplexity-backed research features and benchmark generation.",
)
@click.option(
    "--research-model",
    default=None,
    help="Perplexity model override for research features (defaults to config or HEPHAESTUS_PERPLEXITY_MODEL).",
)
@click.option(
    "--benchmark-corpus",
    "benchmark_topic",
    default=None,
    help="Generate a grounded benchmark corpus for a topic instead of running the invention pipeline.",
)
@click.option(
    "--benchmark-count",
    default=8,
    show_default=True,
    type=click.IntRange(1, 50),
    help="Number of benchmark cases to generate when --benchmark-corpus is used.",
)
@click.option(
    "--olympus/--no-olympus",
    "use_olympus",
    default=True,
    show_default=True,
    help="Enable Stage 0 repo-awareness (Olympus). Automatically detects if cwd is a repo.",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    default=False,
    help="Launch interactive REPL mode.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
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
@click.pass_context
def cli(
    ctx: click.Context,
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
    interactive: bool,
    verbose: bool,
    intensity: str,
    output_mode: str,
    use_research: bool,
    research_model: str | None,
    benchmark_topic: str | None,
    benchmark_count: int,
    exploration_mode: str,
    pressure_translate: bool,
    pressure_search_mode: str,
    use_olympus: bool,
) -> None:
    """Main CLI entry point."""
    import logging as _logging

    if verbose:
        _logging.basicConfig(
            level=_logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        # Show agent-sdk activity so the user sees what Claude is doing
        _logging.basicConfig(
            level=_logging.WARNING,
            format="  %(message)s",
        )
        _logging.getLogger("hephaestus.deepforge.adapters.agent_sdk").setLevel(_logging.INFO)
        _logging.getLogger("hephaestus.core.genesis").setLevel(_logging.INFO)
    console = make_console(quiet=quiet)
    use_branchgenome_v1 = False
    use_adaptive_lens_engine = True
    allow_lens_bundle_fallback = True
    enable_derived_lens_composites = True
    use_pantheon_mode = False
    pantheon_max_rounds = 4
    pantheon_require_unanimity = True
    pantheon_allow_fail_closed = True
    pantheon_resolution_mode = "TASK_SENSITIVE"
    pantheon_max_survivors_to_council = 2
    pantheon_athena_model = None
    pantheon_hermes_model = None
    pantheon_apollo_model = None

    # ── Layered config ────────────────────────────────────────────────────────
    layered = None
    try:
        from hephaestus.config.layered import LayeredConfig

        layered = LayeredConfig()
        resolved = layered.resolve()

        # Use config values where CLI didn't explicitly override
        _VALID_CLI_MODELS = {"claude-max", "claude-cli", "codex", "opus", "gpt5", "both"} # noqa: N806
        src = ctx.get_parameter_source
        if src("depth") != click.core.ParameterSource.COMMANDLINE:
            depth = resolved.depth
        if src("model") != click.core.ParameterSource.COMMANDLINE:
            # Only override if config value is a valid CLI preset
            if resolved.default_model in _VALID_CLI_MODELS:
                model = resolved.default_model
            elif resolved.backend in ("claude-max", "claude-cli"):
                model = resolved.backend
        if src("intensity") != click.core.ParameterSource.COMMANDLINE:
            intensity = resolved.divergence_intensity
        if src("output_mode") != click.core.ParameterSource.COMMANDLINE:
            output_mode = resolved.output_mode
        if src("use_research") != click.core.ParameterSource.COMMANDLINE:
            use_research = resolved.use_perplexity_research
        if src("research_model") != click.core.ParameterSource.COMMANDLINE:
            research_model = resolved.perplexity_model
        use_branchgenome_v1 = getattr(resolved, "use_branchgenome_v1", False)
        use_adaptive_lens_engine = getattr(resolved, "use_adaptive_lens_engine", True)
        allow_lens_bundle_fallback = getattr(resolved, "allow_lens_bundle_fallback", True)
        enable_derived_lens_composites = getattr(resolved, "enable_derived_lens_composites", True)
        use_pantheon_mode = getattr(resolved, "use_pantheon_mode", False)
        pantheon_max_rounds = getattr(resolved, "pantheon_max_rounds", 4)
        pantheon_require_unanimity = getattr(resolved, "pantheon_require_unanimity", True)
        pantheon_allow_fail_closed = getattr(resolved, "pantheon_allow_fail_closed", True)
        pantheon_resolution_mode = getattr(resolved, "pantheon_resolution_mode", "TASK_SENSITIVE")
        pantheon_max_survivors_to_council = getattr(
            resolved, "pantheon_max_survivors_to_council", 2
        )
        pantheon_athena_model = getattr(resolved, "pantheon_athena_model", None)
        pantheon_hermes_model = getattr(resolved, "pantheon_hermes_model", None)
        pantheon_apollo_model = getattr(resolved, "pantheon_apollo_model", None)
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Config load failed, using CLI defaults: %s", exc)

    # ── Benchmark corpus mode ────────────────────────────────────────────────
    if benchmark_topic:
        if problem or raw or interactive:
            print_error(
                console,
                "--benchmark-corpus runs as a standalone research mode.",
                hint='Use `heph --benchmark-corpus "topic"` without a problem, --raw, or --interactive.',
            )
            sys.exit(1)

        if not quiet:
            print_banner(console)

        try:
            asyncio.run(
                _run_benchmark_corpus(
                    console=console,
                    topic=benchmark_topic,
                    count=benchmark_count,
                    output_format=output_format,
                    output=output,
                    quiet=quiet,
                    use_research=use_research,
                    research_model=research_model,
                )
            )
        except KeyboardInterrupt:
            console.print("\n  [dim]Interrupted by user.[/]")
            sys.exit(130)
        except Exception as exc:
            msg = str(exc) or exc.__class__.__name__
            print_error(
                console,
                "Benchmark corpus generation failed.",
                hint=_error_hint(msg) or msg,
            )
            sys.exit(1)
        return

    # ── Interactive mode ──────────────────────────────────────────────────────
    if interactive or (not problem and not raw):
        from hephaestus.cli.repl import run_interactive

        # Auto-detect workspace: if cwd looks like a codebase, enable workspace mode
        workspace_root = None
        try:
            from hephaestus.workspace.scanner import WorkspaceScanner

            cwd = Path.cwd()
            scanner = WorkspaceScanner(cwd, max_files=200, include_repo_dossier=False)
            quick_summary = scanner.scan()
            if quick_summary.total_files >= 2:
                workspace_root = cwd
                if not quiet:
                    console.print(
                        f"  [dim]📂 Workspace detected:[/] [dark_orange]{cwd.name}/[/] "
                        f"[dim]({quick_summary.total_files} files, "
                        f"{quick_summary.primary_language})[/]"
                    )
        except Exception as exc:
            logger.warning("Workspace auto-detection failed: %s", exc)

        run_interactive(console, model=model, layered_config=layered, workspace_root=workspace_root)
        return

    # ── Validate inputs ───────────────────────────────────────────────────────
    if not problem:
        if not quiet:
            print_banner(console)
        console.print(
            "  [yellow]Provide a problem description.[/]\n\n"
            '  Example:  [dark_orange]heph "I need a load balancer for traffic spikes"[/]\n\n'
            "  Run [dark_orange]heph --interactive[/] for the REPL or [dark_orange]heph --help[/] for all options."
        )
        sys.exit(0)

    # ── API key validation ────────────────────────────────────────────────────
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    model_lower = model.lower()
    if model_lower in ("agent-sdk", "claude-max", "claude-cli", "codex"):
        pass
    elif model_lower in ("opus", "both") and not anthropic_key:
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
                    divergence_intensity=intensity,
                    output_mode=output_mode,
                    use_research=use_research,
                    research_model=research_model,
                    use_branchgenome_v1=use_branchgenome_v1,
                    use_adaptive_lens_engine=use_adaptive_lens_engine,
                    allow_lens_bundle_fallback=allow_lens_bundle_fallback,
                    enable_derived_lens_composites=enable_derived_lens_composites,
                    use_pantheon_mode=use_pantheon_mode,
                    pantheon_max_rounds=pantheon_max_rounds,
                    pantheon_require_unanimity=pantheon_require_unanimity,
                    pantheon_allow_fail_closed=pantheon_allow_fail_closed,
                    pantheon_resolution_mode=pantheon_resolution_mode,
                    pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
                    pantheon_athena_model=pantheon_athena_model,
                    pantheon_hermes_model=pantheon_hermes_model,
                    pantheon_apollo_model=pantheon_apollo_model,
                    use_olympus=use_olympus,
                )
            )
    except KeyboardInterrupt:
        console.print("\n  [dim]Interrupted by user.[/]")
        sys.exit(130)
    except Exception as exc:
        msg = str(exc) or exc.__class__.__name__
        print_error(
            console,
            "The CLI run failed before a result was produced.",
            hint=_error_hint(msg) or msg,
        )
        sys.exit(1)


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
    divergence_intensity: str = "STANDARD",
    output_mode: str = "MECHANISM",
    use_research: bool = True,
    research_model: str | None = None,
    use_branchgenome_v1: bool = False,
    use_adaptive_lens_engine: bool = True,
    allow_lens_bundle_fallback: bool = True,
    enable_derived_lens_composites: bool = True,
    use_pantheon_mode: bool = False,
    pantheon_max_rounds: int = 4,
    pantheon_require_unanimity: bool = True,
    pantheon_allow_fail_closed: bool = True,
    pantheon_resolution_mode: str = "TASK_SENSITIVE",
    pantheon_max_survivors_to_council: int = 2,
    pantheon_athena_model: str | None = None,
    pantheon_hermes_model: str | None = None,
    pantheon_apollo_model: str | None = None,
    use_olympus: bool = True,
) -> None:
    """Run the full Genesis invention pipeline."""
    from hephaestus.core.genesis import (
        Genesis,
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
        divergence_intensity=divergence_intensity,
        output_mode=output_mode,
        use_perplexity_research=use_research,
        research_model=research_model,
        use_branchgenome_v1=use_branchgenome_v1,
        use_adaptive_lens_engine=use_adaptive_lens_engine,
        allow_lens_bundle_fallback=allow_lens_bundle_fallback,
        enable_derived_lens_composites=enable_derived_lens_composites,
        use_pantheon_mode=use_pantheon_mode,
        pantheon_max_rounds=pantheon_max_rounds,
        pantheon_require_unanimity=pantheon_require_unanimity,
        pantheon_allow_fail_closed=pantheon_allow_fail_closed,
        pantheon_resolution_mode=pantheon_resolution_mode,
        pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
        pantheon_athena_model=pantheon_athena_model,
        pantheon_hermes_model=pantheon_hermes_model,
        pantheon_apollo_model=pantheon_apollo_model,
    )
    config.olympus_enabled = use_olympus

    # Initialize ForgeBase if transliminality is enabled
    _fb = None
    if config.transliminality_enabled:
        try:
            from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase

            _fb_data_dir = Path.home() / ".hephaestus"
            _fb_data_dir.mkdir(parents=True, exist_ok=True)
            _fb = await create_forgebase(
                ForgeBaseConfig(sqlite_path=str(_fb_data_dir / "forgebase.db")),
            )
        except Exception as fb_exc:
            logger.warning("ForgeBase init failed, transliminality will use harness-only: %s", fb_exc)

    genesis = Genesis(config, forgebase=_fb)

    # ── Streaming pipeline with stage progress ────────────────────────────────
    report: Any = None
    error_msg: str | None = None

    try:
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
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print_error(
            console,
            "The invention pipeline crashed before completion.",
            hint=_error_hint(str(exc))
            or "Check your API keys, backend connectivity, and model selection.",
        )
        sys.exit(1)

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


async def _run_benchmark_corpus(
    console: Console,
    topic: str,
    count: int,
    output_format: str,
    output: Path | None,
    quiet: bool,
    use_research: bool,
    research_model: str | None,
) -> None:
    """Generate and render a grounded benchmark corpus."""
    from hephaestus.research import BenchmarkCorpusBuilder, PerplexityClient

    availability = PerplexityClient(enabled=use_research, model=research_model)
    if not availability.available():
        raise RuntimeError(availability.unavailability_reason())
    await availability.close()

    if not quiet:
        model_label = research_model or "configured default"
        console.print(
            f"  [dim]Generating benchmark corpus for[/] [dark_orange]{topic}[/] "
            f"[dim]({count} cases, model={model_label})[/]\n"
        )

    corpus = await BenchmarkCorpusBuilder(
        topic=topic,
        count=count,
        enabled=use_research,
        model=research_model,
    ).build()

    if not corpus.cases:
        raise RuntimeError("Perplexity returned no benchmark cases for that topic")

    rendered = _serialize_benchmark_corpus(corpus, output_format)
    console.print(rendered)

    if output:
        _save_benchmark_corpus(console, corpus, output, output_format)


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
        print_error(
            console,
            "DeepForge could not complete the raw run.",
            hint=_error_hint(str(exc)) or "Check your API keys and network connection.",
        )
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
            print_success(console, f"Saved to [dark_orange]{output}[/]")


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_json(console: Console, report: Any) -> None:
    """Render report as JSON to stdout."""
    from hephaestus.output.formatter import OutputFormatter

    formatter = OutputFormatter()
    # We need to bridge genesis InventionReport → formatter InventionReport
    fmt_report = _bridge_report(report)
    output = formatter.to_json(fmt_report)
    console.print(output)


def _render_text(console: Console, report: Any) -> None:
    """Render report as plain text to stdout."""
    from hephaestus.output.formatter import OutputFormatter

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

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError:
        print_error(
            console,
            f"Could not write output file: {path}",
            hint="Check that the directory exists and that this shell can write to it.",
        )
        return
    print_success(console, f"Saved to [dark_orange]{path}[/]")


def _serialize_benchmark_corpus(corpus: Any, fmt: str) -> str:
    """Serialize a benchmark corpus for stdout or file export."""
    if fmt == "json":
        return corpus.to_json()
    return corpus.to_markdown()


def _save_benchmark_corpus(console: Console, corpus: Any, path: Path, fmt: str) -> None:
    """Save a benchmark corpus to disk."""
    ext = path.suffix.lower()
    serialize_as = "json" if ext == ".json" or fmt == "json" else "markdown"
    content = _serialize_benchmark_corpus(corpus, serialize_as)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError:
        print_error(
            console,
            f"Could not write benchmark corpus file: {path}",
            hint="Check that the directory exists and that this shell can write to it.",
        )
        return
    print_success(console, f"Saved to [dark_orange]{path}[/]")


def _bridge_report(genesis_report: Any) -> Any:
    """
    Bridge a genesis.InventionReport to the formatter's InventionReport dataclass.

    This translation layer allows the OutputFormatter (used for file/JSON/text output)
    to consume the full pipeline report from Genesis.
    """
    from hephaestus.output.formatter import (
        AlternativeInvention,
    )
    from hephaestus.output.formatter import (
        InventionReport as FmtReport,
    )

    def _explicit_attr(obj: Any, name: str, default: Any = None) -> Any:
        data = getattr(obj, "__dict__", {})
        if isinstance(data, dict) and name in data:
            return data[name]
        return default

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
            input_tokens=getattr(genesis_report, "total_input_tokens", 0),
            output_tokens=getattr(genesis_report, "total_output_tokens", 0),
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
            structural_fidelity=getattr(
                alt.translation.source_candidate, "structural_fidelity", 0.0
            ),
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
        prior_art_report=_explicit_attr(top, "prior_art_report", None),
        baseline_dossier=_explicit_attr(genesis_report, "baseline_dossier", None),
        external_grounding_report=_explicit_attr(top, "grounding_report", None),
        implementation_risk_review=_explicit_attr(top, "implementation_risk_review", None),
        lens_engine_state=_explicit_attr(genesis_report, "lens_engine_state", None),
        pantheon_state=_explicit_attr(genesis_report, "pantheon_state", None),
        pantheon_runtime=_explicit_attr(genesis_report, "pantheon_runtime", None),
        deliberation_graph=_explicit_attr(genesis_report, "deliberation_graph", None),
        cost_breakdown=_explicit_attr(genesis_report, "cost_breakdown", None),
        alternatives=alternatives,
        cost_usd=genesis_report.total_cost_usd,
        input_tokens=getattr(genesis_report, "total_input_tokens", 0),
        output_tokens=getattr(genesis_report, "total_output_tokens", 0),
        models_used=list(
            dict.fromkeys(_explicit_attr(genesis_report, "model_config", {}).values())
        ),
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
    divergence_intensity: str = "STANDARD",
    output_mode: str = "MECHANISM",
    use_perplexity_research: bool = True,
    research_model: str | None = None,
    use_branchgenome_v1: bool = False,
    use_adaptive_lens_engine: bool = True,
    allow_lens_bundle_fallback: bool = True,
    enable_derived_lens_composites: bool = True,
    use_pantheon_mode: bool = False,
    pantheon_max_rounds: int = 4,
    pantheon_require_unanimity: bool = True,
    pantheon_allow_fail_closed: bool = True,
    pantheon_resolution_mode: str = "TASK_SENSITIVE",
    pantheon_max_survivors_to_council: int = 2,
    pantheon_athena_model: str | None = None,
    pantheon_hermes_model: str | None = None,
    pantheon_apollo_model: str | None = None,
    exploration_mode: str = "standard",
    pressure_translate: bool = True,
    pressure_search_mode: str = "adaptive",
) -> Any:
    """Build a GenesisConfig from CLI options."""
    # Load transliminality flag from config (not yet a CLI flag)
    from hephaestus.cli.config import load_config as _load_cfg
    from hephaestus.core.cross_model import get_model_preset
    from hephaestus.core.genesis import GenesisConfig

    _user_cfg = _load_cfg()
    _transliminality = getattr(_user_cfg, "transliminality_enabled", False) if _user_cfg else False

    if model == "agent-sdk":
        models = get_model_preset("opus")
        return GenesisConfig(
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            openrouter_api_key=None,
            use_agent_sdk=True,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            depth=depth,
            domain_hint=domain,
            exploration_mode=exploration_mode.lower(),
            pressure_translate_enabled=pressure_translate,
            pressure_search_mode=pressure_search_mode.lower(),
            num_candidates=candidates,
            use_interference_in_translate=True,
            divergence_intensity=divergence_intensity.upper(),
            output_mode=output_mode.upper(),
            use_perplexity_research=use_perplexity_research,
            perplexity_model=research_model,
            use_branchgenome_v1=use_branchgenome_v1,
            use_adaptive_lens_engine=use_adaptive_lens_engine,
            allow_lens_bundle_fallback=allow_lens_bundle_fallback,
            enable_derived_lens_composites=enable_derived_lens_composites,
            use_pantheon_mode=use_pantheon_mode,
            pantheon_max_rounds=pantheon_max_rounds,
            pantheon_require_unanimity=pantheon_require_unanimity,
            pantheon_allow_fail_closed=pantheon_allow_fail_closed,
            pantheon_resolution_mode=pantheon_resolution_mode,
            pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
            pantheon_athena_model=pantheon_athena_model,
            pantheon_hermes_model=pantheon_hermes_model,
            pantheon_apollo_model=pantheon_apollo_model,
            transliminality_enabled=_transliminality,
        )

    if model == "claude-max":
        models = get_model_preset("opus")
        return GenesisConfig(
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            openrouter_api_key=None,
            use_claude_max=True,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            depth=depth,
            domain_hint=domain,
            exploration_mode=exploration_mode.lower(),
            pressure_translate_enabled=pressure_translate,
            pressure_search_mode=pressure_search_mode.lower(),
            num_candidates=candidates,
            use_interference_in_translate=True,
            divergence_intensity=divergence_intensity.upper(),
            output_mode=output_mode.upper(),
            use_perplexity_research=use_perplexity_research,
            perplexity_model=research_model,
            use_branchgenome_v1=use_branchgenome_v1,
            use_adaptive_lens_engine=use_adaptive_lens_engine,
            allow_lens_bundle_fallback=allow_lens_bundle_fallback,
            enable_derived_lens_composites=enable_derived_lens_composites,
            use_pantheon_mode=use_pantheon_mode,
            pantheon_max_rounds=pantheon_max_rounds,
            pantheon_require_unanimity=pantheon_require_unanimity,
            pantheon_allow_fail_closed=pantheon_allow_fail_closed,
            pantheon_resolution_mode=pantheon_resolution_mode,
            pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
            pantheon_athena_model=pantheon_athena_model,
            pantheon_hermes_model=pantheon_hermes_model,
            pantheon_apollo_model=pantheon_apollo_model,
            transliminality_enabled=_transliminality,
        )

    if model == "claude-cli":
        models = get_model_preset("opus")
        return GenesisConfig(
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            openrouter_api_key=None,
            use_claude_cli=True,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            depth=depth,
            domain_hint=domain,
            exploration_mode=exploration_mode.lower(),
            pressure_translate_enabled=pressure_translate,
            pressure_search_mode=pressure_search_mode.lower(),
            num_candidates=candidates,
            use_interference_in_translate=True,
            divergence_intensity=divergence_intensity.upper(),
            output_mode=output_mode.upper(),
            use_perplexity_research=use_perplexity_research,
            perplexity_model=research_model,
            use_branchgenome_v1=use_branchgenome_v1,
            use_adaptive_lens_engine=use_adaptive_lens_engine,
            allow_lens_bundle_fallback=allow_lens_bundle_fallback,
            enable_derived_lens_composites=enable_derived_lens_composites,
            use_pantheon_mode=use_pantheon_mode,
            pantheon_max_rounds=pantheon_max_rounds,
            pantheon_require_unanimity=pantheon_require_unanimity,
            pantheon_allow_fail_closed=pantheon_allow_fail_closed,
            pantheon_resolution_mode=pantheon_resolution_mode,
            pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
            pantheon_athena_model=pantheon_athena_model,
            pantheon_hermes_model=pantheon_hermes_model,
            pantheon_apollo_model=pantheon_apollo_model,
            transliminality_enabled=_transliminality,
        )

    if model == "codex":
        models = get_model_preset("codex")
        return GenesisConfig(
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            openrouter_api_key=None,
            use_codex_cli=True,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            depth=depth,
            domain_hint=domain,
            exploration_mode=exploration_mode.lower(),
            pressure_translate_enabled=pressure_translate,
            pressure_search_mode=pressure_search_mode.lower(),
            num_candidates=candidates,
            use_interference_in_translate=True,
            divergence_intensity=divergence_intensity.upper(),
            output_mode=output_mode.upper(),
            use_perplexity_research=use_perplexity_research,
            perplexity_model=research_model,
            use_branchgenome_v1=use_branchgenome_v1,
            use_adaptive_lens_engine=use_adaptive_lens_engine,
            allow_lens_bundle_fallback=allow_lens_bundle_fallback,
            enable_derived_lens_composites=enable_derived_lens_composites,
            use_pantheon_mode=use_pantheon_mode,
            pantheon_max_rounds=pantheon_max_rounds,
            pantheon_require_unanimity=pantheon_require_unanimity,
            pantheon_allow_fail_closed=pantheon_allow_fail_closed,
            pantheon_resolution_mode=pantheon_resolution_mode,
            pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
            pantheon_athena_model=pantheon_athena_model,
            pantheon_hermes_model=pantheon_hermes_model,
            pantheon_apollo_model=pantheon_apollo_model,
            transliminality_enabled=_transliminality,
        )

    # Map CLI flag names to preset names
    preset_key = {"opus": "opus", "gpt5": "gpt", "codex": "codex"}.get(model, "both")
    models = get_model_preset(preset_key)

    return GenesisConfig(
        anthropic_api_key=anthropic_key,
        openai_api_key=openai_key,
        decompose_model=models["decompose"],
        search_model=models["search"],
        score_model=models["score"],
        translate_model=models["translate"],
        attack_model=models["attack"],
        defend_model=models["defend"],
        depth=depth,
        domain_hint=domain,
        exploration_mode=exploration_mode.lower(),
        pressure_translate_enabled=pressure_translate,
        pressure_search_mode=pressure_search_mode.lower(),
        num_candidates=candidates,
        use_interference_in_translate=True,
        divergence_intensity=divergence_intensity.upper(),
        output_mode=output_mode.upper(),
        use_perplexity_research=use_perplexity_research,
        perplexity_model=research_model,
        use_branchgenome_v1=use_branchgenome_v1,
        use_adaptive_lens_engine=use_adaptive_lens_engine,
        allow_lens_bundle_fallback=allow_lens_bundle_fallback,
        enable_derived_lens_composites=enable_derived_lens_composites,
        use_pantheon_mode=use_pantheon_mode,
        pantheon_max_rounds=pantheon_max_rounds,
        pantheon_require_unanimity=pantheon_require_unanimity,
        pantheon_allow_fail_closed=pantheon_allow_fail_closed,
        pantheon_resolution_mode=pantheon_resolution_mode,
        pantheon_max_survivors_to_council=pantheon_max_survivors_to_council,
        pantheon_athena_model=pantheon_athena_model,
        pantheon_hermes_model=pantheon_hermes_model,
        pantheon_apollo_model=pantheon_apollo_model,
        transliminality_enabled=_transliminality,
    )


def _build_raw_adapter(
    model: str,
    depth: int,
    anthropic_key: str | None,
    openai_key: str | None,
) -> Any:
    """Build an adapter for raw deepforge mode."""
    from hephaestus.core.cross_model import get_model_preset

    if model == "claude-max":
        from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter

        return ClaudeMaxAdapter(model="claude-opus-4-6")
    if model == "claude-cli":
        from hephaestus.deepforge.adapters.claude_cli import ClaudeCliAdapter

        return ClaudeCliAdapter(model="claude-opus-4-6")
    if model == "codex":
        from hephaestus.deepforge.adapters.codex_cli import CodexCliAdapter

        return CodexCliAdapter(model="gpt-5.4")

    preset_key = {"opus": "opus", "gpt5": "gpt", "codex": "codex"}.get(model, "both")
    models = get_model_preset(preset_key)

    if model in ("opus", "both"):
        from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter(model=models["decompose"], api_key=anthropic_key)
    else:
        from hephaestus.deepforge.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(model=models["decompose"], api_key=openai_key)


# ---------------------------------------------------------------------------
# Error hints
# ---------------------------------------------------------------------------


def _error_hint(error_msg: str) -> str | None:
    """Return a helpful hint based on the error message."""
    msg = error_msg.lower()
    if "api key" in msg or "authentication" in msg or "unauthorized" in msg:
        return "Check that your ANTHROPIC_API_KEY and OPENAI_API_KEY are set correctly."
    if "openrouter" in msg:
        return "Check that OPENROUTER_API_KEY is set and that the selected model is available on OpenRouter."
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
    if "connection" in msg or "network" in msg or "timeout" in msg:
        return "Check outbound network access from this server and try again."
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@click.command(
    name="batch",
    help="Process multiple problems from a file.\n\nExample:\n\n  heph batch --input problems.txt --output-dir inventions/",
)
@click.option(
    "--input",
    "-i",
    "input_file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a text file with one problem per line.",
)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Directory where invention reports will be saved.",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    default="markdown",
    show_default=True,
    type=click.Choice(["markdown", "json", "text"], case_sensitive=False),
    help="Output format for each report.",
)
@click.option(
    "--depth",
    "-d",
    default=3,
    show_default=True,
    type=click.IntRange(1, 10),
    help="Anti-training pressure depth.",
)
@click.option(
    "--model",
    "-m",
    default="both",
    show_default=True,
    type=click.Choice(
        ["claude-max", "claude-cli", "codex", "opus", "gpt5", "both"], case_sensitive=False
    ),
    help="Backend/model preset.",
)
def batch_cmd(
    input_file: Path,
    output_dir: Path,
    output_format: str,
    depth: int,
    model: str,
) -> None:
    """Run the genesis pipeline on every problem in a file."""
    from hephaestus.cli.batch import BatchConfig, run_batch
    from hephaestus.cli.display import print_banner

    console = make_console(quiet=False)
    print_banner(console)
    console.print(f"  [dim]Batch mode: {input_file} → {output_dir}/[/]\n")

    config = BatchConfig(
        input_file=input_file,
        output_dir=output_dir,
        format=output_format,
        depth=depth,
        model=model,
    )
    try:
        asyncio.run(run_batch(config, console))
    except KeyboardInterrupt:
        console.print("\n  [dim]Interrupted by user.[/]")
        sys.exit(130)


@click.command(
    name="init",
    help="Initialize a .hephaestus/ project directory in the current folder.",
)
def init_cmd() -> None:
    """Create a .hephaestus/ directory with starter config and instructions."""
    console = make_console(quiet=False)
    cwd = Path.cwd()
    heph_dir = cwd / ".hephaestus"

    if heph_dir.exists():
        console.print(f"  [yellow]⚠[/] .hephaestus/ already exists in {cwd}")
        return

    heph_dir.mkdir()

    # config.yaml with commented defaults
    config_yaml = heph_dir / "config.yaml"
    config_yaml.write_text(
        "# Hephaestus project configuration\n"
        "# These override your global ~/.hephaestus/config.yaml\n"
        "#\n"
        "# backend: api\n"
        "# depth: 3\n"
        "# candidates: 8\n"
        "# divergence_intensity: STANDARD\n"
        "# output_mode: MECHANISM\n"
        "# use_perplexity_research: true\n"
        "# perplexity_model: sonar-pro\n"
        "# use_branchgenome_v1: false\n"
        "# use_adaptive_lens_engine: true\n"
        "# allow_lens_bundle_fallback: true\n"
        "# enable_derived_lens_composites: true\n"
        "# use_pantheon_mode: false\n"
        "# pantheon_max_rounds: 4\n"
        "# pantheon_require_unanimity: true\n"
        "# pantheon_allow_fail_closed: true\n"
        "# pantheon_resolution_mode: TASK_SENSITIVE\n"
        "# pantheon_max_survivors_to_council: 2\n"
        "# pantheon_athena_model: claude-opus-4-5\n"
        "# pantheon_hermes_model: gpt-4o\n"
        "# pantheon_apollo_model: claude-opus-4-5\n"
        "# auto_save: true\n",
        encoding="utf-8",
    )

    # instructions.md
    instructions = heph_dir / "instructions.md"
    instructions.write_text(
        "# Project Instructions for Hephaestus\n\n"
        "Add project-specific guidance here. Hephaestus will include\n"
        "this context when generating inventions in this directory.\n\n"
        "## Domain Context\n\n"
        "Describe your project's domain, constraints, and goals.\n\n"
        "## Invention Preferences\n\n"
        "Any preferences for source domains, output modes, or depth.\n",
        encoding="utf-8",
    )

    # Add local.yaml to .gitignore
    gitignore = cwd / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".hephaestus/local.yaml" not in content:
            with open(gitignore, "a") as f:
                f.write("\n# Hephaestus local overrides\n.hephaestus/local.yaml\n")
            console.print("  [dim]Added .hephaestus/local.yaml to .gitignore[/]")

    from hephaestus.cli.display import GREEN

    console.print()
    console.print(f"  [{GREEN}]✓[/] Initialized .hephaestus/ in {cwd}")
    console.print("  [dim]Created:[/]")
    console.print(f"    {config_yaml}")
    console.print(f"    {instructions}")
    console.print()
    console.print("  [dim]Edit .hephaestus/config.yaml for project defaults[/]")
    console.print("  [dim]Edit .hephaestus/instructions.md for project context[/]")
    console.print()


@click.command(
    name="lenses",
    help="Show lens library stats and optionally validate all lenses.\n\nExamples:\n\n  heph lenses\n  heph lenses --validate",
)
@click.option(
    "--validate",
    is_flag=True,
    default=False,
    help="Run validation on all lens YAML files and report errors.",
)
def lenses_cmd(validate: bool) -> None:
    """Show lens library stats or validate all lenses."""
    from hephaestus.lenses.validator import compute_lens_stats, validate_all_lenses

    console = make_console(quiet=False)

    if validate:
        results = validate_all_lenses()
        total_files = len(results)
        error_files = {f: errs for f, errs in results.items() if errs}

        if not error_files:
            console.print(f"\n  [bold green]✓[/] All {total_files} lenses passed validation.\n")
        else:
            console.print(
                f"\n  [bold red]✗[/] {len(error_files)}/{total_files} lenses have errors:\n"
            )
            for filename, errs in sorted(error_files.items()):
                console.print(f"  [yellow]{filename}[/]")
                for e in errs:
                    console.print(f"    [{e.field}] {e.message}")
            console.print()
            sys.exit(1)
        return

    stats = compute_lens_stats()
    console.print("\n  [bold]Lens Library[/]")
    console.print(f"  Total lenses:       {stats.total_lenses}")
    console.print(f"  Domains:            {len(stats.domains)}")
    console.print(f"  Total axioms:       {stats.total_axioms}")
    console.print(f"  Total patterns:     {stats.total_patterns}")
    console.print(f"  Avg axioms/lens:    {stats.avg_axioms_per_lens}")
    console.print()
    console.print("  [dim]Domain coverage:[/]")
    for domain in sorted(stats.domain_counts, key=lambda d: stats.domain_counts[d], reverse=True):
        console.print(f"    {domain:<22} {stats.domain_counts[domain]} lenses")
    console.print()


@click.command(
    name="workspace",
    help="Start an interactive workspace session on a codebase.",
)
@click.argument("directory", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--model", "-m", default="both", help="Model preset.")
@click.option(
    "--permission",
    "-p",
    default="workspace-write",
    type=click.Choice(["read-only", "workspace-write", "full-access"]),
    help="Permission level for file operations.",
)
def workspace_cmd(directory: Path, model: str, permission: str) -> None:
    """Start a workspace session."""
    console = make_console(quiet=False)
    print_banner(console)

    from hephaestus.workspace.scanner import WorkspaceScanner

    scanner = WorkspaceScanner(directory)
    summary = scanner.scan()

    console.print(f"\n  [bold yellow]Workspace:[/] {summary.root}")
    console.print(
        f"  [dim]{summary.total_files} files | {summary.total_lines:,} lines | {summary.primary_language}[/]"
    )
    if summary.git:
        console.print(
            f"  [dim]Git: {summary.git.branch} {'(dirty)' if summary.git.has_changes else '(clean)'}[/]"
        )
    if summary.repo_dossier:
        for line in summary.repo_dossier.summary_lines():
            console.print(f"  [dim]{line}[/]")
    console.print()
    console.print(
        "  [yellow]Workspace mode ready.[/] Use the REPL to chat about and modify this codebase."
    )
    console.print(f"  [dim]Permission: {permission} | Model: {model}[/]")
    console.print()

    # Launch REPL with workspace context
    from hephaestus.cli.repl import run_interactive

    run_interactive(console, model=model, workspace_root=directory)


@click.command(
    name="scan",
    help="Scan a codebase and print its structure.",
)
@click.argument("directory", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--tree", is_flag=True, help="Show directory tree.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def scan_cmd(directory: Path, tree: bool, as_json: bool) -> None:
    """Scan a codebase and display summary."""
    import json as _json

    from hephaestus.workspace.scanner import WorkspaceScanner

    console = make_console(quiet=False)
    scanner = WorkspaceScanner(directory)
    summary = scanner.scan()

    if as_json:
        data = {
            "root": summary.root,
            "total_files": summary.total_files,
            "total_lines": summary.total_lines,
            "primary_language": summary.primary_language,
            "languages": summary.languages,
            "config_files": summary.config_files,
            "entry_points": summary.entry_points,
            "top_level_dirs": summary.top_level_dirs,
        }
        if summary.git:
            data["git"] = {
                "branch": summary.git.branch,
                "head_sha": summary.git.head_sha,
                "has_changes": summary.git.has_changes,
                "remote": summary.git.remote_url,
            }
        if summary.repo_dossier:
            data["repo_dossier"] = summary.repo_dossier.to_dict()
        console.print(_json.dumps(data, indent=2), soft_wrap=True)
        return

    console.print()
    console.print("  [bold yellow]⚒️  Workspace Scan[/]")
    console.print()
    console.print(f"  {summary.format_summary()}")
    console.print()

    if summary.repo_dossier:
        console.print("  [bold]Repo Dossier:[/]")
        for line in summary.repo_dossier.architecture_notes:
            console.print(f"  - {line}")
        if summary.repo_dossier.commands:
            console.print(
                "  [dim]Commands:[/] "
                + "; ".join(command.command for command in summary.repo_dossier.commands[:4])
            )
        console.print()

    if tree and summary.tree:
        console.print("  [bold]Directory Tree:[/]")
        for line in summary.tree.splitlines():
            console.print(f"  {line}")
        console.print()


def main() -> None:
    """Entry point for the heph CLI command."""
    # Check for subcommands before Click parses argv
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        sys.argv = [sys.argv[0]]  # Strip 'init' so Click doesn't see it
        init_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # Strip 'batch'
        batch_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "lenses":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # Strip 'lenses'
        lenses_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "workspace":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        workspace_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        scan_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "vault":
        from hephaestus.cli.forgebase_commands import vault_cmd

        sys.argv = [sys.argv[0]] + sys.argv[2:]
        vault_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "ask":
        from hephaestus.cli.forgebase_commands import ask_cmd

        sys.argv = [sys.argv[0]] + sys.argv[2:]
        ask_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "fuse":
        from hephaestus.cli.forgebase_commands import fuse_cmd

        sys.argv = [sys.argv[0]] + sys.argv[2:]
        fuse_cmd(standalone_mode=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "fb-export":
        from hephaestus.cli.forgebase_commands import fb_export_cmd

        sys.argv = [sys.argv[0]] + sys.argv[2:]
        fb_export_cmd(standalone_mode=True)
        return
    cli()


if __name__ == "__main__":
    main()
