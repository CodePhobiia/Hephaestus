"""Lens validation and statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hephaestus.lenses.loader import Lens, LensLoader, StructuralPattern

logger = logging.getLogger(__name__)

_DEFAULT_LIBRARY = Path(__file__).parent / "library"


@dataclass
class LensValidationIssue:
    """A single validation issue found in a lens."""
    file: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.field} — {self.message}"


@dataclass
class LensStats:
    """Aggregate statistics about the lens library."""
    total_lenses: int = 0
    domains: list[str] = field(default_factory=list)
    domain_counts: dict[str, int] = field(default_factory=dict)
    total_axioms: int = 0
    total_patterns: int = 0
    avg_axioms_per_lens: float = 0.0


def validate_lens(lens: Lens, source_file: str = "") -> list[LensValidationIssue]:
    """Validate a single Lens instance."""
    issues: list[LensValidationIssue] = []

    if not lens.name or not lens.name.strip():
        issues.append(LensValidationIssue(source_file, "name", "Name is empty"))
    if not lens.domain or not lens.domain.strip():
        issues.append(LensValidationIssue(source_file, "domain", "Domain is empty"))
    if not lens.axioms:
        issues.append(LensValidationIssue(source_file, "axioms", "No axioms defined"))
    else:
        for i, axiom in enumerate(lens.axioms):
            if not axiom or not axiom.strip():
                issues.append(LensValidationIssue(source_file, f"axioms[{i}]", "Empty axiom"))
    if not lens.structural_patterns:
        issues.append(LensValidationIssue(source_file, "structural_patterns", "No structural patterns"))
    else:
        for i, pat in enumerate(lens.structural_patterns):
            if not pat.name or not pat.name.strip():
                issues.append(LensValidationIssue(source_file, f"patterns[{i}].name", "Empty pattern name"))
            if not pat.abstract or not pat.abstract.strip():
                issues.append(LensValidationIssue(source_file, f"patterns[{i}].abstract", "Empty pattern abstract"))
            if not pat.maps_to:
                issues.append(LensValidationIssue(source_file, f"patterns[{i}].maps_to", "No maps_to entries"))
    if not lens.injection_prompt or not lens.injection_prompt.strip():
        issues.append(LensValidationIssue(source_file, "injection_prompt", "Injection prompt is empty"))

    return issues


def validate_lens_file(path: Path) -> list[LensValidationIssue]:
    """Load a YAML file and validate the lens."""
    fname = path.name
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        return [LensValidationIssue(fname, "yaml", f"Failed to parse: {exc}")]

    if not isinstance(data, dict):
        return [LensValidationIssue(fname, "format", "Expected a YAML mapping")]

    try:
        loader = LensLoader()
        lens = loader._parse_lens(data, path)  # type: ignore[attr-defined]
    except Exception:
        # Fall back to manual construction
        try:
            patterns = [
                StructuralPattern(
                    name=p.get("name", ""),
                    abstract=p.get("abstract", ""),
                    maps_to=p.get("maps_to", []),
                )
                for p in data.get("structural_patterns", [])
            ]
            lens = Lens(
                name=data.get("name", ""),
                domain=data.get("domain", ""),
                subdomain=data.get("subdomain", ""),
                axioms=data.get("axioms", []),
                structural_patterns=patterns,
                injection_prompt=data.get("injection_prompt", ""),
            )
        except Exception as exc:
            return [LensValidationIssue(fname, "parse", f"Could not construct lens: {exc}")]

    return validate_lens(lens, fname)


def validate_all_lenses(library_dir: Path | None = None) -> dict[str, list[LensValidationIssue]]:
    """Validate all YAML files in the lens library. Returns {filename: issues}."""
    lib = library_dir or _DEFAULT_LIBRARY
    results: dict[str, list[LensValidationIssue]] = {}

    if not lib.is_dir():
        return results

    for path in sorted(lib.glob("*.yaml")):
        issues = validate_lens_file(path)
        if issues:
            results[path.name] = issues

    return results


def compute_lens_stats(library_dir: Path | None = None) -> LensStats:
    """Compute aggregate statistics about the lens library."""
    lib = library_dir or _DEFAULT_LIBRARY
    stats = LensStats()

    if not lib.is_dir():
        return stats

    domain_counts: dict[str, int] = {}
    total_axioms = 0
    total_patterns = 0

    for path in sorted(lib.glob("*.yaml")):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue

            domain = data.get("domain", "unknown")
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            axioms = data.get("axioms", [])
            patterns = data.get("structural_patterns", [])
            total_axioms += len(axioms)
            total_patterns += len(patterns)
            stats.total_lenses += 1
        except Exception:
            continue

    stats.domains = sorted(domain_counts.keys())
    stats.domain_counts = domain_counts
    stats.total_axioms = total_axioms
    stats.total_patterns = total_patterns
    stats.avg_axioms_per_lens = total_axioms / stats.total_lenses if stats.total_lenses > 0 else 0.0

    return stats


__all__ = ["LensValidationIssue", "LensStats", "validate_lens", "validate_lens_file", "validate_all_lenses", "compute_lens_stats"]
