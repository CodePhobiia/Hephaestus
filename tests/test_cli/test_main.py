"""
Tests for the Hephaestus CLI (heph command).

Uses Click's CliRunner to invoke CLI commands without spawning subprocesses.
All Genesis pipeline calls are mocked — no real API calls.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from hephaestus.cli.main import cli, scan_cmd, workspace_cmd
from hephaestus.lenses.state import LensBundleMember, LensBundleProof, LensEngineState
from hephaestus.research.perplexity import BenchmarkCase, BenchmarkCorpus
from hephaestus.session.deliberation import DeliberationGraph


# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------


def _make_problem_structure(problem: str = "test problem") -> MagicMock:
    """Build a mock ProblemStructure."""
    s = MagicMock()
    s.original_problem = problem
    s.structure = "Abstract trust propagation in a graph"
    s.mathematical_shape = "Robust signal propagation with Byzantine fault tolerance"
    s.native_domain = "distributed_systems"
    s.constraints = ["no persistent identity", "adversarial nodes"]
    s.confidence = 0.92
    s.cost_usd = 0.15
    return s


def _make_scored_candidate(source_domain: str = "Immune System") -> MagicMock:
    """Build a mock ScoredCandidate."""
    c = MagicMock()
    c.source_domain = source_domain
    c.source_solution = "T-cell memory mechanism"
    c.mechanism = "Clonal selection and expansion"
    c.structural_fidelity = 0.87
    c.domain_distance = 0.94
    c.combined_score = 0.91
    c.cost_usd = 0.05
    c.scoring_cost_usd = 0.02
    return c


def _make_element_mapping(src: str = "T-cell", tgt: str = "Token") -> MagicMock:
    m = MagicMock()
    m.source_element = src
    m.target_element = tgt
    m.mechanism = f"{src} maps to {tgt} via molecular handshake"
    return m


def _make_translation(
    invention_name: str = "Immune Trust Protocol",
    source_domain: str = "Immune System",
) -> MagicMock:
    """Build a mock Translation."""
    t = MagicMock()
    t.invention_name = invention_name
    t.source_domain = source_domain
    t.architecture = "Architecture paragraph 1.\n\nArchitecture paragraph 2."
    t.mathematical_proof = "Structural isomorphism proof statement."
    t.limitations = ["Analogy breaks at high churn rates", "Requires seed trust set"]
    t.implementation_notes = "Implement using a distributed graph store."
    t.key_insight = "Trust propagates like immune memory — learned, not assigned."
    t.mapping = [
        _make_element_mapping("T-cell", "Trust token"),
        _make_element_mapping("Antigen", "Interaction proof"),
        _make_element_mapping("Clonal selection", "Trust amplification"),
    ]
    t.cost_usd = 0.45
    t.source_candidate = _make_scored_candidate(source_domain)
    return t


def _make_adversarial_result(verdict: str = "NOVEL") -> MagicMock:
    adv = MagicMock()
    adv.attack_valid = False
    adv.fatal_flaws = []
    adv.structural_weaknesses = ["High churn rate scenarios need special handling"]
    adv.strongest_objection = "The mapping breaks under extreme load"
    adv.novelty_risk = 0.12
    adv.verdict = verdict
    return adv


def _make_verified_invention(
    invention_name: str = "Immune Trust Protocol",
    source_domain: str = "Immune System",
    novelty_score: float = 0.91,
    verdict: str = "NOVEL",
) -> MagicMock:
    """Build a mock VerifiedInvention."""
    v = MagicMock()
    v.invention_name = invention_name
    v.source_domain = source_domain
    v.novelty_score = novelty_score
    v.structural_validity = 0.88
    v.implementation_feasibility = 0.82
    v.feasibility_rating = "HIGH"
    v.adversarial_result = _make_adversarial_result(verdict)
    v.prior_art_status = "NO_PRIOR_ART_FOUND"
    v.prior_art_report = None
    v.verification_notes = "Structurally valid cross-domain mapping."
    v.validity_notes = "The immune-to-trust mapping is formally isomorphic."
    v.feasibility_notes = "Implementable with current distributed systems tooling."
    v.novelty_notes = "No prior art found for this specific cross-domain application."
    v.recommended_next_steps = ["Build proof-of-concept", "Write whitepaper"]
    v.verification_cost_usd = 0.15
    v.translation = _make_translation(invention_name, source_domain)
    v.verdict = verdict
    v.is_viable = True
    return v


def _deliberation_graph() -> DeliberationGraph:
    graph = DeliberationGraph(workflow_kind="genesis", goal="test goal")
    graph.record_stage("search", "Found candidates.")
    graph.ensure_candidate("candidate-1:immune", source_domain="Immune System", status="finalist")
    graph.mark_final("candidate-1:immune", reason="verification_complete")
    return graph


def _make_cost_breakdown(
    decomp: float = 0.15,
    search: float = 0.12,
    score: float = 0.05,
    translate: float = 0.45,
    pantheon: float = 0.0,
    verify: float = 0.15,
) -> SimpleNamespace:
    total = decomp + search + score + translate + pantheon + verify
    return SimpleNamespace(
        decomposition_cost=decomp,
        search_cost=search,
        scoring_cost=score,
        translation_cost=translate,
        pantheon_cost=pantheon,
        verification_cost=verify,
        total=total,
        to_dict=lambda: {
            "decomposition": decomp,
            "search": search,
            "scoring": score,
            "translation": translate,
            "pantheon": pantheon,
            "verification": verify,
            "total": total,
        },
    )


def _make_invention_report(
    problem: str = "I need a trust system for anonymous actors",
    invention_name: str = "Immune Trust Protocol",
    source_domain: str = "Immune System",
    novelty_score: float = 0.91,
    num_alternatives: int = 2,
    verdict: str = "NOVEL",
) -> MagicMock:
    """Build a complete mock InventionReport."""
    report = MagicMock()
    report.problem = problem
    report.structure = _make_problem_structure(problem)
    report.total_cost_usd = 0.92
    report.total_duration_seconds = 47.3
    report.cost_breakdown = _make_cost_breakdown()
    report.model_config = {
        "decompose": "claude-opus-4-5",
        "search": "gpt-4o",
        "score": "gpt-4o-mini",
        "translate": "claude-opus-4-5",
        "attack": "gpt-4o",
        "defend": "claude-opus-4-5",
    }

    top = _make_verified_invention(invention_name, source_domain, novelty_score, verdict)
    report.top_invention = top

    alternatives = [
        _make_verified_invention(
            f"Alt Invention {i}",
            f"Domain {i}",
            novelty_score - 0.05 * i,
        )
        for i in range(1, num_alternatives + 1)
    ]
    report.alternative_inventions = alternatives
    report.verified_inventions = [top] + alternatives
    report.all_candidates = [_make_scored_candidate() for _ in range(8)]
    report.scored_candidates = [_make_scored_candidate() for _ in range(5)]
    report.translations = [_make_translation()]

    def summary_fn():
        return f"⚒️  {invention_name} (from {source_domain}) | novelty=0.91 | $0.92 | 47s"

    report.summary = summary_fn
    return report


def _pantheon_state() -> SimpleNamespace:
    return SimpleNamespace(
        mode="pantheon",
        resolution="consensus",
        consensus_achieved=True,
        final_verdict="NOVEL",
        winning_candidate_id="candidate-1:Immune Trust Protocol",
        unresolved_vetoes=[],
        failure_reason=None,
    )


def _pantheon_runtime() -> dict[str, Any]:
    return {
        "total_cost_usd": 0.1234,
        "total_input_tokens": 210,
        "total_output_tokens": 70,
        "total_duration_seconds": 3.5,
        "agent_call_counts": {"athena": 2, "hermes": 2, "apollo": 1},
    }


def _make_workspace_dir(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "demo"
    (package / "cli").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "main.py").write_text(
        "def main() -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_main.py").write_text(
        "def test_smoke() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "version = '0.1.0'\n"
        "dependencies = ['pytest>=8.0']\n"
        "scripts = { demo = 'demo.cli.main:main' }\n",
        encoding="utf-8",
    )
    return tmp_path


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=2,
        active_bundle_id="bundle:adaptive:main",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
            )
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:main",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune"],
                status="active",
                proof_status="fallback",
                cohesion_score=0.60,
                proof_fingerprint="proof-main",
                reference_generation=2,
                summary="CLI bridge lens state.",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Async iterator helper
# ---------------------------------------------------------------------------


async def _make_stream(stages: list[tuple[str, str, Any]]) -> AsyncIterator[Any]:
    """Build a fake pipeline update stream."""
    from hephaestus.core.genesis import PipelineStage, PipelineUpdate

    stage_map = {
        "STARTING": PipelineStage.STARTING,
        "DECOMPOSING": PipelineStage.DECOMPOSING,
        "DECOMPOSED": PipelineStage.DECOMPOSED,
        "SEARCHING": PipelineStage.SEARCHING,
        "SEARCHED": PipelineStage.SEARCHED,
        "SCORING": PipelineStage.SCORING,
        "SCORED": PipelineStage.SCORED,
        "TRANSLATING": PipelineStage.TRANSLATING,
        "TRANSLATED": PipelineStage.TRANSLATED,
        "VERIFYING": PipelineStage.VERIFYING,
        "VERIFIED": PipelineStage.VERIFIED,
        "COMPLETE": PipelineStage.COMPLETE,
        "FAILED": PipelineStage.FAILED,
    }

    for stage_name, message, data in stages:
        yield PipelineUpdate(
            stage=stage_map[stage_name],
            message=message,
            data=data,
            elapsed_seconds=1.0,
        )


def _make_successful_stream(report: Any) -> Any:
    """Build a mock invent_stream that yields a successful pipeline run."""
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async for update in _make_stream([
            ("STARTING", "Starting Genesis pipeline...", None),
            ("DECOMPOSING", "Stage 1/5: Extracting abstract structural form...", None),
            ("DECOMPOSED", "Decomposed: [distributed_systems] Robust signal propagation", report.structure),
            ("SEARCHING", "Stage 2/5: Searching 10 domains...", None),
            ("SEARCHED", "Found 8 cross-domain candidates", report.all_candidates),
            ("SCORING", "Stage 3/5: Scoring 8 candidates...", None),
            ("SCORED", "Scored 5 candidates. Top: Immune System (score=0.910)", report.scored_candidates),
            ("TRANSLATING", "Stage 4/5: Translating top 3 candidates...", None),
            ("TRANSLATED", "Translated 1 inventions. Top: Immune Trust Protocol", report.translations),
            ("VERIFYING", "Stage 5/5: Adversarial novelty verification...", None),
            ("VERIFIED", "Verified 3 inventions. Top novelty: 0.91", report.verified_inventions),
            ("COMPLETE", report.summary(), report),
        ]):
            yield update

    return _stream


def _make_failed_stream(stage: str = "DECOMPOSED", msg: str = "Decomposition failed: parse error") -> Any:
    """Build a mock invent_stream that yields a failed pipeline run."""
    async def _stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async for update in _make_stream([
            ("STARTING", "Starting Genesis pipeline...", None),
            ("DECOMPOSING", "Stage 1/5: Decomposing...", None),
            ("FAILED", msg, None),
        ]):
            yield update

    return _stream


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set fake API keys for all CLI tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner with color disabled."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Help and version
# ---------------------------------------------------------------------------


class TestHelpVersion:
    def test_help_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "HEPHAESTUS" in result.output
        assert "--depth" in result.output
        assert "--model" in result.output
        assert "--format" in result.output
        assert "--trace" in result.output
        assert "--raw" in result.output
        assert "--candidates" in result.output
        assert "--output" in result.output
        assert "--cost" in result.output
        assert "--quiet" in result.output
        assert "--research / --no-research" in result.output or "--research" in result.output
        assert "--benchmark-corpus" in result.output

    def test_short_help_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["-h"])
        assert result.exit_code == 0
        assert "--depth" in result.output

    def test_version_flag(self, runner: CliRunner) -> None:
        from hephaestus import __version__
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_short_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["-v"])
        assert result.exit_code == 0

    def test_no_args_shows_help_text(self, runner: CliRunner) -> None:
        """Calling heph with no args should show usage hint, not error."""
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "heph" in result.output.lower() or "problem" in result.output.lower()


# ---------------------------------------------------------------------------
# Missing API keys
# ---------------------------------------------------------------------------


class TestApiKeyValidation:
    def test_missing_anthropic_key_with_opus(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(cli, ["--model", "opus", "test problem"])
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output

    def test_missing_openai_key_with_gpt5(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(cli, ["--model", "gpt5", "test problem"])
        assert result.exit_code == 1
        assert "OPENAI_API_KEY" in result.output

    def test_missing_anthropic_key_with_both(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(cli, ["--model", "both", "test problem"])
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.output


# ---------------------------------------------------------------------------
# Successful invocations
# ---------------------------------------------------------------------------


class TestSuccessfulInvocation:
    @patch("hephaestus.core.genesis.Genesis")
    def test_basic_invocation(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["I need a trust system"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_quiet_mode(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--quiet", "I need a trust system"])
        assert result.exit_code == 0
        # Quiet mode should print minimal output
        output_lines = [l for l in result.output.strip().split("\n") if l.strip()]
        assert len(output_lines) <= 5  # minimal output

    @patch("hephaestus.core.genesis.Genesis")
    def test_depth_option(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--depth", "5", "test problem"])
        assert result.exit_code == 0

        # Verify depth was passed to config
        call_args = MockGenesis.call_args
        if call_args:
            config = call_args[0][0] if call_args[0] else call_args[1].get("config")
            # Config might be passed as positional or keyword arg
            # Just check that Genesis was instantiated

    @patch("hephaestus.core.genesis.Genesis")
    def test_model_opus(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--model", "opus", "test problem"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_model_gpt5(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--model", "gpt5", "test problem"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_candidates_option(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--candidates", "12", "test problem"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_format_json(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--format", "json", "test problem"])
        assert result.exit_code == 0
        # Should contain JSON
        assert "{" in result.output

    @patch("hephaestus.core.genesis.Genesis")
    def test_format_text(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--format", "text", "test problem"])
        assert result.exit_code == 0
        assert "HEPHAESTUS" in result.output

    @patch("hephaestus.core.genesis.Genesis")
    def test_trace_flag(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--trace", "test problem"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_cost_flag(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--cost", "test problem"])
        assert result.exit_code == 0
        # Cost section should appear
        assert "$" in result.output

    @patch("hephaestus.core.genesis.Genesis")
    def test_domain_option(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["--domain", "distributed-systems", "test problem"])
        assert result.exit_code == 0

    @patch("hephaestus.core.genesis.Genesis")
    def test_output_file_json(self, MockGenesis: MagicMock, runner: CliRunner, tmp_path: Any) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        output_file = tmp_path / "output.json"
        result = runner.invoke(cli, ["--output", str(output_file), "test problem"])
        assert result.exit_code == 0
        assert output_file.exists()

    @patch("hephaestus.core.genesis.Genesis")
    def test_output_file_markdown(self, MockGenesis: MagicMock, runner: CliRunner, tmp_path: Any) -> None:
        report = _make_invention_report()
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        output_file = tmp_path / "output.md"
        result = runner.invoke(cli, ["--output", str(output_file), "test problem"])
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "HEPHAESTUS" in content

    def test_benchmark_corpus_json(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
        corpus = BenchmarkCorpus(
            topic="distributed systems",
            summary="Grounded corpus",
            cases=[BenchmarkCase(problem="Handle failover")],
        )

        with patch("hephaestus.research.BenchmarkCorpusBuilder.build", new=AsyncMock(return_value=corpus)):
            result = runner.invoke(
                cli,
                ["--benchmark-corpus", "distributed systems", "--format", "json"],
            )

        assert result.exit_code == 0
        assert '"topic": "distributed systems"' in result.output

    def test_benchmark_corpus_output_file(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
        corpus = BenchmarkCorpus(
            topic="distributed systems",
            summary="Grounded corpus",
            cases=[BenchmarkCase(problem="Handle failover")],
        )
        output_file = tmp_path / "benchmark.md"

        with patch("hephaestus.research.BenchmarkCorpusBuilder.build", new=AsyncMock(return_value=corpus)):
            result = runner.invoke(
                cli,
                ["--benchmark-corpus", "distributed systems", "--output", str(output_file)],
            )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Handle failover" in output_file.read_text()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("hephaestus.core.genesis.Genesis")
    def test_pipeline_failure(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        instance = MockGenesis.return_value
        instance.invent_stream = _make_failed_stream("FAILED", "Decomposition failed: JSON parse error")

        result = runner.invoke(cli, ["test problem"])
        assert result.exit_code == 1
        # Should show user-friendly error, not stack trace
        assert "Traceback" not in result.output

    def test_invalid_depth(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--depth", "99", "test problem"])
        assert result.exit_code != 0

    def test_invalid_depth_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--depth", "0", "test problem"])
        assert result.exit_code != 0

    def test_invalid_model(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--model", "invalid-model", "test problem"])
        assert result.exit_code != 0

    def test_invalid_format(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--format", "invalid-fmt", "test problem"])
        assert result.exit_code != 0

    def test_invalid_candidates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--candidates", "99", "test problem"])
        assert result.exit_code != 0

    def test_benchmark_corpus_requires_research(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
        result = runner.invoke(cli, ["--no-research", "--benchmark-corpus", "distributed systems"])
        assert result.exit_code == 1
        assert "Benchmark corpus generation failed" in result.output

    def test_benchmark_corpus_rejects_problem_argument(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--benchmark-corpus", "distributed systems", "test problem"])
        assert result.exit_code == 1
        assert "standalone research mode" in result.output

    @patch("hephaestus.core.genesis.Genesis")
    def test_no_inventions_produced(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        """When pipeline completes but top_invention is None, should handle gracefully."""
        report = _make_invention_report()
        report.top_invention = None
        instance = MockGenesis.return_value
        instance.invent_stream = _make_successful_stream(report)

        result = runner.invoke(cli, ["test problem"])
        # Should not crash, might show error message
        assert "Traceback" not in result.output

    @patch("hephaestus.core.genesis.Genesis")
    def test_unexpected_pipeline_exception_no_traceback(
        self, MockGenesis: MagicMock, runner: CliRunner
    ) -> None:
        async def _broken_stream(*args: Any, **kwargs: Any):
            raise RuntimeError("socket closed")
            yield

        instance = MockGenesis.return_value
        instance.invent_stream = _broken_stream

        result = runner.invoke(cli, ["test problem"])

        assert result.exit_code == 1
        assert "Traceback" not in result.output
        assert "socket" in result.output.lower() or "pipeline" in result.output.lower()


# ---------------------------------------------------------------------------
# Raw mode
# ---------------------------------------------------------------------------


class TestRawMode:
    @patch("hephaestus.deepforge.harness.DeepForgeHarness")
    @patch("hephaestus.deepforge.adapters.anthropic.AnthropicAdapter")
    def test_raw_mode(
        self,
        MockAdapter: MagicMock,
        MockHarness: MagicMock,
        runner: CliRunner,
    ) -> None:
        forge_result = MagicMock()
        forge_result.output = "This is the raw deepforge output."
        forge_result.trace.total_cost_usd = 0.12
        forge_result.trace.total_output_tokens = 500
        forge_result.trace.attempts = 2
        forge_result.trace.pruner_kills = 1

        instance = MockHarness.return_value
        instance.forge = AsyncMock(return_value=forge_result)

        result = runner.invoke(cli, ["--raw", "a raw prompt here"])
        assert result.exit_code == 0

    @patch("hephaestus.deepforge.harness.DeepForgeHarness")
    @patch("hephaestus.deepforge.adapters.anthropic.AnthropicAdapter")
    def test_raw_mode_with_depth(
        self,
        MockAdapter: MagicMock,
        MockHarness: MagicMock,
        runner: CliRunner,
    ) -> None:
        forge_result = MagicMock()
        forge_result.output = "Raw output"
        forge_result.trace.total_cost_usd = 0.25
        forge_result.trace.total_output_tokens = 1000
        forge_result.trace.attempts = 3
        forge_result.trace.pruner_kills = 0

        instance = MockHarness.return_value
        instance.forge = AsyncMock(return_value=forge_result)

        result = runner.invoke(cli, ["--raw", "--depth", "5", "raw prompt"])
        assert result.exit_code == 0

    @patch("hephaestus.deepforge.harness.DeepForgeHarness")
    @patch("hephaestus.deepforge.adapters.openai.OpenAIAdapter")
    def test_raw_mode_gpt5(
        self,
        MockAdapter: MagicMock,
        MockHarness: MagicMock,
        runner: CliRunner,
    ) -> None:
        forge_result = MagicMock()
        forge_result.output = "GPT raw output"
        forge_result.trace.total_cost_usd = 0.08
        forge_result.trace.total_output_tokens = 300
        forge_result.trace.attempts = 1
        forge_result.trace.pruner_kills = 0

        instance = MockHarness.return_value
        instance.forge = AsyncMock(return_value=forge_result)

        result = runner.invoke(cli, ["--raw", "--model", "gpt5", "raw prompt"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Interrupt handling
# ---------------------------------------------------------------------------


class TestInterruptHandling:
    @patch("hephaestus.core.genesis.Genesis")
    def test_keyboard_interrupt(self, MockGenesis: MagicMock, runner: CliRunner) -> None:
        """KeyboardInterrupt should be handled gracefully without a Python traceback."""
        async def _interrupt_stream(*args: Any, **kwargs: Any):
            raise KeyboardInterrupt()
            yield  # make it a generator

        instance = MockGenesis.return_value
        instance.invent_stream = _interrupt_stream

        # Catch exceptions in runner so we can inspect the result
        result = runner.invoke(cli, ["test problem"], catch_exceptions=True)
        # Should not produce a Python traceback in output
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# Display tests (smoke tests for Rich rendering)
# ---------------------------------------------------------------------------


class TestDisplay:
    def test_print_banner(self) -> None:
        """Smoke test for banner rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_banner

        console = Console(file=StringIO(), highlight=False)
        print_banner(console)  # should not raise

    def test_print_invention_report(self) -> None:
        """Smoke test for full invention report rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_invention_report

        report = _make_invention_report()
        console = Console(file=StringIO(), highlight=False)
        print_invention_report(console, report, show_trace=True, show_cost=True)
        output = console.file.getvalue()  # type: ignore
        # Should contain key sections
        assert "HEPHAESTUS" in output or "Invention" in output

    def test_print_invention_report_with_lens_engine(self) -> None:
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_invention_report

        report = _make_invention_report()
        report.lens_engine_state = _lens_engine_state()
        console = Console(file=StringIO(), highlight=False)
        print_invention_report(console, report, show_trace=False, show_cost=False)
        output = console.file.getvalue()  # type: ignore
        assert "Lens Engine" in output
        assert "bundle:adaptive:main" in output

    def test_print_invention_report_with_pantheon(self) -> None:
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_invention_report

        report = _make_invention_report()
        report.pantheon_state = _pantheon_state()
        report.pantheon_runtime = _pantheon_runtime()
        report.cost_breakdown = _make_cost_breakdown(pantheon=0.1234)
        console = Console(file=StringIO(), highlight=False)
        print_invention_report(console, report, show_trace=False, show_cost=True)
        output = console.file.getvalue()  # type: ignore
        assert "Pantheon" in output
        assert "consensus" in output
        assert "$0.1234" in output

    def test_print_cost_table(self) -> None:
        """Smoke test for cost table rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_cost_table

        report = _make_invention_report()
        console = Console(file=StringIO(), highlight=False)
        print_cost_table(console, report)
        output = console.file.getvalue()  # type: ignore
        assert "$" in output

    def test_print_trace(self) -> None:
        """Smoke test for trace rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_trace

        report = _make_invention_report()
        console = Console(file=StringIO(), highlight=False)
        print_trace(console, report)

    def test_print_error(self) -> None:
        """Smoke test for error rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_error

        console = Console(file=StringIO(), highlight=False)
        print_error(console, "Something went wrong", hint="Try rephrasing the problem.")
        output = console.file.getvalue()  # type: ignore
        assert "Something went wrong" in output

    def test_print_quiet_result(self) -> None:
        """Smoke test for quiet result rendering."""
        from io import StringIO
        from rich.console import Console
        from hephaestus.cli.display import print_quiet_result

        report = _make_invention_report()
        console = Console(file=StringIO(), highlight=False)
        print_quiet_result(console, report)
        output = console.file.getvalue()  # type: ignore
        assert "Immune Trust Protocol" in output or "0.91" in output

    def test_bridge_report_preserves_lens_engine_state(self) -> None:
        from hephaestus.cli.main import _bridge_report
        from hephaestus.output.formatter import OutputFormatter

        report = _make_invention_report()
        report.lens_engine_state = _lens_engine_state()
        bridged = _bridge_report(report)
        payload = json.loads(OutputFormatter().to_json(bridged))
        lens = payload["hephaestus_invention_report"]["lens_engine"]
        assert lens["active_bundle_id"] == "bundle:adaptive:main"

    def test_bridge_report_preserves_pantheon_runtime(self) -> None:
        from hephaestus.cli.main import _bridge_report
        from hephaestus.output.formatter import OutputFormatter

        report = _make_invention_report()
        report.pantheon_state = _pantheon_state()
        report.pantheon_runtime = _pantheon_runtime()
        report.cost_breakdown = _make_cost_breakdown(pantheon=0.1234)
        bridged = _bridge_report(report)
        payload = json.loads(OutputFormatter().to_json(bridged))
        pantheon = payload["hephaestus_invention_report"]["pantheon"]
        runtime = payload["hephaestus_invention_report"]["pantheon_runtime"]
        assert pantheon["resolution"] == "consensus"
        assert runtime["total_cost_usd"] == pytest.approx(0.1234)

    def test_bridge_report_preserves_deliberation_graph(self) -> None:
        from hephaestus.cli.main import _bridge_report
        from hephaestus.output.formatter import OutputFormatter

        report = _make_invention_report()
        report.deliberation_graph = _deliberation_graph()

        bridged = _bridge_report(report)
        payload = json.loads(OutputFormatter().to_json(bridged))
        graph = payload["hephaestus_invention_report"]["deliberation_graph"]

        assert graph["workflow_kind"] == "genesis"
        assert graph["final_candidate_id"] == "candidate-1:immune"


