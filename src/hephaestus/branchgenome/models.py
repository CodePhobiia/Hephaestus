"""Core data structures for the BranchGenome quality-upgrade flow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum

from hephaestus.novelty import NoveltyVector


class CommitmentKind(str, Enum):
    """Kinds of partial structural commitments tracked on a branch."""

    MECHANISM_CLAIM = "mechanism_claim"
    MAPPING_CLAIM = "mapping_claim"
    TARGET_BINDING = "target_binding"
    RESOURCE_POLICY = "resource_policy"
    VERIFICATION_ASSERTION = "verification_assertion"


class OperatorFamily(str, Enum):
    """High-level operator families used to evolve a branch."""

    MECHANISM = "mechanism"
    BIND = "bind"
    CONCRETIZE = "concretize"
    CRITIQUE = "critique"
    ANTI_BASELINE = "anti_baseline"
    ABLATION = "ablation"
    CONSTRAINT = "constraint"


class RecoveryOperatorKind(str, Enum):
    """Named rescue operators used when a branch drifts toward obviousness."""

    ATTRACTOR_BREAKER = "attractor_breaker"
    SUBTRACTION_PROBE = "subtraction_probe"
    ORDER_INVERSION = "order_inversion"
    LOAD_BEARING_ABLATION = "load_bearing_ablation"


class BranchStatus(str, Enum):
    """Lifecycle state for an in-memory branch."""

    ACTIVE = "active"
    PROMOTED = "promoted"
    PRUNED = "pruned"
    TRANSLATED = "translated"
    VERIFIED = "verified"


@dataclass(frozen=True)
class Commitment:
    """Single structural choice that has been accepted for a branch."""

    id: str
    kind: CommitmentKind
    statement: str
    confidence: float
    reversible: bool
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryOperator:
    """Concrete rescue instruction that should survive into translation."""

    kind: RecoveryOperatorKind
    trigger: str
    intervention: str
    preservation_goal: str

    def summary(self) -> str:
        """Return a compact natural-language description for prompts/fingerprints."""
        return (
            f"{self.kind.value}: trigger={self.trigger}; "
            f"intervention={self.intervention}; goal={self.preservation_goal}"
        )


@dataclass
class BranchMetrics:
    """Branch evaluation metrics used for promote/prune decisions."""

    novelty_hint: float = 0.0
    spread_score: float = 0.0
    rejection_overlap: float = 0.0
    positive_overlap: float = 0.0
    collapse_risk: float = 0.0
    verification_hint: float = 0.0
    future_option_preservation: float = 0.0
    genericity_penalty: float = 0.0
    comfort_penalty: float = 0.0
    diversity_credit: float = 0.0
    load_bearing_creativity: float = 0.0
    quality_diversity_score: float = 0.0
    archive_novelty: float = 0.0
    archive_quality: float = 0.0
    archive_cell: str = ""
    island_key: str = ""
    retrieval_expansion_readiness: float = 0.0
    novelty_vector: NoveltyVector = field(default_factory=NoveltyVector)
    score_survival: float = 0.0
    score_promotion: float = 0.0
    token_cost_estimate: int = 0
    runtime_ms_estimate: int = 0
    perturbations_run: int = 0
    perturbations_passed: int = 0
    specialization_pressure: float = 0.0
    repetition_pressure: float = 0.0
    repeated_family_streak: int = 0


@dataclass
class BranchStateSummary:
    """Small, measurable branch-state summary used for ranking and pruning."""

    mechanism_purity: float = 0.0
    baseline_attractor: float = 0.0
    transfer_slack: float = 0.0
    branch_fatigue: float = 0.0


@dataclass
class BranchGenome:
    """Partial invention state used before a candidate is fully translated."""

    branch_id: str
    parent_id: str | None
    source_candidate_index: int
    stage_cursor: str
    commitments: tuple[Commitment, ...]
    open_questions: tuple[str, ...]
    recovery_operators: tuple[RecoveryOperator, ...] = ()
    rejected_patterns: tuple[str, ...] = ()
    operator_family_history: tuple[OperatorFamily, ...] = ()
    metrics: BranchMetrics = field(default_factory=BranchMetrics)
    state_summary: BranchStateSummary = field(default_factory=BranchStateSummary)
    status: BranchStatus = BranchStatus.ACTIVE
    island_key: str = ""
    archive_cell: str = ""
    crossover_parent_ids: tuple[str, ...] = ()
    retrieval_expansion_hints: tuple[str, ...] = ()

    def commitment_text(self) -> str:
        """Return a compact string form of the branch commitments."""
        parts = [commitment.statement for commitment in self.commitments]
        parts.extend(operator.summary() for operator in self.recovery_operators)
        return " ".join(parts)

    def recent_operator_families(self, limit: int | None = None) -> tuple[OperatorFamily, ...]:
        """Return the recent operator-family trace for the branch."""
        if limit is None or limit <= 0:
            return self.operator_family_history
        return self.operator_family_history[-limit:]

    def operator_family_pattern(self, limit: int | None = None) -> str:
        """Render a compact operator-family pattern for logging and observability."""
        families = self.recent_operator_families(limit)
        if not families:
            return "none"
        return " > ".join(family.value for family in families)

    def continuity_signature(self) -> str:
        """Stable signature used to detect branch-state drift across runtime stages."""
        payload = {
            "branch_id": self.branch_id,
            "stage_cursor": self.stage_cursor,
            "status": self.status.value,
            "commitments": [commitment.statement for commitment in self.commitments],
            "open_questions": list(self.open_questions),
            "recovery_operators": [operator.summary() for operator in self.recovery_operators],
            "rejected_patterns": list(self.rejected_patterns),
            "operator_families": [family.value for family in self.operator_family_history],
            "island_key": self.island_key,
            "archive_cell": self.archive_cell,
            "crossover_parent_ids": list(self.crossover_parent_ids),
            "retrieval_expansion_hints": list(self.retrieval_expansion_hints),
            "metrics": {
                "collapse_risk": self.metrics.collapse_risk,
                "future_option_preservation": self.metrics.future_option_preservation,
                "comfort_penalty": self.metrics.comfort_penalty,
                "genericity_penalty": self.metrics.genericity_penalty,
                "quality_diversity_score": self.metrics.quality_diversity_score,
                "load_bearing_creativity": self.metrics.load_bearing_creativity,
                "novelty_vector": self.metrics.novelty_vector.to_dict(),
            },
        }
        normalized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def requires_counterexample_probe(self) -> bool:
        """Whether downstream bundle execution should demand a counterexample probe."""
        return bool(
            self.recovery_operators
            or self.rejected_patterns
            or self.metrics.collapse_risk >= 0.35
            or self.metrics.comfort_penalty >= 0.35
            or self.metrics.genericity_penalty >= 0.35
        )

    def runtime_hooks(self) -> dict[str, object]:
        """Small runtime-facing bundle hooks for orchestration and reporting."""
        return {
            "branch_id": self.branch_id,
            "status": self.status.value,
            "stage_cursor": self.stage_cursor,
            "island_key": self.island_key,
            "archive_cell": self.archive_cell,
            "continuity_signature": self.continuity_signature(),
            "requires_counterexample_probe": self.requires_counterexample_probe(),
            "recovery_operators": [operator.summary() for operator in self.recovery_operators],
            "crossover_parent_ids": list(self.crossover_parent_ids),
            "retrieval_expansion_hints": list(self.retrieval_expansion_hints),
            "quality_diversity_score": self.metrics.quality_diversity_score,
            "load_bearing_creativity": self.metrics.load_bearing_creativity,
            "novelty_vector": self.metrics.novelty_vector.to_dict(),
            "rejected_patterns": list(self.rejected_patterns),
        }
