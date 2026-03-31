"""
Lens Library Manager — loads, validates, and caches cognitive lens YAML files.

A cognitive lens is a curated axiom set from a knowledge domain that, when injected
mid-reasoning, forces an LLM to reason from a structurally foreign frame.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Required top-level keys in every lens YAML
_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"name", "domain", "subdomain", "axioms", "structural_patterns", "injection_prompt"}
)

# Required keys inside each structural_pattern entry
_REQUIRED_PATTERN_KEYS: frozenset[str] = frozenset({"name", "abstract", "maps_to"})

# Default lens library directory (relative to this file)
_DEFAULT_LIBRARY_DIR = Path(__file__).parent / "library"


@dataclass
class StructuralPattern:
    """A named pattern extracted from a domain with abstract description and problem mappings."""

    name: str
    abstract: str
    maps_to: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuralPattern":
        missing = _REQUIRED_PATTERN_KEYS - data.keys()
        if missing:
            raise ValueError(f"Structural pattern missing required keys: {missing}")
        maps_to = data["maps_to"]
        if isinstance(maps_to, str):
            maps_to = [maps_to]
        return cls(
            name=str(data["name"]),
            abstract=str(data["abstract"]),
            maps_to=[str(m) for m in maps_to],
        )


@dataclass
class Lens:
    """
    A cognitive lens — a curated set of axioms and patterns from one knowledge domain
    that can be injected into an LLM's reasoning to force cross-domain thinking.
    """

    name: str
    domain: str
    subdomain: str
    axioms: list[str]
    structural_patterns: list[StructuralPattern]
    injection_prompt: str
    source_file: Path = field(default_factory=Path)

    # Optional metadata
    tags: list[str] = field(default_factory=list)
    distance_hints: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_file: Path | None = None) -> "Lens":
        """Parse and validate a lens from a raw YAML dictionary."""
        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"Lens missing required keys: {missing!r}")

        axioms = data["axioms"]
        if not isinstance(axioms, list) or len(axioms) < 2:
            raise ValueError(f"Lens 'axioms' must be a list with at least 2 entries, got: {axioms!r}")

        raw_patterns = data["structural_patterns"]
        if not isinstance(raw_patterns, list) or len(raw_patterns) < 1:
            raise ValueError("Lens 'structural_patterns' must be a non-empty list")

        patterns = [StructuralPattern.from_dict(p) for p in raw_patterns]

        injection = data["injection_prompt"]
        if not isinstance(injection, str) or len(injection.strip()) < 20:
            raise ValueError("Lens 'injection_prompt' must be a non-empty string (≥20 chars)")

        return cls(
            name=str(data["name"]),
            domain=str(data["domain"]).lower().strip(),
            subdomain=str(data["subdomain"]).lower().strip(),
            axioms=[str(a) for a in axioms],
            structural_patterns=patterns,
            injection_prompt=injection.strip(),
            source_file=source_file or Path(),
            tags=[str(t) for t in data.get("tags", [])],
            distance_hints=dict(data.get("distance_hints", {})),
        )

    @property
    def lens_id(self) -> str:
        """
        Stable identifier derived from the YAML filename stem (e.g., biology_immune).

        The filename stem is the canonical ID because some lenses have single-word
        names (e.g., agriculture, epidemiology) where domain == subdomain would
        produce a redundant double (agriculture_agriculture).
        """
        if self.source_file and self.source_file.stem:
            return self.source_file.stem
        # Fallback: derive from domain_subdomain
        return f"{self.domain}_{self.subdomain}".replace(" ", "_")

    @property
    def all_maps_to(self) -> set[str]:
        """Flat union of all maps_to tags across all structural patterns."""
        result: set[str] = set()
        for p in self.structural_patterns:
            result.update(p.maps_to)
        return result

    def to_metadata_dict(self) -> dict[str, Any]:
        """Return lightweight metadata (no axioms/injection_prompt) for listing."""
        return {
            "lens_id": self.lens_id,
            "name": self.name,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "axiom_count": len(self.axioms),
            "pattern_count": len(self.structural_patterns),
            "maps_to": sorted(self.all_maps_to),
            "tags": self.tags,
        }

    def __repr__(self) -> str:
        return f"Lens(id={self.lens_id!r}, name={self.name!r})"


class LensValidationError(Exception):
    """Raised when a lens YAML fails schema validation."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid lens {path.name!r}: {reason}")


