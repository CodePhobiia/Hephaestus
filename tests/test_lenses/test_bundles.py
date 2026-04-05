"""Tests for bundle fold-state and proofs."""

from __future__ import annotations

from pathlib import Path

from hephaestus.lenses.bundles import build_bundle_candidates
from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.cells import CohesionCellIndex
from hephaestus.lenses.lineage import build_native_lineage
from hephaestus.lenses.loader import Lens, StructuralPattern


def _make_lens(lens_id: str, *, maps_to: list[str], domain: str) -> Lens:
    return Lens(
        name=f"Lens {lens_id}",
        domain=domain,
        subdomain="unit",
        axioms=[
            "A first axiom tying the domain to persistent structural adaptation.",
            "A second axiom explaining how the domain coordinates selective amplification.",
        ],
        structural_patterns=[
            StructuralPattern(
                name="pattern",
                abstract="Reusable bundle-friendly structure with explicit target mappings.",
                maps_to=maps_to,
            )
        ],
        injection_prompt="Reason through the domain with specific structural discipline.",
        source_file=Path(f"/tmp/{lens_id}.yaml"),
        explicit_lens_id=lens_id,
    )


def test_bundle_candidates_produce_proof_and_fold_state() -> None:
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
    index = CohesionCellIndex.build(cards, lineages=lineages)
    bundle_candidates = build_bundle_candidates(
        cards=cards,
        lineages=lineages,
        cell_index=index,
        query_terms=("trust", "verification", "allocation"),
        base_scores={lens_id: 0.9 for lens_id in lenses},
        loader_revision=1,
        min_bundle_score=0.0,
    )

    assert bundle_candidates
    candidate = bundle_candidates[0]
    assert len(candidate.lens_ids) >= 2
    assert candidate.fold_state.proof_strength > 0.0
    validation = candidate.proof.validate(
        cards=cards,
        lineages=lineages,
        loader_revision=1,
    )
    assert validation.valid is True


def test_bundle_proof_detects_reference_context_change() -> None:
    lenses = {
        "biology_immune": _make_lens(
            "biology_immune", maps_to=["trust", "verification"], domain="biology"
        ),
        "economics_markets": _make_lens(
            "economics_markets", maps_to=["trust", "allocation"], domain="economics"
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
    index = CohesionCellIndex.build(cards, lineages=lineages)
    candidate = build_bundle_candidates(
        cards=cards,
        lineages=lineages,
        cell_index=index,
        query_terms=("trust", "verification"),
        base_scores={lens_id: 0.9 for lens_id in lenses},
        loader_revision=1,
        reference_context={"keywords_to_avoid": ["cache"]},
        min_bundle_score=0.0,
    )[0]

    validation = candidate.proof.validate(
        cards=cards,
        lineages=lineages,
        loader_revision=1,
        reference_context={"keywords_to_avoid": ["queue"]},
    )
    assert validation.valid is False
    assert "reference context changed" in validation.reasons
