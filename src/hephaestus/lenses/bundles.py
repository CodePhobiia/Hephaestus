"""Bundle construction and proof validation for adaptive lens selection."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from hephaestus.lenses.cards import LensCard
from hephaestus.lenses.cells import (
    CohesionCell,
    CohesionCellIndex,
    RuntimeCohesionCell,
    RuntimeFoldState,
    build_cohesion_cell,
    build_runtime_fold_state,
)
from hephaestus.lenses.exclusion_ledger import AdaptiveExclusionLedger, LedgerDecision
from hephaestus.lenses.lineage import (
    LensLineage,
    LineageValidationResult,
    compute_reference_signature,
    validate_lineage,
)
from hephaestus.session.reference_lots import ReferenceLot


def _stable_hash(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class FoldState:
    """Bundle fold-state computed from cohesion cells and query coverage."""

    query_terms: tuple[str, ...]
    matched_terms: tuple[str, ...]
    shared_cell_ids: tuple[str, ...]
    coverage_ratio: float
    cohesion_mass: float
    complementarity: float
    conditional_lift: float
    family_diversity: float
    novelty_span: float
    redundancy_penalty: float
    proof_strength: float
    member_contributions: dict[str, float] = field(default_factory=dict)
    blocked_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_terms": list(self.query_terms),
            "matched_terms": list(self.matched_terms),
            "shared_cell_ids": list(self.shared_cell_ids),
            "coverage_ratio": self.coverage_ratio,
            "cohesion_mass": self.cohesion_mass,
            "complementarity": self.complementarity,
            "conditional_lift": self.conditional_lift,
            "family_diversity": self.family_diversity,
            "novelty_span": self.novelty_span,
            "redundancy_penalty": self.redundancy_penalty,
            "proof_strength": self.proof_strength,
            "member_contributions": dict(self.member_contributions),
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class BundleValidationResult:
    """Validation outcome for a bundle proof."""

    valid: bool
    reasons: tuple[str, ...]
    lineage_results: dict[str, LineageValidationResult]


@dataclass(frozen=True)
class BundleProof:
    """Proof object carried with a selected lens bundle."""

    bundle_id: str
    member_lens_ids: tuple[str, ...]
    member_card_fingerprints: dict[str, int]
    lineage_tokens: dict[str, str]
    fold_signature: str
    query_signature: str
    reference_signature: str
    loader_revision: int
    proof_strength: float
    selector_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "member_lens_ids": list(self.member_lens_ids),
            "member_card_fingerprints": dict(self.member_card_fingerprints),
            "lineage_tokens": dict(self.lineage_tokens),
            "fold_signature": self.fold_signature,
            "query_signature": self.query_signature,
            "reference_signature": self.reference_signature,
            "loader_revision": self.loader_revision,
            "proof_strength": self.proof_strength,
            "selector_version": self.selector_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BundleProof:
        return cls(
            bundle_id=str(data["bundle_id"]),
            member_lens_ids=tuple(
                str(item) for item in list(data.get("member_lens_ids", []) or [])
            ),
            member_card_fingerprints={
                str(key): int(value)
                for key, value in dict(data.get("member_card_fingerprints", {}) or {}).items()
            },
            lineage_tokens={
                str(key): str(value)
                for key, value in dict(data.get("lineage_tokens", {}) or {}).items()
            },
            fold_signature=str(data.get("fold_signature", "")),
            query_signature=str(data.get("query_signature", "")),
            reference_signature=str(data.get("reference_signature", "")),
            loader_revision=int(data.get("loader_revision", 0)),
            proof_strength=float(data.get("proof_strength", 0.0)),
            selector_version=int(data.get("selector_version", 1)),
        )

    def validate(
        self,
        *,
        cards: Mapping[str, LensCard],
        lineages: Mapping[str, LensLineage],
        loader_revision: int,
        reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ) -> BundleValidationResult:
        reasons: list[str] = []
        lineage_results: dict[str, LineageValidationResult] = {}
        current_reference = compute_reference_signature(reference_context)
        if self.reference_signature and self.reference_signature != current_reference:
            reasons.append("reference context changed")
        if self.loader_revision != loader_revision:
            reasons.append("loader revision changed")

        for lens_id in self.member_lens_ids:
            card = cards.get(lens_id)
            lineage = lineages.get(lens_id)
            if card is None:
                reasons.append(f"missing card: {lens_id}")
                continue
            if lineage is None:
                reasons.append(f"missing lineage: {lens_id}")
                continue
            if self.member_card_fingerprints.get(lens_id) != card.fingerprint64:
                reasons.append(f"card fingerprint changed: {lens_id}")
            if self.lineage_tokens.get(lens_id) != lineage.proof_token:
                reasons.append(f"lineage token changed: {lens_id}")
            lineage_result = validate_lineage(
                lineage,
                current_cards=cards,
                current_lineages=lineages,
                loader_revision=loader_revision,
                reference_context=reference_context,
            )
            lineage_results[lens_id] = lineage_result
            if not lineage_result.valid:
                reasons.extend(f"{lens_id}: {reason}" for reason in lineage_result.reasons)

        unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
        return BundleValidationResult(
            valid=not unique_reasons,
            reasons=unique_reasons,
            lineage_results=lineage_results,
        )


@dataclass(frozen=True)
class BundleCandidate:
    """One evaluated lens bundle."""

    lens_ids: tuple[str, ...]
    bundle_score: float
    fold_state: FoldState
    proof: BundleProof
    ledger_decision: LedgerDecision
    families: tuple[str, ...]
    novelty_axes: tuple[str, ...]


def _pairwise_overlap(
    index: CohesionCellIndex, lens_ids: Sequence[str], query_terms: Sequence[str]
) -> float:
    if len(lens_ids) < 2:
        return 0.0
    overlaps: list[float] = []
    for left, right in itertools.combinations(lens_ids, 2):
        left_tokens = index.matched_tokens_for_lens(left, query_terms)
        right_tokens = index.matched_tokens_for_lens(right, query_terms)
        union = left_tokens | right_tokens
        if not union:
            overlaps.append(0.0)
            continue
        overlaps.append(len(left_tokens & right_tokens) / len(union))
    return sum(overlaps) / len(overlaps)


def _max_pair_coverage(
    index: CohesionCellIndex, lens_ids: Sequence[str], query_terms: Sequence[str]
) -> float:
    if len(lens_ids) < 3:
        return 0.0
    max_coverage = 0.0
    for pair in itertools.combinations(lens_ids, 2):
        coverage = len(index.bundle_union_tokens(pair, query_terms)) / max(1, len(query_terms))
        max_coverage = max(max_coverage, coverage)
    return max_coverage


def build_fold_state(
    lens_ids: Sequence[str],
    *,
    cards: Mapping[str, LensCard],
    cell_index: CohesionCellIndex,
    query_terms: Sequence[str],
    base_scores: Mapping[str, float],
    shared_cells: Sequence[CohesionCell] | None = None,
) -> FoldState:
    """Compute fold-state metrics for a candidate bundle."""
    shared = list(shared_cells or cell_index.shared_cells(lens_ids, query_terms=query_terms))
    bundle_tokens = cell_index.bundle_union_tokens(lens_ids, query_terms)
    coverage_ratio = len(bundle_tokens) / max(1, len(query_terms))
    cohesion_mass = (
        sum(cell.total_weight for cell in shared) / max(1.0, len(lens_ids)) if shared else 0.0
    )
    member_contributions: dict[str, float] = {}
    novelty_axes: set[str] = set()
    families: set[str] = set()
    for lens_id in lens_ids:
        member_contributions[lens_id] = base_scores.get(lens_id, 0.0) + cell_index.lens_coverage(
            lens_id,
            query_terms,
        )
        card = cards[lens_id]
        novelty_axes.update(card.novelty_axes)
        families.add(card.domain_family)

    complementarity = 0.0
    for lens_id in lens_ids:
        own_tokens = cell_index.matched_tokens_for_lens(lens_id, query_terms)
        other_tokens = cell_index.bundle_union_tokens(
            [other for other in lens_ids if other != lens_id],
            query_terms,
        )
        complementarity += len(own_tokens - other_tokens) / max(1, len(query_terms))
    complementarity /= max(1, len(lens_ids))

    redundancy_penalty = _pairwise_overlap(cell_index, lens_ids, query_terms)
    conditional_lift = max(
        0.0, coverage_ratio - _max_pair_coverage(cell_index, lens_ids, query_terms)
    )
    family_diversity = len(families) / max(1, len(lens_ids))
    novelty_span = len(novelty_axes) / max(
        1,
        sum(max(1, len(cards[lens_id].novelty_axes)) for lens_id in lens_ids),
    )

    max_base = max(base_scores.values(), default=1.0)
    base_strength = sum(base_scores.get(lens_id, 0.0) for lens_id in lens_ids) / (
        max(1, len(lens_ids)) * max(0.001, max_base)
    )
    proof_strength = (
        0.32 * base_strength
        + 0.24 * coverage_ratio
        + 0.16 * cohesion_mass
        + 0.12 * complementarity
        + 0.10 * conditional_lift
        + 0.08 * family_diversity
        + 0.08 * novelty_span
        - 0.14 * redundancy_penalty
    )
    proof_strength = max(0.0, min(1.5, proof_strength))

    return FoldState(
        query_terms=tuple(query_terms),
        matched_terms=tuple(sorted(bundle_tokens)),
        shared_cell_ids=tuple(cell.cell_id for cell in shared),
        coverage_ratio=coverage_ratio,
        cohesion_mass=cohesion_mass,
        complementarity=complementarity,
        conditional_lift=conditional_lift,
        family_diversity=family_diversity,
        novelty_span=novelty_span,
        redundancy_penalty=redundancy_penalty,
        proof_strength=proof_strength,
        member_contributions=member_contributions,
    )


def _make_bundle_proof(
    lens_ids: Sequence[str],
    *,
    cards: Mapping[str, LensCard],
    lineages: Mapping[str, LensLineage],
    fold_state: FoldState,
    loader_revision: int,
    reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
) -> BundleProof:
    member_lens_ids = tuple(lens_ids)
    query_signature = _stable_hash({"query_terms": list(fold_state.query_terms)})
    fold_signature = _stable_hash(fold_state.to_dict())
    reference_signature = compute_reference_signature(reference_context)
    payload = {
        "member_lens_ids": list(member_lens_ids),
        "member_card_fingerprints": {
            lens_id: cards[lens_id].fingerprint64 for lens_id in member_lens_ids
        },
        "lineage_tokens": {lens_id: lineages[lens_id].proof_token for lens_id in member_lens_ids},
        "fold_signature": fold_signature,
        "query_signature": query_signature,
        "reference_signature": reference_signature,
        "loader_revision": loader_revision,
    }
    bundle_id = f"bundle_{_stable_hash(payload)}"
    return BundleProof(
        bundle_id=bundle_id,
        member_lens_ids=member_lens_ids,
        member_card_fingerprints=dict(payload["member_card_fingerprints"]),
        lineage_tokens=dict(payload["lineage_tokens"]),
        fold_signature=fold_signature,
        query_signature=query_signature,
        reference_signature=reference_signature,
        loader_revision=loader_revision,
        proof_strength=fold_state.proof_strength,
    )


def build_bundle_candidates(
    *,
    cards: Mapping[str, LensCard],
    lineages: Mapping[str, LensLineage],
    cell_index: CohesionCellIndex,
    query_terms: Sequence[str],
    base_scores: Mapping[str, float],
    loader_revision: int,
    reference_context: Mapping[str, Any] | Sequence[ReferenceLot] | None = None,
    ledger: AdaptiveExclusionLedger | None = None,
    max_bundle_size: int = 3,
    min_bundle_score: float = 0.55,
    seed_limit: int = 10,
) -> list[BundleCandidate]:
    """Evaluate bundle candidates from the current query and card state."""
    if len(base_scores) < 2:
        return []

    ranked_lens_ids = [
        lens_id
        for lens_id, _ in sorted(base_scores.items(), key=lambda item: item[1], reverse=True)
    ][:seed_limit]
    candidates: list[BundleCandidate] = []

    for size in range(2, min(max_bundle_size, len(ranked_lens_ids)) + 1):
        for lens_ids in itertools.combinations(ranked_lens_ids, size):
            fold_state = build_fold_state(
                lens_ids,
                cards=cards,
                cell_index=cell_index,
                query_terms=query_terms,
                base_scores=base_scores,
            )
            if (
                fold_state.coverage_ratio < 0.25
                or fold_state.proof_strength < 0.4
                or (fold_state.cohesion_mass < 0.1 and fold_state.conditional_lift < 0.1)
            ):
                continue

            novelty_axes = tuple(
                sorted({axis for lens_id in lens_ids for axis in cards[lens_id].novelty_axes})
            )
            families = tuple(sorted({cards[lens_id].domain_family for lens_id in lens_ids}))
            proof = _make_bundle_proof(
                lens_ids,
                cards=cards,
                lineages=lineages,
                fold_state=fold_state,
                loader_revision=loader_revision,
                reference_context=reference_context,
            )
            validation = proof.validate(
                cards=cards,
                lineages=lineages,
                loader_revision=loader_revision,
                reference_context=reference_context,
            )
            lineage_valid = validation.valid
            effective_ledger = ledger or AdaptiveExclusionLedger()
            decision = effective_ledger.decide(
                families=families,
                novelty_axes=novelty_axes,
                proof_token=proof.bundle_id,
                lineage_valid=lineage_valid,
            )
            if decision.blocked:
                if ledger:
                    ledger.register_blocked(
                        lens_ids=lens_ids,
                        families=families,
                        novelty_axes=novelty_axes,
                        proof_token=proof.bundle_id,
                        reasons=decision.reasons or validation.reasons,
                    )
                continue

            bundle_score = fold_state.proof_strength * decision.multiplier
            if bundle_score < min_bundle_score:
                continue
            candidates.append(
                BundleCandidate(
                    lens_ids=tuple(lens_ids),
                    bundle_score=bundle_score,
                    fold_state=fold_state,
                    proof=proof,
                    ledger_decision=decision,
                    families=families,
                    novelty_axes=novelty_axes,
                )
            )

    candidates.sort(
        key=lambda item: (
            item.bundle_score,
            item.fold_state.coverage_ratio,
            item.fold_state.conditional_lift,
            item.fold_state.cohesion_mass,
        ),
        reverse=True,
    )
    return candidates


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


@dataclass(frozen=True)
class CompatibilityEvidence:
    """One proof fragment supporting a runtime bundle."""

    kind: str
    members: tuple[str, ...]
    score: float
    rationale: str
    conditions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "members": list(self.members),
            "score": self.score,
            "rationale": self.rationale,
            "conditions": list(self.conditions),
        }


@dataclass(frozen=True)
class RuntimeBundleProof:
    """Executable proof that a lens bundle should run before singleton fallback."""

    bundle_id: str
    lens_ids: tuple[str, ...]
    translation_order: tuple[str, ...]
    cells: tuple[RuntimeCohesionCell, ...]
    fold_state: RuntimeFoldState
    compatibility_evidence: tuple[CompatibilityEvidence, ...]
    conditional_requirements: dict[str, tuple[str, ...]]
    critical_lens_ids: tuple[str, ...]
    member_scores: dict[str, float]
    member_distances: dict[str, float]
    member_relevance: dict[str, float]
    proof_hash: str
    proof_confidence: float
    pairwise_score: float
    conditional_score: float
    higher_order_score: float
    fallback_score: float
    reference_signature: str
    research_signature: str
    branch_signature: str
    derived_card: LensCard
    retrieval_mode: str = "bundle"
    version: int = 1
    lineage_version: int = 1
    invalidated_lens_ids: tuple[str, ...] = ()
    stale: bool = False
    recomposition_count: int = 0
    invalidation_reasons: tuple[str, ...] = ()

    @property
    def active_lens_ids(self) -> tuple[str, ...]:
        invalidated = set(self.invalidated_lens_ids)
        return tuple(lens_id for lens_id in self.lens_ids if lens_id not in invalidated)

    def strength(self) -> float:
        return self.proof_confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "lens_ids": list(self.lens_ids),
            "active_lens_ids": list(self.active_lens_ids),
            "translation_order": list(self.translation_order),
            "cells": [cell.to_dict() for cell in self.cells],
            "fold_state": self.fold_state.to_dict(),
            "compatibility_evidence": [item.to_dict() for item in self.compatibility_evidence],
            "conditional_requirements": {
                key: list(values) for key, values in self.conditional_requirements.items()
            },
            "critical_lens_ids": list(self.critical_lens_ids),
            "member_scores": dict(self.member_scores),
            "member_distances": dict(self.member_distances),
            "member_relevance": dict(self.member_relevance),
            "proof_hash": self.proof_hash,
            "proof_confidence": self.proof_confidence,
            "pairwise_score": self.pairwise_score,
            "conditional_score": self.conditional_score,
            "higher_order_score": self.higher_order_score,
            "fallback_score": self.fallback_score,
            "reference_signature": self.reference_signature,
            "research_signature": self.research_signature,
            "branch_signature": self.branch_signature,
            "derived_card": self.derived_card.to_dict(),
            "retrieval_mode": self.retrieval_mode,
            "version": self.version,
            "lineage_version": self.lineage_version,
            "invalidated_lens_ids": list(self.invalidated_lens_ids),
            "stale": self.stale,
            "recomposition_count": self.recomposition_count,
            "invalidation_reasons": list(self.invalidation_reasons),
        }


@dataclass(frozen=True)
class BundleSelectionResult:
    """Primary runtime selection result for search orchestration."""

    retrieval_mode: str
    selected_lenses: tuple[Any, ...]
    fallback_lenses: tuple[Any, ...]
    primary_bundle: RuntimeBundleProof | None = None
    active_bundle: RuntimeBundleProof | None = None
    exclusion_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "selected_lenses": [score.lens.lens_id for score in self.selected_lenses],
            "fallback_lenses": [score.lens.lens_id for score in self.fallback_lenses],
            "primary_bundle": self.primary_bundle.to_dict()
            if self.primary_bundle is not None
            else None,
            "active_bundle": self.active_bundle.to_dict()
            if self.active_bundle is not None
            else None,
            "exclusion_snapshot": dict(self.exclusion_snapshot),
        }


@dataclass(frozen=True)
class BundleRecomposition:
    """Result of invalidating part of a runtime bundle during execution."""

    original_bundle_id: str
    invalidated_lens_ids: tuple[str, ...]
    reason: str
    new_bundle: RuntimeBundleProof | None
    fallback_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_bundle_id": self.original_bundle_id,
            "invalidated_lens_ids": list(self.invalidated_lens_ids),
            "reason": self.reason,
            "new_bundle": self.new_bundle.to_dict() if self.new_bundle is not None else None,
            "fallback_required": self.fallback_required,
        }


class BundleComposer:
    """Build higher-order runtime bundle proofs from ranked lens scores."""

    def __init__(
        self,
        *,
        exclusion_ledger: AdaptiveExclusionLedger | None = None,
        max_bundle_size: int = 3,
        candidate_pool_size: int = 6,
        min_bundle_strength: float = 0.46,
        min_bundle_gain: float = 0.03,
        allow_singleton_fallback: bool = True,
    ) -> None:
        self._exclusion_ledger = exclusion_ledger or AdaptiveExclusionLedger()
        self._max_bundle_size = max(2, max_bundle_size)
        self._candidate_pool_size = max(3, candidate_pool_size)
        self._min_bundle_strength = min_bundle_strength
        self._min_bundle_gain = min_bundle_gain
        self._allow_singleton_fallback = allow_singleton_fallback

    def select(
        self,
        lens_scores: list[Any],
        structure: Any,
    ) -> BundleSelectionResult:
        if not lens_scores:
            return BundleSelectionResult(
                retrieval_mode="singleton", selected_lenses=(), fallback_lenses=()
            )

        fallback_score = float(getattr(lens_scores[0], "composite_score", 0.0))
        ranked = lens_scores[: self._candidate_pool_size]
        cells: list[RuntimeCohesionCell] = []
        for score in ranked:
            raw_cell = build_cohesion_cell(
                score,
                structure,
                branch_genome=getattr(score, "branch_genome", None),
            )
            cells.append(
                replace(
                    raw_cell,
                    fatigue_penalty=self._exclusion_ledger.penalty_for_cell(raw_cell),
                )
            )
        score_by_lens = {score.lens.lens_id: score for score in ranked}

        best_proof: RuntimeBundleProof | None = None
        max_bundle_size = min(self._max_bundle_size, len(cells))
        for size in range(2, max_bundle_size + 1):
            for combo in itertools.combinations(cells, size):
                proof = self._prove_bundle(tuple(combo), structure, score_by_lens, fallback_score)
                if best_proof is None or proof.proof_confidence > best_proof.proof_confidence:
                    best_proof = proof

        if best_proof is None:
            return self._singleton_result(lens_scores)

        should_use_bundle = best_proof.proof_confidence >= self._min_bundle_strength and (
            best_proof.proof_confidence >= fallback_score + self._min_bundle_gain
            or (best_proof.conditional_score >= 0.55 and best_proof.higher_order_score >= 0.25)
        )
        if not should_use_bundle and self._allow_singleton_fallback:
            return self._singleton_result(lens_scores)

        order = list(best_proof.translation_order)
        selected_lenses = tuple(
            score_by_lens[lens_id] for lens_id in order if lens_id in score_by_lens
        )
        fallback_lenses = tuple(
            score
            for score in lens_scores
            if score.lens.lens_id not in set(best_proof.active_lens_ids)
        )
        self._exclusion_ledger.record_selection(best_proof.active_lens_ids, best_proof.cells)
        return BundleSelectionResult(
            retrieval_mode="bundle",
            selected_lenses=selected_lenses,
            fallback_lenses=fallback_lenses,
            primary_bundle=best_proof,
            active_bundle=best_proof,
            exclusion_snapshot=self._exclusion_ledger.snapshot(),
        )

    def recompose(
        self,
        bundle: RuntimeBundleProof,
        structure: Any,
        *,
        invalidated_lens_ids: tuple[str, ...],
        reason: str,
    ) -> BundleRecomposition:
        invalidated = tuple(sorted(set((*bundle.invalidated_lens_ids, *invalidated_lens_ids))))
        remaining_cells = tuple(
            cell for cell in bundle.cells if cell.lens_id not in set(invalidated)
        )
        if len(remaining_cells) < 2:
            self._exclusion_ledger.record_outcome(
                lens_ids=bundle.lens_ids,
                cells=bundle.cells,
                outcome="invalidated",
                invalidated_lens_ids=invalidated,
            )
            return BundleRecomposition(
                original_bundle_id=bundle.bundle_id,
                invalidated_lens_ids=invalidated,
                reason=reason,
                new_bundle=None,
                fallback_required=True,
            )

        score_by_lens = {
            lens_id: _SyntheticLensScore(
                lens_id=lens_id,
                composite_score=bundle.member_scores[lens_id],
                domain_distance=bundle.member_distances[lens_id],
                structural_relevance=bundle.member_relevance[lens_id],
                domain_family=next(
                    cell.domain_family for cell in remaining_cells if cell.lens_id == lens_id
                ),
            )
            for lens_id in bundle.active_lens_ids
            if lens_id not in set(invalidated)
        }
        new_proof = self._prove_bundle(
            remaining_cells,
            structure,
            score_by_lens,
            bundle.fallback_score,
            version=bundle.version + 1,
            lineage_version=bundle.lineage_version + 1,
            invalidated_lens_ids=invalidated,
            stale=True,
            recomposition_count=bundle.recomposition_count + 1,
            invalidation_reasons=tuple(dict.fromkeys((*bundle.invalidation_reasons, reason))),
        )
        fallback_required = (
            self._allow_singleton_fallback
            and new_proof.proof_confidence < self._min_bundle_strength
        )
        if fallback_required:
            self._exclusion_ledger.record_outcome(
                lens_ids=bundle.lens_ids,
                cells=bundle.cells,
                outcome="recompose_fallback",
                invalidated_lens_ids=invalidated,
            )
            return BundleRecomposition(
                original_bundle_id=bundle.bundle_id,
                invalidated_lens_ids=invalidated,
                reason=reason,
                new_bundle=None,
                fallback_required=True,
            )

        self._exclusion_ledger.record_outcome(
            lens_ids=bundle.lens_ids,
            cells=bundle.cells,
            outcome="recomposed",
            invalidated_lens_ids=invalidated,
        )
        return BundleRecomposition(
            original_bundle_id=bundle.bundle_id,
            invalidated_lens_ids=invalidated,
            reason=reason,
            new_bundle=new_proof,
            fallback_required=False,
        )

    def _singleton_result(self, lens_scores: list[Any]) -> BundleSelectionResult:
        top = tuple(lens_scores[:1])
        return BundleSelectionResult(
            retrieval_mode="singleton",
            selected_lenses=top,
            fallback_lenses=tuple(lens_scores[1:]),
            primary_bundle=None,
            active_bundle=None,
            exclusion_snapshot=self._exclusion_ledger.snapshot(),
        )

    def _prove_bundle(
        self,
        cells: tuple[RuntimeCohesionCell, ...],
        structure: Any,
        score_by_lens: dict[str, Any],
        fallback_score: float,
        *,
        version: int = 1,
        lineage_version: int = 1,
        invalidated_lens_ids: tuple[str, ...] = (),
        stale: bool = False,
        recomposition_count: int = 0,
        invalidation_reasons: tuple[str, ...] = (),
    ) -> RuntimeBundleProof:
        problem_maps = {
            item.lower() for item in (getattr(structure, "problem_maps_to", set()) or set())
        }
        constraints = list(getattr(structure, "constraints", []) or [])

        pairwise_scores: dict[str, float] = {}
        evidence: list[CompatibilityEvidence] = []
        for left, right in itertools.combinations(cells, 2):
            score = self._pairwise_score(left, right, problem_maps, constraints)
            key = f"{left.lens_id}|{right.lens_id}"
            pairwise_scores[key] = score
            evidence.append(
                CompatibilityEvidence(
                    kind="pairwise",
                    members=(left.lens_id, right.lens_id),
                    score=score,
                    rationale=(
                        "Pairwise fit combines complementary transfer shapes, mechanism diversity, "
                        "and family separation while penalizing shared baseline collapse."
                    ),
                )
            )

        conditional_requirements = self._conditional_requirements(cells, problem_maps)
        conditional_score = self._conditional_score(cells, conditional_requirements, problem_maps)
        for lens_id, conditions in conditional_requirements.items():
            evidence.append(
                CompatibilityEvidence(
                    kind="conditional",
                    members=(lens_id,),
                    score=conditional_score,
                    rationale="This lens remains strong only when the rest of the bundle covers its missing shapes.",
                    conditions=conditions,
                )
            )

        coverage_score = self._coverage_score(cells, problem_maps)
        higher_order_score, critical_lens_ids = self._higher_order_score(
            cells, problem_maps, constraints
        )
        if higher_order_score > 0.0:
            evidence.append(
                CompatibilityEvidence(
                    kind="higher_order",
                    members=tuple(cell.lens_id for cell in cells),
                    score=higher_order_score,
                    rationale=(
                        "The bundle has higher-order support because at least one lens contributes coverage or "
                        "constraint support that only emerges when all active lenses are considered together."
                    ),
                )
            )

        pairwise_mean = sum(pairwise_scores.values()) / max(1, len(pairwise_scores))
        member_ids = [cell.lens_id for cell in cells]
        member_scores = {
            lens_id: float(getattr(score_by_lens[lens_id], "composite_score", 0.0))
            for lens_id in member_ids
        }
        member_distances = {
            lens_id: float(getattr(score_by_lens[lens_id], "domain_distance", 0.0))
            for lens_id in member_ids
        }
        member_relevance = {
            lens_id: float(getattr(score_by_lens[lens_id], "structural_relevance", 0.0))
            for lens_id in member_ids
        }
        base_score = sum(member_scores.values()) / max(1, len(member_scores))
        novelty_pressure = sum(cell.novelty_pressure for cell in cells) / len(cells)
        fatigue_penalty = self._exclusion_ledger.penalty_for_bundle(cells)
        cohesion_score = _clamp01(
            0.30 * base_score
            + 0.20 * coverage_score
            + 0.15 * pairwise_mean
            + 0.15 * conditional_score
            + 0.10 * higher_order_score
            + 0.10 * novelty_pressure
            - fatigue_penalty
        )

        bundle_id = _stable_hash(
            {
                "cells": [cell.cell_id for cell in cells],
                "reference_signature": cells[0].reference_signature if cells else "",
                "research_signature": cells[0].research_signature if cells else "",
                "branch_signature": cells[0].branch_signature if cells else "",
                "version": version,
                "lineage_version": lineage_version,
            }
        )
        derived_card = _compose_bundle_card(bundle_id, cells)
        translation_order = self._translation_order(
            cells,
            member_scores,
            conditional_requirements,
            critical_lens_ids,
        )
        fold_state = build_runtime_fold_state(
            bundle_id,
            cells,
            structure,
            pairwise_compatibility=pairwise_scores,
            conditional_support=conditional_requirements,
            critical_lens_ids=critical_lens_ids,
            higher_order_support=higher_order_score,
            coverage_score=coverage_score,
            cohesion_score=cohesion_score,
            fallback_score=fallback_score,
        )
        proof_hash = _stable_hash(
            {
                "bundle_id": bundle_id,
                "fold_state": fold_state.to_dict(),
                "compatibility_evidence": [item.to_dict() for item in evidence],
                "member_scores": member_scores,
                "member_distances": member_distances,
                "member_relevance": member_relevance,
                "conditional_requirements": conditional_requirements,
            }
        )
        return RuntimeBundleProof(
            bundle_id=bundle_id,
            lens_ids=tuple(member_ids),
            translation_order=translation_order,
            cells=cells,
            fold_state=fold_state,
            compatibility_evidence=tuple(evidence),
            conditional_requirements=conditional_requirements,
            critical_lens_ids=critical_lens_ids,
            member_scores=member_scores,
            member_distances=member_distances,
            member_relevance=member_relevance,
            proof_hash=proof_hash,
            proof_confidence=cohesion_score,
            pairwise_score=pairwise_mean,
            conditional_score=conditional_score,
            higher_order_score=higher_order_score,
            fallback_score=fallback_score,
            reference_signature=cells[0].reference_signature if cells else "",
            research_signature=cells[0].research_signature if cells else "",
            branch_signature=cells[0].branch_signature if cells else "",
            derived_card=derived_card,
            version=version,
            lineage_version=lineage_version,
            invalidated_lens_ids=invalidated_lens_ids,
            stale=stale,
            recomposition_count=recomposition_count,
            invalidation_reasons=invalidation_reasons,
        )

    @staticmethod
    def _pairwise_score(
        left: RuntimeCohesionCell,
        right: RuntimeCohesionCell,
        problem_maps: set[str],
        constraints: list[str],
    ) -> float:
        left_shapes = set(left.transfer_shape)
        right_shapes = set(right.transfer_shape)
        coverage = (
            len((left_shapes | right_shapes) & problem_maps) / len(problem_maps)
            if problem_maps
            else 0.5
        )
        mechanism_diversity = 1.0 - _jaccard(
            set(left.mechanism_signature), set(right.mechanism_signature)
        )
        family_separation = 1.0 if left.domain_family != right.domain_family else 0.55
        baseline_overlap = _jaccard(set(left.disallowed_baselines), set(right.disallowed_baselines))
        constraint_support = 0.5 * left.constraint_support(
            constraints
        ) + 0.5 * right.constraint_support(constraints)
        return _clamp01(
            0.35 * coverage
            + 0.30 * mechanism_diversity
            + 0.20 * family_separation
            + 0.15 * constraint_support
            - 0.25 * baseline_overlap
        )

    @staticmethod
    def _coverage_score(cells: tuple[RuntimeCohesionCell, ...], problem_maps: set[str]) -> float:
        if not problem_maps:
            return 0.5
        union = set().union(*(set(cell.transfer_shape) for cell in cells))
        return len(union & problem_maps) / len(problem_maps)

    @staticmethod
    def _conditional_requirements(
        cells: tuple[RuntimeCohesionCell, ...],
        problem_maps: set[str],
    ) -> dict[str, tuple[str, ...]]:
        if not problem_maps:
            return {cell.lens_id: () for cell in cells}
        union = {cell.lens_id: set(cell.transfer_shape) for cell in cells}
        requirements: dict[str, tuple[str, ...]] = {}
        for cell in cells:
            missing = problem_maps - union[cell.lens_id]
            supplied = missing & set().union(
                *(shapes for lens_id, shapes in union.items() if lens_id != cell.lens_id)
            )
            requirements[cell.lens_id] = tuple(sorted(supplied))
        return requirements

    @staticmethod
    def _conditional_score(
        cells: tuple[RuntimeCohesionCell, ...],
        conditional_requirements: dict[str, tuple[str, ...]],
        problem_maps: set[str],
    ) -> float:
        if not cells:
            return 0.0
        if not problem_maps:
            return 0.5
        scores: list[float] = []
        for cell in cells:
            missing = problem_maps - set(cell.transfer_shape)
            if not missing:
                scores.append(1.0)
                continue
            supported = set(conditional_requirements.get(cell.lens_id, ()))
            scores.append(len(supported) / len(missing))
        return sum(scores) / len(scores)

    @staticmethod
    def _higher_order_score(
        cells: tuple[RuntimeCohesionCell, ...],
        problem_maps: set[str],
        constraints: list[str],
    ) -> tuple[float, tuple[str, ...]]:
        if len(cells) < 2:
            return 0.0, ()

        critical: list[str] = []
        full_coverage = BundleComposer._coverage_score(cells, problem_maps)
        for cell in cells:
            remaining = tuple(item for item in cells if item.lens_id != cell.lens_id)
            remaining_coverage = BundleComposer._coverage_score(remaining, problem_maps)
            remaining_constraint = (
                sum(item.constraint_support(constraints) for item in remaining) / len(remaining)
                if remaining
                else 0.0
            )
            full_constraint = sum(item.constraint_support(constraints) for item in cells) / len(
                cells
            )
            if (
                remaining_coverage + 0.10 < full_coverage
                or remaining_constraint + 0.12 < full_constraint
            ):
                critical.append(cell.lens_id)

        triad_bonus = 0.0
        if len(cells) >= 3 and problem_maps:
            pair_coverages = []
            for subset in itertools.combinations(cells, len(cells) - 1):
                pair_coverages.append(BundleComposer._coverage_score(tuple(subset), problem_maps))
            triad_bonus = max(0.0, full_coverage - max(pair_coverages, default=0.0))

        score = _clamp01(0.70 * (len(critical) / len(cells)) + 0.30 * triad_bonus)
        return score, tuple(sorted(critical))

    @staticmethod
    def _translation_order(
        cells: tuple[RuntimeCohesionCell, ...],
        member_scores: dict[str, float],
        conditional_requirements: dict[str, tuple[str, ...]],
        critical_lens_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        critical = set(critical_lens_ids)
        ordered = sorted(
            cells,
            key=lambda cell: (
                float(cell.lens_id in critical),
                -len(conditional_requirements.get(cell.lens_id, ())),
                member_scores.get(cell.lens_id, 0.0),
                cell.novelty_pressure,
            ),
            reverse=True,
        )
        return tuple(cell.lens_id for cell in ordered)


def _compose_bundle_card(bundle_id: str, cells: tuple[RuntimeCohesionCell, ...]) -> LensCard:
    mechanism = _unique(token for cell in cells for token in cell.mechanism_signature)
    transfer_shape = _unique(token for cell in cells for token in cell.transfer_shape)
    constraints = _unique(token for cell in cells for token in cell.constraint_tokens)
    disallowed = _unique(token for cell in cells for token in cell.disallowed_baselines)
    evidence_atoms = _unique(token for cell in cells for token in cell.evidence_atoms)
    novelty_axes = _unique(token for cell in cells for token in cell.novelty_axes)
    confidence = [
        round(0.55 + 0.35 * cell.novelty_pressure - 0.20 * cell.fatigue_penalty, 4)
        for cell in cells
    ]
    return LensCard(
        lens_id=f"bundle::{bundle_id}",
        domain_name=f"bundle::{bundle_id}",
        domain_family="composite",
        mechanism_signature=list(mechanism),
        transfer_shape=list(transfer_shape),
        constraints=list(constraints),
        disallowed_baselines=list(disallowed),
        evidence_atoms=list(evidence_atoms),
        novelty_axes=list(novelty_axes),
        confidence=confidence,
        provenance={},
        fingerprint64=int(hashlib.sha256(bundle_id.encode("utf-8")).hexdigest()[:16], 16),
        version=max((cell.card_version for cell in cells), default=1) + 1,
    )


def _unique(items: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(str(item))
    return tuple(out)


@dataclass(frozen=True)
class _SyntheticLensScore:
    lens_id: str
    composite_score: float
    domain_distance: float
    structural_relevance: float
    domain_family: str


__all__ = [
    "BundleCandidate",
    "BundleComposer",
    "BundleProof",
    "BundleRecomposition",
    "BundleSelectionResult",
    "BundleValidationResult",
    "CompatibilityEvidence",
    "FoldState",
    "RuntimeBundleProof",
    "build_bundle_candidates",
    "build_fold_state",
]
