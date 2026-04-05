"""Typed Adaptive Bundle-Proof lens-engine state.

This module provides a stable, serialisable representation of the production
lens-engine surfaces that need to survive save/load, compaction, report export,
and research-generation invalidation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.loader import classify_domain_family
from hephaestus.research.perplexity import build_research_reference_state

_UTC = UTC
_ENGINE_VERSION = "adaptive-bundle-proof/v1"
_MAX_HISTORY = 16
_LENS_ENGINE_LOT_KINDS = {
    "lens_bundle",
    "lens_lineage",
    "composite_lens",
    "research_reference",
}


def _now() -> str:
    return datetime.now(_UTC).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _trim_history(items: list[Any], limit: int = _MAX_HISTORY) -> list[Any]:
    return items[-limit:] if len(items) > limit else items


def _explicit_attr(obj: Any, name: str, default: Any = None) -> Any:
    data = getattr(obj, "__dict__", None)
    if isinstance(data, dict) and name in data:
        return data[name]
    return default


@dataclass
class LensBundleMember:
    """One lens participating in a bundle-proof surface."""

    lens_id: str
    lens_name: str
    domain_name: str
    source_domain: str = ""
    domain_family: str = "general"
    domain_distance: float = 0.0
    structural_relevance: float = 0.0
    retrieval_score: float = 0.0
    fidelity_score: float = 0.0
    confidence: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)
    evidence_atoms: list[str] = field(default_factory=list)
    card_fingerprint64: int = 0

    @property
    def rank_score(self) -> float:
        """Unified ranking surface for bundle selection."""
        return (
            0.35 * max(self.retrieval_score, 0.0)
            + 0.25 * max(self.fidelity_score, 0.0)
            + 0.25 * max(self.domain_distance, 0.0)
            + 0.15 * max(self.confidence, 0.0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "lens_name": self.lens_name,
            "domain_name": self.domain_name,
            "source_domain": self.source_domain,
            "domain_family": self.domain_family,
            "domain_distance": self.domain_distance,
            "structural_relevance": self.structural_relevance,
            "retrieval_score": self.retrieval_score,
            "fidelity_score": self.fidelity_score,
            "confidence": self.confidence,
            "matched_patterns": list(self.matched_patterns),
            "evidence_atoms": list(self.evidence_atoms),
            "card_fingerprint64": self.card_fingerprint64,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LensBundleMember:
        return cls(
            lens_id=str(data.get("lens_id", "")),
            lens_name=str(data.get("lens_name", "")),
            domain_name=str(data.get("domain_name", "")),
            source_domain=str(data.get("source_domain", "")),
            domain_family=str(data.get("domain_family", "general")),
            domain_distance=_safe_float(data.get("domain_distance")),
            structural_relevance=_safe_float(data.get("structural_relevance")),
            retrieval_score=_safe_float(data.get("retrieval_score")),
            fidelity_score=_safe_float(data.get("fidelity_score")),
            confidence=_safe_float(data.get("confidence")),
            matched_patterns=[str(x) for x in _safe_list(data.get("matched_patterns")) if x],
            evidence_atoms=[str(x) for x in _safe_list(data.get("evidence_atoms")) if x],
            card_fingerprint64=_safe_int(data.get("card_fingerprint64")),
        )


@dataclass
class ResearchReferenceArtifact:
    """Stable fingerprint for one research/reference artifact."""

    artifact_name: str
    provider: str = "perplexity"
    model: str = ""
    summary: str = ""
    signature: str = ""
    citation_count: int = 0
    citations: list[str] = field(default_factory=list)
    raw_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "provider": self.provider,
            "model": self.model,
            "summary": self.summary,
            "signature": self.signature,
            "citation_count": self.citation_count,
            "citations": list(self.citations),
            "raw_digest": self.raw_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchReferenceArtifact:
        return cls(
            artifact_name=str(data.get("artifact_name", "")),
            provider=str(data.get("provider", "perplexity")),
            model=str(data.get("model", "")),
            summary=str(data.get("summary", "")),
            signature=str(data.get("signature", "")),
            citation_count=_safe_int(data.get("citation_count")),
            citations=[str(x) for x in _safe_list(data.get("citations")) if x],
            raw_digest=str(data.get("raw_digest", "")),
        )


@dataclass
class ResearchReferenceState:
    """Reference-generation surface derived from research artifacts."""

    reference_generation: int = 0
    provider: str = "perplexity"
    model: str = ""
    reference_signature: str = ""
    artifacts: list[ResearchReferenceArtifact] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)

    @property
    def artifact_names(self) -> list[str]:
        return [artifact.artifact_name for artifact in self.artifacts]

    def summary(self) -> str:
        if not self.artifacts:
            return "No research/reference artifacts attached."
        names = ", ".join(self.artifact_names[:4])
        suffix = "…" if len(self.artifacts) > 4 else ""
        return (
            f"generation={self.reference_generation} "
            f"artifacts={len(self.artifacts)} [{names}{suffix}]"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_generation": self.reference_generation,
            "provider": self.provider,
            "model": self.model,
            "reference_signature": self.reference_signature,
            "updated_at": self.updated_at,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchReferenceState:
        return cls(
            reference_generation=_safe_int(data.get("reference_generation")),
            provider=str(data.get("provider", "perplexity")),
            model=str(data.get("model", "")),
            reference_signature=str(data.get("reference_signature", "")),
            updated_at=str(data.get("updated_at", _now())),
            artifacts=[
                ResearchReferenceArtifact.from_dict(item)
                for item in _safe_list(data.get("artifacts"))
                if isinstance(item, dict)
            ],
        )


@dataclass
class LensBundleProof:
    """Proof-carrying bundle selection record."""

    bundle_id: str
    bundle_kind: str
    member_ids: list[str]
    status: str = "standby"
    proof_status: str = "guarded"
    cohesion_score: float = 0.0
    higher_order_score: float = 0.0
    proof_fingerprint: str = ""
    reference_generation: int = 0
    shared_patterns: list[str] = field(default_factory=list)
    complementary_axes: list[str] = field(default_factory=list)
    clauses: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "bundle_kind": self.bundle_kind,
            "member_ids": list(self.member_ids),
            "status": self.status,
            "proof_status": self.proof_status,
            "cohesion_score": self.cohesion_score,
            "higher_order_score": self.higher_order_score,
            "proof_fingerprint": self.proof_fingerprint,
            "reference_generation": self.reference_generation,
            "shared_patterns": list(self.shared_patterns),
            "complementary_axes": list(self.complementary_axes),
            "clauses": list(self.clauses),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LensBundleProof:
        return cls(
            bundle_id=str(data.get("bundle_id", "")),
            bundle_kind=str(data.get("bundle_kind", "singleton")),
            member_ids=[str(x) for x in _safe_list(data.get("member_ids")) if x],
            status=str(data.get("status", "standby")),
            proof_status=str(data.get("proof_status", "guarded")),
            cohesion_score=_safe_float(data.get("cohesion_score")),
            higher_order_score=_safe_float(data.get("higher_order_score")),
            proof_fingerprint=str(data.get("proof_fingerprint", "")),
            reference_generation=_safe_int(data.get("reference_generation")),
            shared_patterns=[str(x) for x in _safe_list(data.get("shared_patterns")) if x],
            complementary_axes=[str(x) for x in _safe_list(data.get("complementary_axes")) if x],
            clauses=[str(x) for x in _safe_list(data.get("clauses")) if x],
            summary=str(data.get("summary", "")),
        )


@dataclass
class LensLineage:
    """Lineage for a lens or derived composite."""

    lineage_id: str
    entity_id: str
    entity_kind: str = "lens"
    generation: int = 1
    derivation_kind: str = "library"
    reference_generation: int = 0
    proof_bundle_id: str = ""
    fingerprint: str = ""
    parent_lineage_ids: list[str] = field(default_factory=list)
    parent_bundle_ids: list[str] = field(default_factory=list)
    invalidated: bool = False
    invalidation_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lineage_id": self.lineage_id,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "generation": self.generation,
            "derivation_kind": self.derivation_kind,
            "reference_generation": self.reference_generation,
            "proof_bundle_id": self.proof_bundle_id,
            "fingerprint": self.fingerprint,
            "parent_lineage_ids": list(self.parent_lineage_ids),
            "parent_bundle_ids": list(self.parent_bundle_ids),
            "invalidated": self.invalidated,
            "invalidation_reason": self.invalidation_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LensLineage:
        return cls(
            lineage_id=str(data.get("lineage_id", "")),
            entity_id=str(data.get("entity_id", "")),
            entity_kind=str(data.get("entity_kind", "lens")),
            generation=_safe_int(data.get("generation"), 1),
            derivation_kind=str(data.get("derivation_kind", "library")),
            reference_generation=_safe_int(data.get("reference_generation")),
            proof_bundle_id=str(data.get("proof_bundle_id", "")),
            fingerprint=str(data.get("fingerprint", "")),
            parent_lineage_ids=[str(x) for x in _safe_list(data.get("parent_lineage_ids")) if x],
            parent_bundle_ids=[str(x) for x in _safe_list(data.get("parent_bundle_ids")) if x],
            invalidated=bool(data.get("invalidated", False)),
            invalidation_reason=str(data.get("invalidation_reason", "")),
        )


@dataclass
class FoldState:
    """Cohesion-cell / fold-state view for an active or standby bundle."""

    fold_id: str
    bundle_id: str
    status: str
    reference_generation: int = 0
    active_lineage_ids: list[str] = field(default_factory=list)
    guard_ids: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "bundle_id": self.bundle_id,
            "status": self.status,
            "reference_generation": self.reference_generation,
            "active_lineage_ids": list(self.active_lineage_ids),
            "guard_ids": list(self.guard_ids),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FoldState:
        return cls(
            fold_id=str(data.get("fold_id", "")),
            bundle_id=str(data.get("bundle_id", "")),
            status=str(data.get("status", "")),
            reference_generation=_safe_int(data.get("reference_generation")),
            active_lineage_ids=[str(x) for x in _safe_list(data.get("active_lineage_ids")) if x],
            guard_ids=[str(x) for x in _safe_list(data.get("guard_ids")) if x],
            summary=str(data.get("summary", "")),
        )


@dataclass
class GuardDecision:
    """Runtime handoff / selection guard."""

    guard_id: str
    kind: str
    status: str
    target_id: str
    summary: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "guard_id": self.guard_id,
            "kind": self.kind,
            "status": self.status,
            "target_id": self.target_id,
            "summary": self.summary,
            "details": list(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuardDecision:
        return cls(
            guard_id=str(data.get("guard_id", "")),
            kind=str(data.get("kind", "")),
            status=str(data.get("status", "")),
            target_id=str(data.get("target_id", "")),
            summary=str(data.get("summary", "")),
            details=[str(x) for x in _safe_list(data.get("details")) if x],
        )


@dataclass
class InvalidationEvent:
    """Invalidation caused by reference changes or composite drift."""

    invalidation_id: str
    target_kind: str
    target_id: str
    cause: str
    status: str
    from_reference_generation: int = 0
    to_reference_generation: int = 0
    affected_lineage_ids: list[str] = field(default_factory=list)
    affected_bundle_ids: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "invalidation_id": self.invalidation_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "cause": self.cause,
            "status": self.status,
            "from_reference_generation": self.from_reference_generation,
            "to_reference_generation": self.to_reference_generation,
            "affected_lineage_ids": list(self.affected_lineage_ids),
            "affected_bundle_ids": list(self.affected_bundle_ids),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvalidationEvent:
        return cls(
            invalidation_id=str(data.get("invalidation_id", "")),
            target_kind=str(data.get("target_kind", "")),
            target_id=str(data.get("target_id", "")),
            cause=str(data.get("cause", "")),
            status=str(data.get("status", "")),
            from_reference_generation=_safe_int(data.get("from_reference_generation")),
            to_reference_generation=_safe_int(data.get("to_reference_generation")),
            affected_lineage_ids=[
                str(x) for x in _safe_list(data.get("affected_lineage_ids")) if x
            ],
            affected_bundle_ids=[str(x) for x in _safe_list(data.get("affected_bundle_ids")) if x],
            summary=str(data.get("summary", "")),
        )


@dataclass
class RecompositionEvent:
    """Record of a recomposition caused by invalidation or research refresh."""

    event_id: str
    trigger: str
    status: str
    from_reference_generation: int = 0
    to_reference_generation: int = 0
    invalidated_bundle_ids: list[str] = field(default_factory=list)
    resulting_bundle_ids: list[str] = field(default_factory=list)
    resulting_composite_ids: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trigger": self.trigger,
            "status": self.status,
            "from_reference_generation": self.from_reference_generation,
            "to_reference_generation": self.to_reference_generation,
            "invalidated_bundle_ids": list(self.invalidated_bundle_ids),
            "resulting_bundle_ids": list(self.resulting_bundle_ids),
            "resulting_composite_ids": list(self.resulting_composite_ids),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecompositionEvent:
        return cls(
            event_id=str(data.get("event_id", "")),
            trigger=str(data.get("trigger", "")),
            status=str(data.get("status", "")),
            from_reference_generation=_safe_int(data.get("from_reference_generation")),
            to_reference_generation=_safe_int(data.get("to_reference_generation")),
            invalidated_bundle_ids=[
                str(x) for x in _safe_list(data.get("invalidated_bundle_ids")) if x
            ],
            resulting_bundle_ids=[
                str(x) for x in _safe_list(data.get("resulting_bundle_ids")) if x
            ],
            resulting_composite_ids=[
                str(x) for x in _safe_list(data.get("resulting_composite_ids")) if x
            ],
            summary=str(data.get("summary", "")),
        )


@dataclass
class CompositeLens:
    """Derived composite lens surface with aggressive invalidation metadata."""

    composite_id: str
    component_lineage_ids: list[str]
    component_lens_ids: list[str]
    derived_from_bundle_id: str
    version: int = 1
    reference_generation: int = 0
    status: str = "active"
    fingerprint: str = ""
    invalidation_reasons: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite_id": self.composite_id,
            "component_lineage_ids": list(self.component_lineage_ids),
            "component_lens_ids": list(self.component_lens_ids),
            "derived_from_bundle_id": self.derived_from_bundle_id,
            "version": self.version,
            "reference_generation": self.reference_generation,
            "status": self.status,
            "fingerprint": self.fingerprint,
            "invalidation_reasons": list(self.invalidation_reasons),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompositeLens:
        return cls(
            composite_id=str(data.get("composite_id", "")),
            component_lineage_ids=[
                str(x) for x in _safe_list(data.get("component_lineage_ids")) if x
            ],
            component_lens_ids=[str(x) for x in _safe_list(data.get("component_lens_ids")) if x],
            derived_from_bundle_id=str(data.get("derived_from_bundle_id", "")),
            version=_safe_int(data.get("version"), 1),
            reference_generation=_safe_int(data.get("reference_generation")),
            status=str(data.get("status", "active")),
            fingerprint=str(data.get("fingerprint", "")),
            invalidation_reasons=[
                str(x) for x in _safe_list(data.get("invalidation_reasons")) if x
            ],
            summary=str(data.get("summary", "")),
        )


@dataclass
class LensEngineState:
    """Full serialisable lens-engine state surface."""

    engine_version: str = _ENGINE_VERSION
    session_reference_generation: int = 0
    active_bundle_id: str = ""
    bundles: list[LensBundleProof] = field(default_factory=list)
    members: list[LensBundleMember] = field(default_factory=list)
    lineages: list[LensLineage] = field(default_factory=list)
    fold_states: list[FoldState] = field(default_factory=list)
    guards: list[GuardDecision] = field(default_factory=list)
    invalidations: list[InvalidationEvent] = field(default_factory=list)
    recompositions: list[RecompositionEvent] = field(default_factory=list)
    composites: list[CompositeLens] = field(default_factory=list)
    research: ResearchReferenceState | None = None
    updated_at: str = field(default_factory=_now)

    @property
    def active_bundle(self) -> LensBundleProof | None:
        for bundle in self.bundles:
            if bundle.bundle_id == self.active_bundle_id:
                return bundle
        return None

    @property
    def active_composites(self) -> list[CompositeLens]:
        return [item for item in self.composites if item.status == "active"]

    @property
    def pending_invalidations(self) -> list[InvalidationEvent]:
        return [
            item for item in self.invalidations if item.status not in {"recomposed", "superseded"}
        ]

    def summary(self) -> str:
        bundle = self.active_bundle
        if bundle is None:
            return "No active lens-engine bundle."
        members = ", ".join(bundle.member_ids[:4])
        suffix = "…" if len(bundle.member_ids) > 4 else ""
        return (
            f"{bundle.bundle_id} {bundle.bundle_kind} {bundle.proof_status} "
            f"(gen={self.session_reference_generation}, members={members}{suffix}, "
            f"guards={len(self.guards)}, invalidations={len(self.pending_invalidations)})"
        )

    def brief_dict(self) -> dict[str, Any]:
        bundle = self.active_bundle
        return {
            "engine_version": self.engine_version,
            "active_bundle_id": self.active_bundle_id,
            "active_bundle_kind": bundle.bundle_kind if bundle else "",
            "active_bundle_members": list(bundle.member_ids) if bundle else [],
            "reference_generation": self.session_reference_generation,
            "composites": [item.composite_id for item in self.active_composites],
            "pending_invalidations": len(self.pending_invalidations),
            "recomposition_events": len(self.recompositions),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "session_reference_generation": self.session_reference_generation,
            "active_bundle_id": self.active_bundle_id,
            "bundles": [item.to_dict() for item in self.bundles],
            "members": [item.to_dict() for item in self.members],
            "lineages": [item.to_dict() for item in self.lineages],
            "fold_states": [item.to_dict() for item in self.fold_states],
            "guards": [item.to_dict() for item in self.guards],
            "invalidations": [item.to_dict() for item in self.invalidations],
            "recompositions": [item.to_dict() for item in self.recompositions],
            "composites": [item.to_dict() for item in self.composites],
            "research": self.research.to_dict() if self.research is not None else None,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LensEngineState:
        research_data = data.get("research")
        return cls(
            engine_version=str(data.get("engine_version", _ENGINE_VERSION)),
            session_reference_generation=_safe_int(data.get("session_reference_generation")),
            active_bundle_id=str(data.get("active_bundle_id", "")),
            bundles=[
                LensBundleProof.from_dict(item)
                for item in _safe_list(data.get("bundles"))
                if isinstance(item, dict)
            ],
            members=[
                LensBundleMember.from_dict(item)
                for item in _safe_list(data.get("members"))
                if isinstance(item, dict)
            ],
            lineages=[
                LensLineage.from_dict(item)
                for item in _safe_list(data.get("lineages"))
                if isinstance(item, dict)
            ],
            fold_states=[
                FoldState.from_dict(item)
                for item in _safe_list(data.get("fold_states"))
                if isinstance(item, dict)
            ],
            guards=[
                GuardDecision.from_dict(item)
                for item in _safe_list(data.get("guards"))
                if isinstance(item, dict)
            ],
            invalidations=[
                InvalidationEvent.from_dict(item)
                for item in _safe_list(data.get("invalidations"))
                if isinstance(item, dict)
            ],
            recompositions=[
                RecompositionEvent.from_dict(item)
                for item in _safe_list(data.get("recompositions"))
                if isinstance(item, dict)
            ],
            composites=[
                CompositeLens.from_dict(item)
                for item in _safe_list(data.get("composites"))
                if isinstance(item, dict)
            ],
            research=(
                ResearchReferenceState.from_dict(research_data)
                if isinstance(research_data, dict)
                else None
            ),
            updated_at=str(data.get("updated_at", _now())),
        )

    def reference_lot_specs(self) -> list[dict[str, Any]]:
        """Return reference-lot definitions needed to resume this state safely."""
        specs: list[dict[str, Any]] = []
        for bundle in self.bundles:
            if bundle.status not in {"active", "standby"}:
                continue
            specs.append(
                {
                    "kind": "lens_bundle",
                    "subject_key": bundle.bundle_id,
                    "exact": {
                        "proof_fingerprint": bundle.proof_fingerprint,
                        "reference_generation": str(bundle.reference_generation),
                        "status": bundle.status,
                    },
                }
            )
        for lineage in self.lineages:
            specs.append(
                {
                    "kind": "lens_lineage",
                    "subject_key": lineage.lineage_id,
                    "exact": {
                        "fingerprint": lineage.fingerprint,
                        "generation": str(lineage.generation),
                        "reference_generation": str(lineage.reference_generation),
                    },
                }
            )
        for composite in self.composites:
            specs.append(
                {
                    "kind": "composite_lens",
                    "subject_key": composite.composite_id,
                    "exact": {
                        "fingerprint": composite.fingerprint,
                        "version": str(composite.version),
                        "reference_generation": str(composite.reference_generation),
                    },
                }
            )
        if self.research is not None:
            for artifact in self.research.artifacts:
                specs.append(
                    {
                        "kind": "research_reference",
                        "subject_key": artifact.artifact_name,
                        "exact": {
                            "signature": artifact.signature,
                            "reference_generation": str(self.research.reference_generation),
                        },
                    }
                )
        return specs

    def with_reference_refresh(
        self,
        new_research: ResearchReferenceState,
        *,
        cause: str = "research_reference_refresh",
    ) -> LensEngineState:
        """Return a copy invalidated by a new research/reference generation."""
        state = LensEngineState.from_dict(self.to_dict())
        if isinstance(new_research, dict):
            new_research = ResearchReferenceState.from_dict(new_research)
        previous_generation = state.session_reference_generation
        state.session_reference_generation = max(
            previous_generation + 1,
            new_research.reference_generation,
        )
        new_research.reference_generation = state.session_reference_generation
        state.research = new_research
        state.updated_at = _now()

        invalidated_bundle_ids: list[str] = []
        for bundle in state.bundles:
            if bundle.status == "invalidated":
                continue
            invalidated_bundle_ids.append(bundle.bundle_id)
            state.invalidations.append(
                InvalidationEvent(
                    invalidation_id=f"inval:{bundle.bundle_id}:{state.session_reference_generation}",
                    target_kind="bundle",
                    target_id=bundle.bundle_id,
                    cause=cause,
                    status="pending",
                    from_reference_generation=bundle.reference_generation,
                    to_reference_generation=state.session_reference_generation,
                    affected_bundle_ids=[bundle.bundle_id],
                    summary=(
                        f"Bundle {bundle.bundle_id} invalidated because reference "
                        f"generation advanced to {state.session_reference_generation}."
                    ),
                )
            )
            bundle.status = "invalidated"
            bundle.summary = (
                f"{bundle.summary} [invalidated by reference generation refresh]".strip()
            )
            bundle.reference_generation = state.session_reference_generation

        for composite in state.composites:
            if composite.status != "active":
                continue
            composite.status = "invalidated"
            composite.invalidation_reasons.append(
                f"reference generation advanced to {state.session_reference_generation}"
            )
            state.invalidations.append(
                InvalidationEvent(
                    invalidation_id=f"inval:{composite.composite_id}:{state.session_reference_generation}",
                    target_kind="composite",
                    target_id=composite.composite_id,
                    cause=cause,
                    status="pending",
                    from_reference_generation=composite.reference_generation,
                    to_reference_generation=state.session_reference_generation,
                    affected_bundle_ids=[composite.derived_from_bundle_id],
                    summary=(
                        f"Composite {composite.composite_id} invalidated because one of its "
                        "reference-bound inputs changed."
                    ),
                )
            )
            composite.reference_generation = state.session_reference_generation

        state.recompositions.append(
            RecompositionEvent(
                event_id=f"recomp:{previous_generation}:{state.session_reference_generation}",
                trigger=cause,
                status="required",
                from_reference_generation=previous_generation,
                to_reference_generation=state.session_reference_generation,
                invalidated_bundle_ids=invalidated_bundle_ids,
                summary=(
                    f"Reference generation moved from {previous_generation} to "
                    f"{state.session_reference_generation}; recomposition required."
                ),
            )
        )

        state.invalidations = _trim_history(state.invalidations)
        state.recompositions = _trim_history(state.recompositions)
        return state

    @classmethod
    def from_report(
        cls,
        report: Any,
        *,
        previous_state: LensEngineState | None = None,
    ) -> LensEngineState:
        """Build lens-engine state from a Genesis report or equivalent object."""
        research = build_research_reference_state(
            baseline_dossier=getattr(report, "baseline_dossier", None),
            grounding_report=getattr(
                getattr(report, "top_invention", None), "grounding_report", None
            ),
            implementation_risk_review=getattr(
                getattr(report, "top_invention", None),
                "implementation_risk_review",
                None,
            ),
            model=str(
                getattr(getattr(report, "model_config", {}), "get", lambda *_: "")("search", "")
            ),
        )
        if isinstance(research, dict):
            research = ResearchReferenceState.from_dict(research)

        previous_generation = previous_state.session_reference_generation if previous_state else 0
        reference_generation = 0
        if research is not None:
            reference_generation = 1
            if previous_state and previous_state.research is not None:
                reference_generation = (
                    previous_generation + 1
                    if previous_state.research.reference_signature != research.reference_signature
                    else max(previous_generation, 1)
                )
            research.reference_generation = reference_generation
        elif previous_state is not None:
            reference_generation = previous_generation

        members = _collect_members(report)
        bundles = _build_bundles(members, reference_generation)
        lineages = _build_lineages(members, bundles, reference_generation)
        composites = _build_composites(bundles, lineages, reference_generation)
        guards = _build_guards(bundles, composites, research, reference_generation)
        folds = _build_fold_states(bundles, lineages, guards, reference_generation)

        state = cls(
            session_reference_generation=reference_generation,
            active_bundle_id=_active_bundle_id(bundles),
            bundles=bundles,
            members=members,
            lineages=lineages,
            fold_states=folds,
            guards=guards,
            composites=composites,
            research=research,
            updated_at=_now(),
        )

        if previous_state is not None:
            state.invalidations = _trim_history(list(previous_state.invalidations))
            state.recompositions = _trim_history(list(previous_state.recompositions))
            if (
                previous_state.research is not None
                and research is not None
                and previous_state.research.reference_signature != research.reference_signature
            ):
                active_prev = previous_state.active_bundle
                invalidated_bundle_ids = []
                if active_prev is not None:
                    invalidated_bundle_ids.append(active_prev.bundle_id)
                    state.invalidations.append(
                        InvalidationEvent(
                            invalidation_id=(
                                f"inval:{active_prev.bundle_id}:{previous_state.session_reference_generation}"
                                f"->{reference_generation}"
                            ),
                            target_kind="bundle",
                            target_id=active_prev.bundle_id,
                            cause="research_reference_refresh",
                            status="recomposed",
                            from_reference_generation=previous_state.session_reference_generation,
                            to_reference_generation=reference_generation,
                            affected_bundle_ids=[active_prev.bundle_id],
                            summary=(
                                f"Bundle {active_prev.bundle_id} was invalidated by research/reference "
                                f"change and recomposed into {state.active_bundle_id}."
                            ),
                        )
                    )
                for composite in previous_state.active_composites:
                    state.invalidations.append(
                        InvalidationEvent(
                            invalidation_id=(
                                f"inval:{composite.composite_id}:{previous_state.session_reference_generation}"
                                f"->{reference_generation}"
                            ),
                            target_kind="composite",
                            target_id=composite.composite_id,
                            cause="research_reference_refresh",
                            status="recomposed",
                            from_reference_generation=previous_state.session_reference_generation,
                            to_reference_generation=reference_generation,
                            affected_bundle_ids=[composite.derived_from_bundle_id],
                            summary=(
                                f"Composite {composite.composite_id} was invalidated and recomposed "
                                f"at reference generation {reference_generation}."
                            ),
                        )
                    )
                state.recompositions.append(
                    RecompositionEvent(
                        event_id=(
                            f"recomp:{previous_state.session_reference_generation}:{reference_generation}"
                        ),
                        trigger="research_reference_refresh",
                        status="completed",
                        from_reference_generation=previous_state.session_reference_generation,
                        to_reference_generation=reference_generation,
                        invalidated_bundle_ids=invalidated_bundle_ids,
                        resulting_bundle_ids=[state.active_bundle_id]
                        if state.active_bundle_id
                        else [],
                        resulting_composite_ids=[
                            item.composite_id for item in state.active_composites
                        ],
                        summary=(
                            f"Research/reference change triggered recomposition from generation "
                            f"{previous_state.session_reference_generation} to {reference_generation}."
                        ),
                    )
                )
                state.invalidations = _trim_history(state.invalidations)
                state.recompositions = _trim_history(state.recompositions)

        return state


def lens_engine_lot_kinds() -> set[str]:
    """Kinds reserved for lens-engine resume lots."""
    return set(_LENS_ENGINE_LOT_KINDS)


def _collect_members(report: Any) -> list[LensBundleMember]:
    members_by_lens: dict[str, LensBundleMember] = {}

    scored = _safe_list(getattr(report, "scored_candidates", []))
    candidates = scored or _safe_list(getattr(report, "all_candidates", []))
    for item in candidates:
        candidate = _explicit_attr(item, "candidate", item)
        lens = _explicit_attr(candidate, "lens_used")
        if lens is None:
            continue

        try:
            card = compile_lens_card(lens)
            fingerprint64 = int(getattr(card, "fingerprint64", 0) or 0)
            domain_name = getattr(card, "domain_name", "") or f"{lens.domain}::{lens.name}"
            evidence_atoms = list(getattr(card, "evidence_atoms", []) or [])
        except Exception:
            fingerprint64 = 0
            domain_name = f"{getattr(lens, 'domain', '')}::{getattr(lens, 'name', '')}".strip(":")
            evidence_atoms = []

        lens_score = _explicit_attr(candidate, "lens_score")
        member = LensBundleMember(
            lens_id=str(getattr(lens, "lens_id", "")),
            lens_name=str(getattr(lens, "name", "")),
            domain_name=domain_name,
            source_domain=str(
                _explicit_attr(candidate, "source_domain", getattr(lens, "name", ""))
            ),
            domain_family=str(classify_domain_family(getattr(lens, "domain", ""))),
            domain_distance=_safe_float(
                _explicit_attr(
                    item,
                    "domain_distance",
                    _explicit_attr(
                        lens_score,
                        "domain_distance",
                        _explicit_attr(candidate, "domain_distance", 0.0),
                    ),
                )
            ),
            structural_relevance=_safe_float(
                _explicit_attr(lens_score, "structural_relevance", 0.0)
            ),
            retrieval_score=_safe_float(
                _explicit_attr(
                    item,
                    "combined_score",
                    _explicit_attr(lens_score, "composite_score", 0.0),
                )
            ),
            fidelity_score=_safe_float(
                _explicit_attr(
                    item, "structural_fidelity", _explicit_attr(candidate, "confidence", 0.0)
                )
            ),
            confidence=_safe_float(_explicit_attr(candidate, "confidence", 0.0)),
            matched_patterns=[
                str(x) for x in _safe_list(_explicit_attr(lens_score, "matched_patterns", [])) if x
            ],
            evidence_atoms=evidence_atoms[:8],
            card_fingerprint64=fingerprint64,
        )

        existing = members_by_lens.get(member.lens_id)
        if existing is None or member.rank_score > existing.rank_score:
            members_by_lens[member.lens_id] = member

    members = sorted(
        members_by_lens.values(),
        key=lambda item: (item.rank_score, item.domain_distance, item.structural_relevance),
        reverse=True,
    )
    return members


def _build_bundles(
    members: list[LensBundleMember],
    reference_generation: int,
) -> list[LensBundleProof]:
    if not members:
        return []

    bundles: list[LensBundleProof] = []
    for idx, member in enumerate(members, start=1):
        fingerprint = _hash_text(
            json.dumps(
                {
                    "kind": "singleton",
                    "lens_id": member.lens_id,
                    "fingerprint64": member.card_fingerprint64,
                    "reference_generation": reference_generation,
                },
                sort_keys=True,
            )
        )
        bundles.append(
            LensBundleProof(
                bundle_id=f"bundle:{member.lens_id}",
                bundle_kind="singleton",
                member_ids=[member.lens_id],
                status="standby",
                proof_status="guarded" if idx > 1 else "fallback",
                cohesion_score=min(max(member.rank_score, 0.0), 1.0),
                higher_order_score=0.0,
                proof_fingerprint=fingerprint,
                reference_generation=reference_generation,
                shared_patterns=list(member.matched_patterns),
                complementary_axes=[member.domain_family],
                clauses=[
                    f"Lens {member.lens_id} cleared the retrieval floor with rank score {member.rank_score:.2f}.",
                    f"Matched patterns: {', '.join(member.matched_patterns) or 'none explicit'}.",
                ],
                summary=(
                    f"Singleton standby for {member.lens_name}."
                    if idx > 1
                    else "Singleton fallback retained because no stronger multi-lens bundle cleared the cohesion floor."
                ),
            )
        )

    selected = _select_adaptive_bundle_members(members)
    if len(selected) > 1:
        shared_patterns = sorted(
            {pattern for member in selected for pattern in member.matched_patterns}
        )
        axes = sorted({member.domain_family for member in selected if member.domain_family})
        cohesion = _cohesion_score(selected, members)
        higher_order = _higher_order_score(selected)
        fingerprint = _hash_text(
            json.dumps(
                {
                    "kind": "adaptive",
                    "member_ids": [member.lens_id for member in selected],
                    "reference_generation": reference_generation,
                    "shared_patterns": shared_patterns,
                },
                sort_keys=True,
            )
        )
        bundle = LensBundleProof(
            bundle_id=f"bundle:adaptive:{fingerprint[:12]}",
            bundle_kind="adaptive_bundle",
            member_ids=[member.lens_id for member in selected],
            status="active",
            proof_status="proven" if cohesion >= 0.68 and higher_order >= 0.55 else "guarded",
            cohesion_score=cohesion,
            higher_order_score=higher_order,
            proof_fingerprint=fingerprint,
            reference_generation=reference_generation,
            shared_patterns=shared_patterns,
            complementary_axes=axes,
            clauses=[
                f"Cohesion floor={cohesion:.2f} across {len(selected)} members.",
                f"Higher-order support={higher_order:.2f} from families {', '.join(axes)}.",
                (
                    "Bundle preserved because members contribute non-redundant structural patterns."
                    if shared_patterns
                    else "Bundle preserved for cross-family diversity despite sparse explicit pattern overlap."
                ),
            ],
            summary=(
                f"Adaptive bundle selected from {', '.join(member.lens_name for member in selected[:3])}."
            ),
        )
        bundles.insert(0, bundle)
        for item in bundles[1:]:
            if item.bundle_id in {f"bundle:{member.lens_id}" for member in selected}:
                item.status = "supporting"
    else:
        bundles[0].status = "active"

    return bundles


def _select_adaptive_bundle_members(
    members: list[LensBundleMember],
    limit: int = 3,
) -> list[LensBundleMember]:
    if not members:
        return []
    selected = [members[0]]
    covered_patterns = set(members[0].matched_patterns)
    used_families = {members[0].domain_family}
    top_score = max(members[0].rank_score, 0.01)
    for member in members[1:]:
        if len(selected) >= limit:
            break
        if member.rank_score < top_score * 0.72:
            continue
        new_patterns = set(member.matched_patterns) - covered_patterns
        family_bonus = (
            member.domain_family not in used_families and member.domain_family != "general"
        )
        if not new_patterns and not family_bonus:
            continue
        selected.append(member)
        covered_patterns.update(member.matched_patterns)
        used_families.add(member.domain_family)
    return selected


def _cohesion_score(
    selected: list[LensBundleMember],
    all_members: list[LensBundleMember],
) -> float:
    if not selected:
        return 0.0
    avg_rank = sum(member.rank_score for member in selected) / len(selected)
    avg_distance = sum(member.domain_distance for member in selected) / len(selected)
    all_patterns = {pattern for member in all_members for pattern in member.matched_patterns}
    selected_patterns = {pattern for member in selected for pattern in member.matched_patterns}
    coverage = len(selected_patterns) / len(all_patterns) if all_patterns else 0.6
    diversity = len({member.domain_family for member in selected if member.domain_family}) / max(
        len(selected), 1
    )
    return round(
        min(
            1.0,
            0.35 * avg_rank + 0.25 * avg_distance + 0.20 * coverage + 0.20 * diversity,
        ),
        4,
    )


def _higher_order_score(selected: list[LensBundleMember]) -> float:
    if len(selected) <= 1:
        return 0.0
    unique_patterns = len({pattern for member in selected for pattern in member.matched_patterns})
    families = len({member.domain_family for member in selected if member.domain_family})
    overlap_penalty = 0.0
    pattern_sets = [set(member.matched_patterns) for member in selected]
    for idx, left in enumerate(pattern_sets):
        for right in pattern_sets[idx + 1 :]:
            if left and right:
                overlap_penalty += len(left & right) / len(left | right)
    if len(selected) > 1:
        overlap_penalty /= len(selected) - 1
    score = (
        0.45 * min(1.0, unique_patterns / 4.0)
        + 0.45 * min(1.0, families / len(selected))
        + 0.10 * (1.0 - min(overlap_penalty, 1.0))
    )
    return round(min(max(score, 0.0), 1.0), 4)


def _active_bundle_id(bundles: list[LensBundleProof]) -> str:
    for bundle in bundles:
        if bundle.status == "active":
            return bundle.bundle_id
    return bundles[0].bundle_id if bundles else ""


def _build_lineages(
    members: list[LensBundleMember],
    bundles: list[LensBundleProof],
    reference_generation: int,
) -> list[LensLineage]:
    lines: list[LensLineage] = []
    proof_bundle_lookup = {
        member_id: bundle.bundle_id
        for bundle in bundles
        for member_id in bundle.member_ids
        if bundle.status in {"active", "supporting"}
    }
    for member in members:
        fingerprint = _hash_text(
            json.dumps(
                {
                    "lens_id": member.lens_id,
                    "fingerprint64": member.card_fingerprint64,
                    "reference_generation": reference_generation,
                },
                sort_keys=True,
            )
        )
        lines.append(
            LensLineage(
                lineage_id=f"lineage:{member.lens_id}:g1",
                entity_id=member.lens_id,
                entity_kind="lens",
                generation=1,
                derivation_kind="library",
                reference_generation=reference_generation,
                proof_bundle_id=proof_bundle_lookup.get(member.lens_id, ""),
                fingerprint=fingerprint,
                parent_bundle_ids=(
                    [proof_bundle_lookup[member.lens_id]]
                    if member.lens_id in proof_bundle_lookup
                    else []
                ),
            )
        )
    return lines


def _build_composites(
    bundles: list[LensBundleProof],
    lineages: list[LensLineage],
    reference_generation: int,
) -> list[CompositeLens]:
    composites: list[CompositeLens] = []
    active_bundle = next((bundle for bundle in bundles if bundle.status == "active"), None)
    if active_bundle is None or len(active_bundle.member_ids) <= 1:
        return composites

    component_lineages = [
        lineage.lineage_id for lineage in lineages if lineage.entity_id in active_bundle.member_ids
    ]
    fingerprint = _hash_text(
        json.dumps(
            {
                "bundle_id": active_bundle.bundle_id,
                "component_lineages": component_lineages,
                "reference_generation": reference_generation,
            },
            sort_keys=True,
        )
    )
    composites.append(
        CompositeLens(
            composite_id=f"composite:{fingerprint[:12]}",
            component_lineage_ids=component_lineages,
            component_lens_ids=list(active_bundle.member_ids),
            derived_from_bundle_id=active_bundle.bundle_id,
            version=1,
            reference_generation=reference_generation,
            status="active",
            fingerprint=fingerprint,
            summary=(
                f"Derived composite lens for bundle {active_bundle.bundle_id} "
                f"with {len(active_bundle.member_ids)} parents."
            ),
        )
    )
    return composites


def _build_guards(
    bundles: list[LensBundleProof],
    composites: list[CompositeLens],
    research: ResearchReferenceState | None,
    reference_generation: int,
) -> list[GuardDecision]:
    guards: list[GuardDecision] = []
    active_bundle = next((bundle for bundle in bundles if bundle.status == "active"), None)
    if active_bundle is not None:
        cohesion_status = "passed" if active_bundle.cohesion_score >= 0.62 else "warning"
        guards.append(
            GuardDecision(
                guard_id=f"guard:cohesion:{active_bundle.bundle_id}",
                kind="bundle_cohesion_floor",
                status=cohesion_status,
                target_id=active_bundle.bundle_id,
                summary=(f"Cohesion floor {cohesion_status} ({active_bundle.cohesion_score:.2f})."),
                details=list(active_bundle.clauses),
            )
        )
        if len(active_bundle.member_ids) == 1:
            guards.append(
                GuardDecision(
                    guard_id=f"guard:singleton:{active_bundle.bundle_id}",
                    kind="singleton_fallback",
                    status="triggered",
                    target_id=active_bundle.bundle_id,
                    summary="No strong higher-order bundle cleared the proof floor; singleton fallback is active.",
                    details=[active_bundle.summary],
                )
            )
        else:
            guards.append(
                GuardDecision(
                    guard_id=f"guard:higher-order:{active_bundle.bundle_id}",
                    kind="higher_order_support",
                    status="passed" if active_bundle.higher_order_score >= 0.50 else "warning",
                    target_id=active_bundle.bundle_id,
                    summary=(
                        f"Higher-order bundle support={active_bundle.higher_order_score:.2f}."
                    ),
                    details=[
                        f"Complementary axes: {', '.join(active_bundle.complementary_axes) or 'none'}"
                    ],
                )
            )
    guards.append(
        GuardDecision(
            guard_id=f"guard:reference-generation:{reference_generation}",
            kind="reference_generation",
            status="passed",
            target_id=str(reference_generation),
            summary=(
                research.summary()
                if research is not None
                else "No research reference artifacts bound to this run."
            ),
            details=[
                (
                    f"reference signature={research.reference_signature}"
                    if research is not None
                    else "reference signature=none"
                )
            ],
        )
    )
    if composites:
        guards.append(
            GuardDecision(
                guard_id=f"guard:composite:{composites[0].composite_id}",
                kind="composite_dependency",
                status="passed",
                target_id=composites[0].composite_id,
                summary="Derived composite lens is bound to the active bundle and current reference generation.",
                details=[composites[0].summary],
            )
        )
    return guards


def _build_fold_states(
    bundles: list[LensBundleProof],
    lineages: list[LensLineage],
    guards: list[GuardDecision],
    reference_generation: int,
) -> list[FoldState]:
    states: list[FoldState] = []
    guard_map: dict[str, list[str]] = {}
    for guard in guards:
        guard_map.setdefault(guard.target_id, []).append(guard.guard_id)

    for bundle in bundles:
        status = "folded"
        if bundle.status == "active" and len(bundle.member_ids) > 1:
            status = "composed"
        elif bundle.status == "active":
            status = "singleton_fallback"
        elif bundle.status == "supporting":
            status = "supporting"
        elif bundle.status == "invalidated":
            status = "invalidated"

        lineage_ids = [
            lineage.lineage_id for lineage in lineages if lineage.entity_id in bundle.member_ids
        ]
        states.append(
            FoldState(
                fold_id=f"fold:{bundle.bundle_id}",
                bundle_id=bundle.bundle_id,
                status=status,
                reference_generation=reference_generation,
                active_lineage_ids=lineage_ids,
                guard_ids=list(guard_map.get(bundle.bundle_id, [])),
                summary=bundle.summary,
            )
        )
    return states


__all__ = [
    "CompositeLens",
    "FoldState",
    "GuardDecision",
    "InvalidationEvent",
    "LensBundleMember",
    "LensBundleProof",
    "LensEngineState",
    "LensLineage",
    "RecompositionEvent",
    "ResearchReferenceArtifact",
    "ResearchReferenceState",
    "lens_engine_lot_kinds",
]
