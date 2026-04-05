"""Lineage primitives for proof-carrying lens selection.

Lineage tracks where a lens came from, which proofs it carries, and which
upstream card or reference changes invalidate it.  Derived composite lenses are
validated through these records before they can participate in bundle
selection.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hephaestus.lenses.cards import LensCard


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_text(text: str, *, prefix: str = "") -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if prefix:
        return f"{prefix}_{digest[:16]}"
    return digest[:16]


def compute_reference_signature(
    reference_context: Mapping[str, Any] | Sequence[Any] | None,
) -> str:
    """Return a deterministic digest of reference-bearing context."""
    if not reference_context:
        return ""

    if isinstance(reference_context, Mapping):
        payload = {
            str(key): reference_context[key] for key in sorted(reference_context.keys(), key=str)
        }
        return _hash_text(_stable_json(payload), prefix="ref")

    payload = []
    for lot in reference_context:
        if hasattr(lot, "to_dict"):
            payload.append(lot.to_dict())
        else:
            payload.append(str(lot))
    return _hash_text(_stable_json(payload), prefix="ref")


@dataclass(frozen=True)
class LineageSource:
    """One upstream source that contributes to a lineage proof."""

    lens_id: str
    version: int
    card_fingerprint64: int
    lineage_token: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "version": self.version,
            "card_fingerprint64": self.card_fingerprint64,
            "lineage_token": self.lineage_token,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LineageSource:
        return cls(
            lens_id=str(data["lens_id"]),
            version=int(data.get("version", 1)),
            card_fingerprint64=int(data.get("card_fingerprint64", 0)),
            lineage_token=str(data.get("lineage_token", "")),
            weight=float(data.get("weight", 1.0)),
        )


@dataclass
class LensLineage:
    """Proof-carrying lineage for a base or derived lens."""

    lens_id: str
    source_kind: str
    version: int
    card_fingerprint64: int
    proof_token: str
    loader_revision: int
    derivation: str
    parent_sources: tuple[LineageSource, ...] = ()
    reference_digest: str = ""
    reference_keys: tuple[str, ...] = ()
    invalidation_keys: tuple[str, ...] = ()
    created_from_bundle: tuple[str, ...] = ()
    stale: bool = False
    stale_reasons: tuple[str, ...] = ()
    lineage_id: str = ""
    bundle_id: str | None = None
    lens_ids: tuple[str, ...] = ()
    proof_hash: str = ""
    reference_signature: str = ""
    research_signature: str = ""
    branch_signature: str = ""
    derived_fingerprint64: int | None = None
    invalidation_count: int = 0
    invalidation_reasons: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "source_kind": self.source_kind,
            "version": self.version,
            "card_fingerprint64": self.card_fingerprint64,
            "proof_token": self.proof_token,
            "loader_revision": self.loader_revision,
            "derivation": self.derivation,
            "parent_sources": [source.to_dict() for source in self.parent_sources],
            "reference_digest": self.reference_digest,
            "reference_keys": list(self.reference_keys),
            "invalidation_keys": list(self.invalidation_keys),
            "created_from_bundle": list(self.created_from_bundle),
            "stale": self.stale,
            "stale_reasons": list(self.stale_reasons),
            "lineage_id": self.lineage_id,
            "bundle_id": self.bundle_id,
            "lens_ids": list(self.lens_ids),
            "proof_hash": self.proof_hash,
            "reference_signature": self.reference_signature,
            "research_signature": self.research_signature,
            "branch_signature": self.branch_signature,
            "derived_fingerprint64": self.derived_fingerprint64,
            "invalidation_count": self.invalidation_count,
            "invalidation_reasons": list(self.invalidation_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LensLineage:
        return cls(
            lens_id=str(data["lens_id"]),
            source_kind=str(data.get("source_kind", "library")),
            version=int(data.get("version", 1)),
            card_fingerprint64=int(data.get("card_fingerprint64", 0)),
            proof_token=str(data.get("proof_token", "")),
            loader_revision=int(data.get("loader_revision", 0)),
            derivation=str(data.get("derivation", "")),
            parent_sources=tuple(
                LineageSource.from_dict(item) for item in list(data.get("parent_sources", []) or [])
            ),
            reference_digest=str(data.get("reference_digest", "")),
            reference_keys=tuple(str(item) for item in list(data.get("reference_keys", []) or [])),
            invalidation_keys=tuple(
                str(item) for item in list(data.get("invalidation_keys", []) or [])
            ),
            created_from_bundle=tuple(
                str(item) for item in list(data.get("created_from_bundle", []) or [])
            ),
            stale=bool(data.get("stale", False)),
            stale_reasons=tuple(str(item) for item in list(data.get("stale_reasons", []) or [])),
            lineage_id=str(data.get("lineage_id", "")),
            bundle_id=str(data["bundle_id"]) if data.get("bundle_id") is not None else None,
            lens_ids=tuple(str(item) for item in list(data.get("lens_ids", []) or [])),
            proof_hash=str(data.get("proof_hash", "")),
            reference_signature=str(data.get("reference_signature", "")),
            research_signature=str(data.get("research_signature", "")),
            branch_signature=str(data.get("branch_signature", "")),
            derived_fingerprint64=(
                int(data["derived_fingerprint64"])
                if data.get("derived_fingerprint64") is not None
                else None
            ),
            invalidation_count=int(data.get("invalidation_count", 0)),
            invalidation_reasons=tuple(
                str(item) for item in list(data.get("invalidation_reasons", []) or [])
            ),
            metadata={str(k): str(v) for k, v in dict(data.get("metadata", {}) or {}).items()},
        )

    def is_continuous(self, reference_state: Any) -> bool:
        expected_reference = self.reference_signature or self.reference_digest
        if expected_reference and expected_reference != getattr(
            reference_state, "reference_signature", ""
        ):
            return False
        if self.research_signature and self.research_signature != getattr(
            reference_state, "research_signature", ""
        ):
            return False
        ref_branch = getattr(reference_state, "branch_signature", "")
        return not (self.branch_signature and ref_branch and self.branch_signature != ref_branch)

    def mark_stale(self, *reasons: str) -> LensLineage:
        unique = tuple(
            dict.fromkeys([*self.stale_reasons, *[reason for reason in reasons if reason]])
        )
        return LensLineage(
            lens_id=self.lens_id,
            source_kind=self.source_kind,
            version=self.version,
            card_fingerprint64=self.card_fingerprint64,
            proof_token=self.proof_token,
            loader_revision=self.loader_revision,
            derivation=self.derivation,
            parent_sources=self.parent_sources,
            reference_digest=self.reference_digest,
            reference_keys=self.reference_keys,
            invalidation_keys=self.invalidation_keys,
            created_from_bundle=self.created_from_bundle,
            stale=True,
            stale_reasons=unique,
            lineage_id=self.lineage_id,
            bundle_id=self.bundle_id,
            lens_ids=self.lens_ids,
            proof_hash=self.proof_hash,
            reference_signature=self.reference_signature,
            research_signature=self.research_signature,
            branch_signature=self.branch_signature,
            derived_fingerprint64=self.derived_fingerprint64,
            invalidation_count=self.invalidation_count,
            invalidation_reasons=self.invalidation_reasons,
            metadata=dict(self.metadata),
        )

    def mark_invalidated(self, *reasons: str) -> LensLineage:
        unique = tuple(
            dict.fromkeys([*self.invalidation_reasons, *[reason for reason in reasons if reason]])
        )
        stale = tuple(dict.fromkeys([*self.stale_reasons, *unique]))
        return LensLineage(
            lens_id=self.lens_id,
            source_kind=self.source_kind,
            version=self.version + 1,
            card_fingerprint64=self.card_fingerprint64,
            proof_token=self.proof_token,
            loader_revision=self.loader_revision,
            derivation=self.derivation,
            parent_sources=self.parent_sources,
            reference_digest=self.reference_digest,
            reference_keys=self.reference_keys,
            invalidation_keys=self.invalidation_keys,
            created_from_bundle=self.created_from_bundle,
            stale=True,
            stale_reasons=stale,
            lineage_id=self.lineage_id,
            bundle_id=self.bundle_id,
            lens_ids=self.lens_ids,
            proof_hash=self.proof_hash,
            reference_signature=self.reference_signature,
            research_signature=self.research_signature,
            branch_signature=self.branch_signature,
            derived_fingerprint64=self.derived_fingerprint64,
            invalidation_count=self.invalidation_count + 1,
            invalidation_reasons=unique,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class LineageValidationResult:
    """Validation outcome for one lineage object."""

    lens_id: str
    valid: bool
    stale: bool
    reasons: tuple[str, ...] = ()
    current_card_fingerprint64: int = 0
    current_reference_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "valid": self.valid,
            "stale": self.stale,
            "reasons": list(self.reasons),
            "current_card_fingerprint64": self.current_card_fingerprint64,
            "current_reference_digest": self.current_reference_digest,
        }


def build_lineage_token(
    *,
    lens_id: str,
    source_kind: str,
    version: int,
    card_fingerprint64: int,
    loader_revision: int,
    derivation: str,
    parent_sources: Sequence[LineageSource] = (),
    reference_digest: str = "",
    invalidation_keys: Sequence[str] = (),
) -> str:
    """Build a deterministic token representing a lineage proof."""
    payload = {
        "lens_id": lens_id,
        "source_kind": source_kind,
        "version": version,
        "card_fingerprint64": card_fingerprint64,
        "loader_revision": loader_revision,
        "derivation": derivation,
        "parent_sources": [source.to_dict() for source in parent_sources],
        "reference_digest": reference_digest,
        "invalidation_keys": list(invalidation_keys),
    }
    return _hash_text(_stable_json(payload), prefix="lin")


def build_native_lineage(
    *,
    lens_id: str,
    version: int,
    card_fingerprint64: int,
    loader_revision: int,
    source_kind: str = "library",
    derivation: str = "yaml",
) -> LensLineage:
    """Create lineage for a native library lens."""
    proof_token = build_lineage_token(
        lens_id=lens_id,
        source_kind=source_kind,
        version=version,
        card_fingerprint64=card_fingerprint64,
        loader_revision=loader_revision,
        derivation=derivation,
        invalidation_keys=(f"card:{lens_id}", f"loader:{loader_revision}"),
    )
    return LensLineage(
        lens_id=lens_id,
        source_kind=source_kind,
        version=version,
        card_fingerprint64=card_fingerprint64,
        proof_token=proof_token,
        loader_revision=loader_revision,
        derivation=derivation,
        invalidation_keys=(f"card:{lens_id}", f"loader:{loader_revision}"),
    )


def build_composite_lineage(
    *,
    lens_id: str,
    version: int,
    card_fingerprint64: int,
    loader_revision: int,
    parent_cards: Sequence[LensCard],
    parent_lineages: Sequence[LensLineage],
    derivation: str,
    reference_context: Mapping[str, Any] | Sequence[Any] | None = None,
    metadata: Mapping[str, str] | None = None,
) -> LensLineage:
    """Create lineage for a derived composite lens."""
    lineage_by_lens = {lineage.lens_id: lineage for lineage in parent_lineages}
    sources: list[LineageSource] = []
    for card in parent_cards:
        parent_lineage = lineage_by_lens.get(card.lens_id)
        sources.append(
            LineageSource(
                lens_id=card.lens_id,
                version=parent_lineage.version if parent_lineage else card.version,
                card_fingerprint64=card.fingerprint64,
                lineage_token=parent_lineage.proof_token if parent_lineage else "",
            )
        )

    reference_digest = compute_reference_signature(reference_context)
    invalidation_items = {
        *[f"parent:{source.lens_id}:{source.card_fingerprint64}" for source in sources],
        f"loader:{loader_revision}",
    }
    if reference_digest:
        invalidation_items.add(f"reference:{reference_digest}")
    invalidation_keys = tuple(sorted(invalidation_items))
    proof_token = build_lineage_token(
        lens_id=lens_id,
        source_kind="derived_composite",
        version=version,
        card_fingerprint64=card_fingerprint64,
        loader_revision=loader_revision,
        derivation=derivation,
        parent_sources=sources,
        reference_digest=reference_digest,
        invalidation_keys=invalidation_keys,
    )
    return LensLineage(
        lens_id=lens_id,
        source_kind="derived_composite",
        version=version,
        card_fingerprint64=card_fingerprint64,
        proof_token=proof_token,
        loader_revision=loader_revision,
        derivation=derivation,
        parent_sources=tuple(sources),
        reference_digest=reference_digest,
        reference_keys=tuple(sorted(metadata.keys())) if metadata else (),
        invalidation_keys=invalidation_keys,
        created_from_bundle=tuple(source.lens_id for source in sources),
        metadata={str(k): str(v) for k, v in dict(metadata or {}).items()},
    )


def validate_lineage(
    lineage: LensLineage,
    *,
    current_cards: Mapping[str, LensCard],
    current_lineages: Mapping[str, LensLineage] | None = None,
    loader_revision: int | None = None,
    reference_context: Mapping[str, Any] | Sequence[Any] | None = None,
) -> LineageValidationResult:
    """Validate one lineage against current cards, parents, and references."""
    reasons: list[str] = []
    current_card = current_cards.get(lineage.lens_id)

    if current_card is not None and current_card.fingerprint64 != lineage.card_fingerprint64:
        reasons.append("card fingerprint changed")

    if lineage.stale:
        reasons.extend(lineage.stale_reasons)

    if (
        loader_revision is not None
        and lineage.source_kind == "derived_composite"
        and loader_revision != lineage.loader_revision
    ):
        reasons.append("loader revision changed")

    current_reference = compute_reference_signature(reference_context)
    if lineage.reference_digest and current_reference != lineage.reference_digest:
        reasons.append("reference context changed")

    for parent in lineage.parent_sources:
        parent_card = current_cards.get(parent.lens_id)
        if parent_card is None:
            reasons.append(f"missing parent card: {parent.lens_id}")
            continue
        if parent_card.fingerprint64 != parent.card_fingerprint64:
            reasons.append(f"parent fingerprint changed: {parent.lens_id}")
        if current_lineages and parent.lineage_token:
            parent_lineage = current_lineages.get(parent.lens_id)
            if parent_lineage is None:
                reasons.append(f"missing parent lineage: {parent.lens_id}")
            elif parent_lineage.proof_token != parent.lineage_token:
                reasons.append(f"parent lineage changed: {parent.lens_id}")

    unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return LineageValidationResult(
        lens_id=lineage.lens_id,
        valid=not unique_reasons,
        stale=bool(unique_reasons),
        reasons=unique_reasons,
        current_card_fingerprint64=current_card.fingerprint64 if current_card else 0,
        current_reference_digest=current_reference,
    )


def validate_lineages(
    lineages: Mapping[str, LensLineage],
    *,
    current_cards: Mapping[str, LensCard],
    loader_revision: int | None = None,
    reference_context: Mapping[str, Any] | Sequence[Any] | None = None,
) -> dict[str, LineageValidationResult]:
    """Validate a full lineage mapping."""
    return {
        lens_id: validate_lineage(
            lineage,
            current_cards=current_cards,
            current_lineages=lineages,
            loader_revision=loader_revision,
            reference_context=reference_context,
        )
        for lens_id, lineage in lineages.items()
    }


def lineage_from_bundle_proof(bundle_proof: Any) -> LensLineage:
    """Build an execution lineage token from a runtime bundle proof."""

    lens_ids = tuple(
        str(item)
        for item in (
            getattr(bundle_proof, "active_lens_ids", ())
            or getattr(bundle_proof, "lens_ids", ())
            or getattr(bundle_proof, "member_lens_ids", ())
        )
    )
    derived_fingerprint64 = getattr(
        getattr(bundle_proof, "derived_card", None), "fingerprint64", None
    )
    payload = {
        "bundle_id": getattr(bundle_proof, "bundle_id", ""),
        "lens_ids": lens_ids,
        "proof_hash": getattr(bundle_proof, "proof_hash", ""),
        "reference_signature": getattr(bundle_proof, "reference_signature", ""),
        "research_signature": getattr(bundle_proof, "research_signature", ""),
        "branch_signature": getattr(bundle_proof, "branch_signature", ""),
        "derived_fingerprint64": derived_fingerprint64,
    }
    proof_token = _hash_text(_stable_json(payload), prefix="lin")
    bundle_id = str(getattr(bundle_proof, "bundle_id", ""))
    return LensLineage(
        lens_id=f"bundle::{bundle_id or 'runtime'}",
        source_kind="bundle_runtime",
        version=int(getattr(bundle_proof, "lineage_version", getattr(bundle_proof, "version", 1))),
        card_fingerprint64=int(derived_fingerprint64 or 0),
        proof_token=proof_token,
        loader_revision=int(getattr(bundle_proof, "loader_revision", 0)),
        derivation="bundle_runtime",
        reference_digest=str(payload["reference_signature"]),
        created_from_bundle=lens_ids,
        stale=bool(getattr(bundle_proof, "stale", False)),
        stale_reasons=tuple(
            str(item) for item in getattr(bundle_proof, "invalidation_reasons", ()) or ()
        ),
        lineage_id=proof_token,
        bundle_id=bundle_id or None,
        lens_ids=lens_ids,
        proof_hash=str(payload["proof_hash"]),
        reference_signature=str(payload["reference_signature"]),
        research_signature=str(payload["research_signature"]),
        branch_signature=str(payload["branch_signature"]),
        derived_fingerprint64=int(derived_fingerprint64)
        if derived_fingerprint64 is not None
        else None,
        invalidation_count=int(getattr(bundle_proof, "recomposition_count", 0)),
        invalidation_reasons=tuple(
            str(item) for item in getattr(bundle_proof, "invalidation_reasons", ()) or ()
        ),
        metadata={"bundle_id": bundle_id},
    )


def lineage_from_singleton(
    lens_id: str,
    reference_state: Any,
    *,
    card_fingerprint64: int | None = None,
) -> LensLineage:
    """Build lineage for singleton fallback mode."""

    payload = {
        "lens_id": lens_id,
        "reference_signature": getattr(reference_state, "reference_signature", ""),
        "research_signature": getattr(reference_state, "research_signature", ""),
        "branch_signature": getattr(reference_state, "branch_signature", ""),
        "card_fingerprint64": card_fingerprint64,
    }
    proof_token = _hash_text(_stable_json(payload), prefix="lin")
    return LensLineage(
        lens_id=lens_id,
        source_kind="singleton_runtime",
        version=1,
        card_fingerprint64=int(card_fingerprint64 or 0),
        proof_token=proof_token,
        loader_revision=0,
        derivation="singleton_runtime",
        reference_digest=str(payload["reference_signature"]),
        stale=False,
        lineage_id=proof_token,
        bundle_id=None,
        lens_ids=(lens_id,),
        proof_hash=_hash_text(_stable_json(payload)),
        reference_signature=str(payload["reference_signature"]),
        research_signature=str(payload["research_signature"]),
        branch_signature=str(payload["branch_signature"]),
        derived_fingerprint64=card_fingerprint64,
    )


__all__ = [
    "LineageSource",
    "LensLineage",
    "LineageValidationResult",
    "build_composite_lineage",
    "build_lineage_token",
    "build_native_lineage",
    "compute_reference_signature",
    "lineage_from_bundle_proof",
    "lineage_from_singleton",
    "validate_lineage",
    "validate_lineages",
]
