"""Tests for diversity scoring."""

from __future__ import annotations

from hephaestus.core.diversity import (
    apply_diversity_rerank,
    compute_diversity,
    compute_text_similarity,
)


class TestTextSimilarity:
    def test_identical(self):
        assert compute_text_similarity("hello world foo", "hello world foo") == 1.0

    def test_no_overlap(self):
        assert compute_text_similarity("alpha beta gamma", "delta epsilon zeta") == 0.0

    def test_partial(self):
        sim = compute_text_similarity("hello world foo bar", "hello world baz qux")
        assert 0.2 < sim < 0.8

    def test_empty(self):
        assert compute_text_similarity("", "hello") == 0.0
        assert compute_text_similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert compute_text_similarity("Hello World", "hello world") == 1.0


class TestComputeDiversity:
    def test_single_candidate(self):
        result = compute_diversity(["A"])
        assert result.mean_similarity == 0.0
        assert result.diversity_bonus == 1.0

    def test_identical_candidates(self):
        result = compute_diversity(["same text here", "same text here"])
        assert result.mean_similarity == 1.0
        assert result.diversity_bonus == 0.0

    def test_diverse_candidates(self):
        result = compute_diversity(
            [
                "Immune system memory cells persist responses",
                "Volcanic eruption pressure release dynamics",
                "Musical counterpoint harmonic resolution",
            ]
        )
        assert result.diversity_bonus > 0.5
        assert len(result.penalty_applied) == 0  # all different enough

    def test_penalty_for_similar(self):
        result = compute_diversity(
            [
                "Load balancing with immune memory cells and rapid recall",
                "Load balancing with immune response and memory recall patterns",
                "Volcanic pressure dynamics for queue management",
            ]
        )
        # First two are similar, third is different
        assert len(result.penalty_applied) >= 1

    def test_custom_text_fn(self):
        items = [{"text": "alpha"}, {"text": "beta"}]
        result = compute_diversity(items, text_fn=lambda x: x["text"])
        assert result.mean_similarity == 0.0


class TestDiversityRerank:
    def test_basic_rerank(self):
        candidates = ["aaa bbb ccc", "aaa bbb ddd", "xxx yyy zzz"]
        scores = [0.9, 0.85, 0.8]
        result = apply_diversity_rerank(candidates, scores)
        # Third candidate should be boosted relative to second (which gets penalized)
        names = [r[0] for r in result]
        assert names[0] == "aaa bbb ccc"  # highest original stays

    def test_empty(self):
        assert apply_diversity_rerank([], []) == []

    def test_penalty_factor(self):
        candidates = ["aaa bbb ccc", "aaa bbb ccc"]  # identical
        scores = [0.9, 0.85]
        result = apply_diversity_rerank(candidates, scores, penalty_factor=0.5)
        # Second should be heavily penalized
        assert result[1][1] < 0.85

    def test_no_penalty_for_diverse(self):
        candidates = ["alpha beta gamma", "delta epsilon zeta"]
        scores = [0.9, 0.8]
        result = apply_diversity_rerank(candidates, scores)
        assert result[0][1] == 0.9
        assert result[1][1] == 0.8  # no penalty
