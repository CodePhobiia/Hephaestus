"""Tests for cohesion-cell derivation and indexing."""

from __future__ import annotations

from pathlib import Path

from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.cells import CohesionCellIndex
from hephaestus.lenses.lineage import build_native_lineage
from hephaestus.lenses.loader import Lens, StructuralPattern


def _make_lens(lens_id: str, *, maps_to: list[str], domain: str = "biology") -> Lens:
    return Lens(
        name=f"Lens {lens_id}",
        domain=domain,
        subdomain="unit",
        axioms=[
            "Signal persists through selective recall under repeated encounters.",
            "Distinct pathways can complement one another when they share a stabilizing interface.",
        ],
        structural_patterns=[
            StructuralPattern(
                name="pattern",
                abstract="Reusable structure with explicit mappings into the target problem.",
                maps_to=maps_to,
            )
        ],
        injection_prompt="Reason through this lens in enough detail for selector tests.",
        source_file=Path(f"/tmp/{lens_id}.yaml"),
        explicit_lens_id=lens_id,
    )


def test_cohesion_index_scores_lenses_from_query_terms() -> None:
    left = _make_lens("left", maps_to=["trust", "verification"])
    right = _make_lens("right", maps_to=["trust", "allocation"], domain="economics")
    left_card = compile_lens_card(left)
    right_card = compile_lens_card(right)
    left_lineage = build_native_lineage(
        lens_id=left.lens_id,
        version=left.version,
        card_fingerprint64=left_card.fingerprint64,
        loader_revision=1,
    )
    right_lineage = build_native_lineage(
        lens_id=right.lens_id,
        version=right.version,
        card_fingerprint64=right_card.fingerprint64,
        loader_revision=1,
    )

    index = CohesionCellIndex.build(
        {left.lens_id: left_card, right.lens_id: right_card},
        lineages={left.lens_id: left_lineage, right.lens_id: right_lineage},
        reference_context={"keywords_to_avoid": ["cache"]},
    )

    scores = index.score_lenses({"trust", "verification"})
    assert scores[left.lens_id] > 0.0
    assert scores[right.lens_id] > 0.0


def test_shared_cells_include_query_aligned_overlap() -> None:
    left = _make_lens("left", maps_to=["trust", "verification"])
    right = _make_lens("right", maps_to=["trust", "allocation"], domain="economics")
    left_card = compile_lens_card(left)
    right_card = compile_lens_card(right)
    index = CohesionCellIndex.build(
        {left.lens_id: left_card, right.lens_id: right_card},
        lineages={},
        reference_context={"baseline_keywords": ["cache"]},
    )

    shared = index.shared_cells([left.lens_id, right.lens_id], query_terms={"trust", "allocation"})
    shared_tokens = {cell.token for cell in shared}

    assert "trust" in shared_tokens
    assert any(
        membership.kind == "reference"
        for membership in index.memberships_for_lens(left.lens_id)
    )
