"""Cohesion-cell substrate for bundle-aware lens selection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hephaestus.lenses.cards import LensCard, compile_lens_card
from hephaestus.lenses.lineage import LensLineage, compute_reference_signature

_CELL_KIND_WEIGHT: dict[str, float] = {
    "mechanism": 1.2,
    "transfer": 1.0,
    "constraint": 0.8,
    "evidence": 0.65,
    "novelty": 0.55,
    "domain": 0.45,
    "lineage": 0.4,
    "reference": 0.4,
    "baseline": 0.35,
}


def _normalize_token(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _extract_tokens(value: str) -> list[str]:
    return [_normalize_token(match) for match in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_\-/ ]{1,40}", value)]


def _stable_hash(parts: Sequence[str]) -> str:
    text = json.dumps(list(parts), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _stable_payload_hash(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LensMembership:
    """A lens's membership in one cohesion cell."""

    lens_id: str
    cell_id: str
    kind: str
    token: str
    weight: float
    confidence: float
    domain_family: str
    lineage_token: str = ""
    reference_signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "cell_id": self.cell_id,
            "kind": self.kind,
            "token": self.token,
            "weight": self.weight,
            "confidence": self.confidence,
            "domain_family": self.domain_family,
            "lineage_token": self.lineage_token,
            "reference_signature": self.reference_signature,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LensMembership:
        return cls(
            lens_id=str(data["lens_id"]),
            cell_id=str(data["cell_id"]),
            kind=str(data["kind"]),
            token=str(data["token"]),
            weight=float(data.get("weight", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            domain_family=str(data.get("domain_family", "general")),
            lineage_token=str(data.get("lineage_token", "")),
            reference_signature=str(data.get("reference_signature", "")),
        )


@dataclass
class CohesionCell:
    """A typed normalized cell shared by one or more lenses."""

    cell_id: str
    kind: str
    token: str
    memberships: list[LensMembership] = field(default_factory=list)

    @property
    def total_weight(self) -> float:
        return sum(member.weight for member in self.memberships)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "kind": self.kind,
            "token": self.token,
            "memberships": [membership.to_dict() for membership in self.memberships],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CohesionCell:
        return cls(
            cell_id=str(data["cell_id"]),
            kind=str(data["kind"]),
            token=str(data["token"]),
            memberships=[
                LensMembership.from_dict(item)
                for item in list(data.get("memberships", []) or [])
            ],
        )


def _reference_tokens(
    reference_context: Mapping[str, Any] | Sequence[Any] | None,
) -> list[str]:
    if not reference_context:
        return []
    if isinstance(reference_context, Mapping):
        tokens: list[str] = []
        for key, value in reference_context.items():
            tokens.extend(_extract_tokens(str(key)))
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    tokens.extend(_extract_tokens(str(item)))
            elif isinstance(value, Mapping):
                tokens.extend(_extract_tokens(json.dumps(dict(value), sort_keys=True)))
            else:
                tokens.extend(_extract_tokens(str(value)))
        return tokens

    tokens = []
    for lot in reference_context:
        tokens.extend(_extract_tokens(getattr(lot, "kind", "")))
        tokens.extend(_extract_tokens(getattr(lot, "subject_key", "")))
    return tokens


def _normalize_tokens(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        for token in _extract_tokens(str(value)):
            if len(token) < 3 or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return tuple(ordered)


def _branch_signature(branch: Any | None) -> str:
    if branch is None:
        return ""
    commitments = [getattr(commitment, "statement", "") for commitment in getattr(branch, "commitments", ())]
    operators = [operator.summary() for operator in getattr(branch, "recovery_operators", ())]
    payload = {
        "branch_id": getattr(branch, "branch_id", ""),
        "commitments": commitments,
        "open_questions": list(getattr(branch, "open_questions", ())),
        "operators": operators,
        "rejected_patterns": list(getattr(branch, "rejected_patterns", ())),
        "stage_cursor": getattr(branch, "stage_cursor", ""),
        "status": getattr(getattr(branch, "status", None), "value", getattr(branch, "status", "")),
        "metrics": {
            "collapse_risk": getattr(getattr(branch, "metrics", None), "collapse_risk", 0.0),
            "future_option_preservation": getattr(
                getattr(branch, "metrics", None),
                "future_option_preservation",
                0.0,
            ),
            "comfort_penalty": getattr(getattr(branch, "metrics", None), "comfort_penalty", 0.0),
        },
    }
    return _stable_payload_hash(payload)


class CohesionCellIndex:
    """Inverted index from typed cell tokens to lens memberships."""

    def __init__(
        self,
        *,
        cells: Mapping[str, CohesionCell] | None = None,
        lens_memberships: Mapping[str, list[LensMembership]] | None = None,
        reference_signature: str = "",
        version_token: str = "",
    ) -> None:
        self._cells: dict[str, CohesionCell] = dict(cells or {})
        self._lens_memberships: dict[str, list[LensMembership]] = {
            lens_id: list(memberships)
            for lens_id, memberships in dict(lens_memberships or {}).items()
        }
        self.reference_signature = reference_signature
        self.version_token = version_token

    @classmethod
    def build(
        cls,
        cards: Mapping[str, LensCard],
        *,
        lineages: Mapping[str, LensLineage] | None = None,
        reference_context: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> CohesionCellIndex:
        lineage_map = dict(lineages or {})
        ref_signature = compute_reference_signature(reference_context)
        cells: dict[str, CohesionCell] = {}
        memberships_by_lens: dict[str, list[LensMembership]] = {}

        for card in cards.values():
            memberships = cls._derive_memberships(
                card,
                lineage=lineage_map.get(card.lens_id),
                reference_context=reference_context,
                reference_signature=ref_signature,
            )
            memberships_by_lens[card.lens_id] = memberships
            for membership in memberships:
                cell = cells.setdefault(
                    membership.cell_id,
                    CohesionCell(
                        cell_id=membership.cell_id,
                        kind=membership.kind,
                        token=membership.token,
                    ),
                )
                cell.memberships.append(membership)

        version_parts = [
            ref_signature,
            *[f"{card.lens_id}:{card.fingerprint64}:{card.lineage_token}" for card in cards.values()],
        ]
        version_token = _stable_hash(version_parts)
        return cls(
            cells=cells,
            lens_memberships=memberships_by_lens,
            reference_signature=ref_signature,
            version_token=version_token,
        )

    @staticmethod
    def _derive_memberships(
        card: LensCard,
        *,
        lineage: LensLineage | None,
        reference_context: Mapping[str, Any] | Sequence[Any] | None,
        reference_signature: str,
    ) -> list[LensMembership]:
        field_map = {
            "mechanism": card.mechanism_signature,
            "transfer": card.transfer_shape,
            "constraint": card.constraints,
            "baseline": card.disallowed_baselines,
            "evidence": card.evidence_atoms,
            "novelty": card.novelty_axes,
            "domain": [card.domain_family, card.domain_name],
        }
        ref_tokens = _reference_tokens(reference_context)
        if ref_tokens:
            field_map["reference"] = sorted(set(ref_tokens))
        if lineage is not None:
            lineage_tokens = [
                lineage.source_kind,
                lineage.derivation,
                *[source.lens_id for source in lineage.parent_sources],
                *lineage.reference_keys,
            ]
            if lineage.reference_digest:
                lineage_tokens.append(lineage.reference_digest)
            field_map["lineage"] = sorted({_normalize_token(token) for token in lineage_tokens if token})

        memberships: list[LensMembership] = []
        confidence_default = sum(card.confidence) / len(card.confidence) if card.confidence else 0.75
        for kind, values in field_map.items():
            base_weight = _CELL_KIND_WEIGHT.get(kind, 0.4)
            for raw_value in values:
                for token in _extract_tokens(raw_value):
                    if not token:
                        continue
                    cell_id = f"{kind}:{token}"
                    memberships.append(
                        LensMembership(
                            lens_id=card.lens_id,
                            cell_id=cell_id,
                            kind=kind,
                            token=token,
                            weight=base_weight,
                            confidence=confidence_default,
                            domain_family=card.domain_family,
                            lineage_token=card.lineage_token,
                            reference_signature=reference_signature or card.reference_signature,
                        )
                    )
        return memberships

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_signature": self.reference_signature,
            "version_token": self.version_token,
            "cells": {cell_id: cell.to_dict() for cell_id, cell in self._cells.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CohesionCellIndex:
        cells = {
            str(cell_id): CohesionCell.from_dict(payload)
            for cell_id, payload in dict(data.get("cells", {}) or {}).items()
        }
        memberships_by_lens: dict[str, list[LensMembership]] = {}
        for cell in cells.values():
            for membership in cell.memberships:
                memberships_by_lens.setdefault(membership.lens_id, []).append(membership)
        return cls(
            cells=cells,
            lens_memberships=memberships_by_lens,
            reference_signature=str(data.get("reference_signature", "")),
            version_token=str(data.get("version_token", "")),
        )

    def memberships_for_lens(self, lens_id: str) -> list[LensMembership]:
        return list(self._lens_memberships.get(lens_id, []))

    def relevant_memberships(self, query_terms: Iterable[str]) -> list[LensMembership]:
        normalized_terms = {_normalize_token(term) for term in query_terms if _normalize_token(term)}
        if not normalized_terms:
            return []
        matches: list[LensMembership] = []
        for cell in self._cells.values():
            if cell.token in normalized_terms:
                matches.extend(cell.memberships)
        return matches

    def score_lenses(self, query_terms: Iterable[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for membership in self.relevant_memberships(query_terms):
            scores[membership.lens_id] = scores.get(membership.lens_id, 0.0) + (
                membership.weight * membership.confidence
            )
        return scores

    def matched_tokens_for_lens(self, lens_id: str, query_terms: Iterable[str]) -> set[str]:
        normalized_terms = {_normalize_token(term) for term in query_terms if _normalize_token(term)}
        return {
            membership.token
            for membership in self._lens_memberships.get(lens_id, [])
            if membership.token in normalized_terms
        }

    def shared_cells(
        self,
        lens_ids: Sequence[str],
        *,
        query_terms: Iterable[str] | None = None,
        min_members: int = 2,
    ) -> list[CohesionCell]:
        if not lens_ids:
            return []
        lens_set = set(lens_ids)
        normalized_terms = None
        if query_terms is not None:
            normalized_terms = {_normalize_token(term) for term in query_terms if _normalize_token(term)}

        shared: list[CohesionCell] = []
        for cell in self._cells.values():
            matching_memberships = [m for m in cell.memberships if m.lens_id in lens_set]
            if len(matching_memberships) < min_members:
                continue
            if normalized_terms is not None and cell.token not in normalized_terms and cell.kind not in {"lineage", "reference"}:
                continue
            shared.append(
                CohesionCell(
                    cell_id=cell.cell_id,
                    kind=cell.kind,
                    token=cell.token,
                    memberships=matching_memberships,
                )
            )
        shared.sort(key=lambda item: item.total_weight, reverse=True)
        return shared

    def lens_coverage(self, lens_id: str, query_terms: Iterable[str]) -> float:
        normalized_terms = {_normalize_token(term) for term in query_terms if _normalize_token(term)}
        if not normalized_terms:
            return 0.0
        matched = self.matched_tokens_for_lens(lens_id, normalized_terms)
        return len(matched) / len(normalized_terms)

    def bundle_union_tokens(self, lens_ids: Sequence[str], query_terms: Iterable[str]) -> set[str]:
        union: set[str] = set()
        for lens_id in lens_ids:
            union.update(self.matched_tokens_for_lens(lens_id, query_terms))
        return union


@dataclass(frozen=True)
class RuntimeReferenceState:
    """Normalized runtime snapshot used by bundle proofs, lineage, and guards."""

    reference_signature: str
    research_signature: str
    branch_signature: str
    constraint_signature: str
    source_versions: dict[str, str] = field(default_factory=dict)
    lot_keys: tuple[str, ...] = ()
    baseline_keywords: tuple[str, ...] = ()
    invalidation_epoch: int = 0

    def combined_signature(self) -> str:
        return _stable_payload_hash(
            {
                "reference_signature": self.reference_signature,
                "research_signature": self.research_signature,
                "branch_signature": self.branch_signature,
                "constraint_signature": self.constraint_signature,
                "source_versions": self.source_versions,
                "lot_keys": self.lot_keys,
                "baseline_keywords": self.baseline_keywords,
                "invalidation_epoch": self.invalidation_epoch,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_signature": self.reference_signature,
            "research_signature": self.research_signature,
            "branch_signature": self.branch_signature,
            "constraint_signature": self.constraint_signature,
            "source_versions": dict(self.source_versions),
            "lot_keys": list(self.lot_keys),
            "baseline_keywords": list(self.baseline_keywords),
            "invalidation_epoch": self.invalidation_epoch,
            "combined_signature": self.combined_signature(),
        }


@dataclass(frozen=True)
class RuntimeCohesionCell:
    """Per-lens runtime cell used to build executable bundle proofs."""

    cell_id: str
    lens_id: str
    domain_family: str
    card_fingerprint: int
    card_version: int
    mechanism_signature: tuple[str, ...]
    transfer_shape: tuple[str, ...]
    constraint_tokens: tuple[str, ...]
    novelty_axes: tuple[str, ...]
    disallowed_baselines: tuple[str, ...]
    evidence_atoms: tuple[str, ...]
    matched_patterns: tuple[str, ...]
    reference_signature: str
    research_signature: str
    branch_signature: str
    fatigue_penalty: float = 0.0
    novelty_pressure: float = 0.0

    def coverage(self, problem_maps_to: set[str]) -> float:
        if not problem_maps_to:
            return 0.0
        target = {item.lower() for item in problem_maps_to}
        covered = target & set(self.transfer_shape)
        return len(covered) / len(target)

    def missing_shapes(self, problem_maps_to: set[str]) -> tuple[str, ...]:
        if not problem_maps_to:
            return ()
        target = {item.lower() for item in problem_maps_to}
        return tuple(sorted(target - set(self.transfer_shape)))

    def constraint_support(self, constraints: list[str]) -> float:
        if not constraints:
            return 1.0
        hits = 0
        cell_tokens = set(self.constraint_tokens)
        for constraint in constraints:
            if cell_tokens & set(_normalize_tokens([constraint])):
                hits += 1
        return hits / len(constraints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "lens_id": self.lens_id,
            "domain_family": self.domain_family,
            "card_fingerprint": self.card_fingerprint,
            "card_version": self.card_version,
            "mechanism_signature": list(self.mechanism_signature),
            "transfer_shape": list(self.transfer_shape),
            "constraint_tokens": list(self.constraint_tokens),
            "novelty_axes": list(self.novelty_axes),
            "disallowed_baselines": list(self.disallowed_baselines),
            "evidence_atoms": list(self.evidence_atoms),
            "matched_patterns": list(self.matched_patterns),
            "reference_signature": self.reference_signature,
            "research_signature": self.research_signature,
            "branch_signature": self.branch_signature,
            "fatigue_penalty": self.fatigue_penalty,
            "novelty_pressure": self.novelty_pressure,
        }


@dataclass(frozen=True)
class RuntimeFoldState:
    """Runtime cohesion state shared by an active bundle."""

    bundle_id: str
    cell_ids: tuple[str, ...]
    active_lens_ids: tuple[str, ...]
    problem_signature: str
    reference_signature: str
    research_signature: str
    branch_signature: str
    shared_shapes: tuple[str, ...]
    union_shapes: tuple[str, ...]
    pairwise_compatibility: dict[str, float]
    conditional_support: dict[str, tuple[str, ...]]
    critical_lens_ids: tuple[str, ...]
    higher_order_support: float
    coverage_score: float
    cohesion_score: float
    fallback_score: float

    def reference_continuous(self, reference_state: RuntimeReferenceState) -> bool:
        return (
            self.reference_signature == reference_state.reference_signature
            and self.research_signature == reference_state.research_signature
            and (
                not self.branch_signature
                or not reference_state.branch_signature
                or self.branch_signature == reference_state.branch_signature
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "cell_ids": list(self.cell_ids),
            "active_lens_ids": list(self.active_lens_ids),
            "problem_signature": self.problem_signature,
            "reference_signature": self.reference_signature,
            "research_signature": self.research_signature,
            "branch_signature": self.branch_signature,
            "shared_shapes": list(self.shared_shapes),
            "union_shapes": list(self.union_shapes),
            "pairwise_compatibility": dict(self.pairwise_compatibility),
            "conditional_support": {
                key: list(values) for key, values in self.conditional_support.items()
            },
            "critical_lens_ids": list(self.critical_lens_ids),
            "higher_order_support": self.higher_order_support,
            "coverage_score": self.coverage_score,
            "cohesion_score": self.cohesion_score,
            "fallback_score": self.fallback_score,
        }


def build_reference_state(
    structure: Any,
    *,
    branch_genome: Any | None = None,
    reference_lots: list[Any] | None = None,
    baseline_dossier: Any | None = None,
) -> RuntimeReferenceState:
    """Build a normalized reference snapshot from the current runtime state."""

    dossier = baseline_dossier if baseline_dossier is not None else getattr(structure, "baseline_dossier", None)
    lots = reference_lots if reference_lots is not None else getattr(structure, "reference_lots", None)
    if lots is None:
        lots = getattr(structure, "session_reference_lots", [])
    lots = list(lots or [])

    baseline_keywords = _normalize_tokens(
        list(getattr(dossier, "keywords_to_avoid", []) or [])
        + list(getattr(dossier, "common_failure_modes", []) or [])
        + list(getattr(dossier, "known_bottlenecks", []) or [])
        + list(getattr(dossier, "standard_approaches", []) or [])
    )
    lot_keys = tuple(
        sorted(
            filter(
                None,
                (
                    f"{getattr(lot, 'kind', '')}:{getattr(lot, 'subject_key', '')}"
                    for lot in lots
                ),
            )
        )
    )

    reference_payload = {
        "problem": getattr(structure, "original_problem", ""),
        "shape": getattr(structure, "mathematical_shape", ""),
        "baseline_summary": getattr(dossier, "summary", "") if dossier is not None else "",
        "lot_keys": lot_keys,
        "epoch": int(getattr(structure, "reference_invalidation_epoch", 0) or 0),
    }
    research_payload = {
        "baseline_keywords": baseline_keywords,
        "summary": getattr(dossier, "summary", "") if dossier is not None else "",
        "adjacent": getattr(dossier, "adjacent_fields", []) if dossier is not None else [],
    }
    constraints = list(getattr(structure, "constraints", []) or [])
    source_versions = {
        "baseline": _stable_payload_hash(
            {
                "summary": getattr(dossier, "summary", "") if dossier is not None else "",
                "keywords": baseline_keywords,
            }
        ),
        "reference_lots": _stable_payload_hash(lot_keys),
        "constraints": _stable_payload_hash(constraints),
    }
    return RuntimeReferenceState(
        reference_signature=_stable_payload_hash(reference_payload),
        research_signature=_stable_payload_hash(research_payload),
        branch_signature=_branch_signature(branch_genome),
        constraint_signature=_stable_payload_hash(constraints),
        source_versions=source_versions,
        lot_keys=lot_keys,
        baseline_keywords=baseline_keywords,
        invalidation_epoch=int(getattr(structure, "reference_invalidation_epoch", 0) or 0),
    )


def build_cohesion_cell(
    lens_score: Any,
    structure: Any,
    *,
    exclusion_penalty: float = 0.0,
    branch_genome: Any | None = None,
    card: LensCard | None = None,
) -> RuntimeCohesionCell:
    """Compile a scored lens into a runtime cohesion cell."""

    card = card or compile_lens_card(getattr(lens_score, "lens"))
    reference_state = build_reference_state(structure, branch_genome=branch_genome)
    matched_patterns = tuple(
        sorted(
            set(getattr(lens_score, "matched_patterns", []) or ())
            or (set(card.transfer_shape) & set(getattr(structure, "problem_maps_to", set()) or set()))
        )
    )
    novelty_pressure = max(
        0.0,
        min(
            1.0,
            0.65 * float(getattr(lens_score, "domain_distance", 0.0))
            + 0.20 * float(getattr(lens_score, "diversity_weight", 1.0))
            + 0.15 * float(getattr(lens_score, "structural_relevance", 0.0)),
        ),
    )
    return RuntimeCohesionCell(
        cell_id=f"{getattr(lens_score, 'lens').lens_id}:{card.fingerprint64:016x}",
        lens_id=getattr(lens_score, "lens").lens_id,
        domain_family=getattr(lens_score, "lens").domain_family,
        card_fingerprint=card.fingerprint64,
        card_version=card.version,
        mechanism_signature=tuple(card.mechanism_signature),
        transfer_shape=tuple(card.transfer_shape),
        constraint_tokens=tuple(card.constraints),
        novelty_axes=tuple(card.novelty_axes),
        disallowed_baselines=tuple(card.disallowed_baselines),
        evidence_atoms=tuple(card.evidence_atoms),
        matched_patterns=matched_patterns,
        reference_signature=reference_state.reference_signature,
        research_signature=reference_state.research_signature,
        branch_signature=reference_state.branch_signature,
        fatigue_penalty=float(exclusion_penalty),
        novelty_pressure=novelty_pressure,
    )


def build_runtime_fold_state(
    bundle_id: str,
    cells: tuple[RuntimeCohesionCell, ...],
    structure: Any,
    *,
    pairwise_compatibility: dict[str, float],
    conditional_support: dict[str, tuple[str, ...]],
    critical_lens_ids: tuple[str, ...],
    higher_order_support: float,
    coverage_score: float,
    cohesion_score: float,
    fallback_score: float,
) -> RuntimeFoldState:
    """Build a runtime fold-state summary for an active lens bundle."""

    problem_signature = _stable_payload_hash(
        {
            "structure": getattr(structure, "structure", ""),
            "math": getattr(structure, "mathematical_shape", ""),
            "constraints": list(getattr(structure, "constraints", []) or []),
            "maps_to": sorted(getattr(structure, "problem_maps_to", set()) or set()),
        }
    )
    shared_shapes: set[str] | None = None
    union_shapes: set[str] = set()
    for cell in cells:
        shapes = set(cell.transfer_shape)
        union_shapes.update(shapes)
        if shared_shapes is None:
            shared_shapes = set(shapes)
        else:
            shared_shapes &= shapes

    return RuntimeFoldState(
        bundle_id=bundle_id,
        cell_ids=tuple(cell.cell_id for cell in cells),
        active_lens_ids=tuple(cell.lens_id for cell in cells),
        problem_signature=problem_signature,
        reference_signature=cells[0].reference_signature if cells else "",
        research_signature=cells[0].research_signature if cells else "",
        branch_signature=cells[0].branch_signature if cells else "",
        shared_shapes=tuple(sorted(shared_shapes or set())),
        union_shapes=tuple(sorted(union_shapes)),
        pairwise_compatibility=dict(pairwise_compatibility),
        conditional_support=dict(conditional_support),
        critical_lens_ids=critical_lens_ids,
        higher_order_support=float(higher_order_support),
        coverage_score=float(coverage_score),
        cohesion_score=float(cohesion_score),
        fallback_score=float(fallback_score),
    )


__all__ = [
    "CohesionCell",
    "CohesionCellIndex",
    "LensMembership",
    "RuntimeCohesionCell",
    "RuntimeFoldState",
    "RuntimeReferenceState",
    "build_cohesion_cell",
    "build_reference_state",
    "build_runtime_fold_state",
]
