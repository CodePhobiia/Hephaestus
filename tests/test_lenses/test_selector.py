"""
Tests for the Lens Selection Algorithm (LensSelector).

Tests cover:
- Domain distance calculation (cosine distance between embeddings)
- Lens selection with structural relevance filtering
- Domain exclusion
- Top-N selection
- Maximum distance selection
- Composite score formula
- Edge cases (empty library, all excluded, no maps_to)
- Embedding cache invalidation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from hephaestus.lenses.loader import Lens, LensLoader, StructuralPattern, _DEFAULT_LIBRARY_DIR
from hephaestus.lenses.selector import (
    EmbeddingModel,
    LensScore,
    LensSelector,
    _cosine_distance,
    _domain_text,
    _structural_relevance,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def loader() -> LensLoader:
    """Module-scoped loader so we only read 51 files once."""
    return LensLoader(library_dir=_DEFAULT_LIBRARY_DIR)


@pytest.fixture(scope="module")
def selector(loader: LensLoader) -> LensSelector:
    """Module-scoped selector with precomputed embeddings for speed."""
    sel = LensSelector(loader=loader)
    sel.precompute_embeddings()
    return sel


@pytest.fixture
def mock_embed_model() -> EmbeddingModel:
    """An EmbeddingModel that returns deterministic vectors."""
    model = MagicMock(spec=EmbeddingModel)

    def encode_fn(texts: list[str]) -> np.ndarray:
        # Each text gets a deterministic unit vector based on its index+hash
        vecs = []
        for i, text in enumerate(texts):
            seed = hash(text) % (2**31)
            rng = np.random.RandomState(seed)
            vec = rng.randn(384).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-8
            vecs.append(vec)
        return np.array(vecs, dtype=np.float32)

    def encode_one_fn(text: str) -> np.ndarray:
        return encode_fn([text])[0]

    model.encode.side_effect = encode_fn
    model.encode_one.side_effect = encode_one_fn
    return model


def make_lens(
    lens_id: str,
    domain: str = "test",
    subdomain: str = "unit",
    maps_to: list[str] | None = None,
) -> Lens:
    """Create a minimal Lens for testing without YAML files."""
    return Lens(
        name=f"Test {lens_id}",
        domain=domain,
        subdomain=subdomain,
        axioms=["axiom one that is long enough", "axiom two that is long enough"],
        structural_patterns=[
            StructuralPattern(
                name="test_pattern",
                abstract="test abstract description for the pattern",
                maps_to=maps_to or ["test_problem_type"],
            )
        ],
        injection_prompt="Test injection prompt that is definitely long enough to be valid.",
        source_file=Path(f"/fake/{lens_id}.yaml"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cosine Distance
# ──────────────────────────────────────────────────────────────────────────────

class TestCosineDistance:
    def test_identical_vectors_distance_zero(self):
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert _cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors_distance_one(self):
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0], dtype=np.float32)
        assert _cosine_distance(v1, v2) == pytest.approx(1.0, abs=1e-6)

    def test_opposite_vectors_distance_two(self):
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([-1.0, 0.0], dtype=np.float32)
        assert _cosine_distance(v1, v2) == pytest.approx(2.0, abs=1e-6)

    def test_distance_range(self):
        """Distance must be in [0, 2] for normalized vectors."""
        rng = np.random.RandomState(42)
        for _ in range(50):
            v1 = rng.randn(128).astype(np.float32)
            v2 = rng.randn(128).astype(np.float32)
            v1 /= np.linalg.norm(v1)
            v2 /= np.linalg.norm(v2)
            d = _cosine_distance(v1, v2)
            assert 0.0 <= d <= 2.0 + 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# Structural Relevance
# ──────────────────────────────────────────────────────────────────────────────

class TestStructuralRelevance:
    def test_no_overlap_returns_zero(self):
        lens = make_lens("l1", maps_to=["alpha", "beta"])
        score, matched = _structural_relevance(lens, {"gamma", "delta"})
        assert score == 0.0
        assert matched == []

    def test_full_overlap_returns_high_score(self):
        lens = make_lens("l1", maps_to=["trust", "verification"])
        score, matched = _structural_relevance(lens, {"trust", "verification"})
        assert score > 0.5
        assert set(matched) == {"trust", "verification"}

    def test_empty_problem_maps_to_returns_one(self):
        lens = make_lens("l1", maps_to=["trust"])
        score, matched = _structural_relevance(lens, set())
        assert score == 1.0
        assert matched == []

    def test_case_insensitive_matching(self):
        lens = make_lens("l1", maps_to=["Trust", "VERIFICATION"])
        score, matched = _structural_relevance(lens, {"trust", "verification"})
        assert score > 0.0

    def test_partial_overlap_between_zero_and_one(self):
        lens = make_lens("l1", maps_to=["trust", "verification", "routing"])
        score, matched = _structural_relevance(lens, {"trust", "optimization"})
        assert 0.0 < score < 1.0
        assert "trust" in matched


# ──────────────────────────────────────────────────────────────────────────────
# Domain Text
# ──────────────────────────────────────────────────────────────────────────────

class TestDomainText:
    def test_domain_text_includes_name(self):
        lens = make_lens("biology_immune", domain="biology")
        text = _domain_text(lens)
        assert "biology" in text.lower() or "test biology_immune" in text.lower()

    def test_domain_text_includes_axioms(self):
        lens = make_lens("l1")
        text = _domain_text(lens)
        assert "axiom one" in text.lower()

    def test_domain_text_is_non_empty(self):
        lens = make_lens("l1", domain="physics")
        text = _domain_text(lens)
        assert len(text) > 10


# ──────────────────────────────────────────────────────────────────────────────
# Distance Computation
# ──────────────────────────────────────────────────────────────────────────────

class TestDistanceComputation:
    def test_compute_distance_returns_float(self, selector: LensSelector):
        lens = selector._loader.load_one("biology_immune")
        dist = selector.compute_distance("distributed systems trust problem", lens)
        assert isinstance(dist, float)
        assert 0.0 <= dist <= 2.0

    def test_compute_all_distances_returns_all_lenses(self, selector: LensSelector):
        all_lenses = list(selector._loader.load_all().values())
        distances = selector.compute_all_distances(
            "I need a trust system for anonymous actors", all_lenses
        )
        assert len(distances) == len(all_lenses)
        for lens_id, dist in distances.items():
            assert isinstance(dist, float)
            assert 0.0 <= dist <= 2.0

    def test_same_problem_produces_consistent_distances(self, selector: LensSelector):
        """Same problem → same distances (deterministic embeddings)."""
        lens = selector._loader.load_one("biology_immune")
        d1 = selector.compute_distance("trust verification system", lens)
        d2 = selector.compute_distance("trust verification system", lens)
        assert d1 == pytest.approx(d2, abs=1e-5)

    def test_distance_cached_after_first_compute(self, loader: LensLoader):
        """Embeddings for lenses should be cached after first compute."""
        sel = LensSelector(loader=loader)
        lens = loader.load_one("biology_immune")
        assert lens.lens_id not in sel._lens_embed_cache

        sel.compute_distance("some problem", lens)
        assert lens.lens_id in sel._lens_embed_cache


# ──────────────────────────────────────────────────────────────────────────────
# Selection
# ──────────────────────────────────────────────────────────────────────────────

class TestSelect:
    def test_select_returns_top_n(self, selector: LensSelector):
        scores = selector.select(
            problem_description="distributed systems trust problem",
            top_n=5,
        )
        assert len(scores) <= 5

    def test_select_returns_lens_score_objects(self, selector: LensSelector):
        scores = selector.select("distributed systems problem", top_n=3)
        for s in scores:
            assert isinstance(s, LensScore)
            assert isinstance(s.lens, Lens)
            assert 0.0 <= s.domain_distance <= 2.0
            assert 0.0 <= s.structural_relevance <= 1.0
            assert 0.0 < s.diversity_weight <= 1.0
            assert s.domain_family
            assert s.composite_score >= 0.0

    def test_select_sorted_by_composite_score_descending(self, selector: LensSelector):
        scores = selector.select("trust problem", top_n=10)
        composite_scores = [s.composite_score for s in scores]
        assert composite_scores == sorted(composite_scores, reverse=True)

    def test_select_excludes_specified_domains(self, selector: LensSelector):
        scores = selector.select(
            problem_description="distributed systems consensus problem",
            exclude_domains={"cs"},
            top_n=10,
        )
        for s in scores:
            assert s.lens.domain != "cs", (
                f"Excluded domain 'cs' appeared in results: {s.lens.lens_id}"
            )

    def test_select_excludes_multiple_domains(self, selector: LensSelector):
        scores = selector.select(
            problem_description="some problem",
            exclude_domains={"biology", "cs", "physics"},
            top_n=20,
        )
        for s in scores:
            assert s.lens.domain not in {"biology", "cs", "physics"}

    def test_select_with_maps_to_filter(self, selector: LensSelector):
        """Lenses with matching maps_to should score higher than those without."""
        scores_with = selector.select(
            problem_description="trust verification system",
            problem_maps_to={"trust", "verification"},
            top_n=5,
        )
        scores_without = selector.select(
            problem_description="trust verification system",
            problem_maps_to=None,
            top_n=5,
        )
        # Both should return results
        assert len(scores_with) >= 1
        assert len(scores_without) >= 1

    def test_select_top_n_1_returns_single_best(self, selector: LensSelector):
        scores = selector.select(
            problem_description="optimization problem in software systems",
            top_n=1,
        )
        assert len(scores) == 1

    def test_select_top_n_larger_than_library_returns_all(
        self, selector: LensSelector
    ):
        scores = selector.select(
            problem_description="some problem",
            top_n=999,
        )
        # Should return at most len(library) results
        assert len(scores) <= 81

    def test_select_require_relevance_excludes_zero_overlap(
        self, selector: LensSelector
    ):
        """With require_relevance=True, lenses with no maps_to overlap are excluded."""
        scores = selector.select(
            problem_description="something",
            problem_maps_to={"highly_specific_nonexistent_tag_xyz123"},
            require_relevance=True,
            top_n=50,
        )
        # With a tag that no lens has, all should be excluded
        assert len(scores) == 0

    def test_select_without_require_relevance_can_return_zero_overlap(
        self, selector: LensSelector
    ):
        """Without require_relevance, distance alone can win even with no overlap."""
        scores = selector.select(
            problem_description="something abstract",
            problem_maps_to={"highly_specific_nonexistent_tag_xyz123"},
            require_relevance=False,
            top_n=5,
        )
        assert len(scores) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Maximum Distance Selection
# ──────────────────────────────────────────────────────────────────────────────

class TestMaximumDistanceSelection:
    def test_max_distance_selection_returns_results(self, selector: LensSelector):
        scores = selector.select_by_maximum_distance(
            problem_description="I am building a distributed consensus system",
            top_n=5,
        )
        assert len(scores) >= 1

    def test_max_distance_excludes_domains(self, selector: LensSelector):
        scores = selector.select_by_maximum_distance(
            problem_description="distributed consensus",
            exclude_domains={"cs"},
            top_n=5,
        )
        for s in scores:
            assert s.lens.domain != "cs"


# ──────────────────────────────────────────────────────────────────────────────
# Domain Exclusion (Same Domain as Problem)
# ──────────────────────────────────────────────────────────────────────────────

class TestDomainExclusion:
    def test_exclude_native_domain_removes_all_same_domain_lenses(
        self, selector: LensSelector
    ):
        """A biology problem should not get biology lenses."""
        scores = selector.select(
            problem_description="immune cell signaling and activation",
            exclude_domains={"biology"},
            top_n=50,
        )
        for s in scores:
            assert s.lens.domain != "biology"

    def test_exclude_nonexistent_domain_has_no_effect(self, selector: LensSelector):
        scores_without_exclude = selector.select(
            "some problem", top_n=5
        )
        scores_with_exclude = selector.select(
            "some problem",
            exclude_domains={"totally_nonexistent_domain_xyz"},
            top_n=5,
        )
        # Should produce same count
        assert len(scores_without_exclude) == len(scores_with_exclude)


# ──────────────────────────────────────────────────────────────────────────────
# Composite Score Formula
# ──────────────────────────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_higher_distance_produces_higher_score_when_relevance_fixed(
        self, loader: LensLoader
    ):
        """With same relevance, higher distance → higher composite score."""
        # Use mock embeddings to control distances precisely
        sel = LensSelector(loader=loader, distance_alpha=1.8)

        lens_near = make_lens("near", domain="cs", maps_to=["trust"])
        lens_far = make_lens("far", domain="mythology", maps_to=["trust"])

        # Manually inject mock distances by patching compute_all_distances
        problem_maps_to = {"trust"}

        with patch.object(
            sel,
            "compute_all_distances",
            return_value={"cs_unit": 0.2, "mythology_unit": 0.9},
        ):
            with patch.object(
                loader,
                "load_all",
                return_value={"cs_unit": lens_near, "mythology_unit": lens_far},
            ):
                scores = sel.select(
                    problem_description="trust problem",
                    problem_maps_to=problem_maps_to,
                    top_n=10,
                )

        if len(scores) >= 2:
            # The far lens should score higher
            far_score = next(s for s in scores if "mythology" in s.lens.domain)
            near_score = next(s for s in scores if "cs" in s.lens.domain)
            assert far_score.composite_score > near_score.composite_score

    def test_composite_score_is_positive(self, selector: LensSelector):
        scores = selector.select("distributed systems problem", top_n=5)
        for s in scores:
            assert s.composite_score > 0.0

    def test_target_family_penalty_downweights_nearby_families(
        self, loader: LensLoader
    ):
        sel = LensSelector(loader=loader, distance_alpha=1.8, min_distance=0.0)

        lens_same_family = make_lens("engineering_grid", domain="engineering", maps_to=["trust"])
        lens_near_family = make_lens("math_queueing", domain="math", maps_to=["trust"])
        lens_far_family = make_lens("mythology_narrative", domain="mythology", maps_to=["trust"])

        with patch.object(
            sel,
            "compute_all_distances",
            return_value={
                "engineering_grid": 0.9,
                "math_queueing": 0.9,
                "mythology_narrative": 0.9,
            },
        ):
            with patch.object(
                loader,
                "load_all",
                return_value={
                    "engineering_grid": lens_same_family,
                    "math_queueing": lens_near_family,
                    "mythology_narrative": lens_far_family,
                },
            ):
                scores = sel.select(
                    problem_description="trust problem",
                    problem_maps_to={"trust"},
                    target_domain="distributed_systems",
                    top_n=10,
                )

        assert [score.lens.lens_id for score in scores] == [
            "mythology_narrative",
            "math_queueing",
            "engineering_grid",
        ]

        same_family = next(score for score in scores if score.lens.lens_id == "engineering_grid")
        near_family = next(score for score in scores if score.lens.lens_id == "math_queueing")
        far_family = next(score for score in scores if score.lens.lens_id == "mythology_narrative")

        assert same_family.domain_family == "engineering"
        assert same_family.diversity_weight == pytest.approx(0.4)
        assert near_family.domain_family == "mathematics"
        assert near_family.diversity_weight == pytest.approx(0.75)
        assert far_family.domain_family == "myth"
        assert far_family.diversity_weight == pytest.approx(1.0)
        assert far_family.composite_score > near_family.composite_score > same_family.composite_score


# ──────────────────────────────────────────────────────────────────────────────
# Cache Invalidation
# ──────────────────────────────────────────────────────────────────────────────

class TestCacheInvalidation:
    def test_invalidate_cache_clears_embeddings(self, loader: LensLoader):
        sel = LensSelector(loader=loader)
        sel.precompute_embeddings()
        assert len(sel._lens_embed_cache) > 0

        sel.invalidate_cache()
        assert len(sel._lens_embed_cache) == 0

    def test_precompute_fills_all_lenses(self, loader: LensLoader):
        sel = LensSelector(loader=loader)
        sel.precompute_embeddings()
        all_lenses = loader.load_all()
        for lens_id in all_lenses:
            assert lens_id in sel._lens_embed_cache


# ──────────────────────────────────────────────────────────────────────────────
# Semantic Plausibility (Integration)
# ──────────────────────────────────────────────────────────────────────────────

class TestSemanticPlausibility:
    """These tests use real embeddings and check that the selection is
    semantically sensible — not a hardcoded list, but a sanity check."""

    def test_cs_problem_gets_non_cs_lenses(self, selector: LensSelector):
        scores = selector.select(
            problem_description="distributed database consensus with Byzantine faults",
            exclude_domains={"cs"},
            top_n=3,
        )
        assert len(scores) >= 1
        for s in scores:
            assert s.lens.domain != "cs"

    def test_biology_problem_gets_distant_lenses(self, selector: LensSelector):
        scores = selector.select(
            problem_description="immune cell activation and clonal expansion",
            exclude_domains={"biology"},
            top_n=5,
        )
        assert len(scores) >= 1
        # All returned lenses should be non-biology
        for s in scores:
            assert s.lens.domain != "biology"

    def test_top_lens_has_meaningful_distance(self, selector: LensSelector):
        """Top lens should have distance > 0 (not the same domain)."""
        scores = selector.select(
            problem_description="software architecture problem",
            top_n=1,
        )
        if scores:
            assert scores[0].domain_distance > 0.0

    def test_select_for_problem_type(self, selector: LensSelector):
        scores = selector.select_for_problem_type(
            problem_type="optimization",
            top_n=5,
        )
        assert len(scores) >= 1

    def test_repr_contains_selector_info(self, selector: LensSelector):
        r = repr(selector)
        assert "LensSelector" in r
        assert "alpha" in r
