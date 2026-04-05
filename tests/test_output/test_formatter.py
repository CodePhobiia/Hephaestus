"""
Tests for the Output Formatter.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from hephaestus.lenses.state import (
    CompositeLens,
    GuardDecision,
    InvalidationEvent,
    LensBundleMember,
    LensBundleProof,
    LensEngineState,
    LensLineage,
    RecompositionEvent,
    ResearchReferenceArtifact,
    ResearchReferenceState,
)
from hephaestus.output.formatter import (
    AlternativeInvention,
    InventionReport,
    OutputFormat,
    OutputFormatter,
    _ascii_bar,
    _domain_distance_interpretation,
    _generate_roadmap_steps,
    _structural_fidelity_interpretation,
    _unicode_bar,
)
from hephaestus.output.prior_art import PatentResult, PriorArtReport
from hephaestus.output.proof import NoveltyProofGenerator
from hephaestus.session.deliberation import DeliberationGraph

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


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=5,
        active_bundle_id="bundle:adaptive:fmt",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
                matched_patterns=["allocation", "memory"],
            ),
            LensBundleMember(
                lens_id="economics_markets",
                lens_name="Market Making",
                domain_name="economics::Market Making",
                matched_patterns=["feedback"],
            ),
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:fmt",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune", "economics_markets"],
                status="active",
                proof_status="proven",
                cohesion_score=0.73,
                higher_order_score=0.61,
                proof_fingerprint="fmt-proof",
                reference_generation=5,
                summary="Adaptive bundle selected.",
            )
        ],
        lineages=[
            LensLineage(
                lineage_id="lineage:biology_immune:g1",
                entity_id="biology_immune",
                fingerprint="lineage-immune",
                reference_generation=5,
            )
        ],
        guards=[
            GuardDecision(
                guard_id="guard:fmt",
                kind="bundle_cohesion_floor",
                status="passed",
                target_id="bundle:adaptive:fmt",
                summary="Cohesion floor passed.",
            )
        ],
        invalidations=[
            InvalidationEvent(
                invalidation_id="inval:fmt",
                target_kind="composite",
                target_id="composite:fmt",
                cause="research_reference_refresh",
                status="pending",
                from_reference_generation=4,
                to_reference_generation=5,
                summary="Composite needs recomposition after research refresh.",
            )
        ],
        recompositions=[
            RecompositionEvent(
                event_id="recomp:fmt",
                trigger="research_reference_refresh",
                status="completed",
                from_reference_generation=4,
                to_reference_generation=5,
                summary="Recomposed at generation 5.",
            )
        ],
        composites=[
            CompositeLens(
                composite_id="composite:fmt",
                component_lineage_ids=["lineage:biology_immune:g1"],
                component_lens_ids=["biology_immune", "economics_markets"],
                derived_from_bundle_id="bundle:adaptive:fmt",
                version=2,
                reference_generation=5,
                fingerprint="composite-fmt",
            )
        ],
        research=ResearchReferenceState(
            reference_generation=5,
            reference_signature="research-fmt",
            artifacts=[
                ResearchReferenceArtifact(
                    artifact_name="baseline_dossier",
                    signature="artifact-fmt",
                    citation_count=1,
                    citations=["https://example.com/fmt"],
                )
            ],
        ),
    )


def _pantheon_state() -> SimpleNamespace:
    runtime = {
        "total_cost_usd": 0.1234,
        "total_input_tokens": 210,
        "total_output_tokens": 70,
        "total_duration_seconds": 3.5,
        "agent_call_counts": {"athena": 2, "hermes": 2, "apollo": 1, "hephaestus": 1},
    }
    return SimpleNamespace(
        mode="pantheon",
        resolution="qualified_consensus",
        resolution_mode="TASK_SENSITIVE",
        outcome_tier="QUALIFIED_CONSENSUS",
        consensus_achieved=True,
        final_verdict="NOVEL",
        winning_candidate_id="candidate-1:Pheromone",
        unresolved_vetoes=[],
        caveats=["Track rollout oscillation in the first cohort."],
        failure_reason=None,
        canon=SimpleNamespace(structural_form="feedback loop"),
        dossier=SimpleNamespace(repo_reality_summary="fits production constraints"),
        rounds=[
            SimpleNamespace(round_index=1, candidate_id="candidate-1:Pheromone", consensus=True)
        ],
        objection_ledger=[
            SimpleNamespace(
                objection_id="obj-athena-1",
                severity="ADVISORY",
                status="WAIVED",
                statement="Track rollout oscillation in the first cohort.",
            )
        ],
        accounting=runtime,
    )


def _deliberation_graph() -> DeliberationGraph:
    graph = DeliberationGraph(workflow_kind="genesis", goal="test problem")
    graph.record_stage("search", "Found candidates.")
    graph.ensure_candidate(
        "candidate-1:Pheromone",
        source_domain="Biology",
        status="finalist",
        route="translate",
    )
    graph.record_route_decision(
        "score",
        "translate:2",
        "Top scores are clustered; keep a broader translation frontier.",
    )
    graph.record_accounting(
        stage="translate",
        route="frontier:2",
        cost_usd=0.45,
        input_tokens=120,
        output_tokens=60,
        duration_seconds=2.4,
        calls=1,
    )
    graph.mark_final("candidate-1:Pheromone", reason="verification_complete")
    return graph


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

    def test_includes_research_sections(self) -> None:
        report = _make_report(
            baseline_dossier=SimpleNamespace(
                summary="Queues and token buckets dominate today.",
                keywords_to_avoid=["retry with backoff"],
            ),
            external_grounding_report=SimpleNamespace(
                summary="Closest public systems use adaptive routing.",
                closest_related_work=["System A"],
                adjacent_fields=["traffic engineering"],
                practitioner_risks=["operational tuning"],
                notable_projects=["Envoy adaptive concurrency"],
            ),
            implementation_risk_review=SimpleNamespace(
                summary="Biggest risk is instability under feedback delay.",
                major_risks=["feedback oscillation"],
                operational_constraints=["telemetry freshness"],
                likely_failure_modes=["runaway reweighting"],
                mitigations=["cap update step size"],
            ),
        )
        md = OutputFormatter().to_markdown(report)
        assert "STATE OF THE ART RECON" in md
        assert "EXTERNAL GROUNDING" in md
        assert "IMPLEMENTATION RISK REVIEW" in md

    def test_includes_lens_engine_section(self) -> None:
        md = OutputFormatter().to_markdown(_make_report(lens_engine_state=_lens_engine_state()))
        assert "LENS ENGINE" in md
        assert "bundle:adaptive:fmt" in md
        assert "composite:fmt" in md
        assert "research refresh" in md.lower()

    def test_includes_pantheon_runtime_section(self) -> None:
        md = OutputFormatter().to_markdown(
            _make_report(
                pantheon_state=_pantheon_state(),
                pantheon_runtime=_pantheon_state().accounting,
                cost_breakdown=SimpleNamespace(
                    decomposition_cost=0.11,
                    search_cost=0.12,
                    scoring_cost=0.05,
                    translation_cost=0.45,
                    pantheon_cost=0.1234,
                    verification_cost=0.15,
                ),
            )
        )
        assert "PANTHEON MODE" in md
        assert "Resolution: `qualified_consensus`" in md
        assert "Outcome tier: `QUALIFIED_CONSENSUS`" in md
        assert "Objection ledger: open=`0` resolved=`0` waived=`1`" in md
        assert "Agent calls" in md
        assert "`pantheon`=$0.1234" in md

    def test_includes_runtime_orchestration_section(self) -> None:
        md = OutputFormatter().to_markdown(_make_report(deliberation_graph=_deliberation_graph()))
        assert "RUNTIME ORCHESTRATION" in md
        assert "Budget policy" in md or "Workflow" in md
        assert "candidate-1:Pheromone" in md


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
        assert meta["cost_breakdown"] is None

    def test_lens_engine_in_json(self) -> None:
        data = json.loads(
            OutputFormatter().to_json(_make_report(lens_engine_state=_lens_engine_state()))
        )
        lens = data["hephaestus_invention_report"]["lens_engine"]
        assert lens["active_bundle_id"] == "bundle:adaptive:fmt"
        assert lens["research"]["reference_generation"] == 5
        assert lens["composites"][0]["composite_id"] == "composite:fmt"

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

    def test_research_sections_in_json(self) -> None:
        data = json.loads(
            OutputFormatter().to_json(
                _make_report(
                    baseline_dossier=SimpleNamespace(
                        summary="Baseline summary", keywords_to_avoid=["queue + backoff"]
                    ),
                    external_grounding_report=SimpleNamespace(
                        summary="Grounding summary", closest_related_work=["Project X"]
                    ),
                    implementation_risk_review=SimpleNamespace(
                        summary="Risk summary", major_risks=["oscillation"]
                    ),
                )
            )
        )
        report = data["hephaestus_invention_report"]
        assert report["state_of_the_art"]["summary"] == "Baseline summary"
        assert report["external_grounding"]["summary"] == "Grounding summary"
        assert report["implementation_risk_review"]["summary"] == "Risk summary"

    def test_pantheon_runtime_in_json(self) -> None:
        data = json.loads(
            OutputFormatter().to_json(
                _make_report(
                    pantheon_state=_pantheon_state(),
                    pantheon_runtime=_pantheon_state().accounting,
                    cost_breakdown=SimpleNamespace(
                        decomposition_cost=0.11,
                        search_cost=0.12,
                        scoring_cost=0.05,
                        translation_cost=0.45,
                        pantheon_cost=0.1234,
                        verification_cost=0.15,
                    ),
                )
            )
        )
        report = data["hephaestus_invention_report"]
        assert report["pantheon"]["resolution"] == "qualified_consensus"
        assert report["pantheon"]["outcome_tier"] == "QUALIFIED_CONSENSUS"
        assert report["pantheon_runtime"]["agent_call_counts"]["hephaestus"] == 1
        assert report["meta"]["cost_breakdown"]["pantheon_cost"] == pytest.approx(0.1234)

    def test_deliberation_graph_in_json(self) -> None:
        data = json.loads(
            OutputFormatter().to_json(_make_report(deliberation_graph=_deliberation_graph()))
        )
        graph = data["hephaestus_invention_report"]["deliberation_graph"]
        assert graph["workflow_kind"] == "genesis"
        assert graph["final_candidate_id"] == "candidate-1:Pheromone"
        assert graph["accounting"]["total_cost_usd"] == pytest.approx(0.45)


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

    def test_contains_confidence_section(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "CONFIDENCE:" in plain

    def test_contains_roadmap_section(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "IMPLEMENTATION ROADMAP:" in plain
        assert "Phase 1:" in plain

    def test_contains_ascii_bar(self) -> None:
        plain = OutputFormatter().to_plain(_make_report())
        assert "[=========" in plain  # 0.94 -> 9 filled

    def test_includes_lens_engine_in_plain_output(self) -> None:
        plain = OutputFormatter().to_plain(_make_report(lens_engine_state=_lens_engine_state()))
        assert "LENS ENGINE" in plain
        assert "bundle:adaptive:fmt" in plain
        assert "Composite: composite:fmt" in plain

    def test_includes_pantheon_runtime_in_plain_output(self) -> None:
        plain = OutputFormatter().to_plain(
            _make_report(
                pantheon_state=_pantheon_state(),
                pantheon_runtime=_pantheon_state().accounting,
                cost_breakdown=SimpleNamespace(
                    decomposition_cost=0.11,
                    search_cost=0.12,
                    scoring_cost=0.05,
                    translation_cost=0.45,
                    pantheon_cost=0.1234,
                    verification_cost=0.15,
                ),
            )
        )
        assert "PANTHEON MODE" in plain
        assert "Resolution: qualified_consensus" in plain
        assert "Outcome tier: QUALIFIED_CONSENSUS" in plain
        assert "Agent calls: athena=2, hermes=2, apollo=1, hephaestus=1" in plain
        assert "pantheon=$0.1234" in plain

    def test_includes_runtime_orchestration_in_plain_output(self) -> None:
        plain = OutputFormatter().to_plain(_make_report(deliberation_graph=_deliberation_graph()))
        assert "RUNTIME ORCHESTRATION" in plain
        assert "candidate-1:Pheromone" in plain


# ---------------------------------------------------------------------------
# Score bar rendering
# ---------------------------------------------------------------------------


class TestScoreBars:
    def test_unicode_bar_full(self) -> None:
        bar = _unicode_bar(1.0)
        assert "██████████" in bar
        assert "░" not in bar

    def test_unicode_bar_empty(self) -> None:
        bar = _unicode_bar(0.0)
        assert "░░░░░░░░░░" in bar
        assert "█" not in bar

    def test_unicode_bar_mid(self) -> None:
        bar = _unicode_bar(0.62)
        assert "██████░░░░" in bar
        assert "0.62" in bar

    def test_ascii_bar_full(self) -> None:
        bar = _ascii_bar(1.0)
        assert "[==========]" in bar

    def test_ascii_bar_empty(self) -> None:
        bar = _ascii_bar(0.0)
        assert "[          ]" in bar

    def test_ascii_bar_mid(self) -> None:
        bar = _ascii_bar(0.62)
        assert "[======    ]" in bar
        assert "0.62" in bar


# ---------------------------------------------------------------------------
# Confidence interpretation
# ---------------------------------------------------------------------------


class TestConfidenceInterpretation:
    def test_far_transfer(self) -> None:
        assert "Far transfer" in _domain_distance_interpretation(0.9)

    def test_moderate_transfer(self) -> None:
        assert "Moderate transfer" in _domain_distance_interpretation(0.6)

    def test_near_transfer(self) -> None:
        assert "Near transfer" in _domain_distance_interpretation(0.3)

    def test_strong_structural_match(self) -> None:
        assert "Strong structural match" in _structural_fidelity_interpretation(0.85)

    def test_loose_analogy(self) -> None:
        assert "Loose analogy" in _structural_fidelity_interpretation(0.4)


# ---------------------------------------------------------------------------
# Confidence & roadmap in markdown output
# ---------------------------------------------------------------------------


class TestMarkdownNewSections:
    def test_confidence_section_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "**CONFIDENCE:**" in md

    def test_confidence_far_transfer_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report(domain_distance=0.94))
        assert "Far transfer" in md

    def test_confidence_loose_analogy_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report(structural_fidelity=0.3))
        assert "Loose analogy" in md

    def test_roadmap_section_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "**IMPLEMENTATION ROADMAP:**" in md
        assert "Phase 1:" in md
        assert "Phase 2:" in md
        assert "Phase 3:" in md

    def test_roadmap_auto_steps_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        # The default architecture has "def route" which should produce a step
        assert "Suggested steps" in md

    def test_unicode_bar_in_markdown(self) -> None:
        md = OutputFormatter().to_markdown(_make_report())
        assert "█" in md
        assert "░" in md

    def test_roadmap_steps_generated(self) -> None:
        steps = _generate_roadmap_steps("def route(req):\n    pass\nclass Balancer:\n    pass")
        assert any("route" in s for s in steps)
        assert any("Balancer" in s for s in steps)

    def test_roadmap_steps_empty_arch(self) -> None:
        steps = _generate_roadmap_steps("")
        assert steps == []
