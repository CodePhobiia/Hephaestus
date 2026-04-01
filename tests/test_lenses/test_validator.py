"""Tests for lens validation and statistics."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.validator import (
    LensStats,
    LensValidationIssue,
    compute_lens_stats,
    validate_all_lenses,
    validate_lens,
    validate_lens_file,
)


def _make_valid_lens(**overrides) -> Lens:
    defaults = dict(
        name="Test Lens",
        domain="biology",
        subdomain="ecology",
        axioms=["Life finds a way.", "Ecosystems self-regulate."],
        structural_patterns=[
            StructuralPattern("competition", "Organisms compete for resources", ["allocation"])
        ],
        injection_prompt="Reason as an ecologist.",
    )
    defaults.update(overrides)
    return Lens(**defaults)


class TestValidateLens:
    def test_valid_lens_has_no_issues(self):
        assert validate_lens(_make_valid_lens()) == []

    def test_empty_name(self):
        issues = validate_lens(_make_valid_lens(name=""))
        assert any(i.field == "name" for i in issues)

    def test_empty_domain(self):
        issues = validate_lens(_make_valid_lens(domain=""))
        assert any(i.field == "domain" for i in issues)

    def test_no_axioms(self):
        issues = validate_lens(_make_valid_lens(axioms=[]))
        assert any(i.field == "axioms" for i in issues)

    def test_empty_axiom(self):
        issues = validate_lens(_make_valid_lens(axioms=["Valid", ""]))
        assert any("axioms[1]" in i.field for i in issues)

    def test_no_patterns(self):
        issues = validate_lens(_make_valid_lens(structural_patterns=[]))
        assert any(i.field == "structural_patterns" for i in issues)

    def test_empty_pattern_name(self):
        bad = StructuralPattern("", "abstract", ["tag"])
        issues = validate_lens(_make_valid_lens(structural_patterns=[bad]))
        assert any("name" in i.field for i in issues)

    def test_empty_injection_prompt(self):
        issues = validate_lens(_make_valid_lens(injection_prompt=""))
        assert any(i.field == "injection_prompt" for i in issues)

    def test_pattern_no_maps_to(self):
        bad = StructuralPattern("name", "abstract", [])
        issues = validate_lens(_make_valid_lens(structural_patterns=[bad]))
        assert any("maps_to" in i.field for i in issues)


class TestValidateLensFile:
    def test_valid_yaml(self, tmp_path: Path):
        data = {
            "name": "Test",
            "domain": "physics",
            "subdomain": "mechanics",
            "axioms": ["F=ma"],
            "structural_patterns": [{"name": "force", "abstract": "Push", "maps_to": ["dynamics"]}],
            "injection_prompt": "Think like a physicist.",
        }
        f = tmp_path / "test.yaml"
        f.write_text(yaml.dump(data))
        assert validate_lens_file(f) == []

    def test_invalid_yaml(self, tmp_path: Path):
        f = tmp_path / "bad.yaml"
        f.write_text(":::not yaml:::")
        issues = validate_lens_file(f)
        assert len(issues) >= 1

    def test_missing_fields(self, tmp_path: Path):
        f = tmp_path / "empty.yaml"
        f.write_text(yaml.dump({"name": "", "domain": ""}))
        issues = validate_lens_file(f)
        assert len(issues) >= 2


class TestValidateAllLenses:
    def test_shipped_lenses_are_valid(self):
        """All shipped lens YAML files should pass validation."""
        errors = validate_all_lenses()
        if errors:
            for fname, issues in errors.items():
                for issue in issues:
                    print(f"  {issue}")
        assert errors == {}, f"Shipped lenses have validation errors: {list(errors.keys())}"

    def test_empty_directory(self, tmp_path: Path):
        assert validate_all_lenses(tmp_path) == {}

    def test_mixed_valid_invalid(self, tmp_path: Path):
        good = {"name": "Good", "domain": "x", "subdomain": "x", "axioms": ["a"],
                "structural_patterns": [{"name": "p", "abstract": "a", "maps_to": ["t"]}],
                "injection_prompt": "x"}
        bad = {"name": "", "domain": ""}
        (tmp_path / "good.yaml").write_text(yaml.dump(good))
        (tmp_path / "bad.yaml").write_text(yaml.dump(bad))
        errors = validate_all_lenses(tmp_path)
        assert "bad.yaml" in errors
        assert "good.yaml" not in errors


class TestComputeStats:
    def test_stats_on_shipped_library(self):
        stats = compute_lens_stats()
        assert stats.total_lenses > 0
        assert len(stats.domains) > 0
        assert stats.total_axioms > 0
        assert stats.total_patterns > 0
        assert stats.avg_axioms_per_lens > 0

    def test_empty_directory(self, tmp_path: Path):
        stats = compute_lens_stats(tmp_path)
        assert stats.total_lenses == 0
        assert stats.avg_axioms_per_lens == 0.0

    def test_single_lens(self, tmp_path: Path):
        data = {"name": "Solo", "domain": "math", "subdomain": "algebra",
                "axioms": ["a", "b", "c"],
                "structural_patterns": [{"name": "p", "abstract": "a", "maps_to": ["t"]}],
                "injection_prompt": "x"}
        (tmp_path / "solo.yaml").write_text(yaml.dump(data))
        stats = compute_lens_stats(tmp_path)
        assert stats.total_lenses == 1
        assert stats.domains == ["math"]
        assert stats.total_axioms == 3
        assert stats.avg_axioms_per_lens == 3.0
