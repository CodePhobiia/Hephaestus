"""Selector tests focused on bundle-first behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.lineage import build_native_lineage
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensSelector


def _make_lens(lens_id: str, *, maps_to: list[str], domain: str) -> Lens:
    return Lens(
        name=f"Lens {lens_id}",
        domain=domain,
        subdomain="unit",
        axioms=[
            "A first structural axiom about maintaining coherence through change.",
            "A second structural axiom about amplifying successful responses under pressure.",
        ],
        structural_patterns=[
            StructuralPattern(
                name="pattern",
                abstract="Reusable structure with explicit mappings into the target problem.",
                maps_to=maps_to,
            )
        ],
        injection_prompt="Reason through this lens with sufficient detail for the selector.",
        source_file=Path(f"/tmp/{lens_id}.yaml"),
        explicit_lens_id=lens_id,
    )


def test_select_plan_prefers_bundle_when_strong_bundle_exists() -> None:
    lenses = {
        "biology_immune": _make_lens(
            "biology_immune", maps_to=["trust", "verification"], domain="biology"
        ),
        "economics_markets": _make_lens(
            "economics_markets", maps_to=["trust", "allocation"], domain="economics"
        ),
        "military_logistics": _make_lens(
            "military_logistics", maps_to=["allocation", "routing"], domain="military"
        ),
    }
    cards = {lens_id: compile_lens_card(lens) for lens_id, lens in lenses.items()}
    lineages = {
        lens_id: build_native_lineage(
            lens_id=lens_id,
            version=lens.version,
            card_fingerprint64=cards[lens_id].fingerprint64,
            loader_revision=1,
        )
        for lens_id, lens in lenses.items()
    }
    from unittest.mock import MagicMock

    loader = MagicMock()
    loader.load_all.return_value = lenses
    loader.get_card.side_effect = lambda lens_id: cards[lens_id]
    loader.get_lineage.side_effect = lambda lens_id, reference_context=None: lineages[lens_id]
    loader.library_revision = 1

    selector = LensSelector(loader=loader, min_distance=0.0, bundle_min_score=0.0)
    with patch.object(
        selector,
        "compute_all_distances",
        return_value={lens_id: 0.9 for lens_id in lenses},
    ):
        plan = selector.select_plan(
            problem_description="trust verification routing problem",
            problem_maps_to={"trust", "verification", "allocation"},
            target_domain="distributed_systems",
            top_n=3,
        )

    assert plan.mode == "bundle"
    assert plan.primary_bundle is not None
    assert any(score.selection_mode == "bundle" for score in plan.scores)
    assert all(score.bundle_id == plan.primary_bundle.proof.bundle_id for score in plan.scores[:2])


def test_select_plan_falls_back_to_singletons_when_bundle_is_weak() -> None:
    lenses = {
        "biology_immune": _make_lens("biology_immune", maps_to=["trust"], domain="biology"),
        "economics_markets": _make_lens(
            "economics_markets", maps_to=["allocation"], domain="economics"
        ),
    }
    cards = {lens_id: compile_lens_card(lens) for lens_id, lens in lenses.items()}
    lineages = {
        lens_id: build_native_lineage(
            lens_id=lens_id,
            version=lens.version,
            card_fingerprint64=cards[lens_id].fingerprint64,
            loader_revision=1,
        )
        for lens_id, lens in lenses.items()
    }
    from unittest.mock import MagicMock

    loader = MagicMock()
    loader.load_all.return_value = lenses
    loader.get_card.side_effect = lambda lens_id: cards[lens_id]
    loader.get_lineage.side_effect = lambda lens_id, reference_context=None: lineages[lens_id]
    loader.library_revision = 1

    selector = LensSelector(loader=loader, min_distance=0.0, bundle_min_score=0.9)
    with patch.object(
        selector,
        "compute_all_distances",
        return_value={lens_id: 0.8 for lens_id in lenses},
    ):
        plan = selector.select_plan(
            problem_description="trust problem",
            problem_maps_to={"trust"},
            target_domain="distributed_systems",
            top_n=2,
            require_relevance=True,
        )

    assert plan.mode == "fallback"
    assert all(score.selection_mode == "singleton" for score in plan.scores)
