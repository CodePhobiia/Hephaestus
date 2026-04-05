"""Tests for proof-carrying lens lineage."""

from __future__ import annotations

from pathlib import Path

from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.lineage import (
    build_composite_lineage,
    build_native_lineage,
    compute_reference_signature,
    validate_lineage,
)
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.session.reference_lots import ReferenceLot


def _make_lens(lens_id: str, *, domain: str = "biology", maps_to: list[str] | None = None) -> Lens:
    return Lens(
        name=f"Lens {lens_id}",
        domain=domain,
        subdomain="unit",
        axioms=[
            "A substantive axiom about preserving signal through structural change.",
            "A second substantive axiom about coordinating multiple selective pressures.",
        ],
        structural_patterns=[
            StructuralPattern(
                name="pattern",
                abstract="A pattern that maps structurally distant mechanisms onto a target problem.",
                maps_to=maps_to or ["trust", "verification"],
            )
        ],
        injection_prompt="Reason through the lens with enough detail to pass validation.",
        source_file=Path(f"/tmp/{lens_id}.yaml"),
        explicit_lens_id=lens_id,
    )


def test_native_lineage_validates_against_current_card() -> None:
    lens = _make_lens("biology_immune")
    card = compile_lens_card(lens)
    lineage = build_native_lineage(
        lens_id=lens.lens_id,
        version=lens.version,
        card_fingerprint64=card.fingerprint64,
        loader_revision=3,
    )

    result = validate_lineage(
        lineage,
        current_cards={lens.lens_id: card},
        current_lineages={lens.lens_id: lineage},
        loader_revision=3,
    )

    assert result.valid is True
    assert result.reasons == ()


def test_composite_lineage_invalidates_when_parent_fingerprint_changes() -> None:
    left = _make_lens("biology_immune")
    right = _make_lens("economics_markets", domain="economics", maps_to=["trust", "allocation"])
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

    composite = _make_lens("composite_bridge", domain="composite", maps_to=["trust", "allocation"])
    composite_card = compile_lens_card(composite, parent_cards=[left_card, right_card])
    composite_lineage = build_composite_lineage(
        lens_id=composite.lens_id,
        version=composite.version,
        card_fingerprint64=composite_card.fingerprint64,
        loader_revision=1,
        parent_cards=[left_card, right_card],
        parent_lineages=[left_lineage, right_lineage],
        derivation="bundle_composite",
    )

    mutated_right = _make_lens(
        "economics_markets", domain="economics", maps_to=["auction", "allocation"]
    )
    mutated_right_card = compile_lens_card(mutated_right)
    validation = validate_lineage(
        composite_lineage,
        current_cards={
            left.lens_id: left_card,
            right.lens_id: mutated_right_card,
            composite.lens_id: composite_card,
        },
        current_lineages={
            left.lens_id: left_lineage,
            right.lens_id: right_lineage,
            composite.lens_id: composite_lineage,
        },
        loader_revision=1,
    )

    assert validation.valid is False
    assert any("parent fingerprint changed" in reason for reason in validation.reasons)


def test_reference_signature_is_stable_across_mapping_order() -> None:
    first = compute_reference_signature({"keywords_to_avoid": ["cache"], "source": "baseline"})
    second = compute_reference_signature({"source": "baseline", "keywords_to_avoid": ["cache"]})
    assert first == second


def test_reference_signature_supports_reference_lots() -> None:
    lots = [
        ReferenceLot(lot_id=1, kind="workspace", subject_key="repo", acquired_op=1),
        ReferenceLot(lot_id=2, kind="tool", subject_key="search", acquired_op=2),
    ]
    digest = compute_reference_signature(lots)
    assert digest.startswith("ref_")
