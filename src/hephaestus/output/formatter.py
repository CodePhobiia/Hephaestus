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
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

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
    novelty_proof: Any | None = None       # NoveltyProof
    alternatives: list[AlternativeInvention] = field(default_factory=list)
    cost_usd: float = 0.0
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
            f"  {report.problem}",
            "",
            "**STRUCTURAL FORM:**",
            f"  {report.structural_form}",
            "",
        ]

        # ── Primary invention ────────────────────────────────────────────────
        lines += [
            "───────────────────────────────────────────────────",
            f"**INVENTION:** {report.invention_name}",
            f"**SOURCE DOMAIN:** {report.source_domain}",
            f"**DOMAIN DISTANCE:** {report.domain_distance:.2f}",
            f"**STRUCTURAL FIDELITY:** {report.structural_fidelity:.2f}",
            f"**NOVELTY SCORE:** {report.novelty_score:.2f}",
            "───────────────────────────────────────────────────",
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
        arch = report.architecture
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
            f"  {report.where_analogy_breaks}",
            "",
        ]

        # ── Prior art check ──────────────────────────────────────────────────
        lines += [
            "**PRIOR ART CHECK:**",
            "",
        ]
        if report.prior_art_report is not None:
            summary = getattr(report.prior_art_report, "summary", "")
            status = getattr(report.prior_art_report, "novelty_status", "UNKNOWN")
            lines.append(f"  {summary}")
            lines.append("")
            lines.append(f"  **Status:** `{status}`")
        else:
            lines.append("  Prior art search not performed.")
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
            formal = getattr(proof, "formal_statement", "")
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
                    f"**{alt.rank}. {alt.invention_name}**",
                    f"   Source: {alt.source_domain} | "
                    f"Distance: {alt.domain_distance:.2f} | "
                    f"Novelty: {alt.novelty_score:.2f}",
                ]
                if alt.summary:
                    lines.append(f"   {alt.summary}")
                lines.append("")
            lines.append("───────────────────────────────────────────────────")
            lines.append("")

        # ── Footer ───────────────────────────────────────────────────────────
        model_str = " + ".join(report.models_used) if report.models_used else "Unknown"
        time_str = f"{report.wall_time_seconds:.1f}s" if report.wall_time_seconds > 0 else "N/A"
        lines += [
            f"**Cost:** ${report.cost_usd:.2f} | "
            f"**Models:** {model_str} | "
            f"**Depth:** {report.depth} | "
            f"**Time:** {time_str}",
            "",
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
            f"  {report.problem}",
            "",
            "STRUCTURAL FORM:",
            f"  {report.structural_form}",
            "",
            "-" * 60,
            f"INVENTION: {report.invention_name}",
            f"SOURCE DOMAIN: {report.source_domain}",
            f"DOMAIN DISTANCE: {report.domain_distance:.2f}",
            f"STRUCTURAL FIDELITY: {report.structural_fidelity:.2f}",
            f"NOVELTY SCORE: {report.novelty_score:.2f}",
            "-" * 60,
            "",
            "MECHANISM:",
            _indent_block(report.mechanism),
            "",
            "TRANSLATION:",
            _indent_block(report.translation),
            "",
            "ARCHITECTURE:",
            _indent_block(report.architecture),
            "",
            "WHERE THE ANALOGY BREAKS:",
            f"  {report.where_analogy_breaks}",
            "",
        ]

        # Prior art
        lines.append("PRIOR ART CHECK:")
        if report.prior_art_report is not None:
            status = getattr(report.prior_art_report, "novelty_status", "UNKNOWN")
            summary = getattr(report.prior_art_report, "summary", "")
            lines.append(f"  Status: {status}")
            lines.append(_indent_block(summary))
        else:
            lines.append("  Not performed.")
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
                    f"  {alt.rank}. {alt.invention_name} "
                    f"(from {alt.source_domain}, novelty={alt.novelty_score:.2f})"
                )
                if alt.summary:
                    lines.append(f"     {alt.summary}")
            lines.append("")

        # Footer
        model_str = " + ".join(report.models_used) if report.models_used else "Unknown"
        time_str = f"{report.wall_time_seconds:.1f}s" if report.wall_time_seconds > 0 else "N/A"
        lines += [
            "-" * 60,
            f"Cost: ${report.cost_usd:.2f}  Models: {model_str}  "
            f"Depth: {report.depth}  Time: {time_str}",
            "=" * 60,
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs for formatted output."""
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return paragraphs or [text.strip()]


def _indent_block(text: str, indent: str = "  ") -> str:
    """Indent every line of a block of text."""
    return "\n".join(f"{indent}{line}" for line in text.splitlines())


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

    return {
        "available": getattr(report, "search_available", False),
        "status": getattr(report, "novelty_status", "UNKNOWN"),
        "summary": getattr(report, "summary", ""),
        "patents": patents,
        "papers": papers,
        "errors": getattr(report, "search_errors", []),
        "searched_at": getattr(report, "searched_at", ""),
    }


def _proof_to_dict(proof: Any | None) -> dict[str, Any] | None:
    """Convert a NoveltyProof to a plain dict."""
    if proof is None:
        return None
    if hasattr(proof, "to_dict"):
        return proof.to_dict()  # type: ignore[return-value]
    return {"novelty_score": getattr(proof, "novelty_score", 0.0)}
