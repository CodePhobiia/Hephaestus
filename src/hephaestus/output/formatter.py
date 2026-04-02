"""
Output Formatter.

Takes the result of a Hephaestus genesis pipeline run and renders it in
multiple formats:

- **Markdown** — Beautiful report with the full ⚒️ HEPHAESTUS header
- **JSON** — Structured, machine-readable output
- **Plain text** — Pipe-friendly, no markup

Every output format includes the complete invention report:
problem, structural form, invention name, source domain, domain distance,
structural fidelity, novelty score, mechanism, translation, architecture,
where the analogy breaks, prior art check, novelty proof, alternative
inventions, and cost summary.

Usage
-----
::

    from hephaestus.output.formatter import InventionReport, OutputFormatter, OutputFormat

    report = InventionReport(
        problem="I need a load balancer for unpredictable traffic",
        structural_form="...",
        invention_name="Pheromone-Gradient Load Balancer",
        source_domain="Ant Colony Optimization",
        domain_distance=0.94,
        structural_fidelity=0.87,
        novelty_score=0.91,
        mechanism="...",
        translation="...",
        architecture="...",
        where_analogy_breaks="...",
        cost_usd=1.18,
    )

    formatter = OutputFormatter()
    print(formatter.format(report, OutputFormat.MARKDOWN))
    print(formatter.format(report, OutputFormat.JSON))
    print(formatter.format(report, OutputFormat.PLAIN))
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from unittest.mock import Mock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output format enum
# ---------------------------------------------------------------------------


class OutputFormat(Enum):
    """Supported output formats for the invention report."""

    MARKDOWN = auto()
    JSON = auto()
    PLAIN = auto()


# ---------------------------------------------------------------------------
# Alternative Invention summary
# ---------------------------------------------------------------------------


@dataclass
class AlternativeInvention:
    """
    A runner-up invention from the genesis pipeline.

    Attributes
    ----------
    rank:
        Rank (2 for second place, 3 for third, etc.).
    invention_name:
        Name of the alternative invention.
    source_domain:
        Source domain it came from.
    domain_distance:
        Domain distance score.
    structural_fidelity:
        Structural fidelity score.
    novelty_score:
        Composite novelty score.
    summary:
        One-paragraph summary of the alternative invention.
    """

    rank: int
    invention_name: str
    source_domain: str
    domain_distance: float = 0.0
    structural_fidelity: float = 0.0
    novelty_score: float = 0.0
    summary: str = ""


# ---------------------------------------------------------------------------
# InventionReport — shared data structure
# ---------------------------------------------------------------------------


@dataclass
class InventionReport:
    """
    The full result of one Hephaestus invention pipeline run.

    This is the central data structure passed to the formatter.  It is also
    the type returned by the genesis pipeline (Phase 3) and consumed by the
    CLI, SDK, and web interface.

    Attributes
    ----------
    problem:
        The original problem as stated by the user.
    structural_form:
        Abstract mathematical/structural form of the problem (from Stage 1).
    invention_name:
        The name of the invented solution.
    source_domain:
        Source domain of the solution (e.g. ``"Ant Colony Optimization"``).
    domain_distance:
        Quantified domain distance (0–1).
    structural_fidelity:
        How precisely the structural mapping holds (0–1).
    novelty_score:
        Composite novelty score (0–1).
    mechanism:
        How the foreign solution works in its native domain.
    translation:
        Element-by-element mapping into the target domain.
    architecture:
        Actual implementation: pseudocode, math, or architecture description.
    where_analogy_breaks:
        Honest description of the analogy's limitations.
    prior_art_report:
        Optional :class:`~hephaestus.output.prior_art.PriorArtReport` object.
    baseline_dossier:
        Optional state-of-the-art reconnaissance summary collected before
        invention.
    external_grounding_report:
        Optional grounded report connecting the invention to related work and
        adjacent systems.
    implementation_risk_review:
        Optional grounded implementation / operational risk review.
    lens_engine_state:
        Optional Adaptive Bundle-Proof lens-engine state attached to the run.
    pantheon_state:
        Optional Pantheon council state attached to the run.
    novelty_proof:
        Optional :class:`~hephaestus.output.proof.NoveltyProof` object.
    alternatives:
        Runner-up inventions from the genesis pipeline.
    cost_usd:
        Total API cost in USD.
    models_used:
        List of model names used during generation.
    depth:
        DeepForge depth (anti-training pressure rounds).
    wall_time_seconds:
        Total elapsed time.
    """

    problem: str
    structural_form: str
    invention_name: str
    source_domain: str
    domain_distance: float
    structural_fidelity: float
    novelty_score: float
    mechanism: str
    translation: str
    architecture: str
    where_analogy_breaks: str
    prior_art_report: Any | None = None    # PriorArtReport
    baseline_dossier: Any | None = None
    external_grounding_report: Any | None = None
    implementation_risk_review: Any | None = None
    lens_engine_state: Any | None = None
    pantheon_state: Any | None = None
    pantheon_runtime: Any | None = None
    deliberation_graph: Any | None = None
    novelty_proof: Any | None = None       # NoveltyProof
    alternatives: list[AlternativeInvention] = field(default_factory=list)
    cost_usd: float = 0.0
    cost_breakdown: Any | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    models_used: list[str] = field(default_factory=list)
    depth: int = 3
    wall_time_seconds: float = 0.0


# ---------------------------------------------------------------------------
# OutputFormatter
# ---------------------------------------------------------------------------


class OutputFormatter:
    """
    Formats an :class:`InventionReport` into various output formats.

    Parameters
    ----------
    indent_json:
        JSON indentation level (default 2).
    """

    def __init__(self, indent_json: int = 2) -> None:
        self._indent = indent_json

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    def format(self, report: InventionReport, fmt: OutputFormat = OutputFormat.MARKDOWN) -> str:
        """
        Format an :class:`InventionReport`.

        Parameters
        ----------
        report:
            The invention report to format.
        fmt:
            Output format (MARKDOWN, JSON, or PLAIN).

        Returns
        -------
        str
            Formatted string output.
        """
        match fmt:
            case OutputFormat.MARKDOWN:
                return self.to_markdown(report)
            case OutputFormat.JSON:
                return self.to_json(report)
            case OutputFormat.PLAIN:
                return self.to_plain(report)
            case _:
                raise ValueError(f"Unknown output format: {fmt}")

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def to_markdown(self, report: InventionReport) -> str:
        """Render the invention report as rich Markdown."""
        lines: list[str] = []

        # ── Header ──────────────────────────────────────────────────────────
        lines += [
            "═══════════════════════════════════════════════════",
            "⚒️  HEPHAESTUS — Invention Report",
            "═══════════════════════════════════════════════════",
            "",
            "**PROBLEM:**",
            f"  {_as_text(report.problem, 'Not provided.')}",
            "",
            "**STRUCTURAL FORM:**",
            f"  {_as_text(report.structural_form, 'Not available.')}",
            "",
        ]

        if report.baseline_dossier is not None:
            lines += [
                "**STATE OF THE ART RECON:**",
                "",
                f"  {_as_text(getattr(report.baseline_dossier, 'summary', ''), 'No external reconnaissance summary available.')}",
                "",
            ]
            avoid = getattr(report.baseline_dossier, "keywords_to_avoid", [])
            if avoid:
                lines.append("  Conventional target-domain mechanisms to avoid reinventing:")
                for item in avoid[:8]:
                    lines.append(f"  - {item}")
                lines.append("")

        # ── Primary invention ────────────────────────────────────────────────
        lines += [
            "───────────────────────────────────────────────────",
            f"**INVENTION:** {report.invention_name}",
            f"**SOURCE DOMAIN:** {report.source_domain}",
            f"**DOMAIN DISTANCE:** {_unicode_bar(report.domain_distance)}",
            f"**STRUCTURAL FIDELITY:** {_unicode_bar(report.structural_fidelity)}",
            f"**NOVELTY SCORE:** {_unicode_bar(report.novelty_score)}",
            "───────────────────────────────────────────────────",
            "",
        ]

        # ── Confidence ────────────────────────────────────────────────────────
        lines += [
            "**CONFIDENCE:**",
            "",
            f"  Domain Distance: {_domain_distance_interpretation(report.domain_distance)}",
            f"  Structural Fidelity: {_structural_fidelity_interpretation(report.structural_fidelity)}",
            "",
        ]

        # ── Mechanism ────────────────────────────────────────────────────────
        lines += [
            "**MECHANISM:**",
            "",
        ]
        for para in _split_paragraphs(report.mechanism):
            lines.append(f"  {para}")
            lines.append("")

        # ── Translation ──────────────────────────────────────────────────────
        lines += [
            "**TRANSLATION:**",
            "",
        ]
        for para in _split_paragraphs(report.translation):
            lines.append(f"  {para}")
            lines.append("")

        # ── Architecture ────────────────────────────────────────────────────
        lines += [
            "**ARCHITECTURE:**",
            "",
        ]
        arch = _as_text(report.architecture, "Not available.")
        if "```" in arch or arch.strip().startswith("#"):
            # Already has code blocks
            lines.append(arch)
        else:
            lines.append("```")
            lines.append(arch)
            lines.append("```")
        lines.append("")

        # ── Where analogy breaks ─────────────────────────────────────────────
        lines += [
            "**WHERE THE ANALOGY BREAKS:**",
            "",
            f"  {_as_text(report.where_analogy_breaks, 'No major analogy limits were recorded.')}",
            "",
        ]

        # ── Prior art check ──────────────────────────────────────────────────
        lines += [
            "**PRIOR ART CHECK:**",
            "",
        ]
        if report.prior_art_report is not None:
            summary = _as_text(getattr(report.prior_art_report, "summary", ""), "Prior art summary not available.")
            status = getattr(report.prior_art_report, "novelty_status", "UNKNOWN")
            lines.append(f"  {summary}")
            lines.append("")
            lines.append(f"  **Status:** `{status}`")
        else:
            lines.append("  Prior art search not performed.")
        lines.append("")

        if report.external_grounding_report is not None:
            lines += [
                "**EXTERNAL GROUNDING:**",
                "",
                f"  {_as_text(getattr(report.external_grounding_report, 'summary', ''), 'No external grounding summary available.')}",
                "",
            ]
            for heading, key in [
                ("Closest related work", "closest_related_work"),
                ("Adjacent fields", "adjacent_fields"),
                ("Practitioner risks", "practitioner_risks"),
                ("Notable projects", "notable_projects"),
            ]:
                values = getattr(report.external_grounding_report, key, [])
                if values:
                    lines.append(f"  {heading}:")
                    for item in values[:6]:
                        lines.append(f"  - {item}")
                    lines.append("")

        if report.implementation_risk_review is not None:
            lines += [
                "**IMPLEMENTATION RISK REVIEW:**",
                "",
                f"  {_as_text(getattr(report.implementation_risk_review, 'summary', ''), 'No grounded risk review available.')}",
                "",
            ]
            for heading, key in [
                ("Major risks", "major_risks"),
                ("Operational constraints", "operational_constraints"),
                ("Likely failure modes", "likely_failure_modes"),
                ("Mitigations", "mitigations"),
            ]:
                values = getattr(report.implementation_risk_review, key, [])
                if values:
                    lines.append(f"  {heading}:")
                    for item in values[:6]:
                        lines.append(f"  - {item}")
                lines.append("")

        if report.lens_engine_state is not None:
            lines += [
                "**LENS ENGINE:**",
                "",
            ]
            lines.extend(_lens_engine_markdown_lines(report.lens_engine_state))
            lines.append("")

        if report.pantheon_state is not None:
            lines += [
                "**PANTHEON MODE:**",
                "",
            ]
            lines.extend(_pantheon_markdown_lines(report.pantheon_state))
            if report.pantheon_runtime is not None:
                lines.extend(_pantheon_runtime_markdown_lines(report.pantheon_runtime))
            lines.append("")

        if report.deliberation_graph is not None:
            lines += [
                "**RUNTIME ORCHESTRATION:**",
                "",
            ]
            lines.extend(_deliberation_graph_markdown_lines(report.deliberation_graph))
            lines.append("")

        # ── Novelty proof ────────────────────────────────────────────────────
        lines += [
            "**NOVELTY PROOF:**",
            "",
        ]
        if report.novelty_proof is not None:
            proof = report.novelty_proof
            score = getattr(proof, "novelty_score", report.novelty_score)
            confidence = getattr(proof, "confidence", "N/A")
            formal = _as_text(getattr(proof, "formal_statement", ""))
            caveats = getattr(proof, "caveats", [])

            lines += [
                f"  Score: **{score:.4f}** | Confidence: **{confidence}**",
                "",
            ]
            if formal:
                lines.append("  <details>")
                lines.append("  <summary>Full formal proof</summary>")
                lines.append("")
                lines.append("  ```")
                lines.append(formal)
                lines.append("  ```")
                lines.append("  </details>")
                lines.append("")

            if caveats:
                lines.append("  **Caveats:**")
                for cav in caveats:
                    lines.append(f"  - {cav}")
                lines.append("")
        else:
            novelty_score = report.novelty_score
            lines.append(
                f"  Novelty score: **{novelty_score:.4f}** "
                f"(based on domain distance × structural fidelity)"
            )
        lines.append("")

        # ── Alternatives ─────────────────────────────────────────────────────
        if report.alternatives:
            lines += [
                "───────────────────────────────────────────────────",
                "**ALTERNATIVE INVENTIONS** *(runner-ups)*",
                "",
            ]
            for alt in report.alternatives:
                lines += [
                    f"**{alt.rank}. {_as_text(alt.invention_name, 'Unnamed alternative')}**",
                    f"   Source: {_as_text(alt.source_domain, 'Unknown domain')} | "
                    f"Distance: {alt.domain_distance:.2f} | "
                    f"Novelty: {alt.novelty_score:.2f}",
                ]
                if alt.summary:
                    lines.append(f"   {_as_text(alt.summary)}")
                lines.append("")
            lines.append("───────────────────────────────────────────────────")
            lines.append("")

        # ── Implementation roadmap ────────────────────────────────────────────
        lines += [
            "**IMPLEMENTATION ROADMAP:**",
            "",
            "  **Phase 1:** Validate core mechanism (prototype the key insight)",
            "  **Phase 2:** Build minimal working system (architecture skeleton)",
            "  **Phase 3:** Harden (address where analogy breaks)",
            "",
        ]
        auto_steps = _generate_roadmap_steps(report.architecture)
        if auto_steps:
            lines.append("  **Suggested steps:**")
            for step in auto_steps:
                lines.append(f"  - {step}")
            lines.append("")

        # ── Footer ───────────────────────────────────────────────────────────
        model_str = " + ".join(report.models_used) if report.models_used else "Unknown"
        time_str = f"{report.wall_time_seconds:.1f}s" if report.wall_time_seconds > 0 else "N/A"
        in_tokens = self._safe_int(getattr(report, "input_tokens", 0))
        out_tokens = self._safe_int(getattr(report, "output_tokens", 0))
        lines += [
            f"**Cost:** ${report.cost_usd:.2f} | "
            f"**Models:** {model_str} | "
            f"**Tokens:** {in_tokens:,} in / {out_tokens:,} out | "
            f"**Depth:** {report.depth} | "
            f"**Time:** {time_str}",
            "",
        ]
        if report.cost_breakdown is not None:
            lines += [
                f"**Stage Costs:** {_cost_breakdown_text(report.cost_breakdown, markdown=True)}",
                "",
            ]
        lines += [
            "═══════════════════════════════════════════════════",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self, report: InventionReport) -> str:
        """Render the invention report as structured JSON."""
        data: dict[str, Any] = {
            "hephaestus_invention_report": {
                "problem": report.problem,
                "structural_form": report.structural_form,
                "invention": {
                    "name": report.invention_name,
                    "source_domain": report.source_domain,
                    "domain_distance": round(report.domain_distance, 4),
                    "structural_fidelity": round(report.structural_fidelity, 4),
                    "novelty_score": round(report.novelty_score, 4),
                    "mechanism": report.mechanism,
                    "translation": report.translation,
                    "architecture": report.architecture,
                    "where_analogy_breaks": report.where_analogy_breaks,
                },
                "prior_art": _prior_art_to_dict(report.prior_art_report),
                "state_of_the_art": _research_obj_to_dict(report.baseline_dossier),
                "external_grounding": _research_obj_to_dict(report.external_grounding_report),
                "implementation_risk_review": _research_obj_to_dict(report.implementation_risk_review),
                "lens_engine": _lens_engine_to_dict(report.lens_engine_state),
                "pantheon": _research_obj_to_dict(report.pantheon_state),
                "pantheon_runtime": _research_obj_to_dict(report.pantheon_runtime),
                "deliberation_graph": _research_obj_to_dict(report.deliberation_graph),
                "novelty_proof": _proof_to_dict(report.novelty_proof),
                "alternatives": [
                    {
                        "rank": alt.rank,
                        "invention_name": alt.invention_name,
                        "source_domain": alt.source_domain,
                        "domain_distance": round(alt.domain_distance, 4),
                        "structural_fidelity": round(alt.structural_fidelity, 4),
                        "novelty_score": round(alt.novelty_score, 4),
                        "summary": alt.summary,
                    }
                    for alt in report.alternatives
                ],
                "meta": {
                    "cost_usd": round(report.cost_usd, 4),
                    "cost_breakdown": _research_obj_to_dict(report.cost_breakdown),
                    "models_used": report.models_used,
                    "depth": report.depth,
                    "wall_time_seconds": round(report.wall_time_seconds, 2),
                },
            }
        }
        return json.dumps(data, indent=self._indent, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Plain text
    # ------------------------------------------------------------------

    def to_plain(self, report: InventionReport) -> str:
        """Render the invention report as pipe-friendly plain text."""
        lines: list[str] = [
            "=" * 60,
            "HEPHAESTUS INVENTION REPORT",
            "=" * 60,
            "",
            "PROBLEM:",
            f"  {_as_text(report.problem, 'Not provided.')}",
            "",
            "STRUCTURAL FORM:",
            f"  {_as_text(report.structural_form, 'Not available.')}",
            "",
        ]

        if report.baseline_dossier is not None:
            lines.append("STATE OF THE ART RECON:")
            lines.append(_indent_block(getattr(report.baseline_dossier, "summary", ""), fallback="No external reconnaissance summary available."))
            avoid = getattr(report.baseline_dossier, "keywords_to_avoid", [])
            if avoid:
                lines.append("  Conventional mechanisms to avoid:")
                for item in avoid[:8]:
                    lines.append(f"  - {item}")
            lines.append("")

        lines += [
            "-" * 60,
            f"INVENTION: {report.invention_name}",
            f"SOURCE DOMAIN: {report.source_domain}",
            f"DOMAIN DISTANCE: {_ascii_bar(report.domain_distance)}",
            f"STRUCTURAL FIDELITY: {_ascii_bar(report.structural_fidelity)}",
            f"NOVELTY SCORE: {_ascii_bar(report.novelty_score)}",
            "-" * 60,
            "",
            "CONFIDENCE:",
            f"  Domain Distance: {_domain_distance_interpretation(report.domain_distance)}",
            f"  Structural Fidelity: {_structural_fidelity_interpretation(report.structural_fidelity)}",
            "",
            "MECHANISM:",
            _indent_block(report.mechanism, fallback="Not available."),
            "",
            "TRANSLATION:",
            _indent_block(report.translation, fallback="Not available."),
            "",
            "ARCHITECTURE:",
            _indent_block(report.architecture, fallback="Not available."),
            "",
            "WHERE THE ANALOGY BREAKS:",
            f"  {_as_text(report.where_analogy_breaks, 'No major analogy limits were recorded.')}",
            "",
        ]

        # Prior art
        lines.append("PRIOR ART CHECK:")
        if report.prior_art_report is not None:
            status = getattr(report.prior_art_report, "novelty_status", "UNKNOWN")
            summary = _as_text(getattr(report.prior_art_report, "summary", ""), "Prior art summary not available.")
            lines.append(f"  Status: {status}")
            lines.append(_indent_block(summary, fallback="Prior art summary not available."))
        else:
            lines.append("  Not performed.")
        lines.append("")

        if report.external_grounding_report is not None:
            lines.append("EXTERNAL GROUNDING:")
            lines.append(_indent_block(getattr(report.external_grounding_report, "summary", ""), fallback="No external grounding summary available."))
            for heading, key in [
                ("Closest related work", "closest_related_work"),
                ("Adjacent fields", "adjacent_fields"),
                ("Practitioner risks", "practitioner_risks"),
                ("Notable projects", "notable_projects"),
            ]:
                values = getattr(report.external_grounding_report, key, [])
                if values:
                    lines.append(f"  {heading}:")
                    for item in values[:6]:
                        lines.append(f"  - {item}")
            lines.append("")

        if report.implementation_risk_review is not None:
            lines.append("IMPLEMENTATION RISK REVIEW:")
            lines.append(_indent_block(getattr(report.implementation_risk_review, "summary", ""), fallback="No grounded risk review available."))
            for heading, key in [
                ("Major risks", "major_risks"),
                ("Operational constraints", "operational_constraints"),
                ("Likely failure modes", "likely_failure_modes"),
                ("Mitigations", "mitigations"),
            ]:
                values = getattr(report.implementation_risk_review, key, [])
                if values:
                    lines.append(f"  {heading}:")
                    for item in values[:6]:
                        lines.append(f"  - {item}")
            lines.append("")

        if report.lens_engine_state is not None:
            lines.append("LENS ENGINE:")
            lines.extend(_lens_engine_plain_lines(report.lens_engine_state))
            lines.append("")

        if report.pantheon_state is not None:
            lines.append("PANTHEON MODE:")
            lines.extend(_pantheon_plain_lines(report.pantheon_state))
            if report.pantheon_runtime is not None:
                lines.extend(_pantheon_runtime_plain_lines(report.pantheon_runtime))
            lines.append("")

        if report.deliberation_graph is not None:
            lines.append("RUNTIME ORCHESTRATION:")
            lines.extend(_deliberation_graph_plain_lines(report.deliberation_graph))
            lines.append("")

        # Novelty proof
        lines.append("NOVELTY PROOF:")
        if report.novelty_proof is not None:
            score = getattr(report.novelty_proof, "novelty_score", report.novelty_score)
            confidence = getattr(report.novelty_proof, "confidence", "N/A")
            lines.append(f"  Novelty Score: {score:.4f}  Confidence: {confidence}")
        else:
            lines.append(f"  Novelty Score: {report.novelty_score:.4f}")
        lines.append("")

        # Alternatives
        if report.alternatives:
            lines.append("ALTERNATIVE INVENTIONS:")
            for alt in report.alternatives:
                lines.append(
                    f"  {alt.rank}. {_as_text(alt.invention_name, 'Unnamed alternative')} "
                    f"(from {_as_text(alt.source_domain, 'Unknown domain')}, novelty={alt.novelty_score:.2f})"
                )
                if alt.summary:
                    lines.append(f"     {_as_text(alt.summary)}")
            lines.append("")

        # Implementation roadmap
        lines += [
            "IMPLEMENTATION ROADMAP:",
            "  Phase 1: Validate core mechanism (prototype the key insight)",
            "  Phase 2: Build minimal working system (architecture skeleton)",
            "  Phase 3: Harden (address where analogy breaks)",
            "",
        ]
        auto_steps = _generate_roadmap_steps(report.architecture)
        if auto_steps:
            lines.append("  Suggested steps:")
            for step in auto_steps:
                lines.append(f"  - {step}")
            lines.append("")

        # Footer
        model_str = " + ".join(report.models_used) if report.models_used else "Unknown"
        time_str = f"{report.wall_time_seconds:.1f}s" if report.wall_time_seconds > 0 else "N/A"
        in_tokens = self._safe_int(getattr(report, "input_tokens", 0))
        out_tokens = self._safe_int(getattr(report, "output_tokens", 0))
        lines += [
            "-" * 60,
            f"Cost: ${report.cost_usd:.2f}  Models: {model_str}  "
            f"Tokens: {in_tokens:,} in / {out_tokens:,} out  "
            f"Depth: {report.depth}  Time: {time_str}",
        ]
        if report.cost_breakdown is not None:
            lines.append(f"Stage Costs: {_cost_breakdown_text(report.cost_breakdown, markdown=False)}")
        lines += [
            "=" * 60,
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_paragraphs(text: Any) -> list[str]:
    """Split text into paragraphs for formatted output."""
    normalized = _as_text(text, "Not available.")
    paragraphs = [p.strip() for p in normalized.strip().split("\n\n") if p.strip()]
    return paragraphs or [normalized.strip()]


def _indent_block(text: Any, indent: str = "  ", fallback: str = "") -> str:
    """Indent every line of a block of text."""
    rendered = _as_text(text, fallback)
    return "\n".join(f"{indent}{line}" for line in rendered.splitlines())


def _as_text(text: Any, fallback: str = "") -> str:
    """Render possibly missing structured data as readable text."""
    if isinstance(text, dict):
        return json.dumps(text, indent=2)
    if text is None:
        return fallback
    if isinstance(text, str):
        stripped = text.strip()
        return stripped or fallback
    rendered = str(text)
    return rendered.strip() or fallback


def _unicode_bar(value: float, width: int = 10) -> str:
    """Render a score as a unicode bar: ██████░░░░ 0.62"""
    filled = round(value * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty} {value:.2f}"


def _ascii_bar(value: float, width: int = 10) -> str:
    """Render a score as an ASCII bar: [======    ] 0.62"""
    filled = round(value * width)
    empty = width - filled
    return f"[{'=' * filled}{' ' * empty}] {value:.2f}"


def _domain_distance_interpretation(score: float) -> str:
    """Interpret a domain distance score."""
    if score > 0.8:
        return "Far transfer (high novelty potential)"
    elif score >= 0.5:
        return "Moderate transfer"
    else:
        return "Near transfer (lower novelty)"


def _structural_fidelity_interpretation(score: float) -> str:
    """Interpret a structural fidelity score."""
    if score > 0.8:
        return "Strong structural match"
    elif score >= 0.5:
        return "Moderate structural match"
    else:
        return "Loose analogy — verify carefully"


def _generate_roadmap_steps(architecture: str) -> list[str]:
    """Auto-generate specific implementation steps from architecture text."""
    steps: list[str] = []
    arch = _as_text(architecture)
    if not arch:
        return steps
    # Extract key nouns/actions from the architecture text
    # Look for function definitions, class names, key terms
    lines = arch.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Pick up def/class lines as prototype targets
        if stripped.startswith("def ") or stripped.startswith("class "):
            name = stripped.split("(")[0].replace("def ", "").replace("class ", "").strip()
            steps.append(f"Implement {name}")
        # Pick up assignment of key data structures
        elif "=" in stripped and not stripped.startswith("//"):
            var = stripped.split("=")[0].strip()
            if var and len(var) < 40 and re.match(r"^[a-zA-Z_]", var):
                steps.append(f"Define {var}")
    return steps[:5]  # cap at 5 specific steps


def _prior_art_to_dict(report: Any | None) -> dict[str, Any]:
    """Convert a PriorArtReport to a plain dict for JSON serialisation."""
    if report is None:
        return {"available": False, "patents": [], "papers": [], "status": "NOT_PERFORMED"}

    patents = [
        {
            "patent_id": getattr(p, "patent_id", ""),
            "title": getattr(p, "title", ""),
            "abstract": getattr(p, "abstract", "")[:300],
            "filing_date": getattr(p, "filing_date", ""),
            "assignee": getattr(p, "assignee", ""),
            "url": getattr(p, "url", ""),
        }
        for p in getattr(report, "patents", [])
    ]

    papers = [
        {
            "paper_id": getattr(p, "paper_id", ""),
            "title": getattr(p, "title", ""),
            "abstract": getattr(p, "abstract", "")[:300],
            "authors": getattr(p, "authors", []),
            "year": getattr(p, "year", None),
            "venue": getattr(p, "venue", ""),
            "citation_count": getattr(p, "citation_count", 0),
            "url": getattr(p, "url", ""),
        }
        for p in getattr(report, "papers", [])
    ]

    related_work = [
        {
            "title": getattr(item, "title", ""),
            "url": getattr(item, "url", ""),
            "relationship": getattr(item, "relationship", ""),
            "why_similar": getattr(item, "why_similar", ""),
        }
        for item in getattr(report, "related_work", [])
    ]

    return {
        "available": getattr(report, "search_available", False),
        "status": getattr(report, "novelty_status", "UNKNOWN"),
        "summary": getattr(report, "summary", ""),
        "overlap_verdict": getattr(report, "overlap_verdict", "UNKNOWN"),
        "overlap_confidence": getattr(report, "overlap_confidence", 0.0),
        "patents": patents,
        "papers": papers,
        "related_work": related_work,
        "citations": getattr(report, "citations", []),
        "errors": getattr(report, "search_errors", []),
        "searched_at": getattr(report, "searched_at", ""),
    }


def _research_obj_to_dict(obj: Any | None) -> dict[str, Any] | None:
    """Convert a simple research dataclass/object into a JSON-safe dict."""
    if obj is None:
        return None
    return _json_safe(obj)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, Mock):
        return {
            str(k): _json_safe(v)
            for k, v in value.__dict__.items()
            if not str(k).startswith("_")
        }
    if hasattr(value, "__dict__"):
        return {str(k): _json_safe(v) for k, v in value.__dict__.items()}
    return str(value)


def _proof_to_dict(proof: Any | None) -> dict[str, Any] | None:
    """Convert a NoveltyProof to a plain dict."""
    if proof is None:
        return None
    if hasattr(proof, "to_dict"):
        return proof.to_dict()  # type: ignore[return-value]
    return {"novelty_score": getattr(proof, "novelty_score", 0.0)}


def _lens_engine_to_dict(state: Any | None) -> dict[str, Any] | None:
    if state is None:
        return None
    if hasattr(state, "to_dict"):
        return state.to_dict()  # type: ignore[return-value]
    return _json_safe(state)


def _lens_engine_markdown_lines(state: Any) -> list[str]:
    lines: list[str] = [f"  {_state_summary_text(state)}"]
    active_bundle = getattr(state, "active_bundle", None)
    if active_bundle is not None:
        lines.append("")
        lines.append(
            f"  - Active bundle: `{active_bundle.bundle_id}` "
            f"({active_bundle.bundle_kind}, {active_bundle.proof_status})"
        )
        lines.append(
            f"  - Cohesion: `{active_bundle.cohesion_score:.2f}` | "
            f"Higher-order support: `{active_bundle.higher_order_score:.2f}`"
        )
        lines.append(
            f"  - Members: {', '.join(f'`{member}`' for member in active_bundle.member_ids)}"
        )
    for composite in getattr(state, "active_composites", [])[:3]:
        lines.append(
            f"  - Composite: `{composite.composite_id}` "
            f"(v{composite.version}) from {', '.join(f'`{member}`' for member in composite.component_lens_ids)}"
        )
    for guard in getattr(state, "guards", [])[:5]:
        lines.append(
            f"  - Guard `{guard.kind}`: **{guard.status.upper()}** — {guard.summary}"
        )
    for item in getattr(state, "pending_invalidations", [])[:5]:
        lines.append(
            f"  - Invalidation `{item.target_kind}` `{item.target_id}`: {item.summary}"
        )
    for item in getattr(state, "recompositions", [])[-3:]:
        lines.append(f"  - Recomposition `{item.status}`: {item.summary}")
    return lines


def _lens_engine_plain_lines(state: Any) -> list[str]:
    lines = [f"  {_state_summary_text(state)}"]
    active_bundle = getattr(state, "active_bundle", None)
    if active_bundle is not None:
        lines.append(
            f"  Active bundle: {active_bundle.bundle_id} "
            f"({active_bundle.bundle_kind}, {active_bundle.proof_status})"
        )
        lines.append(
            f"  Members: {', '.join(active_bundle.member_ids)}"
        )
        lines.append(
            f"  Cohesion: {active_bundle.cohesion_score:.2f}  "
            f"Higher-order support: {active_bundle.higher_order_score:.2f}"
        )
    for composite in getattr(state, "active_composites", [])[:3]:
        lines.append(
            f"  Composite: {composite.composite_id} "
            f"(v{composite.version}) from {', '.join(composite.component_lens_ids)}"
        )
    for guard in getattr(state, "guards", [])[:5]:
        lines.append(f"  Guard [{guard.kind}] {guard.status}: {guard.summary}")
    for item in getattr(state, "pending_invalidations", [])[:5]:
        lines.append(f"  Invalidation [{item.target_kind}] {item.target_id}: {item.summary}")
    for item in getattr(state, "recompositions", [])[-3:]:
        lines.append(f"  Recomposition {item.status}: {item.summary}")
    return lines


def _pantheon_markdown_lines(state: Any) -> list[str]:
    resolution = _lookup(state, "resolution", "")
    failure_reason = _lookup(state, "failure_reason", "")
    objection_ledger = list(_lookup(state, "objection_ledger", []) or [])
    caveats = list(_lookup(state, "caveats", []) or [])
    lines: list[str] = [
        f"  Mode: `{_as_text(_lookup(state, 'mode', ''), 'inactive')}`",
        f"  Resolution: `{_as_text(resolution, 'inactive')}`",
        f"  Resolution mode: `{_as_text(_lookup(state, 'resolution_mode', ''), 'TASK_SENSITIVE')}`",
        f"  Outcome tier: `{_as_text(_lookup(state, 'outcome_tier', ''), 'PENDING')}`",
        f"  Consensus achieved: `{bool(_lookup(state, 'consensus_achieved', False))}`",
        f"  Final verdict: `{_as_text(_lookup(state, 'final_verdict', ''), 'UNKNOWN')}`",
    ]
    initial_structure = getattr(state, "initial_structure", None)
    pipeline_structure = getattr(state, "pipeline_structure", None)
    if isinstance(initial_structure, dict) and isinstance(pipeline_structure, dict):
        lines.append(
            f"  - Athena revised structure: `{initial_structure.get('structure', '')}` → "
            f"`{pipeline_structure.get('structure', '')}`"
        )
    canon = _lookup(state, "canon", None)
    if canon is not None:
        lines.append(f"  - Athena canon: {_as_text(_lookup(canon, 'structural_form', ''), 'n/a')}")
    dossier = _lookup(state, "dossier", None)
    if dossier is not None:
        lines.append(f"  - Hermes dossier: {_as_text(_lookup(dossier, 'repo_reality_summary', ''), 'n/a')}")
    winning_candidate_id = _lookup(state, "winning_candidate_id", None)
    if winning_candidate_id:
        lines.append(f"  - Winning candidate: `{winning_candidate_id}`")
    unresolved = list(_lookup(state, "unresolved_vetoes", []) or [])
    if unresolved:
        lines.append(f"  - Unresolved vetoes: {', '.join(f'`{item}`' for item in unresolved)}")
    if caveats:
        lines.append("  - Caveats:")
        for item in caveats[:3]:
            lines.append(f"    - {_as_text(item)}")
    if failure_reason:
        lines.append(f"  - Failure reason: {_as_text(failure_reason)}")
    for screening in getattr(state, "screenings", [])[:4]:
        lines.append(
            f"  - Pre-council: `{getattr(screening, 'candidate_id', '')}` "
            f"survived=`{bool(getattr(screening, 'survived', False))}` "
            f"priority=`{float(getattr(screening, 'priority_score', 0.0) or 0.0):.2f}`"
        )
    for round_ in list(_lookup(state, "rounds", []) or [])[-3:]:
        lines.append(
            f"  - Round {_lookup(round_, 'round_index', '?')}: "
            f"candidate `{_lookup(round_, 'candidate_id', '')}` "
            f"consensus=`{bool(_lookup(round_, 'consensus', False))}` "
            f"tier=`{_as_text(_lookup(round_, 'outcome_tier', ''), 'PENDING')}`"
        )
    if objection_ledger:
        open_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "OPEN")
        resolved_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "RESOLVED")
        waived_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "WAIVED")
        lines.append(
            f"  - Objection ledger: open=`{open_count}` resolved=`{resolved_count}` waived=`{waived_count}`"
        )
        for objection in objection_ledger[:4]:
            lines.append(
                "  - "
                f"`{_lookup(objection, 'objection_id', '')}` "
                f"[{_as_text(_lookup(objection, 'severity', ''), 'REPAIRABLE')}/"
                f"{_as_text(_lookup(objection, 'status', ''), 'OPEN')}] "
                f"{_as_text(_lookup(objection, 'statement', ''), 'n/a')}"
            )
    return lines


def _pantheon_plain_lines(state: Any) -> list[str]:
    resolution = _lookup(state, "resolution", "")
    failure_reason = _lookup(state, "failure_reason", "")
    objection_ledger = list(_lookup(state, "objection_ledger", []) or [])
    caveats = list(_lookup(state, "caveats", []) or [])
    lines: list[str] = [
        f"  Mode: {_as_text(_lookup(state, 'mode', ''), 'inactive')}",
        f"  Resolution: {_as_text(resolution, 'inactive')}",
        f"  Resolution mode: {_as_text(_lookup(state, 'resolution_mode', ''), 'TASK_SENSITIVE')}",
        f"  Outcome tier: {_as_text(_lookup(state, 'outcome_tier', ''), 'PENDING')}",
        f"  Consensus achieved: {bool(_lookup(state, 'consensus_achieved', False))}",
        f"  Final verdict: {_as_text(_lookup(state, 'final_verdict', ''), 'UNKNOWN')}",
    ]
    initial_structure = getattr(state, "initial_structure", None)
    pipeline_structure = getattr(state, "pipeline_structure", None)
    if isinstance(initial_structure, dict) and isinstance(pipeline_structure, dict):
        lines.append(
            f"  Athena revised structure: {initial_structure.get('structure', '')} -> "
            f"{pipeline_structure.get('structure', '')}"
        )
    canon = _lookup(state, "canon", None)
    if canon is not None:
        lines.append(f"  Athena canon: {_as_text(_lookup(canon, 'structural_form', ''), 'n/a')}")
    dossier = _lookup(state, "dossier", None)
    if dossier is not None:
        lines.append(f"  Hermes dossier: {_as_text(_lookup(dossier, 'repo_reality_summary', ''), 'n/a')}")
    winning_candidate_id = _lookup(state, "winning_candidate_id", None)
    if winning_candidate_id:
        lines.append(f"  Winning candidate: {winning_candidate_id}")
    unresolved = list(_lookup(state, "unresolved_vetoes", []) or [])
    if unresolved:
        lines.append(f"  Unresolved vetoes: {', '.join(unresolved)}")
    if caveats:
        lines.append(f"  Caveats: {'; '.join(str(item) for item in caveats[:3])}")
    if failure_reason:
        lines.append(f"  Failure reason: {_as_text(failure_reason)}")
    for screening in getattr(state, "screenings", [])[:4]:
        lines.append(
            f"  Pre-council: {getattr(screening, 'candidate_id', '')} "
            f"survived={bool(getattr(screening, 'survived', False))} "
            f"priority={float(getattr(screening, 'priority_score', 0.0) or 0.0):.2f}"
        )
    for round_ in list(_lookup(state, "rounds", []) or [])[-3:]:
        lines.append(
            f"  Round {_lookup(round_, 'round_index', '?')}: "
            f"candidate {_lookup(round_, 'candidate_id', '')} "
            f"consensus={bool(_lookup(round_, 'consensus', False))} "
            f"tier={_as_text(_lookup(round_, 'outcome_tier', ''), 'PENDING')}"
        )
    if objection_ledger:
        open_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "OPEN")
        resolved_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "RESOLVED")
        waived_count = sum(1 for objection in objection_ledger if _lookup(objection, "status", "") == "WAIVED")
        lines.append(f"  Objection ledger: open={open_count} resolved={resolved_count} waived={waived_count}")
        for objection in objection_ledger[:4]:
            lines.append(
                f"  {_lookup(objection, 'objection_id', '')} "
                f"[{_as_text(_lookup(objection, 'severity', ''), 'REPAIRABLE')}/"
                f"{_as_text(_lookup(objection, 'status', ''), 'OPEN')}] "
                f"{_as_text(_lookup(objection, 'statement', ''), 'n/a')}"
            )
    return lines


def _state_summary_text(state: Any) -> str:
    summary_value = getattr(state, "summary", "")
    summary = summary_value() if callable(summary_value) else summary_value
    return _as_text(summary, "Lens engine state attached.")


def _pantheon_runtime_markdown_lines(runtime: Any) -> list[str]:
    return [
        (
            "  - Runtime: "
            f"`{_lookup(runtime, 'total_duration_seconds', 0.0):.2f}s` "
            f"| cost=`${_lookup(runtime, 'total_cost_usd', 0.0):.4f}` "
            f"| tokens=`{int(_lookup(runtime, 'total_input_tokens', 0) or 0):,} in / "
            f"{int(_lookup(runtime, 'total_output_tokens', 0) or 0):,} out`"
        ),
        f"  - Agent calls: {_agent_call_text(_lookup(runtime, 'agent_call_counts', {}), markdown=True)}",
    ]


def _pantheon_runtime_plain_lines(runtime: Any) -> list[str]:
    return [
        (
            "  Runtime: "
            f"{_lookup(runtime, 'total_duration_seconds', 0.0):.2f}s "
            f"| cost=${_lookup(runtime, 'total_cost_usd', 0.0):.4f} "
            f"| tokens={int(_lookup(runtime, 'total_input_tokens', 0) or 0):,} in / "
            f"{int(_lookup(runtime, 'total_output_tokens', 0) or 0):,} out"
        ),
        f"  Agent calls: {_agent_call_text(_lookup(runtime, 'agent_call_counts', {}), markdown=False)}",
    ]


def _agent_call_text(values: Any, *, markdown: bool) -> str:
    if not isinstance(values, dict) or not values:
        return "`none`" if markdown else "none"
    parts = []
    for agent, count in values.items():
        label = f"`{agent}`={count}" if markdown else f"{agent}={count}"
        parts.append(label)
    return ", ".join(parts)


def _cost_breakdown_text(cost: Any, *, markdown: bool) -> str:
    if cost is None:
        return "`n/a`" if markdown else "n/a"
    labels = [
        ("decomposition_cost", "decompose"),
        ("search_cost", "search"),
        ("scoring_cost", "score"),
        ("translation_cost", "translate"),
        ("pantheon_cost", "pantheon"),
        ("verification_cost", "verify"),
    ]
    rendered: list[str] = []
    for attr_name, label in labels:
        amount = float(_lookup(cost, attr_name, 0.0) or 0.0)
        if amount <= 0:
            continue
        rendered.append(f"`{label}`=${amount:.4f}" if markdown else f"{label}=${amount:.4f}")
    return ", ".join(rendered) if rendered else ("`none`" if markdown else "none")


def _lookup(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _deliberation_graph_markdown_lines(graph: Any) -> list[str]:
    candidate_count = len(_lookup(graph, "candidates", []) or [])
    evidence_count = len(_lookup(graph, "evidence", []) or [])
    objection_count = len(_lookup(graph, "objections", []) or [])
    open_objections = sum(
        1
        for item in list(_lookup(graph, "objections", []) or [])
        if str(_lookup(item, "status", "")).lower() == "open"
    )
    routing = list(_lookup(graph, "routing_history", []) or [])
    events = list(_lookup(graph, "stage_events", []) or [])
    accounting = _lookup(graph, "accounting", None)
    budget_policy = _lookup(graph, "budget_policy", None)
    lines = [
        f"  Workflow: `{_as_text(_lookup(graph, 'workflow_kind', ''), 'genesis')}`",
        f"  Candidates: `{candidate_count}` | evidence: `{evidence_count}` | objections: `{objection_count}` (`{open_objections}` open)",
    ]
    if budget_policy is not None:
        lines.append(
            f"  - Budget policy: `{_lookup(budget_policy, 'profile', 'balanced')}` "
            f"| translation frontier=`{_lookup(budget_policy, 'translation_frontier', 0)}` "
            f"| verification depth=`{_lookup(budget_policy, 'verification_depth', 'standard')}`"
        )
    if accounting is not None:
        lines.append(
            "  - Runtime totals: "
            f"`{_lookup(accounting, 'total_duration_seconds', 0.0):.2f}s` "
            f"| cost=`${_lookup(accounting, 'total_cost_usd', 0.0):.4f}` "
            f"| tokens=`{int(_lookup(accounting, 'total_input_tokens', 0) or 0):,} in / "
            f"{int(_lookup(accounting, 'total_output_tokens', 0) or 0):,} out`"
        )
    for decision in routing[:4]:
        lines.append(
            f"  - Route `{_lookup(decision, 'stage', '')}` -> `{_lookup(decision, 'selected_route', '')}`: "
            f"{_as_text(_lookup(decision, 'reason', ''), 'n/a')}"
        )
    for candidate in list(_lookup(graph, "candidates", []) or [])[:4]:
        lines.append(
            f"  - Candidate `{_lookup(candidate, 'candidate_id', '')}` "
            f"status=`{_lookup(candidate, 'status', 'alive')}` "
            f"evidence=`{float(_lookup(candidate, 'evidence_coverage', 0.0) or 0.0):.2f}` "
            f"unresolved=`{int(_lookup(candidate, 'unresolved_objections', 0) or 0)}` "
            f"spent=`${float(_lookup(candidate, 'compute_spent_usd', 0.0) or 0.0):.4f}`"
        )
    if events:
        last_event = events[-1]
        lines.append(
            f"  - Last stage: `{_lookup(last_event, 'stage', '')}` / "
            f"`{_lookup(last_event, 'status', '')}` — {_as_text(_lookup(last_event, 'message', ''), 'n/a')}"
        )
    return lines


def _deliberation_graph_plain_lines(graph: Any) -> list[str]:
    candidate_count = len(_lookup(graph, "candidates", []) or [])
    evidence_count = len(_lookup(graph, "evidence", []) or [])
    objection_count = len(_lookup(graph, "objections", []) or [])
    open_objections = sum(
        1
        for item in list(_lookup(graph, "objections", []) or [])
        if str(_lookup(item, "status", "")).lower() == "open"
    )
    routing = list(_lookup(graph, "routing_history", []) or [])
    events = list(_lookup(graph, "stage_events", []) or [])
    accounting = _lookup(graph, "accounting", None)
    budget_policy = _lookup(graph, "budget_policy", None)
    lines = [
        f"  Workflow: {_as_text(_lookup(graph, 'workflow_kind', ''), 'genesis')}",
        f"  Candidates: {candidate_count}  Evidence: {evidence_count}  Objections: {objection_count} ({open_objections} open)",
    ]
    if budget_policy is not None:
        lines.append(
            f"  Budget policy: {_lookup(budget_policy, 'profile', 'balanced')}  "
            f"translation frontier={_lookup(budget_policy, 'translation_frontier', 0)}  "
            f"verification depth={_lookup(budget_policy, 'verification_depth', 'standard')}"
        )
    if accounting is not None:
        lines.append(
            "  Runtime totals: "
            f"{_lookup(accounting, 'total_duration_seconds', 0.0):.2f}s "
            f"| cost=${_lookup(accounting, 'total_cost_usd', 0.0):.4f} "
            f"| tokens={int(_lookup(accounting, 'total_input_tokens', 0) or 0):,} in / "
            f"{int(_lookup(accounting, 'total_output_tokens', 0) or 0):,} out"
        )
    for decision in routing[:4]:
        lines.append(
            f"  Route {_lookup(decision, 'stage', '')} -> {_lookup(decision, 'selected_route', '')}: "
            f"{_as_text(_lookup(decision, 'reason', ''), 'n/a')}"
        )
    for candidate in list(_lookup(graph, "candidates", []) or [])[:4]:
        lines.append(
            f"  Candidate {_lookup(candidate, 'candidate_id', '')} "
            f"status={_lookup(candidate, 'status', 'alive')} "
            f"evidence={float(_lookup(candidate, 'evidence_coverage', 0.0) or 0.0):.2f} "
            f"unresolved={int(_lookup(candidate, 'unresolved_objections', 0) or 0)} "
            f"spent=${float(_lookup(candidate, 'compute_spent_usd', 0.0) or 0.0):.4f}"
        )
    if events:
        last_event = events[-1]
        lines.append(
            f"  Last stage: {_lookup(last_event, 'stage', '')} / "
            f"{_lookup(last_event, 'status', '')} - {_as_text(_lookup(last_event, 'message', ''), 'n/a')}"
        )
    return lines
