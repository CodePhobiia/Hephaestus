from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.branchgenome.models import BranchStatus
from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.genesis import Genesis, GenesisConfig
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.core.verifier import AdversarialResult, VerifiedInvention
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="Need a scheduler that keeps working under repeated overload.",
        structure="Adaptive resource allocation under repeated shocks.",
        constraints=["bounded memory", "fast failover"],
        mathematical_shape="feedback control with bounded resources",
        native_domain="distributed_systems",
        problem_maps_to={"allocation", "control"},
        cost_usd=0.01,
    )


def _make_scored(index: int = 0) -> ScoredCandidate:
    lens = Lens(
        name=f"Lens {index}",
        domain="biology",
        subdomain="immune",
        axioms=["Memory persists."],
        structural_patterns=[StructuralPattern("allocation", "Allocate adaptively", ["allocation"])],
        injection_prompt="Reason biologically.",
    )
    lens_score = LensScore(
        lens=lens,
        domain_distance=0.86 - 0.03 * index,
        structural_relevance=0.79,
        composite_score=0.75,
        matched_patterns=["allocation"],
    )
    candidate = SearchCandidate(
        source_domain=f"Immune System {index}",
        source_solution="Clonal memory response",
        mechanism="Successful responses are retained and recalled under later stress.",
        structural_mapping="Retained responders become fast recovery paths.",
        lens_used=lens,
        lens_score=lens_score,
        confidence=0.83,
        cost_usd=0.02,
    )
    return ScoredCandidate(
        candidate=candidate,
        structural_fidelity=0.82 - 0.02 * index,
        domain_distance=lens_score.domain_distance,
        combined_score=0.74 - 0.03 * index,
        mechanism_novelty=0.71,
        strong_mappings=["Retained responders shrink later recovery time."],
        scoring_cost_usd=0.01,
    )


def _make_verified(translation: Translation) -> VerifiedInvention:
    adversarial = AdversarialResult(
        attack_valid=False,
        fatal_flaws=[],
        structural_weaknesses=[],
        strongest_objection="",
        novelty_risk=0.1,
        verdict="NOVEL",
    )
    return VerifiedInvention(
        invention_name=translation.invention_name,
        translation=translation,
        novelty_score=0.86,
        structural_validity=0.83,
        implementation_feasibility=0.79,
        feasibility_rating="HIGH",
        adversarial_result=adversarial,
        prior_art_status="NO_PRIOR_ART_FOUND",
        verification_cost_usd=0.02,
    )


def _mock_stages(translator_inputs: list[list[ScoredCandidate]]) -> dict[str, MagicMock]:
    structure = _make_structure()
    scored = [_make_scored(0), _make_scored(1), _make_scored(2)]
    candidates = [candidate.candidate for candidate in scored]

    decomposer = MagicMock()
    decomposer.decompose = AsyncMock(return_value=structure)

    searcher = MagicMock()
    searcher.search = AsyncMock(return_value=candidates)

    scorer = MagicMock()
    scorer.score = AsyncMock(return_value=scored)

    async def _translate(inputs, structure):
        translator_inputs.append(list(inputs))
        translations: list[Translation] = []
        for idx, source_candidate in enumerate(inputs):
            translations.append(
                Translation(
                    invention_name=f"Translation {idx}",
                    mapping=[ElementMapping("source", "target", "maps cleanly")],
                    architecture="Concrete architecture with bounded decay and fast recovery paths.",
                    mathematical_proof="The control loop preserves the retained state invariant.",
                    limitations=["Requires careful decay tuning."],
                    implementation_notes="Use an explicit bounded retention window.",
                    key_insight="Retain successful recovery paths so repeated shocks recover faster.",
                    source_candidate=source_candidate,
                )
            )
        return translations

    translator = MagicMock()
    translator.translate = AsyncMock(side_effect=_translate)

    async def _verify(translations, structure):
        return [_make_verified(translation) for translation in translations]

    verifier = MagicMock()
    verifier.verify = AsyncMock(side_effect=_verify)

    return {
        "decomposer": decomposer,
        "searcher": searcher,
        "scorer": scorer,
        "translator": translator,
        "verifier": verifier,
    }


def _run_genesis(
    config: GenesisConfig,
    translator_inputs: list[list[ScoredCandidate]],
):
    genesis = Genesis(config)
    mocks = _mock_stages(translator_inputs)

    return genesis, (
        patch("hephaestus.core.genesis.ProblemDecomposer", return_value=mocks["decomposer"]),
        patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=mocks["searcher"]),
        patch("hephaestus.core.genesis.CandidateScorer", return_value=mocks["scorer"]),
        patch("hephaestus.core.genesis.SolutionTranslator", return_value=mocks["translator"]),
        patch("hephaestus.core.genesis.NoveltyVerifier", return_value=mocks["verifier"]),
        patch("hephaestus.core.genesis.AnthropicAdapter"),
        patch("hephaestus.core.genesis.OpenAIAdapter"),
        patch("hephaestus.core.genesis.LensLoader"),
        patch("hephaestus.core.genesis.LensSelector"),
        patch("hephaestus.memory.anti_memory.AntiMemory"),
        patch("hephaestus.analytics.failure_log.FailureLog"),
    )


