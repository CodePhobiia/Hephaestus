"""
Lens Library Manager — loads, validates, versions, and caches cognitive lenses.

This loader handles both static YAML lenses and derived composite lenses used by
the adaptive bundle-proof selector.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hephaestus.lenses.cards import LensCard, compile_lens_card
from hephaestus.lenses.cells import CohesionCellIndex
from hephaestus.lenses.lineage import (
    LensLineage,
    build_composite_lineage,
    build_native_lineage,
    compute_reference_signature,
    validate_lineage,
)
from hephaestus.session.reference_lots import ReferenceLot

logger = logging.getLogger(__name__)

_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"name", "domain", "subdomain", "axioms", "structural_patterns", "injection_prompt"}
)
_REQUIRED_PATTERN_KEYS: frozenset[str] = frozenset({"name", "abstract", "maps_to"})
_DEFAULT_LIBRARY_DIR = Path(__file__).parent / "library"

_SUPPORTED_DOMAIN_FAMILIES: frozenset[str] = frozenset(
    {
        "physical_sciences",
        "biology",
        "economics",
        "myth",
        "linguistics",
        "arts",
        "military",
        "agriculture",
        "psychology",
        "mathematics",
        "engineering",
        "general",
    }
)

_DOMAIN_FAMILY_BY_ALIAS: dict[str, str] = {
    "physical_sciences": "physical_sciences",
    "physics": "physical_sciences",
    "chemistry": "physical_sciences",
    "astronomy": "physical_sciences",
    "geology": "physical_sciences",
    "meteorology": "physical_sciences",
    "oceanography": "physical_sciences",
    "materials": "physical_sciences",
    "materials_science": "physical_sciences",
    "biology": "biology",
    "neuroscience": "biology",
    "epidemiology": "biology",
    "ecology": "biology",
    "mycology": "biology",
    "economics": "economics",
    "finance": "economics",
    "markets": "economics",
    "business": "economics",
    "myth": "myth",
    "mythology": "myth",
    "folklore": "myth",
    "legend": "myth",
    "linguistics": "linguistics",
    "language": "linguistics",
    "semantics": "linguistics",
    "syntax": "linguistics",
    "pragmatics": "linguistics",
    "phonology": "linguistics",
    "arts": "arts",
    "art": "arts",
    "music": "arts",
    "film": "arts",
    "textiles": "arts",
    "military": "military",
    "martial_arts": "military",
    "sports": "military",
    "agriculture": "agriculture",
    "forestry": "agriculture",
    "cooking": "agriculture",
    "culinary": "agriculture",
    "psychology": "psychology",
    "sociology": "psychology",
    "mathematics": "mathematics",
    "math": "mathematics",
    "philosophy": "mathematics",
    "logic": "mathematics",
    "engineering": "engineering",
    "cs": "engineering",
    "computer_science": "engineering",
    "distributed_systems": "engineering",
    "machine_learning": "engineering",
    "software": "engineering",
    "architecture": "engineering",
    "urban_planning": "engineering",
    "navigation": "engineering",
    "infrastructure": "engineering",
    "systems": "engineering",
    "general": "general",
}

_DOMAIN_FAMILY_TOKEN_HINTS: dict[str, set[str]] = {
    "physical_sciences": {
        "physics",
        "physical",
        "chemistry",
        "chemical",
        "astronomy",
        "geology",
        "meteorology",
        "oceanography",
        "materials",
        "optics",
        "quantum",
        "thermodynamics",
    },
    "biology": {
        "biology",
        "bio",
        "immune",
        "ecology",
        "evolution",
        "epidemiology",
        "neuro",
        "neuroscience",
        "virology",
        "mycology",
        "coral",
        "reef",
    },
    "economics": {
        "economics",
        "economic",
        "finance",
        "financial",
        "market",
        "markets",
        "auction",
        "pricing",
        "mechanism",
        "incentive",
    },
    "myth": {"myth", "mythology", "folklore", "legend", "heroic", "narrative"},
    "linguistics": {
        "linguistics",
        "language",
        "syntax",
        "semantics",
        "pragmatics",
        "phonology",
        "grammar",
    },
    "arts": {
        "art",
        "arts",
        "music",
        "film",
        "textiles",
        "color",
        "counterpoint",
        "cinematography",
    },
    "military": {
        "military",
        "martial",
        "combat",
        "warfare",
        "sports",
        "boxing",
        "chess",
        "naval",
        "strategy",
    },
    "agriculture": {
        "agriculture",
        "forestry",
        "farm",
        "crop",
        "soil",
        "cooking",
        "culinary",
        "food",
        "fermentation",
        "maillard",
        "emulsification",
    },
    "psychology": {
        "psychology",
        "psychological",
        "behavior",
        "behavioral",
        "cognitive",
        "social",
        "sociology",
    },
    "mathematics": {
        "math",
        "mathematics",
        "proof",
        "logic",
        "topology",
        "chaos",
        "queueing",
        "information",
        "philosophy",
        "dynamical",
    },
    "engineering": {
        "engineering",
        "engineered",
        "distributed",
        "systems",
        "software",
        "computer",
        "network",
        "architecture",
        "urban",
        "planning",
        "navigation",
        "grid",
        "semiconductor",
        "traffic",
        "infrastructure",
    },
}


def _normalize_domain_label(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def classify_domain_family(
    domain: str | None,
    subdomain: str | None = None,
    explicit_family: str | None = None,
) -> str:
    normalized_explicit = _normalize_domain_label(explicit_family)
    if normalized_explicit:
        return _DOMAIN_FAMILY_BY_ALIAS.get(normalized_explicit, normalized_explicit)

    for raw in (domain, subdomain):
        normalized = _normalize_domain_label(raw)
        if normalized in _DOMAIN_FAMILY_BY_ALIAS:
            return _DOMAIN_FAMILY_BY_ALIAS[normalized]

    tokens: set[str] = set()
    for raw in (domain, subdomain):
        normalized = _normalize_domain_label(raw)
        if normalized:
            tokens.update(part for part in normalized.split("_") if part)

    for family, hints in _DOMAIN_FAMILY_TOKEN_HINTS.items():
        if tokens & hints:
            return family

    return "general"


def _slug(value: str) -> str:
    return _normalize_domain_label(value) or "lens"


def _reference_key_tokens(
    reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None,
) -> list[str]:
    if not reference_context:
        return []
    if isinstance(reference_context, Mapping):
        return [_slug(str(key)) for key in reference_context.keys()]
    tokens: list[str] = []
    for lot in reference_context:
        tokens.append(_slug(getattr(lot, "kind", "")))
        tokens.append(_slug(getattr(lot, "subject_key", "")))
    return [token for token in tokens if token]


@dataclass
class StructuralPattern:
    name: str
    abstract: str
    maps_to: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuralPattern:
        missing = _REQUIRED_PATTERN_KEYS - data.keys()
        if missing:
            raise ValueError(f"Structural pattern missing required keys: {missing}")
        maps_to = data["maps_to"]
        if isinstance(maps_to, str):
            maps_to = [maps_to]
        return cls(
            name=str(data["name"]),
            abstract=str(data["abstract"]),
            maps_to=[str(item) for item in maps_to],
        )


@dataclass
class Lens:
    name: str
    domain: str
    subdomain: str
    axioms: list[str]
    structural_patterns: list[StructuralPattern]
    injection_prompt: str
    source_file: Path = field(default_factory=Path)
    tags: list[str] = field(default_factory=list)
    distance_hints: dict[str, float] = field(default_factory=dict)
    domain_family: str = ""
    source_kind: str = "library"
    version: int = 1
    explicit_lens_id: str = ""
    parent_lens_ids: tuple[str, ...] = ()
    reference_signature: str = ""
    lineage_token: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.domain = self.domain.lower().strip()
        self.subdomain = self.subdomain.lower().strip()
        if not self.domain_family:
            self.domain_family = classify_domain_family(self.domain, self.subdomain)
        self.source_kind = _slug(self.source_kind or "library")
        self.parent_lens_ids = tuple(_slug(item) for item in self.parent_lens_ids if item)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_file: Path | None = None) -> Lens:
        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"Lens missing required keys: {missing!r}")

        axioms = data["axioms"]
        if not isinstance(axioms, list) or len(axioms) < 2:
            raise ValueError(f"Lens 'axioms' must be a list with at least 2 entries, got: {axioms!r}")

        raw_patterns = data["structural_patterns"]
        if not isinstance(raw_patterns, list) or len(raw_patterns) < 1:
            raise ValueError("Lens 'structural_patterns' must be a non-empty list")

        patterns = [StructuralPattern.from_dict(pattern) for pattern in raw_patterns]
        injection = data["injection_prompt"]
        if not isinstance(injection, str) or len(injection.strip()) < 20:
            raise ValueError("Lens 'injection_prompt' must be a non-empty string (≥20 chars)")

        return cls(
            name=str(data["name"]),
            domain=str(data["domain"]),
            subdomain=str(data["subdomain"]),
            axioms=[str(item) for item in axioms],
            structural_patterns=patterns,
            injection_prompt=injection.strip(),
            source_file=source_file or Path(),
            tags=[str(item) for item in data.get("tags", [])],
            distance_hints={str(k): float(v) for k, v in dict(data.get("distance_hints", {})).items()},
            domain_family=classify_domain_family(
                str(data["domain"]),
                str(data["subdomain"]),
                str(data.get("domain_family", "")),
            ),
            source_kind=str(data.get("source_kind", "library")),
            version=int(data.get("version", 1)),
            explicit_lens_id=str(data.get("lens_id", "")),
            parent_lens_ids=tuple(str(item) for item in list(data.get("parent_lens_ids", []) or [])),
            reference_signature=str(data.get("reference_signature", "")),
            metadata={str(k): str(v) for k, v in dict(data.get("metadata", {})).items()},
        )

    @property
    def lens_id(self) -> str:
        if self.explicit_lens_id:
            return self.explicit_lens_id
        if self.source_file and self.source_file.stem:
            return self.source_file.stem
        return f"{self.domain}_{self.subdomain}".replace(" ", "_")

    @property
    def all_maps_to(self) -> set[str]:
        result: set[str] = set()
        for pattern in self.structural_patterns:
            result.update(pattern.maps_to)
        return result

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "name": self.name,
            "domain": self.domain,
            "domain_family": self.domain_family,
            "subdomain": self.subdomain,
            "axiom_count": len(self.axioms),
            "pattern_count": len(self.structural_patterns),
            "maps_to": sorted(self.all_maps_to),
            "tags": list(self.tags),
            "source_kind": self.source_kind,
            "version": self.version,
            "parent_lens_ids": list(self.parent_lens_ids),
        }

    def __repr__(self) -> str:
        return f"Lens(id={self.lens_id!r}, kind={self.source_kind!r}, version={self.version})"


class LensValidationError(Exception):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid lens {path.name!r}: {reason}")


class LensLoader:
    """Loads, versions, and caches library plus derived lenses."""

    def __init__(
        self,
        library_dir: Path | str | None = None,
        hot_reload: bool = False,
        allow_derived_composites: bool = True,
    ) -> None:
        self._library_dir = Path(library_dir) if library_dir else _DEFAULT_LIBRARY_DIR
        self._hot_reload = hot_reload
        self._allow_derived_composites = allow_derived_composites
        self._cache: dict[str, tuple[Lens, float]] = {}
        self._card_cache: dict[str, LensCard] = {}
        self._lineage_cache: dict[str, LensLineage] = {}
        self._load_errors: dict[str, str] = {}
        self._library_revision = 1

        self._derived_lenses: dict[str, Lens] = {}
        self._derived_cards: dict[str, LensCard] = {}
        self._derived_lineages: dict[str, LensLineage] = {}
        self._derived_invalid: dict[str, tuple[str, ...]] = {}
        self._cell_index_cache: dict[str, CohesionCellIndex] = {}

    @property
    def library_dir(self) -> Path:
        return self._library_dir

    @property
    def hot_reload(self) -> bool:
        return self._hot_reload

    @property
    def allow_derived_composites(self) -> bool:
        return self._allow_derived_composites

    @property
    def library_revision(self) -> int:
        return self._library_revision

    def _yaml_files(self) -> list[Path]:
        if not self._library_dir.is_dir():
            raise FileNotFoundError(f"Lens library directory not found: {self._library_dir}")
        return sorted(self._library_dir.glob("*.yaml"))

    def _load_file(self, path: Path) -> Lens:
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
        if lens_id not in self._cache:
            return None
        cached_lens, cached_mtime = self._cache[lens_id]
        if self._hot_reload and self._get_mtime(path) != cached_mtime:
            logger.debug("Hot-reload detected change in %s", path.name)
            return None
        return cached_lens

    def _invalidate_index_cache(self) -> None:
        self._cell_index_cache.clear()

    def _cache_put(self, lens: Lens, path: Path) -> None:
        card = compile_lens_card(lens)
        lineage = build_native_lineage(
            lens_id=lens.lens_id,
            version=lens.version,
            card_fingerprint64=card.fingerprint64,
            loader_revision=self._library_revision,
            source_kind=lens.source_kind,
        )
        lens.lineage_token = lineage.proof_token
        card.lineage_token = lineage.proof_token
        self._cache[lens.lens_id] = (lens, self._get_mtime(path))
        self._card_cache[lens.lens_id] = card
        self._lineage_cache[lens.lens_id] = lineage
        self._invalidate_index_cache()

    def _validate_derived(
        self,
        *,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> list[str]:
        valid_ids: list[str] = []
        current_cards = {
            **self._card_cache,
            **self._derived_cards,
        }
        current_lineages = {
            **self._lineage_cache,
            **self._derived_lineages,
        }
        for lens_id, lineage in list(self._derived_lineages.items()):
            validation = validate_lineage(
                lineage,
                current_cards=current_cards,
                current_lineages=current_lineages,
                loader_revision=self._library_revision,
                reference_context=reference_context,
            )
            if validation.valid:
                self._derived_invalid.pop(lens_id, None)
                valid_ids.append(lens_id)
                continue
            self._derived_invalid[lens_id] = validation.reasons
            self._derived_lineages[lens_id] = lineage.mark_stale(*validation.reasons)
        return valid_ids

    def load_all(
        self,
        skip_errors: bool = False,
        *,
        include_derived: bool = True,
        include_stale: bool = False,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> dict[str, Lens]:
        self._load_errors.clear()
        lenses: dict[str, Lens] = {}
        for path in self._yaml_files():
            stem = path.stem
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

        if include_derived and self._allow_derived_composites and self._derived_lenses:
            valid_ids = set(self._validate_derived(reference_context=reference_context))
            for lens_id, lens in self._derived_lenses.items():
                if lens_id in valid_ids or (include_stale and lens_id in self._derived_invalid):
                    lenses[lens_id] = lens

        return lenses

    def load_one(
        self,
        lens_id: str,
        *,
        include_stale: bool = False,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> Lens:
        if lens_id in self._derived_lenses:
            valid_ids = set(self._validate_derived(reference_context=reference_context))
            if lens_id in valid_ids or include_stale:
                return self._derived_lenses[lens_id]
            reasons = ", ".join(self._derived_invalid.get(lens_id, ()))
            raise ValueError(f"Derived lens {lens_id!r} is stale: {reasons}")

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
        lenses = self.load_all(skip_errors=skip_errors)
        return sorted(
            [lens.to_metadata_dict() for lens in lenses.values()],
            key=lambda item: item["lens_id"],
        )

    def get_by_domain(self, domain: str) -> list[Lens]:
        target = domain.lower().strip()
        return [
            lens
            for lens in self.load_all(skip_errors=True).values()
            if lens.domain == target
        ]

    def get_by_maps_to(self, problem_type: str) -> list[Lens]:
        target = problem_type.lower().strip()
        return [
            lens
            for lens in self.load_all(skip_errors=True).values()
            if target in {item.lower() for item in lens.all_maps_to}
        ]

    def reload(self) -> dict[str, Lens]:
        self._library_revision += 1
        self._cache.clear()
        self._card_cache.clear()
        self._lineage_cache.clear()
        self._invalidate_index_cache()
        if self._derived_lenses:
            self.invalidate_derived_lenses("library reloaded")
        return self.load_all(skip_errors=False)

    def invalidate_derived_lenses(self, reason: str) -> None:
        for lens_id, lineage in list(self._derived_lineages.items()):
            self._derived_lineages[lens_id] = lineage.mark_stale(reason)
            self._derived_invalid[lens_id] = self._derived_lineages[lens_id].stale_reasons
        self._invalidate_index_cache()

    def register_derived_lens(
        self,
        lens: Lens,
        *,
        card: LensCard | None = None,
        lineage: LensLineage | None = None,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> Lens:
        if lens.lens_id in self._cache:
            raise ValueError(f"Cannot overwrite library lens {lens.lens_id!r} with derived lens")

        derived_card = card or compile_lens_card(lens, reference_context=reference_context or {})
        if lineage is None:
            if lens.source_kind == "derived_composite" and lens.parent_lens_ids:
                parent_cards = [self.get_card(parent_id) for parent_id in lens.parent_lens_ids]
                parent_lineages = [self.get_lineage(parent_id) for parent_id in lens.parent_lens_ids]
                lineage = build_composite_lineage(
                    lens_id=lens.lens_id,
                    version=lens.version,
                    card_fingerprint64=derived_card.fingerprint64,
                    loader_revision=self._library_revision,
                    parent_cards=parent_cards,
                    parent_lineages=parent_lineages,
                    derivation=lens.metadata.get("derivation", "composite"),
                    reference_context=reference_context,
                    metadata=lens.metadata,
                )
            else:
                lineage = build_native_lineage(
                    lens_id=lens.lens_id,
                    version=lens.version,
                    card_fingerprint64=derived_card.fingerprint64,
                    loader_revision=self._library_revision,
                    source_kind=lens.source_kind,
                    derivation=lens.metadata.get("derivation", "derived"),
                )

        lens.lineage_token = lineage.proof_token
        lens.reference_signature = lineage.reference_digest or lens.reference_signature
        derived_card.lineage_token = lineage.proof_token
        derived_card.reference_signature = lineage.reference_digest or derived_card.reference_signature
        self._derived_lenses[lens.lens_id] = lens
        self._derived_cards[lens.lens_id] = derived_card
        self._derived_lineages[lens.lens_id] = lineage
        self._derived_invalid.pop(lens.lens_id, None)
        self._invalidate_index_cache()
        return lens

    def derive_composite_lens(
        self,
        *,
        name: str,
        parent_lens_ids: Sequence[str],
        injection_prompt: str | None = None,
        tags: Sequence[str] | None = None,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
        lens_id: str | None = None,
    ) -> Lens:
        if not self._allow_derived_composites:
            raise RuntimeError("Derived lens composites are disabled by configuration")
        unique_parent_ids = tuple(dict.fromkeys(_slug(parent_id) for parent_id in parent_lens_ids if parent_id))
        if len(unique_parent_ids) < 2:
            raise ValueError("Composite lenses require at least two parent lenses")

        parents = [self.load_one(parent_id) for parent_id in unique_parent_ids]
        parent_cards = [self.get_card(parent_id) for parent_id in unique_parent_ids]
        parent_lineages = [self.get_lineage(parent_id) for parent_id in unique_parent_ids]
        maps_to = sorted({shape for card in parent_cards for shape in card.transfer_shape})
        ref_signature = compute_reference_signature(reference_context)

        axioms: list[str] = []
        for card in parent_cards:
            if card.evidence_atoms:
                axioms.append(f"{card.domain_name} contributes {card.evidence_atoms[0]}.")
        shared_terms = sorted(
            set.intersection(*[set(card.transfer_shape) for card in parent_cards])
        ) if parent_cards else []
        if shared_terms:
            axioms.append(
                "Composite transfer is stabilized by shared structural commitments: "
                + ", ".join(shared_terms[:6])
                + "."
            )
        axioms.append(
            "The bundle remains valid only while all parent cards and reference anchors remain current."
        )

        patterns = [
            StructuralPattern(
                name="composite_bridge",
                abstract=(
                    "Merge structurally distant mechanisms into a coordinated fold-state bundle "
                    "while preserving lineage-proof traceability."
                ),
                maps_to=maps_to[:8] or ["composite_transfer"],
            )
        ]
        if len(maps_to) > 3:
            patterns.append(
                StructuralPattern(
                    name="conditional_cohesion",
                    abstract=(
                        "Higher-order compatibility appears only when the combined transfer shape "
                        "covers multiple complementary query terms."
                    ),
                    maps_to=maps_to[3:10],
                )
            )

        composite_lens_id = lens_id or (
            f"composite_{_slug(name)}_{hashlib.sha256('|'.join(unique_parent_ids).encode('utf-8')).hexdigest()[:8]}"
        )
        merged_tags = sorted(
            {
                *[tag for parent in parents for tag in parent.tags],
                *(tags or ()),
                *_reference_key_tokens(reference_context),
                "composite",
                "bundle",
            }
        )
        prompt = injection_prompt or (
            f"Reason using the composite fold-state of {', '.join(parent.name for parent in parents)}. "
            "Preserve each parent mechanism, respect lineage invalidation, and only transfer mechanisms "
            "that survive bundle proof validation."
        )
        lens = Lens(
            name=name,
            domain="composite",
            subdomain=_slug(name),
            axioms=axioms[:8],
            structural_patterns=patterns,
            injection_prompt=prompt,
            source_file=Path(),
            tags=merged_tags,
            domain_family="general",
            source_kind="derived_composite",
            version=max(parent.version for parent in parents) + 1,
            explicit_lens_id=composite_lens_id,
            parent_lens_ids=unique_parent_ids,
            reference_signature=ref_signature,
            metadata={
                "derivation": "bundle_composite",
                "parent_count": str(len(unique_parent_ids)),
            },
        )
        card = compile_lens_card(
            lens,
            parent_cards=parent_cards,
            reference_context={"reference_keys": _reference_key_tokens(reference_context)},
        )
        lineage = build_composite_lineage(
            lens_id=lens.lens_id,
            version=lens.version,
            card_fingerprint64=card.fingerprint64,
            loader_revision=self._library_revision,
            parent_cards=parent_cards,
            parent_lineages=parent_lineages,
            derivation="bundle_composite",
            reference_context=reference_context,
            metadata=lens.metadata,
        )
        return self.register_derived_lens(
            lens,
            card=card,
            lineage=lineage,
            reference_context=reference_context,
        )

    def get_card(self, lens_id: str) -> LensCard:
        if lens_id in self._derived_cards:
            valid_ids = set(self._validate_derived(reference_context=None))
            if lens_id not in valid_ids and lens_id in self._derived_invalid:
                reasons = ", ".join(self._derived_invalid[lens_id])
                raise ValueError(f"Derived lens card {lens_id!r} is stale: {reasons}")
            return self._derived_cards[lens_id]
        if lens_id not in self._card_cache:
            lens = self.load_one(lens_id)
            self._cache_put(lens, lens.source_file)
        return self._card_cache[lens_id]

    def get_all_cards(
        self,
        *,
        skip_errors: bool = True,
        include_derived: bool = True,
        include_stale: bool = False,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> dict[str, LensCard]:
        self.load_all(
            skip_errors=skip_errors,
            include_derived=include_derived,
            include_stale=include_stale,
            reference_context=reference_context,
        )
        cards = dict(self._card_cache)
        if include_derived:
            valid_ids = set(self._validate_derived(reference_context=reference_context))
            for lens_id, card in self._derived_cards.items():
                if lens_id in valid_ids or (include_stale and lens_id in self._derived_invalid):
                    cards[lens_id] = card
        return cards

    def get_lineage(
        self,
        lens_id: str,
        *,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> LensLineage:
        if lens_id in self._derived_lineages:
            valid_ids = set(self._validate_derived(reference_context=reference_context))
            if lens_id not in valid_ids and lens_id in self._derived_invalid:
                reasons = ", ".join(self._derived_invalid[lens_id])
                raise ValueError(f"Derived lens lineage {lens_id!r} is stale: {reasons}")
            return self._derived_lineages[lens_id]
        if lens_id not in self._lineage_cache:
            lens = self.load_one(lens_id)
            self._cache_put(lens, lens.source_file)
        return self._lineage_cache[lens_id]

    def get_all_lineages(
        self,
        *,
        skip_errors: bool = True,
        include_derived: bool = True,
        include_stale: bool = False,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> dict[str, LensLineage]:
        self.load_all(
            skip_errors=skip_errors,
            include_derived=include_derived,
            include_stale=include_stale,
            reference_context=reference_context,
        )
        lineages = dict(self._lineage_cache)
        if include_derived:
            valid_ids = set(self._validate_derived(reference_context=reference_context))
            for lens_id, lineage in self._derived_lineages.items():
                if lens_id in valid_ids or (include_stale and lens_id in self._derived_invalid):
                    lineages[lens_id] = lineage
        return lineages

    def get_cell_index(
        self,
        *,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
        include_derived: bool = True,
    ) -> CohesionCellIndex:
        ref_signature = compute_reference_signature(reference_context)
        state_signature = self.state_signature(
            reference_context=reference_context,
            include_derived=include_derived,
        )
        cache_key = f"{state_signature}:{ref_signature}"
        if cache_key in self._cell_index_cache:
            return self._cell_index_cache[cache_key]

        cards = self.get_all_cards(
            include_derived=include_derived,
            reference_context=reference_context,
        )
        lineages = self.get_all_lineages(
            include_derived=include_derived,
            reference_context=reference_context,
        )
        index = CohesionCellIndex.build(
            cards,
            lineages=lineages,
            reference_context=reference_context,
        )
        self._cell_index_cache = {cache_key: index}
        return index

    def state_signature(
        self,
        *,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
        include_derived: bool = True,
    ) -> str:
        cards = self.get_all_cards(
            include_derived=include_derived,
            reference_context=reference_context,
        )
        lineages = self.get_all_lineages(
            include_derived=include_derived,
            reference_context=reference_context,
        )
        parts = [
            f"rev:{self._library_revision}",
            *[
                f"{lens_id}:{card.fingerprint64}:{lineages[lens_id].proof_token}"
                for lens_id, card in sorted(cards.items())
                if lens_id in lineages
            ],
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:16]

    def get_load_errors(self) -> dict[str, str]:
        return dict(self._load_errors)

    def __len__(self) -> int:
        return len(self._cache) + len(
            [lens_id for lens_id in self._derived_lenses if lens_id not in self._derived_invalid]
        )

    def __contains__(self, lens_id: str) -> bool:
        return lens_id in self._derived_lenses or (self._library_dir / f"{lens_id}.yaml").exists()

    def __repr__(self) -> str:
        return (
            f"LensLoader(library_dir={self._library_dir!r}, cached={len(self._cache)}, "
            f"derived={len(self._derived_lenses)}, hot_reload={self._hot_reload}, "
            f"revision={self._library_revision})"
        )


__all__ = [
    "Lens",
    "LensLoader",
    "LensValidationError",
    "StructuralPattern",
    "_DEFAULT_LIBRARY_DIR",
    "_SUPPORTED_DOMAIN_FAMILIES",
    "classify_domain_family",
]
