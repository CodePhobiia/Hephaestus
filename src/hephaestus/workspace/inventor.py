"""Workspace-aware invention — analyze a codebase and invent improvements.

The WorkspaceInventor reads the codebase, identifies structural problems
and opportunities, then runs the Hephaestus genesis pipeline on each one
to produce cross-domain inventions that could improve the project.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from hephaestus.workspace.context import WorkspaceContext
from hephaestus.workspace.scanner import WorkspaceScanner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Analysis prompt — this asks the model to identify real problems
# ---------------------------------------------------------------------------

_ANALYSIS_SYSTEM = """\
You are a senior software architect analyzing a codebase to identify
structural problems, performance bottlenecks, missing capabilities,
and architectural opportunities.

Focus on problems that are:
1. Structurally interesting (not just "add more tests")
2. Non-obvious — things the developers might not have considered
3. Concrete enough to solve with a specific mechanism
4. Significant enough to improve the product meaningfully

For each problem, write it as a clear engineering challenge that could
benefit from cross-domain structural transfer.

Return ONLY a JSON array of objects:
[
  {
    "problem": "one-sentence problem description suitable for invention",
    "category": "architecture|performance|reliability|scalability|ux|security|data",
    "severity": "high|medium|low",
    "context": "brief explanation of why this matters for this specific codebase"
  }
]

Return 3-7 problems, ranked by impact. Be specific to THIS codebase.
"""

_ANALYSIS_PROMPT = """\
Analyze this codebase and identify structural problems and opportunities
that could benefit from novel engineering solutions.

{workspace_context}