class LensLoader:
    """
    Loads, validates, and caches cognitive lens YAML files from the library directory.

    Features:
    - Lazy loading (load on first access)
    - In-memory cache for fast repeated access
    - Hot-reload support for development (watches file mtime)
    - Schema validation on every load
    - Friendly error messages for malformed lenses
    """

    def __init__(
        self,
        library_dir: Path | str | None = None,
        hot_reload: bool = False,
    ) -> None:
        """
        Args:
            library_dir: Directory containing YAML lens files.
                         Defaults to the bundled library/ directory.
            hot_reload: If True, re-read files when mtime changes (dev mode).
        """
        self._library_dir = Path(library_dir) if library_dir else _DEFAULT_LIBRARY_DIR
        self._hot_reload = hot_reload

        # Cache: lens_id → (Lens, mtime_at_load)
        self._cache: dict[str, tuple[Lens, float]] = {}
        # Errors encountered during bulk load
        self._load_errors: dict[str, str] = {}

    @property
    def library_dir(self) -> Path:
        return self._library_dir

    @property
    def hot_reload(self) -> bool:
        return self._hot_reload

    def _yaml_files(self) -> list[Path]:
        """Return sorted list of .yaml files in the library directory."""
        if not self._library_dir.is_dir():
            raise FileNotFoundError(f"Lens library directory not found: {self._library_dir}")
        return sorted(self._library_dir.glob("*.yaml"))

    def _load_file(self, path: Path) -> Lens:
        """Parse a single YAML file into a Lens object, with full validation."""
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LensValidationError(path, f"Cannot read file: {exc}") from exc

        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise LensValidationError(path, f"YAML parse error: {exc}") from exc

        if not isinstance(data, dict):
            raise LensValidationError(path, f"Expected a YAML mapping, got {type(data).__name__}")

        try:
            lens = Lens.from_dict(data, source_file=path)
        except ValueError as exc:
            raise LensValidationError(path, str(exc)) from exc

        return lens

    def _get_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _cache_get(self, lens_id: str, path: Path) -> Lens | None:
        """Return cached lens if valid (or if hot_reload is False)."""
        if lens_id not in self._cache:
            return None
        cached_lens, cached_mtime = self._cache[lens_id]
        if self._hot_reload:
            current_mtime = self._get_mtime(path)
            if current_mtime != cached_mtime:
                logger.debug("Hot-reload: %s mtime changed, reloading", path.name)
                return None
        return cached_lens

    def _cache_put(self, lens: Lens, path: Path) -> None:
        self._cache[lens.lens_id] = (lens, self._get_mtime(path))

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def load_all(self, skip_errors: bool = False) -> dict[str, Lens]:
        """
        Load every lens YAML in the library directory.

        Args:
            skip_errors: If True, log errors and continue. If False, raise on first error.

        Returns:
            Mapping of lens_id → Lens for all successfully loaded lenses.
        """
        self._load_errors.clear()
        lenses: dict[str, Lens] = {}

        for path in self._yaml_files():
            # Derive expected lens_id from filename (before loading)
            stem = path.stem  # e.g. "biology_immune"
            cached = self._cache_get(stem, path)
            if cached is not None:
                lenses[cached.lens_id] = cached
                continue

            try:
                lens = self._load_file(path)
                self._cache_put(lens, path)
                lenses[lens.lens_id] = lens
            except LensValidationError as exc:
                self._load_errors[path.name] = str(exc)
                if skip_errors:
                    logger.warning("Skipping invalid lens: %s", exc)
                else:
                    raise

        return lenses

    def load_one(self, lens_id: str) -> Lens:
        """
        Load a single lens by its ID (e.g., 'biology_immune').

        Raises:
            FileNotFoundError: If the lens file doesn't exist.
            LensValidationError: If the file is invalid.
        """
        path = self._library_dir / f"{lens_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Lens not found: {lens_id!r} (looked for {path})")

        cached = self._cache_get(lens_id, path)
        if cached is not None:
            return cached

        lens = self._load_file(path)
        self._cache_put(lens, path)
        return lens

    def list_available(self, skip_errors: bool = True) -> list[dict[str, Any]]:
        """
        Return lightweight metadata for all available lenses (no heavy axiom text).

        Args:
            skip_errors: Skip malformed files instead of raising.

        Returns:
            List of metadata dicts (sorted by lens_id).
        """
        lenses = self.load_all(skip_errors=skip_errors)
        return sorted(
            [lens.to_metadata_dict() for lens in lenses.values()],
            key=lambda d: d["lens_id"],
        )

    def get_by_domain(self, domain: str) -> list[Lens]:
        """Return all lenses whose domain matches (case-insensitive)."""
        all_lenses = self.load_all(skip_errors=True)
        target = domain.lower().strip()
        return [l for l in all_lenses.values() if l.domain == target]

    def get_by_maps_to(self, problem_type: str) -> list[Lens]:
        """Return lenses that have the given problem_type in any pattern's maps_to."""
        all_lenses = self.load_all(skip_errors=True)
        target = problem_type.lower().strip()
        return [l for l in all_lenses.values() if target in {m.lower() for m in l.all_maps_to}]

    def reload(self) -> dict[str, Lens]:
        """Force-clear cache and reload everything from disk."""
        self._cache.clear()
        return self.load_all(skip_errors=False)

    def get_load_errors(self) -> dict[str, str]:
        """Return any errors encountered during the last load_all() call."""
        return dict(self._load_errors)

    def __len__(self) -> int:
        """Number of successfully cached lenses."""
        return len(self._cache)

    def __contains__(self, lens_id: str) -> bool:
        return (self._library_dir / f"{lens_id}.yaml").exists()

    def __repr__(self) -> str:
        return (
            f"LensLoader(library_dir={self._library_dir!r}, "
            f"cached={len(self._cache)}, hot_reload={self._hot_reload})"
        )
