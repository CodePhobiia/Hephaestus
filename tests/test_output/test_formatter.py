"""
Tests for the Output Formatter.
"""

from __future__ import annotations

import json

import pytest

from hephaestus.output.formatter import (
    AlternativeInvention,
    InventionReport,
    OutputFormat,
    OutputFormatter,
)
from hephaestus.output.prior_art import PriorArtReport, PatentResult, PaperResult
from hephaestus.output.proof import NoveltyProof, NoveltyProofGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(**overrides: object) -> InventionReport:
    """Create a minimal InventionReport for testing."""
    defaults = dict(
        problem="I need a load balancer for unpredictable traffic spikes",
        structural_form="Adaptive flow control under dynamic load with positive feedback",
        invention_name="Pheromone-Gradient Load Balancer",
        source_domain="Ant Colony Optimization (Biology)",
        domain_distance=0.94,
        structural_fidelity=0.87,
        novelty_score=0.91,
        mechanism=(
            "Ants deposit pheromone on paths to food sources. "
            "Shorter, faster paths accumulate more pheromone, attracting more ants. "
            "This creates a positive feedback loop that converges on optimal paths."
        ),
        translation=(
            "Requests are routed to servers. "
            "Faster responses → higher routing weight. "
            "Positive feedback concentrates load on fast servers, self-balancing the system."
        ),
        architecture=(
            "# Pheromone Load Balancer\n"
            "server_weights = {s: 1.0 for s in servers}\n"
            "def route(req):\n"
            "    s = weighted_choice(server_weights)\n"
            "    t = send(req, s)\n"
            "    server_weights[s] *= (1 + 1/t)  # evaporate + deposit\n"
            "    normalize(server_weights)\n"
        ),
        where_analogy_breaks=(
            "Real ant colonies adapt over minutes; "
            "load balancers must adapt in milliseconds. "
            "Pheromone evaporation rates must be tuned carefully."
        ),
        cost_usd=1.18,
        models_used=["claude-opus-4-6", "gpt-5.4"],
        depth=3,
        wall_time_seconds=47.3,
    )
    defaults.update(overrides)
    return InventionReport(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# OutputFormat enum
# ---------------------------------------------------------------------------


class TestOutputFormat:
    def test_enum_values_exist(self) -> None:
        assert OutputFormat.MARKDOWN
        assert OutputFormat.JSON
        assert OutputFormat.PLAIN


# ---------------------------------------------------------------------------
# OutputFormatter.format() dispatch
# ---------------------------------------------------------------------------


class TestFormatDispatch:
    def test_format_markdown_default(self) -> None:
        formatter = OutputFormatter()
        report = _make_report()
        result = formatter.format(report)  # default is MARKDOWN
        assert "⚒️" in result
        assert "HEPHAESTUS" in result

    def test_format_json(self) -> None:
        formatter = OutputFormatter()
        report = _make_report()
        result = formatter.format(report, OutputFormat.JSON)
        data = json.loads(result)
        assert "hephaestus_invention_report" in data

    def test_format_plain(self) -> None:
        formatter = OutputFormatter()
        report = _make_report()
        result = formatter.format(report, OutputFormat.PLAIN)
        assert "HEPHAESTUS INVENTION REPORT" in result

    def test_unknown_format_raises(self) -> None:
        formatter = OutputFormatter()
        report = _make_report()
        with pytest.raises(Exception):
            formatter.format(report, "invalid_format")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------


class TestMarkdownOutput:
    def test_contains_header(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "⚒️  HEPHAESTUS — Invention Report" in md

    def test_contains_problem(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "load balancer for unpredictable traffic" in md

    def test_contains_structural_form(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "Adaptive flow control" in md

    def test_contains_invention_name(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "Pheromone-Gradient Load Balancer" in md

    def test_contains_source_domain(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "Ant Colony Optimization" in md

    def test_contains_domain_distance(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "0.94" in md

    def test_contains_fidelity(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "0.87" in md

    def test_contains_novelty_score(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "0.91" in md

    def test_contains_mechanism(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "pheromone" in md.lower()

    def test_contains_where_analogy_breaks(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "WHERE THE ANALOGY BREAKS" in md

    def test_contains_prior_art_section(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "PRIOR ART" in md

    def test_contains_novelty_proof_section(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "NOVELTY PROOF" in md

    def test_contains_cost(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "1.18" in md

    def test_contains_model_names(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "claude-opus-4-6" in md
        assert "gpt-5.4" in md

    def test_contains_separator_lines(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "═══════════════════════════" in md

    def test_no_models_listed(self) -> None:
        report = _make_report(models_used=[])
        md = OutputFormatter().to_markdown(report)
        assert "Unknown" in md

    def test_with_alternatives(self) -> None:
        alts = [
            AlternativeInvention(
                rank=2,
                invention_name="Slime Mold Router",
                source_domain="Physarum polycephalum (Biology)",
                domain_distance=0.89,
                structural_fidelity=0.81,
                novelty_score=0.85,
                summary="Uses slime mold pathfinding to optimize routing.",
            )
        ]
        report = _make_report(alternatives=alts)
        md = OutputFormatter().to_markdown(report)
        assert "ALTERNATIVE INVENTIONS" in md
        assert "Slime Mold Router" in md

    def test_with_prior_art_report(self) -> None:
        report_obj = PriorArtReport(
            query="load balancer pheromone",
            invention_name="Pheromone Load Balancer",
            patents=[],
            papers=[],
        )
        report = _make_report(prior_art_report=report_obj)
        md = OutputFormatter().to_markdown(report)
        assert "NO_PRIOR_ART_FOUND" in md

    def test_with_prior_art_found(self) -> None:
        patent = PatentResult(
            patent_id="US123456",
            title="Ant-inspired load balancing",
            abstract="Some abstract",
        )
        report_obj = PriorArtReport(
            query="load balancer pheromone",
            invention_name="Pheromone Load Balancer",
            patents=[patent],
        )
        report = _make_report(prior_art_report=report_obj)
        md = OutputFormatter().to_markdown(report)
        assert "POSSIBLE_PRIOR_ART" in md

    def test_with_novelty_proof(self) -> None:
        generator = NoveltyProofGenerator()
        proof = generator.generate(
            problem="my problem",
            invention_name="Test Invention",
            source_domain="Biology",
            target_domain="Distributed Systems",
            domain_distance=0.94,
            structural_fidelity=0.87,
            mechanism="some mechanism",
        )
        report = _make_report(novelty_proof=proof)
        md = OutputFormatter().to_markdown(report)
        assert "NOVELTY PROOF" in md
        # Score should appear
        assert str(proof.confidence) in md


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_valid_json(self) -> None:
        result = OutputFormatter().to_json(_make_report())
        data = json.loads(result)  # should not raise
        assert isinstance(data, dict)

    def test_top_level_key(self) -> None:
        data = json.loads(OutputFormatter().to_json(_make_report()))
        assert "hephaestus_invention_report" in data

    def test_problem_in_json(self) -> None:
        data = json.loads(OutputFormatter().to_json(_make_report()))
        inv = data["hephaestus_invention_report"]
        assert "load balancer" in inv["problem"]

    def test_invention_section(self) -> None:
        data = json.loads(OutputFormatter().to_json(_make_report()))
        inv = data["hephaestus_invention_report"]["invention"]
        assert inv["name"] == "Pheromone-Gradient Load Balancer"
        assert inv["domain_distance"] == pytest.approx(0.94, abs=1e-3)
        assert inv["structural_fidelity"] == pytest.approx(0.87, abs=1e-3)
        assert inv["novelty_score"] == pytest.approx(0.91, abs=1e-3)

    def test_meta_section(self) -> None:
        data = json.loads(OutputFormatter().to_json(_make_report()))
        meta = data["hephaestus_invention_report"]["meta"]
        assert meta["cost_usd"] == pytest.approx(1.18, abs=1e-2)
        assert meta["depth"] == 3
        assert "claude-opus-4-6" in meta["models_used"]

    def test_alternatives_in_json(self) -> None:
        alts = [
            AlternativeInvention(
                rank=2,
                invention_name="Alt Invention",
                source_domain="Physics",
                domain_distance=0.85,
                structural_fidelity=0.78,
                novelty_score=0.82,
            )
        ]
        data = json.loads(OutputFormatter().to_json(_make_report(alternatives=alts)))
        alts_json = data["hephaestus_invention_report"]["alternatives"]
        assert len(alts_json) == 1
        assert alts_json[0]["invention_name"] == "Alt Invention"

    def test_prior_art_in_json(self) -> None:
        pat = PatentResult(patent_id="US1", title="test patent")
        pa = PriorArtReport(query="q", invention_name="I", patents=[pat])
        data = json.loads(OutputFormatter().to_json(_make_report(prior_art_report=pa)))
        prior = data["hephaestus_invention_report"]["prior_art"]
        assert prior["available"] is True
        assert len(prior["patents"]) == 1

    def test_indent_parameter(self) -> None:
        formatter = OutputFormatter(indent_json=4)
        result = formatter.to_json(_make_report())
        # 4-space indented JSON should have 4-space indentation
        assert "    " in result

    def test_proof_in_json(self) -> None:
        gen = NoveltyProofGenerator()
        proof = gen.generate(
            problem="p",
            invention_name="I",
            source_domain="Biology",
            target_domain="CS",
            domain_distance=0.9,
            structural_fidelity=0.8,
            mechanism="m",
        )
        data = json.loads(OutputFormatter().to_json(_make_report(novelty_proof=proof)))
        proof_json = data["hephaestus_invention_report"]["novelty_proof"]
        assert proof_json is not None
        assert "novelty_score" in proof_json


# ---------------------------------------------------------------------------
# Plain text output
# ---------------------------------------------------------------------------


class TestPlainOutput:
    def test_contains_header(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "HEPHAESTUS INVENTION REPORT" in plain

    def test_contains_problem(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "load balancer" in plain

    def test_contains_invention_name(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "Pheromone-Gradient Load Balancer" in plain

    def test_no_markdown_syntax(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        # Should not contain bold markdown (** pairs)
        assert "**" not in plain

    def test_contains_cost_line(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "$1.18" in plain

    def test_with_alternatives(self) -> None:
        alts = [
            AlternativeInvention(
                rank=2,
                invention_name="Alt",
                source_domain="Physics",
                novelty_score=0.82,
            )
        ]
        plain = OutputFormatter().to_plain(_make_report(alternatives=alts))
        assert "ALTERNATIVE INVENTIONS" in plain
        assert "Alt" in plain
