"""Publication-ready markdown export for invention reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ExportConfig:
    """Controls what sections appear in the exported report."""

    include_confidence: bool = True
    include_roadmap: bool = True
    include_alternatives: bool = True
    include_prior_art: bool = True
    include_cost: bool = False
    title_prefix: str = ""
    author: str = ""
    date: str = ""

    def __post_init__(self) -> None:
        if not self.date:
            self.date = datetime.now(UTC).strftime("%Y-%m-%d")


def export_markdown(report: Any, config: ExportConfig | None = None) -> str:
    """Generate a publication-ready markdown document from an InventionReport."""
    cfg = config or ExportConfig()
    lines: list[str] = []

    # Title block
    title = (
        f"{cfg.title_prefix}{report.invention_name}" if cfg.title_prefix else report.invention_name
    )
    lines.append(f"# {title}")
    lines.append("")
    meta_parts = []
    if cfg.author:
        meta_parts.append(f"**Author:** {cfg.author}")
    meta_parts.append(f"**Date:** {cfg.date}")
    meta_parts.append(f"**Source Domain:** {report.source_domain}")
    lines.append(" | ".join(meta_parts))
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"This invention, **{report.invention_name}**, addresses the problem of "
        f"*{_truncate(report.problem, 200)}* by transferring structural insights from "
        f"**{report.source_domain}** (domain distance: {report.domain_distance:.2f}, "
        f"structural fidelity: {report.structural_fidelity:.2f}, "
        f"novelty score: {report.novelty_score:.2f})."
    )
    lines.append("")

    # Problem
    lines.append("## Problem Statement")
    lines.append("")
    lines.append(report.problem)
    lines.append("")

    # Structural form
    if report.structural_form:
        lines.append("## Structural Form")
        lines.append("")
        lines.append(report.structural_form)
        lines.append("")

    baseline = getattr(report, "baseline_dossier", None)
    if baseline is not None:
        lines.append("## State of the Art Recon")
        lines.append("")
        lines.append(
            getattr(baseline, "summary", "") or "No external reconnaissance summary available."
        )
        lines.append("")
        avoid = getattr(baseline, "keywords_to_avoid", [])
        if avoid:
            lines.append("### Conventional Mechanisms to Avoid")
            for item in avoid[:8]:
                lines.append(f"- {item}")
            lines.append("")

    # Solution
    lines.append("## Solution Overview")
    lines.append("")
    if report.mechanism:
        lines.append("### Key Insight")
        lines.append("")
        lines.append(report.mechanism)
        lines.append("")

    # Mapping table
    if report.translation:
        lines.append("### Structural Mapping")
        lines.append("")
        if "→" in report.translation or "•" in report.translation:
            for line in report.translation.strip().split("\n"):
                lines.append(line)
        else:
            lines.append(report.translation)
        lines.append("")

    # Architecture
    if report.architecture:
        lines.append("## Architecture")
        lines.append("")
        lines.append(report.architecture)
        lines.append("")

    # Confidence
    if cfg.include_confidence:
        lines.append("## Confidence Analysis")
        lines.append("")
        lines.append("| Metric | Score | Interpretation |")
        lines.append("|--------|-------|----------------|")
        lines.append(
            f"| Domain Distance | {report.domain_distance:.2f} | "
            f"{'Far transfer (high novelty)' if report.domain_distance > 0.8 else 'Moderate transfer' if report.domain_distance > 0.5 else 'Near transfer'} |"
        )
        lines.append(
            f"| Structural Fidelity | {report.structural_fidelity:.2f} | "
            f"{'Strong structural match' if report.structural_fidelity > 0.8 else 'Moderate match' if report.structural_fidelity > 0.5 else 'Loose analogy'} |"
        )
        lines.append(
            f"| Novelty Score | {report.novelty_score:.2f} | "
            f"{'Highly novel' if report.novelty_score > 0.8 else 'Moderately novel' if report.novelty_score > 0.5 else 'Low novelty'} |"
        )
        lines.append("")

    # Limitations
    if report.where_analogy_breaks:
        lines.append("## Known Limitations")
        lines.append("")
        lines.append(report.where_analogy_breaks)
        lines.append("")

    # Roadmap
    if cfg.include_roadmap:
        lines.append("## Implementation Roadmap")
        lines.append("")
        lines.append("1. **Validate core mechanism** — prototype the key insight in isolation")
        lines.append("2. **Build minimal system** — implement the architecture skeleton")
        lines.append("3. **Harden** — address known limitations and edge cases")
        lines.append("4. **Benchmark** — compare against existing solutions quantitatively")
        lines.append("")

    # Alternatives
    alts = getattr(report, "alternatives", [])
    if cfg.include_alternatives and alts:
        lines.append("## Alternative Approaches")
        lines.append("")
        for alt in alts:
            lines.append(
                f"- **{alt.invention_name}** (from {alt.source_domain}, "
                f"novelty: {alt.novelty_score:.2f})"
            )
            if alt.summary:
                lines.append(f"  {alt.summary}")
        lines.append("")

    # Prior art
    prior = getattr(report, "prior_art_report", None)
    if cfg.include_prior_art and prior is not None:
        lines.append("## Prior Art")
        lines.append("")
        summary = getattr(prior, "summary", "")
        if summary:
            lines.append(summary)
        lines.append("")

    grounding = getattr(report, "external_grounding_report", None)
    if grounding is not None:
        lines.append("## External Grounding")
        lines.append("")
        lines.append(
            getattr(grounding, "summary", "") or "No external grounding summary available."
        )
        lines.append("")
        for title, values in [
            ("Closest Related Work", getattr(grounding, "closest_related_work", [])),
            ("Adjacent Fields", getattr(grounding, "adjacent_fields", [])),
            ("Practitioner Risks", getattr(grounding, "practitioner_risks", [])),
            ("Notable Projects", getattr(grounding, "notable_projects", [])),
        ]:
            if values:
                lines.append(f"### {title}")
                for item in values[:8]:
                    lines.append(f"- {item}")
                lines.append("")

    risk = getattr(report, "implementation_risk_review", None)
    if risk is not None:
        lines.append("## Implementation Risk Review")
        lines.append("")
        lines.append(getattr(risk, "summary", "") or "No grounded risk review available.")
        lines.append("")
        for title, values in [
            ("Major Risks", getattr(risk, "major_risks", [])),
            ("Operational Constraints", getattr(risk, "operational_constraints", [])),
            ("Likely Failure Modes", getattr(risk, "likely_failure_modes", [])),
            ("Mitigations", getattr(risk, "mitigations", [])),
        ]:
            if values:
                lines.append(f"### {title}")
                for item in values[:8]:
                    lines.append(f"- {item}")
                lines.append("")

    pantheon = getattr(report, "pantheon_state", None)
    if pantheon is not None:
        lines.append("## Pantheon Council")
        lines.append("")
        lines.append(f"- Mode: `{getattr(pantheon, 'mode', 'inactive')}`")
        lines.append(
            f"- Resolution mode: `{getattr(pantheon, 'resolution_mode', 'TASK_SENSITIVE')}`"
        )
        lines.append(f"- Outcome tier: `{getattr(pantheon, 'outcome_tier', 'PENDING')}`")
        lines.append(
            f"- Consensus achieved: `{bool(getattr(pantheon, 'consensus_achieved', False))}`"
        )
        lines.append(f"- Final verdict: `{getattr(pantheon, 'final_verdict', 'UNKNOWN')}`")
        winning_candidate_id = getattr(pantheon, "winning_candidate_id", "")
        if winning_candidate_id:
            lines.append(f"- Winning candidate: `{winning_candidate_id}`")
        canon = getattr(pantheon, "canon", None)
        if canon is not None and getattr(canon, "structural_form", ""):
            lines.append(f"- Athena canon: {getattr(canon, 'structural_form', '')}")
        dossier = getattr(pantheon, "dossier", None)
        if dossier is not None and getattr(dossier, "repo_reality_summary", ""):
            lines.append(f"- Hermes dossier: {getattr(dossier, 'repo_reality_summary', '')}")
        screenings = getattr(pantheon, "screenings", []) or []
        if screenings:
            lines.append("")
            lines.append("### Pre-Council Screening")
            for screening in screenings[:6]:
                lines.append(
                    f"- `{screening.candidate_id}` survived=`{bool(getattr(screening, 'survived', False))}` "
                    f"priority={float(getattr(screening, 'priority_score', 0.0) or 0.0):.2f}"
                )
                summary = getattr(screening, "summary", "")
                if summary:
                    lines.append(f"  {summary}")
        rounds = getattr(pantheon, "rounds", []) or []
        if rounds:
            lines.append("")
            lines.append("### Council Rounds")
            for round_ in rounds[-4:]:
                lines.append(
                    f"- Round {getattr(round_, 'round_index', '?')}: "
                    f"`{getattr(round_, 'candidate_id', '')}` "
                    f"consensus=`{bool(getattr(round_, 'consensus', False))}` "
                    f"tier=`{getattr(round_, 'outcome_tier', 'PENDING')}`"
                )
                summary = getattr(round_, "revision_summary", "")
                if summary:
                    lines.append(f"  {summary}")
        caveats = getattr(pantheon, "caveats", []) or []
        if caveats:
            lines.append("")
            lines.append("### Pantheon Caveats")
            for item in caveats[:8]:
                lines.append(f"- {item}")
        objection_ledger = getattr(pantheon, "objection_ledger", []) or []
        if objection_ledger:
            lines.append("")
            lines.append("### Objection Ledger")
            for objection in objection_ledger[:8]:
                lines.append(
                    f"- `{getattr(objection, 'objection_id', '')}` "
                    f"[{getattr(objection, 'severity', 'REPAIRABLE')}/"
                    f"{getattr(objection, 'status', 'OPEN')}] "
                    f"{getattr(objection, 'statement', '')}"
                )
        unresolved = getattr(pantheon, "unresolved_vetoes", []) or []
        if unresolved:
            lines.append("")
            lines.append("### Unresolved Vetoes")
            for item in unresolved[:8]:
                lines.append(f"- {item}")
        lines.append("")

    # Cost
    if cfg.include_cost:
        lines.append("## Generation Metadata")
        lines.append("")
        lines.append(f"- **Cost:** ${report.cost_usd:.4f}")
        models = getattr(report, "models_used", [])
        if models:
            lines.append(f"- **Models:** {', '.join(models)}")
        lines.append(f"- **Depth:** {report.depth}")
        wt = getattr(report, "wall_time_seconds", 0)
        if wt:
            lines.append(f"- **Generation time:** {wt:.1f}s")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"*Generated by [Hephaestus](https://github.com/hephaestus-ai/hephaestus) on {cfg.date}*"
    )
    lines.append("")

    return "\n".join(lines)


def export_to_file(report: Any, path: Path, config: ExportConfig | None = None) -> None:
    """Export an invention report to a file. Format inferred from extension."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ext = path.suffix.lower()
    if ext == ".json":
        from hephaestus.output.formatter import OutputFormatter

        content = OutputFormatter().to_json(report)
    elif ext == ".txt":
        from hephaestus.output.formatter import OutputFormatter

        content = OutputFormatter().to_plain(report)
    else:
        content = export_markdown(report, config)

    path.write_text(content, encoding="utf-8")


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


__all__ = ["ExportConfig", "export_markdown", "export_to_file"]
