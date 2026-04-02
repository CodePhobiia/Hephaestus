"""Lens disclosure cards.

Cards are the normalized typed surface that powers bundle retrieval.  They are
derived from the raw YAML lens plus any lineage metadata already attached to
the lens object.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hephaestus.lenses.loader import Lens


_STOP_WORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "into",
    "through",
    "about",
    "this",
    "when",
    "where",
    "their",
    "they",
    "have",
    "must",
    "under",
    "over",
    "uses",
    "using",
    "real",
    "well",
    "same",
    "problem",
    "domain",
    "system",
    "systems",
    "process",
    "across",
    "within",
    "between",
    "which",
    "will",
}
_BASELINE_PATTERNS = (
    "cache",
    "retry",
    "queue",
    "observer",
    "state machine",
    "load balancing",
    "backoff",
    "replication",
)


def _normalize_token(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _normalize_phrase(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s:/-]+", "", value)
    return value.strip(" -:/")


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", text.lower())
    return [
        _normalize_token(word)
        for word in words
        if word not in _STOP_WORDS
    ]


def _uniq(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _normalized_tokens(items: Sequence[str], *, limit: int) -> list[str]:
    tokens = [_normalize_token(item) for item in items if _normalize_token(item)]
    return _uniq(tokens)[:limit]


def _normalized_phrases(items: Sequence[str], *, limit: int) -> list[str]:
    phrases = [_normalize_phrase(item) for item in items if _normalize_phrase(item)]
    return _uniq(phrases)[:limit]


def _stable_fingerprint(payload: Mapping[str, Any]) -> int:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass
class SpanRef:
    file_id: str
    start_line: int
    end_line: int
    yaml_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "yaml_path": self.yaml_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SpanRef:
        return cls(
            file_id=str(data.get("file_id", "")),
            start_line=int(data.get("start_line", 0)),
            end_line=int(data.get("end_line", 0)),
            yaml_path=str(data.get("yaml_path", "")),
        )


@dataclass
class LensCard:
    lens_id: str
    domain_name: str
    mechanism_signature: list[str] = field(default_factory=list)
    transfer_shape: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    disallowed_baselines: list[str] = field(default_factory=list)
    evidence_atoms: list[str] = field(default_factory=list)
    novelty_axes: list[str] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)
    provenance: dict[str, list[SpanRef]] = field(default_factory=dict)
    fingerprint64: int = 0
    version: int = 1
    domain_family: str = "general"
    source_kind: str = "library"
    parent_lens_ids: tuple[str, ...] = ()
    lineage_token: str = ""
    reference_signature: str = ""

    def __post_init__(self) -> None:
        self.domain_name = re.sub(r"\s+", " ", str(self.domain_name).strip())
        self.domain_family = _normalize_token(self.domain_family) or "general"
        self.source_kind = _normalize_token(self.source_kind) or "library"
        self.mechanism_signature = _normalized_tokens(self.mechanism_signature, limit=20)
        self.transfer_shape = _normalized_tokens(self.transfer_shape, limit=20)
        self.constraints = _normalized_tokens(self.constraints, limit=16)
        self.disallowed_baselines = _normalized_tokens(self.disallowed_baselines, limit=12)
        self.evidence_atoms = _normalized_phrases(self.evidence_atoms, limit=20)
        self.novelty_axes = _normalized_tokens(self.novelty_axes, limit=16)
        self.parent_lens_ids = tuple(_normalized_tokens(self.parent_lens_ids, limit=12))
        self.lineage_token = str(self.lineage_token)
        self.reference_signature = str(self.reference_signature)
        self.confidence = [
            min(1.0, max(0.0, float(value)))
            for value in self.confidence[: max(
                1,
                len(self.mechanism_signature)
                + len(self.transfer_shape)
                + len(self.constraints),
            )]
        ]
        if not self.confidence:
            self.confidence = self._default_confidence()
        if not self.fingerprint64:
            self.fingerprint64 = self._compute_fingerprint()

    def _default_confidence(self) -> list[float]:
        values: list[float] = []
        values.extend([0.92] * min(4, len(self.mechanism_signature)))
        values.extend([0.86] * min(4, len(self.transfer_shape)))
        values.extend([0.78] * min(4, len(self.constraints)))
        values.extend([0.7] * min(3, len(self.evidence_atoms)))
        values.extend([0.62] * min(3, len(self.novelty_axes)))
        return values or [0.75]

    def _compute_fingerprint(self) -> int:
        payload = {
            "lens_id": self.lens_id,
            "domain_name": _normalize_phrase(self.domain_name),
            "domain_family": self.domain_family,
            "source_kind": self.source_kind,
            "mechanism_signature": self.mechanism_signature,
            "transfer_shape": self.transfer_shape,
            "constraints": self.constraints,
            "disallowed_baselines": self.disallowed_baselines,
            "evidence_atoms": self.evidence_atoms,
            "novelty_axes": self.novelty_axes,
            "parent_lens_ids": list(self.parent_lens_ids),
            "reference_signature": self.reference_signature,
            "version": self.version,
        }
        return _stable_fingerprint(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "domain_name": self.domain_name,
            "mechanism_signature": list(self.mechanism_signature),
            "transfer_shape": list(self.transfer_shape),
            "constraints": list(self.constraints),
            "disallowed_baselines": list(self.disallowed_baselines),
            "evidence_atoms": list(self.evidence_atoms),
            "novelty_axes": list(self.novelty_axes),
            "confidence": list(self.confidence),
            "provenance": {
                key: [ref.to_dict() for ref in refs]
                for key, refs in self.provenance.items()
            },
            "fingerprint64": self.fingerprint64,
            "version": self.version,
            "domain_family": self.domain_family,
            "source_kind": self.source_kind,
            "parent_lens_ids": list(self.parent_lens_ids),
            "lineage_token": self.lineage_token,
            "reference_signature": self.reference_signature,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LensCard:
        provenance = {
            str(key): [SpanRef.from_dict(item) for item in list(value or [])]
            for key, value in dict(data.get("provenance", {}) or {}).items()
        }
        return cls(
            lens_id=str(data["lens_id"]),
            domain_name=str(data.get("domain_name", "")),
            mechanism_signature=list(data.get("mechanism_signature", []) or []),
            transfer_shape=list(data.get("transfer_shape", []) or []),
            constraints=list(data.get("constraints", []) or []),
            disallowed_baselines=list(data.get("disallowed_baselines", []) or []),
            evidence_atoms=list(data.get("evidence_atoms", []) or []),
            novelty_axes=list(data.get("novelty_axes", []) or []),
            confidence=[float(value) for value in list(data.get("confidence", []) or [])],
            provenance=provenance,
            fingerprint64=int(data.get("fingerprint64", 0)),
            version=int(data.get("version", 1)),
            domain_family=str(data.get("domain_family", "general")),
            source_kind=str(data.get("source_kind", "library")),
            parent_lens_ids=tuple(data.get("parent_lens_ids", []) or []),
            lineage_token=str(data.get("lineage_token", "")),
            reference_signature=str(data.get("reference_signature", "")),
        )

    def summary_text(self) -> str:
        return (
            f"{self.domain_name} | family={self.domain_family} | "
            f"mech={', '.join(self.mechanism_signature[:6])} | "
            f"shape={', '.join(self.transfer_shape[:4])} | "
            f"constraints={', '.join(self.constraints[:4])}"
        )


def compile_lens_card(
    lens: Lens,
    *,
    parent_cards: Sequence[LensCard] | None = None,
    reference_context: Mapping[str, Any] | None = None,
) -> LensCard:
    """Compile a Lens into a normalized typed card."""
    parent_cards = list(parent_cards or [])
    mechanism_signature = _mechanism_signature(lens, parent_cards)
    transfer_shape = _transfer_shape(lens, parent_cards)
    constraints = _constraints(lens, reference_context)
    disallowed = _disallowed_baselines(lens, reference_context)
    evidence_atoms = _evidence_atoms(lens, parent_cards)
    novelty_axes = _novelty_axes(lens, parent_cards, reference_context)

    file_id = str(lens.source_file) if getattr(lens, "source_file", None) else lens.lens_id
    base_ref = SpanRef(file_id=file_id, start_line=1, end_line=9999, yaml_path="/")
    provenance = {
        "mechanism_signature": [base_ref],
        "transfer_shape": [SpanRef(file_id=file_id, start_line=1, end_line=9999, yaml_path="/structural_patterns")],
        "constraints": [SpanRef(file_id=file_id, start_line=1, end_line=9999, yaml_path="/axioms")],
        "evidence_atoms": [SpanRef(file_id=file_id, start_line=1, end_line=9999, yaml_path="/axioms")],
        "novelty_axes": [SpanRef(file_id=file_id, start_line=1, end_line=9999, yaml_path="/tags")],
    }
    if parent_cards:
        provenance["lineage"] = [
            SpanRef(
                file_id=parent.lens_id,
                start_line=0,
                end_line=0,
                yaml_path="/lineage/parents",
            )
            for parent in parent_cards
        ]
    if reference_context:
        provenance["reference"] = [
            SpanRef(
                file_id="reference_context",
                start_line=0,
                end_line=0,
                yaml_path=f"/{_normalize_token(str(key))}",
            )
            for key in reference_context.keys()
        ]

    card = LensCard(
        lens_id=lens.lens_id,
        domain_name=f"{lens.domain}::{lens.name}",
        mechanism_signature=mechanism_signature,
        transfer_shape=transfer_shape,
        constraints=constraints,
        disallowed_baselines=disallowed,
        evidence_atoms=evidence_atoms,
        novelty_axes=novelty_axes,
        confidence=_confidence_vector(
            mechanism_count=len(mechanism_signature),
            transfer_count=len(transfer_shape),
            constraint_count=len(constraints),
            evidence_count=len(evidence_atoms),
            novelty_count=len(novelty_axes),
        ),
        provenance=provenance,
        version=int(getattr(lens, "version", 1)),
        domain_family=str(getattr(lens, "domain_family", "general")),
        source_kind=str(getattr(lens, "source_kind", "library")),
        parent_lens_ids=tuple(getattr(lens, "parent_lens_ids", ())),
        lineage_token=str(getattr(lens, "lineage_token", "")),
        reference_signature=str(getattr(lens, "reference_signature", "")),
    )
    return card


def score_query_against_card(query_terms: set[str], card: LensCard) -> float:
    """Score overlap on the disclosure-card surface."""
    normalized_terms = {_normalize_token(term) for term in query_terms if _normalize_token(term)}
    if not normalized_terms:
        return 0.0

    evidence_tokens = {
        token
        for atom in card.evidence_atoms
        for token in _keywords(atom)
    }
    novelty_tokens = set(card.novelty_axes)
    score = 0.0
    score += 5.0 * _jaccard(normalized_terms, set(card.mechanism_signature))
    score += 4.0 * _jaccard(normalized_terms, set(card.transfer_shape))
    score += 3.0 * _jaccard(normalized_terms, set(card.constraints))
    score += 2.0 * _jaccard(normalized_terms, evidence_tokens)
    score += 1.4 * _jaccard(normalized_terms, novelty_tokens)
    if normalized_terms & set(card.disallowed_baselines):
        score -= 6.0
    if normalized_terms & set(card.parent_lens_ids):
        score += 0.75
    return score


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _mechanism_signature(lens: Lens, parent_cards: Sequence[LensCard]) -> list[str]:
    tokens: list[str] = []
    for pattern in lens.structural_patterns:
        tokens.extend(_keywords(pattern.name))
        tokens.extend(_keywords(pattern.abstract))
        tokens.extend(_normalized_tokens(pattern.maps_to, limit=16))
    for parent in parent_cards:
        tokens.extend(parent.mechanism_signature[:4])
    tokens.extend(_normalized_tokens(getattr(lens, "tags", []), limit=8))
    return _normalized_tokens(tokens, limit=20)


def _transfer_shape(lens: Lens, parent_cards: Sequence[LensCard]) -> list[str]:
    tokens = list(lens.all_maps_to)
    for parent in parent_cards:
        tokens.extend(parent.transfer_shape[:6])
    return _normalized_tokens(tokens, limit=16)


def _constraints(lens: Lens, reference_context: Mapping[str, Any] | None) -> list[str]:
    tokens: list[str] = []
    for axiom in lens.axioms[:8]:
        tokens.extend(_keywords(axiom)[:4])
    tokens.extend(_normalized_tokens(getattr(lens, "tags", []), limit=8))
    if reference_context:
        for key in ("constraints", "common_failure_modes", "known_bottlenecks"):
            raw_values = reference_context.get(key)
            if isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
                for raw in raw_values:
                    tokens.extend(_keywords(str(raw))[:3])
    return _normalized_tokens(tokens, limit=16)


def _evidence_atoms(lens: Lens, parent_cards: Sequence[LensCard]) -> list[str]:
    atoms = [str(axiom).strip().rstrip(".") for axiom in lens.axioms[:16] if str(axiom).strip()]
    if parent_cards and getattr(lens, "source_kind", "") == "derived_composite":
        for parent in parent_cards:
            atoms.extend(parent.evidence_atoms[:2])
    return _normalized_phrases(atoms, limit=18)


def _disallowed_baselines(lens: Lens, reference_context: Mapping[str, Any] | None) -> list[str]:
    text = " ".join(lens.axioms).lower()
    matches = [pattern for pattern in _BASELINE_PATTERNS if pattern in text]
    if reference_context:
        for key in ("keywords_to_avoid", "baseline_keywords", "avoid"):
            raw_values = reference_context.get(key)
            if isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
                matches.extend(str(value) for value in raw_values)
    return _normalized_tokens(matches, limit=12)


def _novelty_axes(
    lens: Lens,
    parent_cards: Sequence[LensCard],
    reference_context: Mapping[str, Any] | None,
) -> list[str]:
    axes = [
        lens.domain,
        lens.subdomain,
        getattr(lens, "domain_family", "general"),
        getattr(lens, "source_kind", "library"),
    ]
    axes.extend(getattr(lens, "tags", [])[:6])
    axes.extend(getattr(lens, "parent_lens_ids", ())[:4])
    for parent in parent_cards:
        axes.extend(parent.novelty_axes[:3])
    if reference_context:
        axes.extend(_normalize_token(str(key)) for key in reference_context.keys())
    return _normalized_tokens(axes, limit=16)


def _confidence_vector(
    *,
    mechanism_count: int,
    transfer_count: int,
    constraint_count: int,
    evidence_count: int,
    novelty_count: int,
) -> list[float]:
    values: list[float] = []
    values.extend([0.92] * min(4, mechanism_count))
    values.extend([0.86] * min(4, transfer_count))
    values.extend([0.8] * min(4, constraint_count))
    values.extend([0.72] * min(3, evidence_count))
    values.extend([0.64] * min(3, novelty_count))
    return values or [0.75]


__all__ = [
    "SpanRef",
    "LensCard",
    "compile_lens_card",
    "score_query_against_card",
]
