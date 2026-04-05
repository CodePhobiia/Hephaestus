"""Tests for LintAnalyzer ABC and result types."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.linting.analyzer import (
    ContradictionResult,
    LintAnalyzer,
    ResolvabilityAssessment,
    SourceGapAssessment,
)
from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer

# ---------------------------------------------------------------------------
# Result type tests
# ---------------------------------------------------------------------------


class TestContradictionResult:
    def test_fields(self):
        r = ContradictionResult(
            is_contradictory=True,
            explanation="They disagree",
            confidence=0.9,
        )
        assert r.is_contradictory is True
        assert r.explanation == "They disagree"
        assert r.confidence == 0.9

    def test_false_contradiction(self):
        r = ContradictionResult(
            is_contradictory=False,
            explanation="No conflict",
            confidence=0.1,
        )
        assert r.is_contradictory is False


class TestSourceGapAssessment:
    def test_fields(self):
        r = SourceGapAssessment(
            is_gap=True,
            severity="critical",
            explanation="Only one source",
        )
        assert r.is_gap is True
        assert r.severity == "critical"
        assert r.explanation == "Only one source"

    def test_no_gap(self):
        r = SourceGapAssessment(
            is_gap=False,
            severity="minor",
            explanation="Well supported",
        )
        assert r.is_gap is False
        assert r.severity == "minor"


class TestResolvabilityAssessment:
    def test_fields(self):
        r = ResolvabilityAssessment(
            is_resolvable=True,
            search_query="evidence for X",
            confidence=0.7,
        )
        assert r.is_resolvable is True
        assert r.search_query == "evidence for X"
        assert r.confidence == 0.7

    def test_not_resolvable(self):
        r = ResolvabilityAssessment(
            is_resolvable=False,
            search_query="",
            confidence=0.1,
        )
        assert r.is_resolvable is False


# ---------------------------------------------------------------------------
# ABC contract tests
# ---------------------------------------------------------------------------


class TestLintAnalyzerABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LintAnalyzer()  # type: ignore[abstract]

    def test_mock_is_subclass(self):
        assert issubclass(MockLintAnalyzer, LintAnalyzer)


# ---------------------------------------------------------------------------
# MockLintAnalyzer tests
# ---------------------------------------------------------------------------


class TestMockLintAnalyzer:
    @pytest.fixture
    def analyzer(self) -> MockLintAnalyzer:
        return MockLintAnalyzer()

    async def test_detect_contradictions_opposing_keywords(self, analyzer: MockLintAnalyzer):
        pairs = [("X is not true", "X is true")]
        results = await analyzer.detect_contradictions(pairs)
        assert len(results) == 1
        assert results[0].is_contradictory is True
        assert results[0].confidence == 0.8
        assert isinstance(results[0], ContradictionResult)

    async def test_detect_contradictions_no_opposition(self, analyzer: MockLintAnalyzer):
        pairs = [("X is true", "Y is true")]
        results = await analyzer.detect_contradictions(pairs)
        assert len(results) == 1
        assert results[0].is_contradictory is False
        assert results[0].confidence == 0.2

    async def test_detect_contradictions_both_negated(self, analyzer: MockLintAnalyzer):
        pairs = [("X is not true", "Y is not true")]
        results = await analyzer.detect_contradictions(pairs)
        assert len(results) == 1
        assert results[0].is_contradictory is False

    async def test_detect_contradictions_multiple_pairs(self, analyzer: MockLintAnalyzer):
        pairs = [
            ("A is not right", "A is right"),
            ("B is fine", "B is fine"),
            ("C is safe", "C is not safe"),
        ]
        results = await analyzer.detect_contradictions(pairs)
        assert len(results) == 3
        assert results[0].is_contradictory is True
        assert results[1].is_contradictory is False
        assert results[2].is_contradictory is True

    async def test_detect_contradictions_empty(self, analyzer: MockLintAnalyzer):
        results = await analyzer.detect_contradictions([])
        assert results == []

    async def test_detect_contradictions_explanation_contains_claim_text(
        self, analyzer: MockLintAnalyzer
    ):
        pairs = [("Alpha claim text here", "Beta claim text here")]
        results = await analyzer.detect_contradictions(pairs)
        assert "Alpha claim text here" in results[0].explanation

    async def test_assess_source_gaps_few_sources(self, analyzer: MockLintAnalyzer):
        result = await analyzer.assess_source_gaps("quantum computing", 1, ["claim A"])
        assert result.is_gap is True
        assert result.severity == "moderate"
        assert isinstance(result, SourceGapAssessment)
        assert "quantum computing" in result.explanation

    async def test_assess_source_gaps_sufficient_sources(self, analyzer: MockLintAnalyzer):
        result = await analyzer.assess_source_gaps("topic", 5, ["a", "b", "c"])
        assert result.is_gap is False
        assert result.severity == "minor"

    async def test_assess_source_gaps_threshold_boundary(self, analyzer: MockLintAnalyzer):
        # Exactly 2 sources: not a gap (evidence_count < 2 triggers gap)
        result = await analyzer.assess_source_gaps("topic", 2, ["a", "b"])
        assert result.is_gap is False

    async def test_assess_source_gaps_zero_sources(self, analyzer: MockLintAnalyzer):
        result = await analyzer.assess_source_gaps("topic", 0, [])
        assert result.is_gap is True

    async def test_check_resolvable_few_support(self, analyzer: MockLintAnalyzer):
        result = await analyzer.check_resolvable_by_search("claim X", ["src1"])
        assert result.is_resolvable is True
        assert result.confidence == 0.7
        assert isinstance(result, ResolvabilityAssessment)
        assert "claim X" in result.search_query

    async def test_check_resolvable_sufficient_support(self, analyzer: MockLintAnalyzer):
        result = await analyzer.check_resolvable_by_search("claim X", ["a", "b", "c"])
        assert result.is_resolvable is False
        assert result.confidence == 0.3

    async def test_check_resolvable_threshold_boundary(self, analyzer: MockLintAnalyzer):
        # Exactly 2 supports: not resolvable (len < 2 triggers resolvable)
        result = await analyzer.check_resolvable_by_search("claim X", ["a", "b"])
        assert result.is_resolvable is False

    async def test_check_resolvable_empty_support(self, analyzer: MockLintAnalyzer):
        result = await analyzer.check_resolvable_by_search("claim X", [])
        assert result.is_resolvable is True

    async def test_check_resolvable_search_query_truncated(self, analyzer: MockLintAnalyzer):
        long_claim = "A" * 100
        result = await analyzer.check_resolvable_by_search(long_claim, [])
        # Search query should contain truncated claim (first 50 chars)
        assert len(result.search_query) < len(long_claim) + 20