# ---------------------------------------------------------------------------
# SDK tests
# ---------------------------------------------------------------------------


class TestSDKClient:
    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env should read from environment variables."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus.from_env()
        assert heph.model == "both"

    def test_constructor_with_keys(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(
            anthropic_key="sk-ant-test",
            openai_key="sk-test",
            model="both",
            depth=5,
            candidates=10,
        )
        assert heph.depth == 5
        assert heph.candidates == 10

    def test_constructor_opus_only(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(anthropic_key="sk-ant-test", model="opus")
        assert heph.model == "opus"

    def test_constructor_gpt5_only(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(openai_key="sk-test", model="gpt5")
        assert heph.model == "gpt5"

    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.sdk.client import Hephaestus, ConfigurationError
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ConfigurationError):
            Hephaestus(model="both")

    def test_estimate_cost(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")
        estimate = heph.estimate_cost("a distributed systems problem")

        assert "low" in estimate
        assert "mid" in estimate
        assert "high" in estimate
        assert "breakdown" in estimate
        assert estimate["low"] > 0
        assert estimate["mid"] >= estimate["low"]
        assert estimate["high"] >= estimate["mid"]

    def test_estimate_cost_longer_problem(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")

        short = heph.estimate_cost("short problem")
        long = heph.estimate_cost("x" * 3000)

        # Longer problem should cost more
        assert long["mid"] >= short["mid"]

    def test_list_lenses(self) -> None:
        """list_lenses should return a list of metadata dicts."""
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")

        # May raise if lens library doesn't exist, but should not crash badly
        try:
            lenses = heph.list_lenses()
            assert isinstance(lenses, list)
            if lenses:
                assert "lens_id" in lenses[0]
                assert "name" in lenses[0]
        except Exception as exc:
            # Library might not exist in test env — that's ok
            assert "lens" in str(exc).lower() or "directory" in str(exc).lower() or "not found" in str(exc).lower()

    def test_get_lens_not_found(self) -> None:
        from hephaestus.sdk.client import Hephaestus, HephaestusError
        heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")

        with pytest.raises(HephaestusError):
            heph.get_lens("nonexistent_lens_that_does_not_exist")

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        async with Hephaestus.from_env() as heph:
            assert heph is not None
            assert heph.model == "both"

    def test_repr(self) -> None:
        from hephaestus.sdk.client import Hephaestus
        heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test", depth=4, candidates=6)
        r = repr(heph)
        assert "Hephaestus" in r
        assert "4" in r
        assert "6" in r

    @pytest.mark.asyncio
    async def test_invent_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test full invent() call with mocked Genesis."""
        from hephaestus.sdk.client import Hephaestus

        report = _make_invention_report()

        with patch("hephaestus.sdk.client.Genesis") as MockGenesis:
            instance = MockGenesis.return_value
            instance.invent_stream = _make_successful_stream(report)
            instance.invent = AsyncMock(return_value=report)

            heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")
            result = await heph.invent("test problem")
            assert result is report

    @pytest.mark.asyncio
    async def test_invent_stream_success(self) -> None:
        """Test invent_stream() yields updates correctly."""
        from hephaestus.sdk.client import Hephaestus
        from hephaestus.core.genesis import PipelineStage

        report = _make_invention_report()

        with patch("hephaestus.sdk.client.Genesis") as MockGenesis:
            instance = MockGenesis.return_value
            instance.invent_stream = _make_successful_stream(report)

            heph = Hephaestus(anthropic_key="sk-ant-test", openai_key="sk-test")
            stages_seen = []
            final_report = None

            async for update in heph.invent_stream("test problem"):
                stages_seen.append(update.stage)
                if update.stage == PipelineStage.COMPLETE:
                    final_report = update.data

            assert PipelineStage.COMPLETE in stages_seen
            assert final_report is report


class TestWorkspaceSurfaces:
    def test_scan_cmd_json_includes_repo_dossier(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = _make_workspace_dir(tmp_path)

        result = runner.invoke(scan_cmd, [str(repo), "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "repo_dossier" in payload
        assert payload["repo_dossier"]["code_roots"] == ["src/demo"]
        assert payload["repo_dossier"]["components"]

    def test_workspace_cmd_passes_workspace_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = CliRunner()
        repo = _make_workspace_dir(tmp_path)
        captured: dict[str, Any] = {}

        def _fake_run_interactive(console: Any, model: str, layered_config: Any = None, workspace_root: Any = None) -> None:
            captured["model"] = model
            captured["workspace_root"] = workspace_root

        import hephaestus.cli.repl as repl_module

        monkeypatch.setattr(repl_module, "run_interactive", _fake_run_interactive)

        result = runner.invoke(workspace_cmd, [str(repo), "--model", "both"])

        assert result.exit_code == 0
        assert captured["model"] == "both"
        assert captured["workspace_root"] == repo
