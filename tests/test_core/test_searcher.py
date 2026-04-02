from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.searcher import CrossDomainSearcher
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.bundles import BundleComposer, BundleSelectionResult
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="Need a scheduler that verifies and routes work under repeated failures.",
        structure="Adaptive allocation with explicit verification and bounded recovery.",
        constraints=["bounded latency", "explicit verification", "fast recovery"],
        mathematical_shape="control and allocation under adversarial uncertainty",
        native_domain="distributed_systems",
        problem_maps_to={"allocation", "verification", "control"},
    )


def _make_lens(
    *,
    domain: str,
    subdomain: str,
    name: str,
    maps_to: list[str],
) -> Lens:
    return Lens(
        name=name,
        domain=domain,
        subdomain=subdomain,
        axioms=[
            f"{name} keeps a stable control state under stress.",
            f"{name} uses explicit gating instead of blind routing.",
        ],
        structural_patterns=[
            StructuralPattern(name=f"{name.lower()}-pattern", abstract=f"{name} pattern", maps_to=maps_to)
        ],
        injection_prompt=f"Reason as {name}.",
    )


def _make_score(
    lens: Lens,
    *,
    distance: float,
    relevance: float,
    matched_patterns: list[str],
) -> LensScore:
    return LensScore(
        lens=lens,
        domain_distance=distance,
        structural_relevance=relevance,
        composite_score=distance * relevance,
        matched_patterns=matched_patterns,
        domain_family=lens.domain_family,
        diversity_weight=1.0,
    )


def _forge_result(source_domain: str, *, confidence: float = 0.9) -> ForgeResult:
    trace = ForgeTrace(prompt="search")
    trace.total_cost_usd = 0.01
    return ForgeResult(
        output=json.dumps(
            {
                "source_domain": source_domain,
                "source_solution": f"{source_domain} stabilizes the system with explicit control state.",
                "mechanism": "Explicit gating plus retained control state",
                "structural_mapping": "Foreign gating maps to runtime admission and verification",
                "confidence": confidence,
            }
        ),
        trace=trace,
        success=True,
    )


class _SelectorStub:
    def __init__(self, selection: BundleSelectionResult) -> None:
        self._selection = selection

    def select_bundle_first(self, **_: object) -> BundleSelectionResult:
        return self._selection


class _SelectorWithFallback(_SelectorStub):
    def __init__(self, selection: BundleSelectionResult, fallback_scores: list[LensScore]) -> None:
        super().__init__(selection)
        self._fallback_scores = fallback_scores

    def select(self, **_: object) -> list[LensScore]:
        return list(self._fallback_scores)


@pytest.mark.asyncio
async def test_searcher_carries_bundle_proof_and_lineage() -> None:
    structure = _make_structure()
    lens_a = _make_lens(domain="biology", subdomain="immune", name="Immune Memory", maps_to=["allocation", "control"])
    lens_b = _make_lens(domain="economics", subdomain="auction", name="Auction Clearing", maps_to=["verification", "control"])
    score_a = _make_score(lens_a, distance=0.92, relevance=0.82, matched_patterns=["allocation", "control"])
    score_b = _make_score(lens_b, distance=0.88, relevance=0.79, matched_patterns=["verification", "control"])

    selection = BundleComposer().select([score_a, score_b], structure)
    harness = MagicMock()
    harness.forge = AsyncMock(side_effect=[_forge_result("Immune Memory"), _forge_result("Auction Clearing")])

    searcher = CrossDomainSearcher(
        harness=harness,
        selector=_SelectorStub(selection),
        num_candidates=4,
        num_lenses=2,
    )

    candidates = await searcher.search(structure)

    assert searcher.last_runtime is not None
    assert searcher.last_runtime.retrieval_mode == "bundle"
    assert searcher.last_runtime.bundle_proof is not None
    assert len(candidates) == 2
    assert all(candidate.bundle_proof is not None for candidate in candidates)
    assert all(candidate.bundle_lineage is not None for candidate in candidates)
    assert all(candidate.selection_mode == "bundle" for candidate in candidates)


@pytest.mark.asyncio
async def test_searcher_falls_back_to_singleton_when_bundle_retrieval_is_weak() -> None:
    structure = _make_structure()
    lens_a = _make_lens(domain="biology", subdomain="immune", name="Immune Memory", maps_to=["allocation", "control"])
    lens_b = _make_lens(domain="economics", subdomain="auction", name="Auction Clearing", maps_to=["verification", "control"])
    fallback_lens = _make_lens(domain="physics", subdomain="optics", name="Optical Thresholds", maps_to=["control"])

    score_a = _make_score(lens_a, distance=0.92, relevance=0.82, matched_patterns=["allocation", "control"])
    score_b = _make_score(lens_b, distance=0.88, relevance=0.79, matched_patterns=["verification", "control"])
    fallback_score = _make_score(fallback_lens, distance=0.75, relevance=0.68, matched_patterns=["control"])

    base_selection = BundleComposer().select([score_a, score_b], structure)
    selection = BundleSelectionResult(
        retrieval_mode="bundle",
        selected_lenses=base_selection.selected_lenses,
        fallback_lenses=(fallback_score,),
        primary_bundle=base_selection.primary_bundle,
        active_bundle=base_selection.active_bundle,
        exclusion_snapshot=base_selection.exclusion_snapshot,
    )

    harness = MagicMock()
    harness.forge = AsyncMock(
        side_effect=[
            _forge_result("Immune Memory", confidence=0.15),
            _forge_result("Auction Clearing", confidence=0.10),
            _forge_result("Optical Thresholds", confidence=0.91),
        ]
    )

    searcher = CrossDomainSearcher(
        harness=harness,
        selector=_SelectorStub(selection),
        num_candidates=4,
        num_lenses=2,
        min_confidence=0.4,
    )

    candidates = await searcher.search(structure)

    assert searcher.last_runtime is not None
    assert searcher.last_runtime.fallback_used is True
    assert len(candidates) == 1
    assert candidates[0].selection_mode == "singleton_fallback"
    assert candidates[0].bundle_proof is None


@pytest.mark.asyncio
async def test_searcher_can_disable_adaptive_lens_engine() -> None:
    structure = _make_structure()
    lens_a = _make_lens(domain="biology", subdomain="immune", name="Immune Memory", maps_to=["allocation", "control"])
    lens_b = _make_lens(domain="economics", subdomain="auction", name="Auction Clearing", maps_to=["verification", "control"])
    score_a = _make_score(lens_a, distance=0.92, relevance=0.82, matched_patterns=["allocation", "control"])
    score_b = _make_score(lens_b, distance=0.88, relevance=0.79, matched_patterns=["verification", "control"])

    selection = BundleComposer().select([score_a, score_b], structure)
    harness = MagicMock()
    harness.forge = AsyncMock(side_effect=[_forge_result("Immune Memory"), _forge_result("Auction Clearing")])

    searcher = CrossDomainSearcher(
        harness=harness,
        selector=_SelectorWithFallback(selection, [score_a, score_b]),
        num_candidates=4,
        num_lenses=2,
        use_adaptive_lens_engine=False,
    )

    candidates = await searcher.search(structure)

    assert searcher.last_runtime is not None
    assert searcher.last_runtime.retrieval_mode == "singleton"
    assert all(candidate.bundle_proof is None for candidate in candidates)
