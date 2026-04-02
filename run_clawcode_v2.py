"""
Full-capability Hephaestus run on the claw-code repo.
Scans repo -> Genesis pipeline (all 5 stages, Pantheon v2) -> V2 architecture report.
Outputs to /home/ubuntu/.openclaw/workspace/hephaestus/outputs/clawcode-v2/
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ["OPENROUTER_API_KEY"] = "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"

from rich.console import Console
from rich.panel import Panel

from hephaestus.core.genesis import Genesis, GenesisConfig, PipelineStage
from hephaestus.workspace.context import WorkspaceContext
from hephaestus.workspace.scanner import WorkspaceScanner

console = Console()
REPO = Path("/home/ubuntu/.openclaw/workspace/claw-code")
OUT = Path("/home/ubuntu/.openclaw/workspace/hephaestus/outputs/clawcode-v2")
OUT.mkdir(parents=True, exist_ok=True)
M = "qwen/qwen3.6-plus:free"

PROBLEM = (
    "Design the next-generation architecture (V2) of claw-code - a Rust-based AI coding assistant "
    "with server/agent architecture. Consider: multi-agent orchestration, autonomous task planning, "
    "tool-use evolution, context management beyond RAG, self-improvement loops, memory systems, "
    "deployment patterns, and plugin ecosystems. Must be a genuine architectural leap."
)


def log(msg: str) -> None:
    console.print(f"  [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")


async def main() -> None:
    t0 = time.monotonic()
    console.print()
    console.print(Panel(
        f"[bold]Hephaestus - claw-code V2 Run\n\n"
        f"Repo: {REPO}\nModel: {M}\nOut: {OUT}",
        style="cyan",
    ))

    api_key = os.environ["OPENROUTER_API_KEY"]
    cfg = GenesisConfig(
        openrouter_api_key=api_key,
        decompose_model=M, search_model=M, score_model=M,
        translate_model=M, attack_model=M, defend_model=M,
        num_candidates=8, num_translations=4,
        use_interference_in_search=False,
        use_interference_in_translate=True,
        use_perplexity_research=False,
        use_pantheon_mode=True,
        pantheon_allow_fail_closed=False,
        pantheon_max_rounds=4,
        divergence_intensity="AGGRESSIVE",
        output_mode="SYSTEM",
        pantheon_athena_model=M,
        pantheon_hermes_model=M,
        pantheon_apollo_model=M,
    )

    pipeline = Genesis(cfg)

    log("Scanning claw-code...")
    ctx = WorkspaceContext.from_directory(REPO, budget_chars=12_000)
    repo_text = ctx.to_prompt_text()
    enriched = PROBLEM + "\n\n[REPOSITORY CONTEXT]\n" + repo_text
    (OUT / "workspace-context.md").write_text(repo_text, encoding="utf-8")
    log(f"Context: {len(repo_text)} chars")

    log("Starting pipeline...")
    report = None
    async for upd in pipeline.invent_stream(enriched):
        s = upd.stage.name.lower()
        if s == "decomposed":
            console.print(f"  [green]Decomposed:[/] {upd.data.structure}")
            console.print(f"    Maps: {', '.join(list(upd.data.problem_maps_to)[:5])}")
        elif s == "searched":
            console.print(f"  [green]{len(upd.data)} candidates[/]")
        elif s == "scored":
            scored = upd.data
            top = sorted(scored, key=lambda c: getattr(c, "combined_score", 0), reverse=True)
            if top:
                tc = getattr(top[0], "candidate", None) or top[0]
                name = getattr(tc, "source_domain", getattr(tc, "name", "candidate"))
                console.print(f"  [green]Top:[/] {name} ({top[0].combined_score:.2f})")
        elif s == "translated":
            console.print(f"  [green]{len(upd.data)} translations[/]")
        elif s == "verified":
            console.print(f"  [green]Verified[/]")
        elif s == "complete":
            report = upd.data
            console.print(f"  [bold green]COMPLETE[/]")
        elif s == "failed":
            raise Exception(upd.message or str(upd.data))
        # else: pass silently for intermediate stages

    if report is None:
        raise RuntimeError("No report returned")

    # Save full report JSON
    from dataclasses import asdict
    (OUT / "report-full.json").write_text(
        json.dumps(asdict(report), indent=2, default=str),
        encoding="utf-8",
    )
    log("Full report -> report-full.json")

    # Save each invention as markdown
    inventions = (report.verified_inventions or report.translations or [])
    log(f"Inventions: {len(inventions)}")
    for i, inv in enumerate(inventions):
        d = inv.__dict__ if hasattr(inv, "__dict__") else dict(inv)
        slug = d.get("name", "invention").lower().replace(" ", "-").replace("/", "_")[:60]
        p = OUT / f"report-{i+1:02d}-{slug}.md"
        md = [f"# {d.get('name', 'Invention')}", ""]
        if d.get("domain"):
            md += ["## Domain", d["domain"], ""]
        if d.get("core_principles"):
            md += ["## Core Principles"] + [f"- {x}" for x in d["core_principles"]] + [""]
        if d.get("components"):
            md.append("## Components")
            for c in d["components"]:
                md += [f"### {c.get('name','?')}", c.get("description",""), ""]
        p.write_text("\n".join(md), encoding="utf-8")
        log(f"Report -> {p.name}")

    elapsed = time.monotonic() - t0
    top = report.top_invention
    top_name = top.get("name") if isinstance(top, dict) else getattr(top, "name", "N/A")
    console.print()
    console.print(Panel(
        f"[bold green]Done in {elapsed/60:.1f}m\n"
        f"Top: {top_name}\n"
        f"Inventions: {len(inventions)}\n"
        f"Out: {OUT}",
        style="green",
    ))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]FAILED: {e}[/]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
