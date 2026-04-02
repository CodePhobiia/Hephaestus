"""Tests for lens disclosure cards."""

from __future__ import annotations

from pathlib import Path

from hephaestus.lenses.cards import LensCard, compile_lens_card, score_query_against_card
from hephaestus.lenses.loader import Lens, StructuralPattern


def _make_lens() -> Lens:
    return Lens(
        name="Immune Memory",
        domain="biology",
        subdomain="immune",
        axioms=[
            "Cells retain a memory of prior structurally similar encounters.",
            "Recall latency decreases as clone frequency increases.",
            "Competing signals can suppress weaker responses.",
        ],
        structural_patterns=[
            StructuralPattern(
                name="clonal archive",
                abstract="A population retains indexed traces of past encounters and recalls them faster on re-exposure.",
                maps_to=["memory", "selection", "adaptive_response"],
            )
        ],
        injection_prompt="Reason as an immune system with memory and selection dynamics.",
        source_file=Path("/tmp/biology_immune.yaml"),
        tags=["memory", "selection"],
    )


def test_compile_lens_card() -> None:
    card = compile_lens_card(_make_lens())
    assert isinstance(card, LensCard)
    assert card.lens_id == "biology_immune"
    assert "memory" in card.transfer_shape
    assert card.fingerprint64 > 0


def test_card_summary_text() -> None:
    card = compile_lens_card(_make_lens())
    txt = card.summary_text()
    assert "biology::Immune Memory" in txt
    assert "shape=" in txt


def test_card_to_dict() -> None:
    card = compile_lens_card(_make_lens())
    data = card.to_dict()
    assert data["lens_id"] == "biology_immune"
    assert isinstance(data["provenance"], dict)


def test_score_query_against_card_positive() -> None:
    card = compile_lens_card(_make_lens())
    score = score_query_against_card({"memory", "adaptive_response"}, card)
    assert score > 0


def test_score_query_against_card_penalty() -> None:
    lens = _make_lens()
    lens.axioms.append("This domain often relies on cache and retry semantics.")
    card = compile_lens_card(lens)
    score = score_query_against_card({"cache"}, card)
    assert score < 0