Return a JSON array of problems to solve.
"""


@dataclass
class IdentifiedProblem:
    """A problem identified by analyzing the codebase."""
    problem: str
    category: str
    severity: str
    context: str


@dataclass
class WorkspaceInvention:
    """An invention produced for a specific codebase problem."""
    problem: IdentifiedProblem
    invention_name: str = ""
    source_domain: str = ""
    key_insight: str = ""
    architecture: str = ""
    novelty_score: float = 0.0
    verdict: str = ""
    implementation_hint: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return bool(self.invention_name) and not self.error


@dataclass
class WorkspaceInventionReport:
    """Full report of workspace-aware invention run."""
    workspace_root: str
    problems_found: int = 0
    inventions_attempted: int = 0
    inventions_succeeded: int = 0
    inventions: list[WorkspaceInvention] = field(default_factory=list)
    total_cost_usd: float = 0.0


class WorkspaceInventor:
    """Analyzes a codebase and invents improvements using the genesis pipeline.

    Usage::

        inventor = WorkspaceInventor(adapter, workspace_root=Path("."))
        report = await inventor.analyze_and_invent()
        for inv in report.inventions:
            print(f"{inv.invention_name}: {inv.key_insight}")
    """

    def __init__(
        self,
        adapter: Any,
        workspace_root: Path | str,
        *,
        max_inventions: int = 5,
        depth: int = 3,
        model: str = "both",
        intensity: str = "STANDARD",
    ) -> None:
        self.adapter = adapter
        self.root = Path(workspace_root).resolve()
        self.max_inventions = max_inventions
        self.depth = depth
        self.model = model
        self.intensity = intensity

    async def analyze_codebase(self) -> list[IdentifiedProblem]:
        """Use the model to analyze the codebase and identify problems."""
        from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig

        context = WorkspaceContext.from_directory(self.root, budget_chars=20_000)
        prompt = _ANALYSIS_PROMPT.format(workspace_context=context.to_prompt_text())

        harness = DeepForgeHarness(
            adapter=self.adapter,
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=2000,
                temperature=0.7,
            ),
        )
        result = await harness.forge(prompt, system=_ANALYSIS_SYSTEM)
        return _parse_problems(result.output)

    async def invent_for_problem(
        self,
        problem: IdentifiedProblem,
        console: Console | None = None,
    ) -> WorkspaceInvention:
        """Run the genesis pipeline for a single identified problem."""
        inv = WorkspaceInvention(problem=problem)

        # Enrich the problem with workspace context
        enriched = (
            f"{problem.problem}\n\n"
            f"Context: This is for a {self.root.name} codebase. {problem.context}"
        )

        try:
            import os
            from hephaestus.cli.main import _build_genesis_config
            from hephaestus.core.genesis import Genesis

            config = _build_genesis_config(
                model=self.model,
                depth=self.depth,
                candidates=6,
                domain=None,
                anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
                openai_key=os.environ.get("OPENAI_API_KEY"),
                divergence_intensity=self.intensity,
                output_mode="MECHANISM",
            )

            genesis = Genesis(config)
            report = await genesis.invent(enriched)

            top = report.top_invention
            if top:
                inv.invention_name = top.invention_name
                inv.source_domain = top.source_domain
                inv.novelty_score = top.novelty_score
                inv.verdict = top.verdict
                inv.key_insight = getattr(top.translation, "key_insight", "")
                inv.architecture = getattr(top.translation, "architecture", "")
                inv.implementation_hint = _generate_impl_hint(
                    inv.architecture, problem.problem, self.root.name
                )
            else:
                inv.error = "Pipeline produced no viable invention"

        except Exception as exc:
            inv.error = str(exc)[:200]
            logger.warning("Invention failed for '%s': %s", problem.problem, exc)

        return inv

    async def analyze_and_invent(
        self,
        console: Console | None = None,
    ) -> WorkspaceInventionReport:
        """Full pipeline: analyze codebase → identify problems → invent solutions."""
        report = WorkspaceInventionReport(workspace_root=str(self.root))

        if console:
            console.print(f"\n  [bold cyan]Analyzing codebase...[/] {self.root.name}/")

        # Step 1: Analyze
        try:
            problems = await self.analyze_codebase()
        except Exception as exc:
            if console:
                console.print(f"  [red]Analysis failed: {exc}[/]")
            return report

        report.problems_found = len(problems)
        problems = problems[:self.max_inventions]

        if console:
            console.print(f"  [green]Found {len(problems)} problems to solve[/]\n")
            for i, p in enumerate(problems, 1):
                console.print(f"  [{p.severity.upper()}] {i}. {p.problem}")
            console.print()

        # Step 2: Invent for each problem
        report.inventions_attempted = len(problems)
        for i, problem in enumerate(problems, 1):
            if console:
                console.print(f"  [cyan]Inventing [{i}/{len(problems)}]:[/] {problem.problem[:60]}...")

            inv = await self.invent_for_problem(problem, console)
            report.inventions.append(inv)

            if inv.success:
                report.inventions_succeeded += 1
                if console:
                    console.print(
                        f"    [green]✓[/] {inv.invention_name} "
                        f"[dim](from {inv.source_domain}, novelty: {inv.novelty_score:.2f})[/]"
                    )
            else:
                if console:
                    console.print(f"    [red]✗[/] {inv.error[:60]}")

        return report

    def format_report(self, report: WorkspaceInventionReport) -> str:
        """Format the workspace invention report as markdown."""
        lines = [
            f"# Workspace Inventions for {Path(report.workspace_root).name}",
            "",
            f"**Problems found:** {report.problems_found}",
            f"**Inventions attempted:** {report.inventions_attempted}",
            f"**Inventions succeeded:** {report.inventions_succeeded}",
            "",
        ]

        for i, inv in enumerate(report.inventions, 1):
            if inv.success:
                lines.extend([
                    f"## {i}. {inv.invention_name}",
                    "",
                    f"**Problem:** {inv.problem.problem}",
                    f"**Source Domain:** {inv.source_domain}",
                    f"**Novelty Score:** {inv.novelty_score:.2f}",
                    f"**Verdict:** {inv.verdict}",
                    "",
                    f"### Key Insight",
                    inv.key_insight or "N/A",
                    "",
                    f"### Architecture",
                    inv.architecture or "N/A",
                    "",
                    f"### How to Implement in This Codebase",
                    inv.implementation_hint or "See architecture above.",
                    "",
                    "---",
                    "",
                ])
            else:
                lines.extend([
                    f"## {i}. ❌ {inv.problem.problem}",
                    f"**Error:** {inv.error}",
                    "",
                    "---",
                    "",
                ])

        return "\n".join(lines)


def _parse_problems(text: str) -> list[IdentifiedProblem]:
    """Parse the model's JSON response into IdentifiedProblem objects."""
    import json
    import re

    # Extract JSON array from response
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return []

    problems = []
    for item in data:
        if isinstance(item, dict) and "problem" in item:
            problems.append(IdentifiedProblem(
                problem=item["problem"],
                category=item.get("category", "architecture"),
                severity=item.get("severity", "medium"),
                context=item.get("context", ""),
            ))

    return problems


def _generate_impl_hint(architecture: str, problem: str, project_name: str) -> str:
    """Generate a brief implementation hint for the specific codebase."""
    if not architecture:
        return ""
    return (
        f"To implement this in {project_name}:\n"
        f"1. Identify the components in the codebase that relate to: {problem[:100]}\n"
        f"2. Apply the architectural pattern described above\n"
        f"3. Start with a minimal prototype of the core mechanism\n"
        f"4. Wire it into the existing architecture incrementally"
    )


__all__ = [
    "WorkspaceInventor",
    "WorkspaceInventionReport",
    "WorkspaceInvention",
    "IdentifiedProblem",
]