@pytest.mark.asyncio
async def test_genesis_without_branchgenome_passes_scored_candidates_through() -> None:
    inputs: list[list[ScoredCandidate]] = []
    config = GenesisConfig(
        anthropic_api_key="test",
        openai_api_key="test",
        use_perplexity_research=False,
        run_prior_art=False,
        use_branchgenome_v1=False,
    )
    genesis, patches = _run_genesis(config, inputs)

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10]:
        genesis._stages_built = True
        genesis._harnesses = {key: MagicMock() for key in ["decompose", "search", "score", "translate", "attack", "defend"]}
        genesis._adapters = {}
        report = await genesis.invent("test problem")

    assert len(inputs) == 1
    assert len(inputs[0]) == config.num_translations
    assert not hasattr(inputs[0][0], "branch_genome")
    assert report.branchgenome_metrics == {}


@pytest.mark.asyncio
async def test_genesis_with_branchgenome_promotes_branch_candidates_and_records_metrics(tmp_path) -> None:
    inputs: list[list[ScoredCandidate]] = []
    config = GenesisConfig(
        anthropic_api_key="test",
        openai_api_key="test",
        use_perplexity_research=False,
        run_prior_art=False,
        use_branchgenome_v1=True,
        num_translations=2,
        branchgenome_rejection_ledger_path=str(tmp_path / "branchgenome.jsonl"),
    )
    genesis, patches = _run_genesis(config, inputs)

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10]:
        genesis._stages_built = True
        genesis._harnesses = {key: MagicMock() for key in ["decompose", "search", "score", "translate", "attack", "defend"]}
        genesis._adapters = {}
        report = await genesis.invent("test problem")

    assert len(inputs) == 1
    assert len(inputs[0]) == config.num_translations
    assert hasattr(inputs[0][0], "branch_genome")
    assert report.branchgenome_metrics["branches_seeded"] >= config.num_translations
    assert report.branchgenome_metrics["branches_promoted"] == config.num_translations
    assert report.branchgenome_metrics["branches_recovered"] >= 0
    assert "family_frequency" in report.branchgenome_metrics
    assert "repeated_family_streaks" in report.branchgenome_metrics
    assert "avg_baseline_attractor" in report.branchgenome_metrics
    assert "avg_branch_fatigue" in report.branchgenome_metrics
    assert "avg_future_option_preservation" in report.branchgenome_metrics
    assert report.branchgenome_metrics["promoted_family_patterns"]
    assert report.branchgenome_metrics["promoted_branch_outcomes"]
    first_outcome = next(iter(report.branchgenome_metrics["promoted_branch_outcomes"].values()))
    assert "operator_family_pattern" in first_outcome
    assert "branch_state" in first_outcome
    assert (tmp_path / "branchgenome.jsonl").exists()


@pytest.mark.asyncio
async def test_branchgenome_bundle_invalidation_prunes_invalidated_promoted_branch(tmp_path) -> None:
    config = GenesisConfig(
        anthropic_api_key="test",
        openai_api_key="test",
        use_perplexity_research=False,
        run_prior_art=False,
        use_branchgenome_v1=True,
        num_translations=2,
        branchgenome_rejection_ledger_path=str(tmp_path / "branchgenome.jsonl"),
    )
    genesis = Genesis(config)
    stage_mocks = _mock_stages([])

    translator_calls: list[list[ScoredCandidate]] = []

    class _TranslatorStub:
        def __init__(self) -> None:
            self.last_runtime = None

        async def translate(self, inputs, structure):
            translator_calls.append(list(inputs))
            self.last_runtime = SimpleNamespace(
                invalidated_lens_ids=(inputs[1].lens_id,),
                to_dict=lambda: {
                    "retrieval_mode": "bundle",
                    "invalidated_lens_ids": [inputs[1].lens_id],
                },
            )
            return [
                Translation(
                    invention_name="Guarded Translation",
                    mapping=[ElementMapping("source", "target", "maps cleanly")],
                    architecture="Concrete architecture that preserves bounded recovery.",
                    mathematical_proof="The invariant is preserved.",
                    limitations=["Needs bounded state."],
                    implementation_notes="Retain explicit control state.",
                    key_insight="Keep recovery explicit and bounded.",
                    source_candidate=inputs[0],
                )
            ]

    translator_stub = _TranslatorStub()

    with (
        patch("hephaestus.core.genesis.ProblemDecomposer", return_value=stage_mocks["decomposer"]),
        patch("hephaestus.core.genesis.CrossDomainSearcher", return_value=stage_mocks["searcher"]),
        patch("hephaestus.core.genesis.CandidateScorer", return_value=stage_mocks["scorer"]),
        patch("hephaestus.core.genesis.SolutionTranslator", return_value=translator_stub),
        patch("hephaestus.core.genesis.NoveltyVerifier", return_value=stage_mocks["verifier"]),
        patch("hephaestus.core.genesis.AnthropicAdapter"),
        patch("hephaestus.core.genesis.OpenAIAdapter"),
        patch("hephaestus.core.genesis.LensLoader"),
        patch("hephaestus.core.genesis.LensSelector"),
        patch("hephaestus.memory.anti_memory.AntiMemory"),
        patch("hephaestus.analytics.failure_log.FailureLog"),
    ):
        genesis._stages_built = True
        genesis._harnesses = {key: MagicMock() for key in ["decompose", "search", "score", "translate", "attack", "defend"]}
        genesis._adapters = {}
        await genesis.invent("test problem")

    assert translator_calls
    assert translator_calls[0][1].branch_genome.status == BranchStatus.PRUNED
