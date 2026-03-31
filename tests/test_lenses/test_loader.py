"""
Tests for the Lens Library Manager (LensLoader).

Tests cover:
- Loading all 51 YAML lens files from the library directory
- Schema validation (required keys, types, minimum content)
- In-memory caching behavior
- Hot-reload when file mtime changes
- Listing available lenses with metadata
- Error handling for malformed/missing lenses
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import yaml

from hephaestus.lenses.loader import (
    Lens,
    LensLoader,
    LensValidationError,
    StructuralPattern,
    _DEFAULT_LIBRARY_DIR,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def library_dir() -> Path:
    """Return the path to the bundled lens library."""
    return _DEFAULT_LIBRARY_DIR


@pytest.fixture
def loader(library_dir: Path) -> LensLoader:
    """Return a fresh LensLoader pointing at the real library."""
    return LensLoader(library_dir=library_dir)


@pytest.fixture
def hot_loader(library_dir: Path) -> LensLoader:
    """Return a hot-reload LensLoader."""
    return LensLoader(library_dir=library_dir, hot_reload=True)


@pytest.fixture
def tmp_library(tmp_path: Path) -> Path:
    """Return a temporary directory for writing test YAML files."""
    lib = tmp_path / "library"
    lib.mkdir()
    return lib


def write_valid_lens(dir: Path, name: str = "test_lens") -> Path:
    """Write a syntactically valid lens YAML into dir."""
    data = {
        "name": "Test Lens",
        "domain": "testing",
        "subdomain": "unit_tests",
        "axioms": [
            "Every test must be isolated from all other tests.",
            "A failing test is information; an absent test is blindness.",
            "Fixtures set up preconditions; assertions verify postconditions.",
            "Side effects must be cleaned up.",
        ],
        "structural_patterns": [
            {
                "name": "isolation_pattern",
                "abstract": "Each unit is tested independently of all external dependencies.",
                "maps_to": ["isolation", "independence", "modularity"],
            },
            {
                "name": "assertion_pattern",
                "abstract": "Expected outcomes are explicitly stated before the fact and verified after.",
                "maps_to": ["verification", "contract", "expectation"],
            },
        ],
        "injection_prompt": (
            "You are now reasoning as if this problem exists within a test harness. "
            "Every component must be independently verifiable. Isolate, assert, verify."
        ),
    }
    path = dir / f"{name}.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Library directory
# ──────────────────────────────────────────────────────────────────────────────

class TestLibraryDirectory:
    def test_default_library_dir_exists(self):
        assert _DEFAULT_LIBRARY_DIR.is_dir(), (
            f"Bundled library directory not found: {_DEFAULT_LIBRARY_DIR}"
        )

    def test_library_has_51_yaml_files(self, library_dir: Path):
        yaml_files = list(library_dir.glob("*.yaml"))
        assert len(yaml_files) == 51, (
            f"Expected 51 YAML files, found {len(yaml_files)}: "
            f"{sorted(f.stem for f in yaml_files)}"
        )

    def test_all_expected_lenses_present(self, library_dir: Path):
        """Verify all 51 expected lens files are present."""
        expected = [
            "biology_immune", "biology_ecology", "biology_mycology",
            "biology_swarm", "biology_evolution",
            "physics_thermodynamics", "physics_fluid_dynamics",
            "physics_quantum", "physics_optics",
            "chemistry_catalysis", "chemistry_polymers",
            "math_topology", "math_game_theory", "math_chaos",
            "cs_network_theory", "cs_cryptography", "cs_distributed_systems",
            "military_strategy", "military_logistics", "military_intelligence",
            "economics_markets", "economics_behavioral", "economics_game_theory",
            "music_theory", "music_acoustics",
            "linguistics_syntax", "linguistics_semantics",
            "neuroscience_memory", "neuroscience_perception", "neuroscience_plasticity",
            "urban_planning", "architecture_structural",
            "materials_science", "geology_tectonics",
            "meteorology", "oceanography", "astronomy_orbital",
            "sociology_networks", "psychology_cognitive", "psychology_evolutionary",
            "philosophy_logic",
            "agriculture", "cooking_fermentation", "textiles_weaving",
            "forestry_management", "epidemiology",
            "mythology_narrative", "sports_strategy", "film_cinematography",
            "martial_arts", "navigation_wayfinding",
        ]
        present = {f.stem for f in library_dir.glob("*.yaml")}
        missing = set(expected) - present
        assert not missing, f"Missing lens files: {sorted(missing)}"


# ──────────────────────────────────────────────────────────────────────────────
# Load All
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadAll:
    def test_load_all_returns_51_lenses(self, loader: LensLoader):
        lenses = loader.load_all()
        assert len(lenses) == 51

    def test_load_all_returns_lens_objects(self, loader: LensLoader):
        lenses = loader.load_all()
        for lens_id, lens in lenses.items():
            assert isinstance(lens, Lens), f"{lens_id} is not a Lens"

    def test_all_lenses_have_required_fields(self, loader: LensLoader):
        lenses = loader.load_all()
        for lens_id, lens in lenses.items():
            assert lens.name, f"{lens_id} missing name"
            assert lens.domain, f"{lens_id} missing domain"
            assert lens.subdomain, f"{lens_id} missing subdomain"
            assert len(lens.axioms) >= 2, f"{lens_id} has fewer than 2 axioms"
            assert len(lens.structural_patterns) >= 1, f"{lens_id} has no patterns"
            assert len(lens.injection_prompt) >= 20, f"{lens_id} injection_prompt too short"

    def test_all_lenses_have_deep_axioms(self, loader: LensLoader):
        """Each axiom should be a substantive sentence, not a stub."""
        lenses = loader.load_all()
        for lens_id, lens in lenses.items():
            for i, axiom in enumerate(lens.axioms):
                assert len(axiom) > 30, (
                    f"{lens_id} axiom[{i}] is too short: {axiom!r}"
                )

    def test_all_structural_patterns_have_maps_to(self, loader: LensLoader):
        lenses = loader.load_all()
        for lens_id, lens in lenses.items():
            for pat in lens.structural_patterns:
                assert isinstance(pat.maps_to, list), (
                    f"{lens_id} pattern {pat.name!r}: maps_to must be a list"
                )
                assert len(pat.maps_to) >= 1, (
                    f"{lens_id} pattern {pat.name!r}: maps_to is empty"
                )


# ──────────────────────────────────────────────────────────────────────────────
# Load One
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadOne:
    def test_load_one_returns_correct_lens(self, loader: LensLoader):
        lens = loader.load_one("biology_immune")
        assert lens.lens_id == "biology_immune"
        assert "immune" in lens.name.lower() or "immune" in lens.subdomain.lower()

    def test_load_one_missing_raises_file_not_found(self, loader: LensLoader):
        with pytest.raises(FileNotFoundError):
            loader.load_one("nonexistent_lens_xyz")

    def test_load_one_returns_same_object_on_second_call(self, loader: LensLoader):
        lens1 = loader.load_one("biology_immune")
        lens2 = loader.load_one("biology_immune")
        assert lens1 is lens2  # Cache hit should return same object


# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────

class TestValidation:
    def test_missing_required_key_raises_validation_error(self, tmp_library: Path):
        # Write a lens missing 'domain'
        data = {
            "name": "Incomplete Lens",
            "subdomain": "test",
            "axioms": ["axiom one", "axiom two"],
            "structural_patterns": [
                {"name": "pat", "abstract": "something", "maps_to": ["x"]}
            ],
            "injection_prompt": "This is a test injection prompt that is long enough.",
        }
        path = tmp_library / "incomplete.yaml"
        path.write_text(yaml.dump(data))
        loader = LensLoader(library_dir=tmp_library)
        with pytest.raises(LensValidationError) as exc_info:
            loader.load_all(skip_errors=False)
        assert "domain" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

    def test_too_few_axioms_raises_validation_error(self, tmp_library: Path):
        data = {
            "name": "One Axiom Lens",
            "domain": "test",
            "subdomain": "test",
            "axioms": ["Only one axiom here and it exists."],  # Only 1, need ≥2
            "structural_patterns": [
                {"name": "pat", "abstract": "desc", "maps_to": ["x"]}
            ],
            "injection_prompt": "This injection prompt is definitely long enough to pass.",
        }
        path = tmp_library / "one_axiom.yaml"
        path.write_text(yaml.dump(data))
        loader = LensLoader(library_dir=tmp_library)
        with pytest.raises(LensValidationError):
            loader.load_all(skip_errors=False)

    def test_invalid_yaml_raises_validation_error(self, tmp_library: Path):
        path = tmp_library / "bad_yaml.yaml"
        path.write_text("{ invalid: yaml: content: [unclosed")
        loader = LensLoader(library_dir=tmp_library)
        with pytest.raises(LensValidationError):
            loader.load_all(skip_errors=False)

    def test_skip_errors_continues_past_bad_file(self, tmp_library: Path):
        # Write one valid and one invalid lens
        write_valid_lens(tmp_library, "valid_lens")
        (tmp_library / "broken.yaml").write_text("not: valid: yaml: [")
        loader = LensLoader(library_dir=tmp_library)
        lenses = loader.load_all(skip_errors=True)
        assert len(lenses) == 1
        errors = loader.get_load_errors()
        assert "broken.yaml" in errors

    def test_non_dict_yaml_raises_validation_error(self, tmp_library: Path):
        path = tmp_library / "list_lens.yaml"
        path.write_text("- item1\n- item2\n")
        loader = LensLoader(library_dir=tmp_library)
        with pytest.raises(LensValidationError):
            loader.load_all(skip_errors=False)


# ──────────────────────────────────────────────────────────────────────────────
# Caching
# ──────────────────────────────────────────────────────────────────────────────

class TestCaching:
    def test_cache_populated_after_load_all(self, loader: LensLoader):
        loader.load_all()
        assert len(loader) == 51

    def test_second_load_all_uses_cache(self, loader: LensLoader):
        lenses1 = loader.load_all()
        lenses2 = loader.load_all()
        # All lens objects should be identical (same Python objects)
        for lens_id in lenses1:
            assert lenses1[lens_id] is lenses2[lens_id]

    def test_reload_clears_cache(self, loader: LensLoader):
        lenses1 = loader.load_all()
        loader.reload()
        lenses2 = loader.load_all()
        # After reload, same data but different objects
        assert set(lenses1.keys()) == set(lenses2.keys())
        # After reload, at least one lens should be a new Python object
        ids1 = {id(l) for l in lenses1.values()}
        ids2 = {id(l) for l in lenses2.values()}
        assert ids1 != ids2, "Reload should produce fresh lens objects"


# ──────────────────────────────────────────────────────────────────────────────
# Hot Reload
# ──────────────────────────────────────────────────────────────────────────────

class TestHotReload:
    def test_hot_reload_detects_mtime_change(self, tmp_library: Path):
        path = write_valid_lens(tmp_library, "hot_lens")
        loader = LensLoader(library_dir=tmp_library, hot_reload=True)

        # First load — lens_id comes from the filename stem ("hot_lens")
        lenses1 = loader.load_all()
        lens1 = lenses1["hot_lens"]

        # Touch file to update mtime (sleep briefly to ensure mtime changes)
        time.sleep(0.05)
        data = yaml.safe_load(path.read_text())
        data["name"] = "Modified Test Lens"
        path.write_text(yaml.dump(data))

        # Second load — should detect mtime change and re-read
        lenses2 = loader.load_all()
        lens2 = lenses2["hot_lens"]

        assert lens2.name == "Modified Test Lens"
        assert lens1 is not lens2

    def test_no_hot_reload_returns_cached_even_after_file_change(
        self, tmp_library: Path
    ):
        path = write_valid_lens(tmp_library, "static_lens")
        loader = LensLoader(library_dir=tmp_library, hot_reload=False)

        # First load — lens_id comes from the filename stem ("static_lens")
        lenses1 = loader.load_all()
        lens1 = lenses1["static_lens"]

        # Modify file
        time.sleep(0.05)
        data = yaml.safe_load(path.read_text())
        data["name"] = "Should Not Be Seen"
        path.write_text(yaml.dump(data))

        # Second load — should use cache without re-reading
        lenses2 = loader.load_all()
        lens2 = lenses2["static_lens"]

        # Should be cached version
        assert lens1 is lens2


# ──────────────────────────────────────────────────────────────────────────────
# Listing
# ──────────────────────────────────────────────────────────────────────────────

class TestListAvailable:
    def test_list_available_returns_51_items(self, loader: LensLoader):
        items = loader.list_available()
        assert len(items) == 51

    def test_list_available_sorted_by_lens_id(self, loader: LensLoader):
        items = loader.list_available()
        ids = [d["lens_id"] for d in items]
        assert ids == sorted(ids)

    def test_list_available_contains_metadata_fields(self, loader: LensLoader):
        items = loader.list_available()
        for item in items:
            assert "lens_id" in item
            assert "name" in item
            assert "domain" in item
            assert "subdomain" in item
            assert "axiom_count" in item
            assert "pattern_count" in item
            assert "maps_to" in item

    def test_list_available_no_injection_prompt(self, loader: LensLoader):
        """Metadata should not include the full injection_prompt (heavy)."""
        items = loader.list_available()
        for item in items:
            assert "injection_prompt" not in item
            assert "axioms" not in item


# ──────────────────────────────────────────────────────────────────────────────
# Domain Queries
# ──────────────────────────────────────────────────────────────────────────────

class TestDomainQueries:
    def test_get_by_domain_biology(self, loader: LensLoader):
        bio_lenses = loader.get_by_domain("biology")
        assert len(bio_lenses) == 5
        for lens in bio_lenses:
            assert lens.domain == "biology"

    def test_get_by_domain_case_insensitive(self, loader: LensLoader):
        lenses = loader.get_by_domain("BIOLOGY")
        assert len(lenses) == 5

    def test_get_by_maps_to_trust(self, loader: LensLoader):
        trust_lenses = loader.get_by_maps_to("trust")
        assert len(trust_lenses) >= 1
        for lens in trust_lenses:
            assert "trust" in {m.lower() for m in lens.all_maps_to}


# ──────────────────────────────────────────────────────────────────────────────
# Lens Properties
# ──────────────────────────────────────────────────────────────────────────────

class TestLensProperties:
    def test_lens_id_format(self, loader: LensLoader):
        lenses = loader.load_all()
        for lens_id, lens in lenses.items():
            assert "_" in lens_id or len(lens_id) > 0
            assert lens_id == lens.lens_id

    def test_all_maps_to_is_union(self, loader: LensLoader):
        lens = loader.load_one("biology_immune")
        all_maps = lens.all_maps_to
        assert isinstance(all_maps, set)
        assert len(all_maps) >= 1
        # Should be union of all patterns' maps_to
        manual_union: set[str] = set()
        for pat in lens.structural_patterns:
            manual_union.update(pat.maps_to)
        assert all_maps == manual_union

    def test_contains_operator(self, loader: LensLoader):
        assert "biology_immune" in loader
        assert "nonexistent_lens" not in loader

    def test_repr_includes_key_info(self, loader: LensLoader):
        r = repr(loader)
        assert "LensLoader" in r
        assert "hot_reload" in r
