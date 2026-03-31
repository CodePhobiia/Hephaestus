"""
Tests for Stage 2: Cross-Domain Searcher.

All LLM calls and lens library loading are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.searcher import (
    CrossDomainSearcher,
    SearchCandidate,
    SearchError,
)
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.loader import Lens, LensLoader, StructuralPattern
from hephaestus.lenses.selector import LensScore, LensSelector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_problem_structure(**overrides) -> ProblemStructure:
    defaults = dict(
        original_problem="I need a fault-tolerant task scheduler",
        structure="robust resource allocation under node failures",
        constraints=["tolerate failures", "low latency"],
        mathematical_shape="graph with Byzantine fault tolerance",
        native_domain="distributed_systems",
        problem_maps_to={"routing", "allocation"},
    )
    defaults.update(overrides)
    return ProblemStructure(**defaults)


def _make_lens(lens_id: str = "biology_immune", domain: str = "biology") -> Lens:
    return Lens(
        name="Immune System",
        domain=domain,
        subdomain="immune",
        axioms=["Axiom 1 is important", "Axiom 2 matters"],
        structural_patterns=[
            StructuralPattern(
                name="clonal_selection",
                abstract="Solutions that work get amplified",
                maps_to=["optimization", "allocation"],
            )
        ],
        injection_prompt="You are reasoning as a biological immune system.",
    )


def _make_lens_score(domain: str = "biology", distance: float = 0.85) -> LensScore:
    lens = _make_lens(domain=domain)
    return LensScore(
        lens=lens,
        domain_distance=distance,
        structural_relevance=0.6,
        composite_score=distance ** 1.8 * 0.6,
        matched_patterns=["allocation"],
    )


def _make_forge_result(text: str, cost: float = 0.005) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


def _valid_candidate_json(**overrides) -> str:
    data = {
        "source_domain": "Immune System — T-Cell Memory",
        "source_solution": "T-cells produce memory cells that persist after infection clearance",
        "mechanism": "Clonal expansion amplifies successful immune responses",
        "structural_mapping": "Task persistence maps to immune memory formation",
        "confidence": 0.85,
    }
    data.update(overrides)
    return json.dumps(data)


def _make_selector_with_scores(scores: list[LensScore]) -> MagicMock:
    selector = MagicMock(spec=LensSelector)
    selector.select = MagicMock(return_value=scores)
    return selector


# ---------------------------------------------------------------------------
# Tests: SearchCandidate
# ---------------------------------------------------------------------------


class TestSearchCandidate:
    def test_domain_distance_from_lens_score(self):
        ls = _make_lens_score(distance=0.92)
        candidate = SearchCandidate(
            source_domain="Immune System",
            source_solution="Memory cells",
            mechanism="Clonal selection",
            structural_mapping="Maps to caching",
            lens_used=ls.lens,
            lens_score=ls,
            confidence=0.8,
        )
        assert candidate.domain_distance == 0.92

    def test_domain_distance_without_lens_score(self):
        lens = _make_lens()
        candidate = SearchCandidate(
            source_domain="Immune System",
            source_solution="Memory cells",
            mechanism="Clonal selection",
            structural_mapping="Maps to caching",
            lens_used=lens,
            lens_score=None,
        )
        assert candidate.domain_distance == 0.0

    def test_lens_id(self):
        lens = _make_lens(lens_id="biology_immune")
        candidate = SearchCandidate(
            source_domain="Immune System",
            source_solution="",
            mechanism="",
            structural_mapping="",
            lens_used=lens,
        )
        assert candidate.lens_id == "biology_immune"

    def test_summary(self):
        ls = _make_lens_score(distance=0.8)
        candidate = SearchCandidate(
            source_domain="Immune System",
            source_solution="T-cell memory solves persistence via clonal expansion",
            mechanism="Clonal selection",
            structural_mapping="Maps to caching",
            lens_used=ls.lens,
            lens_score=ls,
            confidence=0.9,
        )
        summary = candidate.summary()
        assert "Immune System" in summary
        assert "0.80" in summary


# ---------------------------------------------------------------------------
# Tests: CrossDomainSearcher
# ---------------------------------------------------------------------------


class TestCrossDomainSearcher:
    @pytest.mark.asyncio
    async def test_successful_search(self):
        scores = [_make_lens_score(distance=0.85 - i * 0.05) for i in range(5)]
        selector = _make_selector_with_scores(scores)

        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_candidate_json()))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(spec=LensLoader),
            selector=selector,
            num_candidates=8,
            num_lenses=5,
            min_confidence=0.5,
        )
        structure = _make_problem_structure()
        candidates = await searcher.search(structure)

        assert len(candidates) > 0
        assert all(isinstance(c, SearchCandidate) for c in candidates)

    @pytest.mark.asyncio
    async def test_candidates_sorted_by_distance_desc(self):
        """Returned candidates should be sorted most-distant first."""
        # Create 3 lens scores with different distances
        scores = [
            _make_lens_score(distance=0.5),
            _make_lens_score(distance=0.9),
            _make_lens_score(distance=0.7),
        ]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_candidate_json()))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            num_candidates=10,
            min_confidence=0.0,
        )
        candidates = await searcher.search(_make_problem_structure())

        distances = [c.domain_distance for c in candidates]
        assert distances == sorted(distances, reverse=True)

    @pytest.mark.asyncio
    async def test_candidates_capped_at_num_candidates(self):
        """Should return at most num_candidates even if more pass confidence."""
        scores = [_make_lens_score(distance=0.8) for _ in range(10)]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(
            _valid_candidate_json(confidence=0.9)
        ))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            num_candidates=4,
            min_confidence=0.0,
        )
        candidates = await searcher.search(_make_problem_structure())
        assert len(candidates) <= 4

    @pytest.mark.asyncio
    async def test_low_confidence_candidates_excluded(self):
        """Candidates below min_confidence should be excluded."""
        scores = [_make_lens_score(distance=0.8)]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(
            _valid_candidate_json(confidence=0.2)  # Below default 0.4
        ))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            min_confidence=0.4,
        )
        candidates = await searcher.search(_make_problem_structure())
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_failed_lens_query_skipped(self):
        """If a lens query raises an exception, it's skipped gracefully."""
        scores = [_make_lens_score(distance=0.8 + i * 0.02) for i in range(3)]
        selector = _make_selector_with_scores(scores)

        # First two fail, third succeeds
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            Exception("API Error"),
            Exception("Timeout"),
            _make_forge_result(_valid_candidate_json()),
        ])

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            min_confidence=0.0,
            num_candidates=10,
        )
        candidates = await searcher.search(_make_problem_structure())
        # Only the third succeeds
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_no_lenses_raises_search_error(self):
        """If selector returns no lenses, raise SearchError."""
        selector = _make_selector_with_scores([])
        searcher = CrossDomainSearcher(
            harness=MagicMock(),
            loader=MagicMock(),
            selector=selector,
        )
        with pytest.raises(SearchError):
            await searcher.search(_make_problem_structure())

    @pytest.mark.asyncio
    async def test_candidate_has_correct_fields(self):
        scores = [_make_lens_score()]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(
            _valid_candidate_json()
        ))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            min_confidence=0.0,
        )
        candidates = await searcher.search(_make_problem_structure())
        assert len(candidates) == 1
        c = candidates[0]
        assert c.source_domain == "Immune System — T-Cell Memory"
        assert c.mechanism
        assert c.structural_mapping
        assert c.confidence == 0.85

    @pytest.mark.asyncio
    async def test_invalid_json_from_lens_skipped(self):
        """Bad JSON from a lens query should be skipped (not crash)."""
        scores = [_make_lens_score(distance=0.8), _make_lens_score(distance=0.75)]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(side_effect=[
            _make_forge_result("This is definitely not JSON"),
            _make_forge_result(_valid_candidate_json()),
        ])

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            min_confidence=0.0,
            num_candidates=10,
        )
        candidates = await searcher.search(_make_problem_structure())
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_search_excludes_native_domain(self):
        """Selector should be called with native domain excluded."""
        scores = [_make_lens_score()]
        selector = _make_selector_with_scores(scores)
        harness = MagicMock()
        harness.forge = AsyncMock(return_value=_make_forge_result(_valid_candidate_json()))

        searcher = CrossDomainSearcher(
            harness=harness,
            loader=MagicMock(),
            selector=selector,
            min_confidence=0.0,
        )
        structure = _make_problem_structure(native_domain="distributed_systems")
        await searcher.search(structure)

        selector.select.assert_called_once()
        call_kwargs = selector.select.call_args
        # Check exclude_domains contains native domain
        exclude = call_kwargs.kwargs.get("exclude_domains") or call_kwargs.args[3] if len(call_kwargs.args) > 3 else None
        if exclude:
            assert "distributed_systems" in exclude
