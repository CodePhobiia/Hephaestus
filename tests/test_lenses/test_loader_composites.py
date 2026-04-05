"""Tests for derived composite lenses in the loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from hephaestus.lenses.loader import LensLoader


def _write_lens(path: Path, *, name: str, domain: str, subdomain: str, maps_to: list[str]) -> None:
    data = {
        "name": name,
        "domain": domain,
        "subdomain": subdomain,
        "axioms": [
            "A first detailed axiom that preserves enough substance for loader validation.",
            "A second detailed axiom that preserves enough substance for loader validation.",
        ],
        "structural_patterns": [
            {
                "name": "pattern",
                "abstract": "A structural pattern with clear mappings into the target problem.",
                "maps_to": maps_to,
            }
        ],
        "injection_prompt": "Reason through this lens with sufficient detail for production validation.",
    }
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_loader_registers_and_invalidates_composite_lenses(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    _write_lens(
        library / "biology_immune.yaml",
        name="Immune Lens",
        domain="biology",
        subdomain="immune",
        maps_to=["trust", "verification"],
    )
    _write_lens(
        library / "economics_markets.yaml",
        name="Market Lens",
        domain="economics",
        subdomain="markets",
        maps_to=["allocation", "trust"],
    )

    loader = LensLoader(library_dir=library)
    loader.load_all()
    composite = loader.derive_composite_lens(
        name="Trust Bridge",
        parent_lens_ids=["biology_immune", "economics_markets"],
        reference_context={"keywords_to_avoid": ["cache"]},
    )

    assert composite.lens_id in loader.load_all(
        include_derived=True, reference_context={"keywords_to_avoid": ["cache"]}
    )
    assert (
        loader.get_lineage(
            composite.lens_id, reference_context={"keywords_to_avoid": ["cache"]}
        ).source_kind
        == "derived_composite"
    )

    loader.reload()
    loaded = loader.load_all(include_derived=True)
    assert composite.lens_id not in loaded
