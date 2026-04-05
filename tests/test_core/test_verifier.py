"""
Tests for Stage 5: Novelty Verifier.

LLM calls and prior art searches are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.core.verifier import (
    AdversarialResult,
    NoveltyVerifier,
    VerifiedInvention,
)
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_scored_candidate(distance: float = 0.85) -> ScoredCandidate:
    lens = _make_lens()
    ls = LensScore(
        lens=lens,
        domain_distance=distance,
        structural_relevance=0.7,
        composite_score=0.8 * distance**1.5,
        matched_patterns=["allocation"],
    )
    search_candidate = SearchCandidate(
        source_domain="Immune System — T-Cell Memory",
        source_solution="T-cell memory solves persistence through clonal expansion",
        mechanism="Successful immune responses trigger memory cell formation",
        structural_mapping="Task state maps to immune memory",
        lens_used=lens,
        lens_score=ls,
        confidence=0.85,
    )
    return ScoredCandidate(
        candidate=search_candidate,
        structural_fidelity=0.8,
        domain_distance=distance,
        combined_score=0.8 * distance**1.5,
        fidelity_reasoning="Strong match",
        strong_mappings=["T-cell → task"],
        weak_mappings=["No MHC equivalent"],
    )


def _make_translation(invention_name: str = "Immune-Memory Scheduler") -> Translation:
    sc = _make_scored_candidate()
    return Translation(
        invention_name=invention_name,
        mapping=[
            ElementMapping("T-cell receptor", "Task type signature", "Both identify entity type"),
            ElementMapping("Memory cell", "Cached result", "Both persist successful outcomes"),
        ],
        architecture=(
            "The scheduler maintains an immune memory layer that caches successful task "
            "execution patterns. Node failures trigger clonal expansion of healthy nodes."
        ),
        mathematical_proof="T maps to T' under the structural isomorphism",
        limitations=["Requires cache invalidation strategy", "No MHC equivalent"],
        implementation_notes="Use Redis for memory layer",
        key_insight="Immune memory eliminates redundant recognition work",
        source_candidate=sc,
        cost_usd=0.02,
    )


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="I need a fault-tolerant distributed task scheduler",
        structure="Robust resource allocation under node failures",
        constraints=["fault tolerance", "low latency"],
        mathematical_shape="graph with Byzantine fault tolerance",
        native_domain="distributed_systems",
        problem_maps_to={"routing", "allocation"},
    )


def _make_forge_result(text: str, cost: float = 0.005) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


def _valid_attack_json(verdict: str = "NOVEL", has_flaws: bool = False) -> str:
    return json.dumps(
        {
            "attack_valid": has_flaws,
            "fatal_flaws": ["Fundamental mapping breaks under high load"] if has_flaws else [],
            "structural_weaknesses": ["Cache invalidation not addressed"],
            "strongest_objection": "The analogy may not hold under adversarial conditions",
            "novelty_risk": 0.15 if verdict == "NOVEL" else 0.6,
            "verdict": verdict,
        }
    )


def _valid_validity_json(feasibility: str = "HIGH") -> str:
    return json.dumps(
        {
            "structural_validity": 0.85,
            "implementation_feasibility": 0.80,
            "novelty_score": 0.88,
            "feasibility_rating": feasibility,
            "validity_notes": "The structural mapping holds across all major constraints",
            "feasibility_notes": "Implementable with Redis + standard scheduler frameworks",
            "novelty_notes": "No prior art found for this specific immune-scheduler mapping",
            "recommended_next_steps": [
                "Prototype the memory layer with Redis",
                "Benchmark against standard schedulers",
            ],
        }
    )


# ---------------------------------------------------------------------------
# Tests: AdversarialResult
# ---------------------------------------------------------------------------


class TestAdversarialResult:
    def test_creation(self):
        ar = AdversarialResult(
            attack_valid=False,
            fatal_flaws=[],
            structural_weaknesses=["Cache invalidation not addressed"],
            strongest_objection="May not hold under adversarial conditions",
            novelty_risk=0.2,
            verdict="NOVEL",
        )
        assert ar.verdict == "NOVEL"
        assert not ar.attack_valid
        assert ar.novelty_risk == 0.2


# ---------------------------------------------------------------------------
# Tests: VerifiedInvention
# ---------------------------------------------------------------------------


class TestVerifiedInvention:
    def _make_verified(self, verdict="NOVEL", feasibility="HIGH") -> VerifiedInvention:
        ar = AdversarialResult(
            attack_valid=False,
            fatal_flaws=[],
            structural_weaknesses=[],
            strongest_objection="",
            novelty_risk=0.1,
            verdict=verdict,
        )
        return VerifiedInvention(
            invention_name="Immune-Memory Scheduler",
            translation=_make_translation(),
            novelty_score=0.88,
            structural_validity=0.85,
            implementation_feasibility=0.80,
            feasibility_rating=feasibility,
            adversarial_result=ar,
            prior_art_status="NO_PRIOR_ART_FOUND",
        )

    def test_is_viable_true(self):
        inv = self._make_verified(verdict="NOVEL", feasibility="HIGH")
        assert inv.is_viable

    def test_is_viable_false_with_fatal_flaws(self):
        ar = AdversarialResult(
            attack_valid=True,
            fatal_flaws=["Fundamental flaw"],
            structural_weaknesses=[],
            strongest_objection="Fatal",
            novelty_risk=0.8,
            verdict="INVALID",
        )
        inv = VerifiedInvention(
            invention_name="Test",
            translation=_make_translation(),
            novelty_score=0.3,
            structural_validity=0.3,
            implementation_feasibility=0.2,
            feasibility_rating="LOW",
            adversarial_result=ar,
        )
        assert not inv.is_viable

    def test_is_viable_false_with_low_feasibility(self):
        inv = self._make_verified(feasibility="LOW")
        assert not inv.is_viable

    def test_source_domain_delegation(self):
        inv = self._make_verified()
        assert inv.source_domain == "Immune System — T-Cell Memory"

    def test_verdict_delegation(self):
        inv = self._make_verified(verdict="QUESTIONABLE")
        assert inv.verdict == "QUESTIONABLE"

    def test_summary(self):
        inv = self._make_verified()
        s = inv.summary()
        assert "Immune-Memory Scheduler" in s
        assert "novelty=" in s
        assert "feasibility=HIGH" in s


# ---------------------------------------------------------------------------
# Tests: NoveltyVerifier
# ---------------------------------------------------------------------------


class TestNoveltyVerifier:
    @pytest.mark.asyncio
    async def test_successful_verification(self):
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(
            side_effect=[
                _make_forge_result(_valid_attack_json("NOVEL")),
                _make_forge_result(_valid_validity_json("HIGH")),
            ]
        )

        verifier = NoveltyVerifier(
            attack_harness=attack_harness,
            defend_harness=attack_harness,
            run_prior_art=False,
        )

        translations = [_make_translation()]
        result = await verifier.verify(translations, _make_structure())

        assert len(result) == 1
        inv = result[0]
        assert isinstance(inv, VerifiedInvention)
        assert 0.0 <= inv.novelty_score <= 1.0
        assert inv.feasibility_rating in ("HIGH", "MEDIUM", "LOW", "THEORETICAL")

    @pytest.mark.asyncio
    async def test_sorted_by_novelty_score_desc(self):
        """Results should be sorted by novelty_score descending."""
        attack_harness = MagicMock()

        # 3 translations — 6 forge calls total (2 per translation: attack + defend)
        attack_harness.forge = AsyncMock(
            side_effect=[
                # Translation 1: low novelty_risk → high novelty
                _make_forge_result(_valid_attack_json("NOVEL")),
                _make_forge_result(
                    json.dumps(
                        {
                            "structural_validity": 0.9,
                            "implementation_feasibility": 0.9,
                            "feasibility_rating": "HIGH",
                            "validity_notes": "",
                            "feasibility_notes": "",
                            "novelty_notes": "",
                            "recommended_next_steps": [],
                        }
                    )
                ),
                # Translation 2: medium novelty
                _make_forge_result(_valid_attack_json("QUESTIONABLE")),
                _make_forge_result(
                    json.dumps(
                        {
                            "structural_validity": 0.5,
                            "implementation_feasibility": 0.5,
                            "feasibility_rating": "MEDIUM",
                            "validity_notes": "",
                            "feasibility_notes": "",
                            "novelty_notes": "",
                            "recommended_next_steps": [],
                        }
                    )
                ),
                # Translation 3: low novelty
                _make_forge_result(_valid_attack_json("DERIVATIVE")),
                _make_forge_result(
                    json.dumps(
                        {
                            "structural_validity": 0.3,
                            "implementation_feasibility": 0.3,
                            "feasibility_rating": "LOW",
                            "validity_notes": "",
                            "feasibility_notes": "",
                            "novelty_notes": "",
                            "recommended_next_steps": [],
                        }
                    )
                ),
            ]
        )

        verifier = NoveltyVerifier(
            attack_harness=attack_harness,
            run_prior_art=False,
        )

        translations = [_make_translation(f"Invention {i}") for i in range(3)]
        result = await verifier.verify(translations, _make_structure())

        scores = [inv.novelty_score for inv in result]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_empty_translations_returns_empty(self):
        verifier = NoveltyVerifier(
            attack_harness=MagicMock(),
            run_prior_art=False,
        )
        result = await verifier.verify([], _make_structure())
        assert result == []

    @pytest.mark.asyncio
    async def test_failed_verification_gets_fallback(self):
        """Verification failure for one translation should produce fallback, not crash."""
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(side_effect=Exception("API error"))

        verifier = NoveltyVerifier(
            attack_harness=attack_harness,
            run_prior_art=False,
        )

        translations = [_make_translation()]
        result = await verifier.verify(translations, _make_structure())

        assert len(result) == 1
        assert result[0].novelty_score == 0.3  # fallback score

    @pytest.mark.asyncio
    async def test_prior_art_check_graceful_fallback(self):
        """If prior art search fails, verification continues with SEARCH_UNAVAILABLE."""
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(
            side_effect=[
                _make_forge_result(_valid_attack_json("NOVEL")),
                _make_forge_result(_valid_validity_json("HIGH")),
            ]
        )

        verifier = NoveltyVerifier(
            attack_harness=attack_harness,
            run_prior_art=True,
        )

        # Inject a broken prior art searcher
        mock_searcher = MagicMock()
        mock_searcher.search = AsyncMock(side_effect=Exception("Network error"))
        verifier._prior_art_searcher = mock_searcher

        result = await verifier.verify([_make_translation()], _make_structure())

        assert len(result) == 1
        assert result[0].prior_art_status == "SEARCH_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_attaches_grounding_and_risk_reviews(self):
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(
            side_effect=[
                _make_forge_result(_valid_attack_json("NOVEL")),
                _make_forge_result(_valid_validity_json("HIGH")),
            ]
        )

        verifier = NoveltyVerifier(attack_harness=attack_harness, run_prior_art=False)
        verifier._perplexity_client = MagicMock()
        verifier._perplexity_client.ground_invention_report = AsyncMock(
            return_value=MagicMock(summary="Grounded against adjacent systems")
        )
        verifier._perplexity_client.review_implementation_risks = AsyncMock(
            return_value=MagicMock(summary="Main risk is feedback delay")
        )

        result = await verifier.verify([_make_translation()], _make_structure())
        assert result[0].grounding_report is not None
        assert result[0].implementation_risk_review is not None
        assert "Grounding:" in result[0].verification_notes
        assert "Risk review:" in result[0].verification_notes

    @pytest.mark.asyncio
    async def test_novelty_score_penalised_by_fatal_flaws(self):
        """Fatal flaws from adversarial attack should reduce novelty score."""
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(
            side_effect=[
                _make_forge_result(_valid_attack_json("INVALID", has_flaws=True)),
                _make_forge_result(_valid_validity_json("LOW")),
            ]
        )

        verifier = NoveltyVerifier(attack_harness=attack_harness, run_prior_art=False)
        result = await verifier.verify([_make_translation()], _make_structure())

        # Fatal flaws should reduce score significantly
        assert result[0].novelty_score < 0.7

    @pytest.mark.asyncio
    async def test_novelty_score_reduced_by_prior_art(self):
        """POSSIBLE_PRIOR_ART status should reduce novelty score."""
        attack_harness = MagicMock()
        attack_harness.forge = AsyncMock(
            side_effect=[
                _make_forge_result(_valid_attack_json("QUESTIONABLE")),
                _make_forge_result(_valid_validity_json("MEDIUM")),
            ]
        )

        verifier = NoveltyVerifier(attack_harness=attack_harness, run_prior_art=True)

        mock_searcher = MagicMock()
        mock_prior_report = MagicMock()
        mock_prior_report.novelty_status = "POSSIBLE_PRIOR_ART"
        mock_searcher.search = AsyncMock(return_value=mock_prior_report)
        verifier._prior_art_searcher = mock_searcher

        result_novel = NoveltyVerifier._compute_novelty_score(
            verifier,
            attack_result=AdversarialResult(False, [], [], "", 0.2, "NOVEL"),
            structural_validity=0.8,
            prior_art_status="NO_PRIOR_ART_FOUND",
            domain_distance=0.8,
        )
        result_prior_art = NoveltyVerifier._compute_novelty_score(
            verifier,
            attack_result=AdversarialResult(False, [], [], "", 0.2, "NOVEL"),
            structural_validity=0.8,
            prior_art_status="POSSIBLE_PRIOR_ART",
            domain_distance=0.8,
        )

        assert result_prior_art < result_novel

    def test_compute_novelty_score_range(self):
        verifier = NoveltyVerifier(attack_harness=MagicMock(), run_prior_art=False)
        ar = AdversarialResult(False, [], [], "", 0.2, "NOVEL")

        for prior_status in ["NO_PRIOR_ART_FOUND", "POSSIBLE_PRIOR_ART", "SEARCH_UNAVAILABLE"]:
            score = verifier._compute_novelty_score(
                attack_result=ar,
                structural_validity=0.8,
                prior_art_status=prior_status,
                domain_distance=0.85,
            )
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {prior_status}"
