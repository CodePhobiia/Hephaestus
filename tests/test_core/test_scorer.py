"""
Tests for Stage 3: Candidate Scorer.

LLM calls and embedding models are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.scorer import (
    CandidateScorer,
    ScoredCandidate,
    ScoringError,
)
from hephaestus.core.searcher import SearchCandidate
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import EmbeddingModel, LensScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_structure(**overrides) -> ProblemStructure:
    defaults = dict(
        original_problem="I need a fault-tolerant system",
        structure="distributed resource allocation under failures",
        constraints=["fault tolerance", "low latency"],
        mathematical_shape="graph with Byzantine fault tolerance",
        native_domain="distributed_systems",
        problem_maps_to={"routing", "allocation"},
    )
    defaults.update(overrides)
    return ProblemStructure(**defaults)


def _make_lens(domain: str = "biology") -> Lens:
    return Lens(
        name="Immune System",
        domain=domain,
        subdomain="immune",
        axioms=["Trust is earned through molecular handshake", "Memory is distributed"],
        structural_patterns=[
            StructuralPattern("clonal", "Amplify solutions that work", ["allocation"]),
        ],
        injection_prompt="You are reasoning as a biological immune system with molecular precision.",
    )


def _make_lens_score(distance: float = 0.85) -> LensScore:
    lens = _make_lens()
    return LensScore(
        lens=lens,
        domain_distance=distance,
        structural_relevance=0.7,
        composite_score=distance ** 1.8 * 0.7,
        matched_patterns=["allocation"],
    )


def _make_candidate(
    source_domain: str = "Immune System",
    confidence: float = 0.8,
    distance: float = 0.85,
) -> SearchCandidate:
    ls = _make_lens_score(distance=distance)
    return SearchCandidate(
        source_domain=source_domain,
        source_solution="T-cell memory solves persistence through clonal expansion",
        mechanism="Successful responses trigger amplification and memory formation",
        structural_mapping="Task persistence maps to immune memory persistence",
        lens_used=ls.lens,
        lens_score=ls,
        confidence=confidence,
        cost_usd=0.005,
    )


def _make_forge_result(text: str, cost: float = 0.003) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


def _valid_fidelity_json(fidelity: float = 0.8) -> str:
    return json.dumps({
        "structural_fidelity": fidelity,
        "fidelity_reasoning": "Strong structural match between immune memory and task persistence",
        "strong_mappings": ["T-cell → task executor", "memory cell → cached result"],
        "weak_mappings": ["No equivalent to MHC presentation"],
    })


def _make_mock_embedding_model(distance: float = 0.8) -> MagicMock:
    """Create a mock embedding model that returns vectors with known cosine distance."""
    embed = MagicMock(spec=EmbeddingModel)
    # Return vectors where first is problem, rest are domain vectors
    # Cosine distance is controlled by dot product
    def encode_side_effect(texts):
        n = len(texts)
        # Problem vector
        problem = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        # Domain vectors at distance `distance` from problem
        cos_sim = 1.0 - distance
        angle_component = np.sqrt(max(0.0, 1.0 - cos_sim ** 2))
        domain = np.array([cos_sim, angle_component, 0.0], dtype=np.float32)
        return np.stack([problem] + [domain] * (n - 1))

    embed.encode = MagicMock(side_effect=encode_side_effect)
    embed.encode_one = MagicMock(return_value=np.array([1.0, 0.0, 0.0], dtype=np.float32))
    return embed


# ---------------------------------------------------------------------------
# Tests: ScoredCandidate
# ---------------------------------------------------------------------------


class TestScoredCandidate:
    def test_delegate_properties(self):
        candidate = _make_candidate(source_domain="Immune System", distance=0.9)
        scored = ScoredCandidate(
            candidate=candidate,
            structural_fidelity=0.8,
            domain_distance=0.9,
            combined_score=0.8 * 0.9 ** 1.5,
        )
        assert scored.source_domain == "Immune System"
        assert scored.mechanism
        assert scored.source_solution

    def test_total_cost(self):
        candidate = _make_candidate()
        candidate.cost_usd = 0.005
        scored = ScoredCandidate(
            candidate=candidate,
            structural_fidelity=0.8,
            domain_distance=0.9,
            combined_score=0.5,
            scoring_cost_usd=0.003,
        )
        assert scored.total_cost_usd() == pytest.approx(0.008)

    def test_combined_score_formula(self):
        """combined_score = fidelity × distance^1.5"""
        fidelity = 0.8
        distance = 0.9
        expected = fidelity * (distance ** 1.5)

        candidate = _make_candidate(distance=distance)
        scored = ScoredCandidate(
            candidate=candidate,
            structural_fidelity=fidelity,
            domain_distance=distance,
            combined_score=expected,
        )
        assert scored.combined_score == pytest.approx(expected)

    def test_summary(self):
        candidate = _make_candidate()
        scored = ScoredCandidate(
            candidate=candidate,
            structural_fidelity=0.75,
            domain_distance=0.88,
            combined_score=0.6,
        )
        summary = scored.summary()
        assert "0.75" in summary
        assert "0.88" in summary
        assert "0.600" in summary


# ---------------------------------------------------------------------------
# Tests: CandidateScorer
# ---------------------------------------------------------------------------


class TestCandidateScorer:
    @pytest.mark.asyncio
    async def test_successful_scoring(self):
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_fidelity_json(0.8)))

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.3,
        )

        candidates = [_make_candidate(distance=0.85)]
        structure = _make_structure()
        result = await scorer.score(candidates, structure)

        assert len(result) == 1
        scored = result[0]
        assert isinstance(scored, ScoredCandidate)
        assert 0.0 <= scored.structural_fidelity <= 1.0
        assert 0.0 <= scored.domain_distance <= 1.0
        assert scored.combined_score > 0.0

    @pytest.mark.asyncio
    async def test_sorted_by_combined_score_desc(self):
        """Results should be sorted by combined_score descending."""
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            _make_forge_result(_valid_fidelity_json(0.4)),  # low fidelity
            _make_forge_result(_valid_fidelity_json(0.9)),  # high fidelity
            _make_forge_result(_valid_fidelity_json(0.7)),  # medium fidelity
        ])

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.0,
        )

        candidates = [
            _make_candidate("Domain A", distance=0.8),
            _make_candidate("Domain B", distance=0.8),
            _make_candidate("Domain C", distance=0.8),
        ]
        result = await scorer.score(candidates, _make_structure())

        scores = [r.combined_score for r in result]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_adjacent_domains_filtered(self):
        """Candidates with distance < min_domain_distance should be excluded."""
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_fidelity_json()))

        embed = _make_mock_embedding_model(distance=0.15)  # Below 0.3 threshold
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.3,
        )

        candidates = [_make_candidate(distance=0.15)]
        result = await scorer.score(candidates, _make_structure())

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        scorer = CandidateScorer(harness=MagicMock(), min_domain_distance=0.3)
        result = await scorer.score([], _make_structure())
        assert result == []

    @pytest.mark.asyncio
    async def test_failed_scoring_uses_fallback(self):
        """If LLM scoring fails for a candidate, use fallback confidence score."""
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=Exception("API error"))

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.3,
        )

        candidates = [_make_candidate(confidence=0.7)]
        result = await scorer.score(candidates, _make_structure())

        # Should fall back rather than drop
        assert len(result) == 1
        assert result[0].structural_fidelity == 0.7  # Uses candidate confidence

    @pytest.mark.asyncio
    async def test_fidelity_clamped_to_0_1(self):
        """Model returning out-of-range fidelity should be clamped."""
        bad_json = json.dumps({"structural_fidelity": 1.5})  # Out of range
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(bad_json))

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.0,
        )

        candidates = [_make_candidate(distance=0.8)]
        result = await scorer.score(candidates, _make_structure())

        assert result[0].structural_fidelity <= 1.0

    @pytest.mark.asyncio
    async def test_scoring_cost_tracked(self):
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(
            _valid_fidelity_json(), cost=0.003
        ))

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.0,
        )

        candidates = [_make_candidate(distance=0.8)]
        result = await scorer.score(candidates, _make_structure())
        assert result[0].scoring_cost_usd == pytest.approx(0.006)

    @pytest.mark.asyncio
    async def test_mechanism_novelty_flows_into_creativity_score(self):
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            _make_forge_result(_valid_fidelity_json(0.8)),
            _make_forge_result(
                json.dumps(
                    {
                        "mechanism_novelty": 0.9,
                        "target_domain_equivalent": "no close equivalent",
                        "novelty_reasoning": "The mechanism is still strange in the target domain.",
                        "would_engineer_reach_for_this": False,
                    }
                )
            ),
        ])

        scorer = CandidateScorer(
            harness=harness,
            embedding_model=_make_mock_embedding_model(distance=0.8),
            min_domain_distance=0.0,
        )

        result = await scorer.score([_make_candidate(distance=0.8)], _make_structure())

        assert result[0].mechanism_novelty == pytest.approx(0.9)
        assert result[0].creativity_score > 0.5
        assert result[0].novelty_vector.mechanism_distance == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_all_adjacent_returns_empty(self):
        """When all candidates are filtered as adjacent, return empty."""
        harness = MagicMock()
        embed = _make_mock_embedding_model(distance=0.05)  # Very close

        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.3,
        )

        candidates = [_make_candidate(distance=0.05) for _ in range(3)]
        result = await scorer.score(candidates, _make_structure())
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json_parsed(self):
        """Fidelity JSON wrapped in markdown fences should be parsed."""
        fidelity_json = _valid_fidelity_json(0.75)
        wrapped = f"```json\n{fidelity_json}\n```"
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(wrapped))

        embed = _make_mock_embedding_model(distance=0.8)
        scorer = CandidateScorer(
            harness=harness,
            embedding_model=embed,
            min_domain_distance=0.0,
        )

        result = await scorer.score([_make_candidate(distance=0.8)], _make_structure())
        assert result[0].structural_fidelity == pytest.approx(0.75)
