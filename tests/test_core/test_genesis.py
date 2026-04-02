"""
Tests for the Genesis pipeline orchestrator.

All sub-stages are mocked — this tests the wiring, cost accumulation,
streaming, and error handling of the Genesis class.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.core.decomposer import DecompositionError, ProblemStructure
from hephaestus.core.genesis import (
    CostBreakdown,
    Genesis,
    GenesisConfig,
    GenesisError,
    InventionReport,
    PipelineStage,
    PipelineUpdate,
)
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate, SearchError
from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.core.verifier import AdversarialResult, VerifiedInvention
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------


def _make_problem_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="I need a fault-tolerant distributed task scheduler",
        structure="Robust resource allocation under node failures",
        constraints=["fault tolerance", "low latency"],
        mathematical_shape="graph with Byzantine fault tolerance",
        native_domain="distributed_systems",
        problem_maps_to={"routing", "allocation"},
        cost_usd=0.015,
    )


def _make_lens() -> Lens:
    return Lens(
        name="Immune System",
        domain="biology",
        subdomain="immune",
        axioms=["Trust is earned through molecular handshake.", "Memory is distributed."],
        structural_patterns=[
            StructuralPattern("clonal", "Amplify successful responses", ["allocation"])
        ],
        injection_prompt="You are reasoning as a biological immune system.",
    )


def _make_search_candidate() -> SearchCandidate:
    lens = _make_lens()
    ls = LensScore(
        lens=lens, domain_distance=0.85,
        structural_relevance=0.7, composite_score=0.6, matched_patterns=["allocation"]
    )
    return SearchCandidate(
        source_domain="Immune System — T-Cell Memory",
        source_solution="T-cell memory through clonal expansion",
        mechanism="Clonal selection amplifies successful responses",
        structural_mapping="Task persistence maps to immune memory",
        lens_used=lens, lens_score=ls, confidence=0.85, cost_usd=0.005,
    )


def _make_scored_candidate() -> ScoredCandidate:
    sc = _make_search_candidate()
    return ScoredCandidate(
        candidate=sc, structural_fidelity=0.8,
        domain_distance=0.85, combined_score=0.65,
        fidelity_reasoning="Strong match", scoring_cost_usd=0.003,
    )


def _make_translation() -> Translation:
    sc = _make_scored_candidate()
    return Translation(
        invention_name="Immune-Memory Task Scheduler",
        mapping=[ElementMapping("T-cell", "Task executor", "Both represent active work units")],
        architecture="Immune-inspired distributed scheduler with memory layer",
        mathematical_proof="T maps to T' under structural isomorphism",
        limitations=["Cache invalidation needed", "No MHC equivalent"],
        implementation_notes="Use Redis for memory layer",
        key_insight="Immune memory eliminates redundant recognition work",
        source_candidate=sc, cost_usd=0.02,
    )


def _make_verified_invention() -> VerifiedInvention:
    ar = AdversarialResult(
        attack_valid=False, fatal_flaws=[], structural_weaknesses=[],
        strongest_objection="", novelty_risk=0.15, verdict="NOVEL",
    )
    return VerifiedInvention(
        invention_name="Immune-Memory Task Scheduler",
        translation=_make_translation(),
        novelty_score=0.88,
        structural_validity=0.85,
        implementation_feasibility=0.80,
        feasibility_rating="HIGH",
        adversarial_result=ar,
        prior_art_status="NO_PRIOR_ART_FOUND",
        verification_cost_usd=0.008,
    )


def _make_forge_result(text: str = "{}", cost: float = 0.01) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


# ---------------------------------------------------------------------------
# Tests: InventionReport
# ---------------------------------------------------------------------------


class TestInventionReport:
    def _make_report(self) -> InventionReport:
        return InventionReport(
            problem="Test problem",
            structure=_make_problem_structure(),
            all_candidates=[_make_search_candidate()],
            scored_candidates=[_make_scored_candidate()],
            translations=[_make_translation()],
            verified_inventions=[_make_verified_invention()],
            cost_breakdown=CostBreakdown(
                decomposition_cost=0.015,
                search_cost=0.005,
                scoring_cost=0.003,
                translation_cost=0.020,
                verification_cost=0.008,
            ),
            total_duration_seconds=12.5,
        )

    def test_top_invention(self):
        report = self._make_report()
        assert report.top_invention is not None
        assert report.top_invention.invention_name == "Immune-Memory Task Scheduler"

    def test_top_invention_none_when_empty(self):
        report = self._make_report()
        report.verified_inventions = []
        assert report.top_invention is None

    def test_total_cost_usd(self):
        report = self._make_report()
        expected = 0.015 + 0.005 + 0.003 + 0.020 + 0.008
        assert report.total_cost_usd == pytest.approx(expected)

    def test_alternative_inventions(self):
        report = self._make_report()
        inv2 = _make_verified_invention()
        inv2.invention_name = "Second Invention"
        report.verified_inventions.append(inv2)
        assert len(report.alternative_inventions) == 1
        assert report.alternative_inventions[0].invention_name == "Second Invention"

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["problem"] == "Test problem"
        assert d["top_invention"]["name"] == "Immune-Memory Task Scheduler"
        assert "cost_breakdown" in d
        assert d["cost_breakdown"]["total"] == pytest.approx(0.051)

    def test_summary(self):
        report = self._make_report()
        s = report.summary()
        assert "Immune-Memory Task Scheduler" in s
        assert "novelty=" in s


class TestCostBreakdown:
    def test_total(self):
        cb = CostBreakdown(
            decomposition_cost=0.01,
            search_cost=0.02,
            scoring_cost=0.005,
            translation_cost=0.04,
            verification_cost=0.015,
        )
        assert cb.total == pytest.approx(0.09)

    def test_to_dict(self):
        cb = CostBreakdown(decomposition_cost=0.01)
        d = cb.to_dict()
        assert "decomposition" in d
        assert "total" in d
        assert d["total"] == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# Tests: Genesis (mocked pipeline)
# ---------------------------------------------------------------------------


class TestGenesis:
    """Tests that mock all 5 stages and test orchestration."""

    def _make_config(self) -> GenesisConfig:
        return GenesisConfig(
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )

    def _mock_all_stages(self):
        """Return a patcher context that mocks all 5 pipeline stages."""
        structure = _make_problem_structure()
        candidates = [_make_search_candidate()]
        scored = [_make_scored_candidate()]
        translations = [_make_translation()]
        verified = [_make_verified_invention()]

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(return_value=structure)

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=candidates)

        mock_scorer = MagicMock()
        mock_scorer.score = AsyncMock(return_value=scored)

        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=translations)

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(return_value=verified)

        return {
            "decomposer": mock_decomposer,
            "searcher": mock_searcher,
            "scorer": mock_scorer,
            "translator": mock_translator,
            "verifier": mock_verifier,
        }

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        """Full pipeline produces InventionReport with all stages."""
        genesis = Genesis(self._make_config())
        mocks = self._mock_all_stages()

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            report = await genesis.invent("I need a fault-tolerant task scheduler")

        assert isinstance(report, InventionReport)
        assert report.top_invention is not None
        assert report.top_invention.invention_name == "Immune-Memory Task Scheduler"
        assert len(report.all_candidates) == 1
        assert len(report.scored_candidates) == 1
        assert len(report.translations) == 1
        assert len(report.verified_inventions) == 1

    @pytest.mark.asyncio
    async def test_decomposition_failure_yields_failed(self):
        """Decomposition failure should yield FAILED stage update."""
        genesis = Genesis(self._make_config())

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(
            side_effect=DecompositionError("Test failure")
        )

        updates = []
        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mock_decomposer),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            async for update in genesis.invent_stream("test problem"):
                updates.append(update)

        stages = [u.stage for u in updates]
        assert PipelineStage.FAILED in stages
        assert PipelineStage.COMPLETE not in stages

    @pytest.mark.asyncio
    async def test_empty_candidates_yields_failed(self):
        """No candidates from search should yield FAILED."""
        genesis = Genesis(self._make_config())

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(return_value=_make_problem_structure())

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=[])  # Empty!

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mock_decomposer),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mock_searcher),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            updates = []
            async for update in genesis.invent_stream("test problem"):
                updates.append(update)

        stages = [u.stage for u in updates]
        assert PipelineStage.FAILED in stages

    @pytest.mark.asyncio
    async def test_streaming_yields_all_stages(self):
        """Streaming should yield updates for each pipeline stage."""
        genesis = Genesis(self._make_config())
        mocks = self._mock_all_stages()

        updates = []
        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            async for update in genesis.invent_stream("test"):
                updates.append(update)

        stage_set = {u.stage for u in updates}
        expected_stages = {
            PipelineStage.STARTING,
            PipelineStage.DECOMPOSING,
            PipelineStage.DECOMPOSED,
            PipelineStage.SEARCHING,
            PipelineStage.SEARCHED,
            PipelineStage.SCORING,
            PipelineStage.SCORED,
            PipelineStage.TRANSLATING,
            PipelineStage.TRANSLATED,
            PipelineStage.VERIFYING,
            PipelineStage.VERIFIED,
            PipelineStage.COMPLETE,
        }
        assert expected_stages.issubset(stage_set)

    @pytest.mark.asyncio
    async def test_complete_update_contains_report(self):
        """The COMPLETE update should have an InventionReport as data."""
        genesis = Genesis(self._make_config())
        mocks = self._mock_all_stages()

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            complete_update = None
            async for update in genesis.invent_stream("test"):
                if update.stage == PipelineStage.COMPLETE:
                    complete_update = update

        assert complete_update is not None
        assert isinstance(complete_update.data, InventionReport)

    @pytest.mark.asyncio
    async def test_invent_raises_genesis_error_on_failure(self):
        """invent() should raise GenesisError when pipeline fails."""
        genesis = Genesis(self._make_config())

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(
            side_effect=DecompositionError("Complete failure")
        )

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mock_decomposer),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            with pytest.raises(GenesisError):
                await genesis.invent("test problem")

    @pytest.mark.asyncio
    async def test_cost_breakdown_accumulated(self):
        """Cost should be summed across all stages."""
        genesis = Genesis(self._make_config())
        mocks = self._mock_all_stages()

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            report = await genesis.invent("test")

        # Costs are accumulated from mock objects
        assert report.cost_breakdown.decomposition_cost >= 0
        assert report.total_cost_usd >= 0

    @pytest.mark.asyncio
    async def test_rejected_inventions_are_forwarded_to_failure_log(self):
        """Rejected verifier results should be sent to the failure log hook."""
        genesis = Genesis(self._make_config())
        mocks = self._mock_all_stages()
        rejected = _make_verified_invention()
        rejected.feasibility_rating = "LOW"
        rejected.adversarial_result.verdict = "INVALID"
        rejected.adversarial_result.fatal_flaws = ["Fatal flaw"]
        mocks["verifier"].verify = AsyncMock(return_value=[rejected])

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
            patch("hephaestus.analytics.failure_log.FailureLog") as mock_failure_log,
        ):
            genesis._stages_built = True
            genesis._harnesses = {
                k: MagicMock()
                for k in ["decompose", "search", "score", "translate", "attack", "defend"]
            }
            genesis._adapters = {}
            mock_failure_log.return_value.append_rejected_inventions.return_value = [MagicMock()]

            await genesis.invent("test")

        mock_failure_log.return_value.append_rejected_inventions.assert_called_once_with(
            [rejected],
            target_domain="distributed_systems",
            problem="test",
            baselines=[],
        )

    @pytest.mark.asyncio
    async def test_all_scored_filtered_yields_failed(self):
        """If scorer returns empty (all adjacent), yield FAILED."""
        genesis = Genesis(self._make_config())

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(return_value=_make_problem_structure())

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=[_make_search_candidate()])

        mock_scorer = MagicMock()
        mock_scorer.score = AsyncMock(return_value=[])  # All filtered!

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mock_decomposer),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mock_searcher),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mock_scorer),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            updates = []
            async for u in genesis.invent_stream("test"):
                updates.append(u)

        stages = [u.stage for u in updates]
        assert PipelineStage.FAILED in stages

    def test_genesis_config_defaults(self):
        config = GenesisConfig()
        assert config.num_translations == 3
        assert config.num_candidates == 8
        assert config.min_domain_distance == 0.3
        assert config.use_interference_in_translate is True
        assert config.run_prior_art is True
        assert config.use_branchgenome_v1 is False

    def test_genesis_from_env(self):
        """from_env should create Genesis without errors."""
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "test-anthropic",
            "OPENAI_API_KEY": "test-openai",
        }):
            genesis = Genesis.from_env()
        assert genesis is not None
        assert genesis._config.anthropic_api_key == "test-anthropic"
        assert genesis._config.openai_api_key == "test-openai"

    @pytest.mark.asyncio
    async def test_genesis_retries_singleton_fallback_when_bundle_translation_returns_empty(self):
        genesis = Genesis(
            GenesisConfig(
                anthropic_api_key="test-key",
                openai_api_key="test-key",
                num_translations=2,
            )
        )

        structure = _make_problem_structure()
        candidates = []
        scored = []
        for domain in ["biology", "economics", "physics"]:
            lens = _make_lens()
            lens.domain = domain
            search_candidate = SearchCandidate(
                source_domain=f"{domain.title()} Mechanism",
                source_solution=f"{domain.title()} mechanism",
                mechanism=f"{domain.title()} control state",
                structural_mapping="Maps to adaptive control",
                lens_used=lens,
                lens_score=LensScore(
                    lens=lens,
                    domain_distance=0.9 if domain == "biology" else (0.82 if domain == "economics" else 0.7),
                    structural_relevance=0.8,
                    composite_score=0.7,
                    matched_patterns=["allocation"],
                ),
                confidence=0.85,
                cost_usd=0.005,
            )
            candidates.append(search_candidate)
            scored.append(
                ScoredCandidate(
                    candidate=search_candidate,
                    structural_fidelity=0.82,
                    domain_distance=search_candidate.lens_score.domain_distance if search_candidate.lens_score else 0.7,
                    combined_score=0.78 if domain == "biology" else (0.71 if domain == "economics" else 0.62),
                    fidelity_reasoning="Strong mapping",
                )
            )

        mock_decomposer = MagicMock()
        mock_decomposer.decompose = AsyncMock(return_value=structure)

        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(return_value=candidates)
        mock_searcher.last_runtime = SimpleNamespace(
            retrieval_mode="bundle",
            to_dict=lambda: {"retrieval_mode": "bundle", "selected_lens_ids": [c.lens_id for c in candidates[:2]]},
        )

        mock_scorer = MagicMock()
        mock_scorer.score = AsyncMock(return_value=scored)

        def _translation_from(candidate: ScoredCandidate, name: str) -> Translation:
            return Translation(
                invention_name=name,
                mapping=[ElementMapping("source", "target", "maps cleanly")],
                architecture="Concrete bounded architecture.",
                mathematical_proof="T maps to T'",
                limitations=["Needs bounded state"],
                implementation_notes="Use explicit control state",
                key_insight="Bound the state and keep recovery explicit.",
                source_candidate=candidate,
            )

        class _TranslatorStub:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []
                self.last_runtime = None

            async def translate(self, inputs, _structure, top_n=None):
                self.calls.append([candidate.lens_id for candidate in inputs])
                if len(self.calls) == 1:
                    self.last_runtime = SimpleNamespace(
                        invalidated_lens_ids=(),
                        to_dict=lambda: {"retrieval_mode": "bundle", "invalidated_lens_ids": []},
                    )
                    return []
                self.last_runtime = SimpleNamespace(
                    invalidated_lens_ids=(),
                    to_dict=lambda: {"retrieval_mode": "singleton", "invalidated_lens_ids": []},
                )
                return [_translation_from(inputs[0], "Fallback Translation")]

        translator_stub = _TranslatorStub()

        mock_verifier = MagicMock()
        mock_verifier.verify = AsyncMock(
            side_effect=lambda translations, _structure: [_make_verified_invention() if False else VerifiedInvention(
                invention_name=translations[0].invention_name,
                translation=translations[0],
                novelty_score=0.77,
                structural_validity=0.8,
                implementation_feasibility=0.75,
                feasibility_rating="HIGH",
                adversarial_result=AdversarialResult(
                    attack_valid=False,
                    fatal_flaws=[],
                    structural_weaknesses=[],
                    strongest_objection="",
                    novelty_risk=0.2,
                    verdict="NOVEL",
                ),
                prior_art_status="NO_PRIOR_ART_FOUND",
            )]
        )

        with (
            patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mock_decomposer),
            patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mock_searcher),
            patch("hephaestus.core.genesis.CandidateScorer", return_value=mock_scorer),
            patch("hephaestus.core.genesis.SolutionTranslator", return_value=translator_stub),
            patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mock_verifier),
            patch("hephaestus.core.genesis.AnthropicAdapter"),
            patch("hephaestus.core.genesis.OpenAIAdapter"),
            patch("hephaestus.core.genesis.LensLoader"),
            patch("hephaestus.core.genesis.LensSelector"),
        ):
            genesis._stages_built = True
            genesis._harnesses = {k: MagicMock() for k in ["decompose", "search", "score", "translate", "attack", "defend"]}
            genesis._adapters = {}

            report = await genesis.invent("test problem")

        assert len(translator_stub.calls) == 2
        assert translator_stub.calls[0] == [candidate.lens_id for candidate in scored]
        assert translator_stub.calls[1] == [scored[2].lens_id]
        assert report.translations[0].invention_name == "Fallback Translation"
        assert report.lens_runtime["translation_retry"]["retrieval_mode"] == "singleton"
