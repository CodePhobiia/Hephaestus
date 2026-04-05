"""In-memory branch arena for BranchGenome."""

from __future__ import annotations

import copy
import logging
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from hephaestus.branchgenome.assay import branch_similarity
from hephaestus.branchgenome.ledger import fingerprint_tokens
from hephaestus.branchgenome.models import (
    BranchGenome,
    BranchMetrics,
    BranchStateSummary,
    BranchStatus,
    Commitment,
    CommitmentKind,
    OperatorFamily,
    RecoveryOperator,
    RecoveryOperatorKind,
)
from hephaestus.branchgenome.strategy import BranchStrategy

logger = logging.getLogger(__name__)


@dataclass
class BranchArena:
    """In-memory collection of branch states and their lifecycle decisions."""

    branches: dict[str, BranchGenome] = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)
    promoted_ids: list[str] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)
    recovered_ids: list[str] = field(default_factory=list)
    crossover_ids: list[str] = field(default_factory=list)
    positive_archive: dict[str, str] = field(default_factory=dict)
    island_elites: dict[str, str] = field(default_factory=dict)

    def add_branch(self, branch: BranchGenome) -> None:
        self.branches[branch.branch_id] = branch
        if branch.parent_id is not None:
            self.children.setdefault(branch.parent_id, []).append(branch.branch_id)
        self.children.setdefault(branch.branch_id, [])

    def active_branches(self) -> list[BranchGenome]:
        return sorted(
            (branch for branch in self.branches.values() if branch.status == BranchStatus.ACTIVE),
            key=lambda branch: branch.branch_id,
        )

    def promote_top_k(self, k: int) -> list[BranchGenome]:
        ranked = sorted(self.active_branches(), key=_promotion_sort_key, reverse=True)
        promoted: list[BranchGenome] = []
        selected_ids: set[str] = set()

        for branch in ranked:
            if len(promoted) >= k:
                break
            cell = branch.archive_cell or branch.metrics.archive_cell
            if not cell:
                continue
            if any(
                (other.archive_cell or other.metrics.archive_cell) == cell for other in promoted
            ):
                continue
            promoted.append(branch)
            selected_ids.add(branch.branch_id)

        for branch in ranked:
            if len(promoted) >= k:
                break
            island = branch.island_key or branch.metrics.island_key
            if not island or branch.branch_id in selected_ids:
                continue
            if any((other.island_key or other.metrics.island_key) == island for other in promoted):
                continue
            promoted.append(branch)
            selected_ids.add(branch.branch_id)

        for branch in ranked:
            if len(promoted) >= k:
                break
            if branch.branch_id in selected_ids:
                continue
            promoted.append(branch)
            selected_ids.add(branch.branch_id)

        for branch in promoted:
            branch.status = BranchStatus.PROMOTED
            self.promoted_ids.append(branch.branch_id)
            self._register_positive_archive(branch)
        return promoted

    def prune_over_budget(self, strategy: BranchStrategy) -> list[BranchGenome]:
        pruned: list[BranchGenome] = []
        sibling_groups: dict[int, list[BranchGenome]] = {}
        for branch in self.active_branches():
            sibling_groups.setdefault(branch.source_candidate_index, []).append(branch)

        strongest_by_candidate = {
            index: max(branches, key=_promotion_sort_key)
            for index, branches in sibling_groups.items()
        }

        for branch in self.active_branches():
            failed_checks = branch.metrics.perturbations_run - branch.metrics.perturbations_passed
            stronger_sibling = strongest_by_candidate.get(branch.source_candidate_index)
            duplicate_of_stronger = (
                stronger_sibling is not None
                and stronger_sibling.branch_id != branch.branch_id
                and stronger_sibling.metrics.score_promotion >= branch.metrics.score_promotion
                and branch_similarity(branch, stronger_sibling)
                >= strategy.duplicate_similarity_threshold
                and (branch.archive_cell or branch.metrics.archive_cell)
                == (stronger_sibling.archive_cell or stronger_sibling.metrics.archive_cell)
            )
            too_comfortable = (
                branch.metrics.comfort_penalty >= strategy.recovery_activation_threshold
                and branch.metrics.future_option_preservation < strategy.min_option_preservation
            )
            diversity_reserve = (
                branch.metrics.quality_diversity_score >= strategy.min_quality_diversity_score
                and bool(branch.archive_cell or branch.metrics.archive_cell)
                and (branch.archive_cell or branch.metrics.archive_cell)
                not in self.positive_archive
            )
            hard_prune = any(
                (
                    branch.metrics.rejection_overlap >= strategy.baseline_equivalent_overlap,
                    branch.state_summary.baseline_attractor >= strategy.max_baseline_attractor,
                    branch.metrics.token_cost_estimate > strategy.per_branch_token_cap,
                    failed_checks > strategy.max_failed_perturbations,
                    branch.state_summary.branch_fatigue >= strategy.max_branch_fatigue,
                    branch.metrics.score_survival < strategy.min_survival_score,
                )
            )
            soft_prune = too_comfortable or duplicate_of_stronger
            should_prune = hard_prune or (soft_prune and not diversity_reserve)
            if should_prune:
                branch.status = BranchStatus.PRUNED
                if branch.branch_id not in self.pruned_ids:
                    self.pruned_ids.append(branch.branch_id)
                pruned.append(branch)
        return pruned

    def observability_snapshot(self) -> dict[str, Any]:
        all_branches = list(self.branches.values())
        if not all_branches:
            return {
                "branches_seeded": 0,
                "branches_promoted": 0,
                "branches_pruned": 0,
                "branches_recovered": 0,
                "avg_spread_score": 0.0,
                "avg_rejection_overlap": 0.0,
                "avg_collapse_risk": 0.0,
                "avg_future_option_preservation": 0.0,
                "avg_genericity_penalty": 0.0,
                "avg_comfort_penalty": 0.0,
                "avg_baseline_attractor": 0.0,
                "avg_branch_fatigue": 0.0,
                "tokens_spent_branching": 0,
                "tokens_saved_by_pruning": 0,
                "family_frequency": _empty_family_frequency(),
                "positive_archive_size": 0,
                "archive_cell_count": 0,
                "island_count": 0,
                "archive_cells": {},
                "island_elites": {},
                "avg_quality_diversity_score": 0.0,
                "avg_load_bearing_creativity": 0.0,
                "avg_diversity_credit": 0.0,
                "retrieval_expansion_ready": 0,
                "crossover_branches": 0,
                "repeated_family_streaks": {},
                "promoted_family_patterns": {},
                "promoted_branch_outcomes": {},
            }

        return {
            "branches_seeded": len(all_branches),
            "branches_promoted": len(self.promoted_ids),
            "branches_pruned": len(self.pruned_ids),
            "branches_recovered": len(self.recovered_ids),
            "avg_spread_score": sum(branch.metrics.spread_score for branch in all_branches)
            / len(all_branches),
            "avg_rejection_overlap": sum(
                branch.metrics.rejection_overlap for branch in all_branches
            )
            / len(all_branches),
            "avg_collapse_risk": sum(branch.metrics.collapse_risk for branch in all_branches)
            / len(all_branches),
            "avg_future_option_preservation": sum(
                branch.metrics.future_option_preservation for branch in all_branches
            )
            / len(all_branches),
            "avg_genericity_penalty": sum(
                branch.metrics.genericity_penalty for branch in all_branches
            )
            / len(all_branches),
            "avg_comfort_penalty": sum(branch.metrics.comfort_penalty for branch in all_branches)
            / len(all_branches),
            "avg_baseline_attractor": sum(
                branch.state_summary.baseline_attractor for branch in all_branches
            )
            / len(all_branches),
            "avg_branch_fatigue": sum(
                branch.state_summary.branch_fatigue for branch in all_branches
            )
            / len(all_branches),
            "tokens_spent_branching": sum(
                branch.metrics.token_cost_estimate for branch in all_branches
            ),
            "tokens_saved_by_pruning": sum(
                self.branches[branch_id].metrics.token_cost_estimate
                for branch_id in self.pruned_ids
            ),
            "family_frequency": _family_frequency(all_branches),
            "positive_archive_size": len(self.positive_archive),
            "archive_cell_count": len(
                {
                    branch.archive_cell or branch.metrics.archive_cell
                    for branch in all_branches
                    if branch.archive_cell or branch.metrics.archive_cell
                }
            ),
            "island_count": len(
                {
                    branch.island_key or branch.metrics.island_key
                    for branch in all_branches
                    if branch.island_key or branch.metrics.island_key
                }
            ),
            "archive_cells": _archive_cell_distribution(all_branches),
            "island_elites": dict(sorted(self.island_elites.items())),
            "avg_quality_diversity_score": sum(
                branch.metrics.quality_diversity_score for branch in all_branches
            )
            / len(all_branches),
            "avg_load_bearing_creativity": sum(
                branch.metrics.load_bearing_creativity for branch in all_branches
            )
            / len(all_branches),
            "avg_diversity_credit": sum(branch.metrics.diversity_credit for branch in all_branches)
            / len(all_branches),
            "retrieval_expansion_ready": sum(
                1 for branch in all_branches if branch.metrics.retrieval_expansion_readiness >= 0.5
            ),
            "crossover_branches": len(self.crossover_ids),
            "repeated_family_streaks": {
                branch.branch_id: branch.metrics.repeated_family_streak for branch in all_branches
            },
            "promoted_family_patterns": _promoted_family_patterns(
                self.branches[branch_id]
                for branch_id in self.promoted_ids
                if branch_id in self.branches
            ),
            "promoted_branch_outcomes": {},
        }

    def spawn_recovery_branches(
        self,
        strategy: BranchStrategy,
        *,
        structure: Any,
        scored_candidates: list[Any],
    ) -> list[BranchGenome]:
        """Create a single bounded recovery wave for branches drifting toward obviousness."""
        created: list[BranchGenome] = []
        if strategy.max_recovery_branches <= 0:
            return created

        ranked = sorted(
            (
                branch
                for branch in self.active_branches()
                if branch.stage_cursor == "pre_translation"
                and branch.metrics.score_survival >= strategy.min_survival_score - 0.12
                and branch.metrics.future_option_preservation >= strategy.min_option_preservation
                and (
                    branch.metrics.comfort_penalty >= strategy.recovery_activation_threshold
                    or branch.metrics.genericity_penalty >= strategy.recovery_activation_threshold
                    or branch.metrics.collapse_risk >= strategy.recovery_collapse_threshold
                )
            ),
            key=lambda branch: (
                branch.metrics.comfort_penalty
                + branch.metrics.genericity_penalty
                + branch.metrics.collapse_risk,
                branch.metrics.future_option_preservation,
                branch.metrics.score_survival,
            ),
            reverse=True,
        )

        for branch in ranked:
            candidate = scored_candidates[branch.source_candidate_index]
            operators = _select_recovery_operators(branch, strategy)
            for operator in operators:
                if len(created) >= strategy.max_recovery_branches:
                    return created
                branch_id = f"{branch.branch_id}:{operator.kind.value}"
                if branch_id in self.branches:
                    continue
                recovery_branch = _branch_with_recovery_operator(
                    parent=branch,
                    branch_id=branch_id,
                    operator=operator,
                    candidate=candidate,
                    structure=structure,
                )
                self.add_branch(recovery_branch)
                self.recovered_ids.append(recovery_branch.branch_id)
                created.append(recovery_branch)
        return created

    def spawn_crossover_branches(
        self,
        strategy: BranchStrategy,
        *,
        structure: Any,
        scored_candidates: list[Any],
    ) -> list[BranchGenome]:
        """Create bounded crossover branches from viable but distinct parents."""
        created: list[BranchGenome] = []
        if strategy.max_crossover_branches <= 0:
            return created

        candidates = [
            branch
            for branch in self.active_branches()
            if branch.metrics.quality_diversity_score >= strategy.min_quality_diversity_score
            and branch.metrics.future_option_preservation >= strategy.min_option_preservation
        ]
        candidates.sort(key=_promotion_sort_key, reverse=True)
        for idx, left in enumerate(candidates):
            for right in candidates[idx + 1 :]:
                if len(created) >= strategy.max_crossover_branches:
                    return created
                similarity = branch_similarity(left, right)
                if not (
                    strategy.crossover_similarity_floor
                    <= similarity
                    <= strategy.crossover_similarity_ceiling
                ):
                    continue
                if left.source_candidate_index == right.source_candidate_index:
                    continue
                if (left.island_key or left.metrics.island_key) == (
                    right.island_key or right.metrics.island_key
                ):
                    continue
                branch_id = f"{left.branch_id}+{right.branch_id}:crossover"
                if branch_id in self.branches:
                    continue
                crossover_branch = _crossover_branch(
                    branch_id=branch_id,
                    left=left,
                    right=right,
                    left_candidate=scored_candidates[left.source_candidate_index],
                    right_candidate=scored_candidates[right.source_candidate_index],
                    structure=structure,
                )
                self.add_branch(crossover_branch)
                self.crossover_ids.append(crossover_branch.branch_id)
                created.append(crossover_branch)
        return created

    def _register_positive_archive(self, branch: BranchGenome) -> None:
        cell = branch.archive_cell or branch.metrics.archive_cell
        island = branch.island_key or branch.metrics.island_key
        if cell:
            incumbent_id = self.positive_archive.get(cell)
            incumbent = self.branches.get(incumbent_id) if incumbent_id is not None else None
            if (
                incumbent is None
                or branch.metrics.quality_diversity_score
                >= incumbent.metrics.quality_diversity_score
            ):
                self.positive_archive[cell] = branch.branch_id
        if island:
            incumbent_id = self.island_elites.get(island)
            incumbent = self.branches.get(incumbent_id) if incumbent_id is not None else None
            if (
                incumbent is None
                or branch.metrics.quality_diversity_score
                >= incumbent.metrics.quality_diversity_score
            ):
                self.island_elites[island] = branch.branch_id


def seed_branches_from_translation_inputs(
    scored_candidates: list[Any],
    structure: Any,
    strategy: BranchStrategy,
    *,
    banned_patterns: tuple[str, ...] = (),
) -> BranchArena:
    arena = BranchArena()
    variants = strategy.branch_variants()
    branch_budget = strategy.max_seeded_branches

    for candidate_index, candidate in enumerate(scored_candidates):
        if len(arena.branches) >= branch_budget:
            break
        for variant in variants:
            if len(arena.branches) >= branch_budget:
                break
            branch_id = f"bg-{candidate_index}-{variant}"
            branch = BranchGenome(
                branch_id=branch_id,
                parent_id=None,
                source_candidate_index=candidate_index,
                stage_cursor="pre_translation",
                commitments=_commitments_for_variant(
                    candidate=candidate, structure=structure, variant=variant
                ),
                open_questions=_open_questions_for_variant(
                    structure=structure,
                    candidate=candidate,
                    variant=variant,
                ),
                recovery_operators=(),
                rejected_patterns=tuple(pattern for pattern in banned_patterns[:4] if pattern),
                operator_family_history=_operator_families_for_variant(variant),
                metrics=BranchMetrics(),
                island_key=_seed_island_key(candidate, variant),
            )
            arena.add_branch(branch)

    return arena


def branch_candidate_for_translation(branch: BranchGenome, candidate: Any) -> Any:
    try:
        clone = replace(candidate)
    except Exception as exc:
        logger.warning("dataclass replace() failed, falling back to copy: %s", exc)
        clone = copy.copy(candidate)
    clone.branch_genome = branch
    clone.branch_rank_score = branch.metrics.score_promotion or branch.metrics.score_survival
    clone.branch_runtime_hooks = branch.runtime_hooks()
    return clone


def _promotion_sort_key(branch: BranchGenome) -> tuple[float, float, float, float, float, float]:
    return (
        branch.metrics.score_promotion or branch.metrics.score_survival,
        branch.metrics.quality_diversity_score,
        branch.metrics.future_option_preservation,
        branch.state_summary.mechanism_purity,
        1.0 - branch.state_summary.baseline_attractor,
        1.0 - branch.state_summary.branch_fatigue,
    )


def _empty_family_frequency() -> dict[str, int]:
    return {family.value: 0 for family in OperatorFamily}


def _family_frequency(branches: list[BranchGenome]) -> dict[str, int]:
    counts = Counter(
        family.value for branch in branches for family in branch.operator_family_history
    )
    return {family.value: counts.get(family.value, 0) for family in OperatorFamily}


def _archive_cell_distribution(branches: list[BranchGenome]) -> dict[str, int]:
    counts = Counter(
        branch.archive_cell or branch.metrics.archive_cell
        for branch in branches
        if branch.archive_cell or branch.metrics.archive_cell
    )
    return dict(sorted(counts.items()))


def _promoted_family_patterns(branches: Any) -> dict[str, int]:
    counts = Counter(branch.operator_family_pattern() for branch in branches)
    return dict(sorted(counts.items()))


def _operator_families_for_variant(variant: str) -> tuple[OperatorFamily, ...]:
    if variant == "mechanism-pure":
        return (
            OperatorFamily.MECHANISM,
            OperatorFamily.MECHANISM,
            OperatorFamily.ANTI_BASELINE,
            OperatorFamily.CRITIQUE,
        )
    if variant == "target-feasible":
        return (
            OperatorFamily.BIND,
            OperatorFamily.CONCRETIZE,
            OperatorFamily.CONSTRAINT,
        )
    if variant == "novelty-max":
        return (
            OperatorFamily.ANTI_BASELINE,
            OperatorFamily.ABLATION,
            OperatorFamily.ANTI_BASELINE,
            OperatorFamily.CRITIQUE,
        )
    return (
        OperatorFamily.CONSTRAINT,
        OperatorFamily.BIND,
        OperatorFamily.CONCRETIZE,
        OperatorFamily.CRITIQUE,
    )


def _seed_island_key(candidate: Any, variant: str) -> str:
    lens = getattr(candidate, "lens_used", None)
    family = str(getattr(lens, "domain_family", "") or getattr(lens, "domain", "") or "unknown")
    return f"{family.strip().replace(' ', '_').lower()}:{variant}"


def _commitments_for_variant(
    *, candidate: Any, structure: Any, variant: str
) -> tuple[Commitment, ...]:
    constraints = list(getattr(structure, "constraints", []))
    top_constraint = constraints[0] if constraints else "respect hard operating constraints"
    source_domain = str(getattr(candidate, "source_domain", "") or "")
    source_solution = str(getattr(candidate, "source_solution", "") or "")
    mechanism = str(getattr(candidate, "mechanism", "") or "")
    structural_mapping = str(
        getattr(candidate, "candidate", candidate).structural_mapping
        if hasattr(getattr(candidate, "candidate", candidate), "structural_mapping")
        else ""
    )
    strong_mappings = list(getattr(candidate, "strong_mappings", []) or [])
    primary_mapping = strong_mappings[0] if strong_mappings else structural_mapping
    native_domain = str(getattr(structure, "native_domain", "")).replace("_", " ")

    common = [
        Commitment(
            id=f"{variant}:mechanism",
            kind=CommitmentKind.MECHANISM_CLAIM,
            statement=f"Preserve the load-bearing mechanism from {source_domain}: {mechanism or source_solution}.",
            confidence=float(getattr(candidate, "structural_fidelity", 0.5)),
            reversible=True,
            provenance=(variant, "seed"),
        ),
        Commitment(
            id=f"{variant}:mapping",
            kind=CommitmentKind.MAPPING_CLAIM,
            statement=f"Keep the structural bridge explicit: {primary_mapping or structural_mapping or 'map the foreign mechanism onto the target shape directly'}.",
            confidence=float(getattr(candidate, "combined_score", 0.5)),
            reversible=True,
            provenance=(variant, "seed"),
        ),
        Commitment(
            id=f"{variant}:binding",
            kind=CommitmentKind.TARGET_BINDING,
            statement=f"Bind the mechanism to a concrete {native_domain} architecture that matches {getattr(structure, 'mathematical_shape', '')}.",
            confidence=float(getattr(candidate, "domain_distance", 0.5)),
            reversible=True,
            provenance=(variant, "seed"),
        ),
    ]

    if variant == "mechanism-pure":
        extras = [
            Commitment(
                id=f"{variant}:verification",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement="Reject any translation that collapses into a familiar engineering baseline after the source vocabulary is removed.",
                confidence=0.75,
                reversible=True,
                provenance=(variant, "guard"),
            ),
        ]
    elif variant == "target-feasible":
        extras = [
            Commitment(
                id=f"{variant}:resource",
                kind=CommitmentKind.RESOURCE_POLICY,
                statement=f"Prefer the minimal viable implementation that still satisfies: {top_constraint}.",
                confidence=0.80,
                reversible=True,
                provenance=(variant, "guard"),
            ),
        ]
    elif variant == "novelty-max":
        extras = [
            Commitment(
                id=f"{variant}:verification",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement="Favor the target-side commitment that stays maximally distinct from baseline caching, retry, queue, or load-balancing patterns.",
                confidence=0.85,
                reversible=True,
                provenance=(variant, "novelty"),
            ),
        ]
    else:
        extras = [
            Commitment(
                id=f"{variant}:resource",
                kind=CommitmentKind.RESOURCE_POLICY,
                statement=f"Make hard constraints first-class design commitments, starting with: {top_constraint}.",
                confidence=0.82,
                reversible=True,
                provenance=(variant, "constraint"),
            ),
            Commitment(
                id=f"{variant}:verification",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement="Add an explicit failure guard so the architecture fails closed instead of degrading into a decorative analogy.",
                confidence=0.78,
                reversible=True,
                provenance=(variant, "guard"),
            ),
        ]

    return tuple(common + extras)


def _open_questions_for_variant(*, structure: Any, candidate: Any, variant: str) -> tuple[str, ...]:
    first_constraint = next(
        iter(getattr(structure, "constraints", []) or ["the hard constraints"]),
        "the hard constraints",
    )
    if variant == "mechanism-pure":
        return (
            "Which target-side components preserve the foreign mechanism without renaming it into a standard pattern?",
            "What evidence would prove the mechanism still matters after source-domain words are stripped out?",
        )
    if variant == "target-feasible":
        return (
            "What is the smallest deployable architecture that keeps the mechanism load-bearing?",
            f"How does the design satisfy {first_constraint} without adding unnecessary machinery?",
        )
    if variant == "novelty-max":
        return (
            "Which commitment keeps the translation meaningfully far from obvious baselines in the target domain?",
            f"What target-side choice best preserves the distance implied by {getattr(candidate, 'source_domain', 'the source domain')}?",
        )
    return (
        f"Which explicit guardrail keeps {first_constraint} satisfied under stress?",
        "What commitment should become irreversible only at the translation boundary?",
    )


def _select_recovery_operators(
    branch: BranchGenome, strategy: BranchStrategy
) -> tuple[RecoveryOperator, ...]:
    existing = {operator.kind for operator in branch.recovery_operators}
    selected: list[RecoveryOperator] = []

    def add_if_missing(
        kind: RecoveryOperatorKind, trigger: str, intervention: str, preservation_goal: str
    ) -> None:
        if kind in existing or any(operator.kind == kind for operator in selected):
            return
        selected.append(
            RecoveryOperator(
                kind=kind,
                trigger=trigger,
                intervention=intervention,
                preservation_goal=preservation_goal,
            )
        )

    obviousness = max(branch.metrics.comfort_penalty, branch.metrics.genericity_penalty)
    if obviousness >= strategy.recovery_activation_threshold:
        add_if_missing(
            RecoveryOperatorKind.ATTRACTOR_BREAKER,
            "The branch is converging toward an obvious target-domain baseline.",
            "Forbid the closest baseline as the primary organizing primitive and introduce a second-order control state.",
            "Preserve a target-side decision that only exists if the imported mechanism remains load-bearing.",
        )
    if (
        branch.metrics.genericity_penalty >= strategy.recovery_activation_threshold
        or branch.metrics.rejection_overlap >= 0.18
    ):
        add_if_missing(
            RecoveryOperatorKind.SUBTRACTION_PROBE,
            "The branch can survive by metaphor or source-domain naming alone.",
            "Rewrite the architecture in target-domain-only language and prove it still differs from the obvious baseline.",
            "Preserve a measurable difference that remains after the source vocabulary is stripped out.",
        )
    if (
        branch.metrics.collapse_risk >= strategy.recovery_collapse_threshold
        or branch.metrics.spread_score < 0.55
    ):
        add_if_missing(
            RecoveryOperatorKind.ORDER_INVERSION,
            "The branch defaults to the usual construction order and collapses under perturbation.",
            "Design from failure/recovery behavior backward into admission and dispatch rather than the other way around.",
            "Preserve an architecture whose normal path is derived from the recovery logic instead of copied from a standard scheduler.",
        )
    if branch.metrics.verification_hint < 0.60 or branch.metrics.collapse_risk >= 0.42:
        add_if_missing(
            RecoveryOperatorKind.LOAD_BEARING_ABLATION,
            "The branch may still work after removing the supposedly novel mechanism.",
            "Ablate the imported mechanism and reject the branch if it still looks plausible as a generic solution.",
            "Preserve only commitments whose removal would visibly break the target architecture.",
        )

    return tuple(selected[: strategy.max_recovery_operators_per_branch])


def _branch_with_recovery_operator(
    *,
    parent: BranchGenome,
    branch_id: str,
    operator: RecoveryOperator,
    candidate: Any,
    structure: Any,
) -> BranchGenome:
    commitments = list(parent.commitments)
    open_questions = list(parent.open_questions)
    native_domain = str(getattr(structure, "native_domain", "")).replace("_", " ")
    baseline = str(
        getattr(candidate, "target_domain_equivalent", "") or "the obvious baseline pattern"
    )

    if operator.kind == RecoveryOperatorKind.ATTRACTOR_BREAKER:
        commitments.append(
            Commitment(
                id=f"{branch_id}:attractor-breaker",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement=(
                    f"Break the closest {native_domain} attractor ({baseline}) by refusing it as the primary "
                    "organizing primitive and introducing a second-order control state that only exists because "
                    "the imported mechanism remains load-bearing."
                ),
                confidence=0.83,
                reversible=True,
                provenance=(operator.kind.value, "recovery"),
            )
        )
        open_questions.extend(
            [
                f"What target-side state replaces {baseline} as the primary control primitive?",
                "Which control decision exists only because the imported mechanism is still structurally necessary?",
            ]
        )
    elif operator.kind == RecoveryOperatorKind.SUBTRACTION_PROBE:
        commitments.append(
            Commitment(
                id=f"{branch_id}:subtraction-probe",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement=(
                    f"Describe the branch using only {native_domain} language and prove it still differs structurally "
                    f"from {baseline} after the source-domain vocabulary is removed."
                ),
                confidence=0.84,
                reversible=True,
                provenance=(operator.kind.value, "recovery"),
            )
        )
        open_questions.extend(
            [
                "What measurable behavior remains distinctive after all source-domain words are deleted?",
                "Which target-side mechanism still looks strange even when described without analogy language?",
            ]
        )
    elif operator.kind == RecoveryOperatorKind.ORDER_INVERSION:
        commitments.append(
            Commitment(
                id=f"{branch_id}:order-inversion",
                kind=CommitmentKind.RESOURCE_POLICY,
                statement=(
                    "Invert the usual construction order: choose the recovery and failure-handling state transition "
                    "first, then derive admission, routing, and steady-state behavior from that choice."
                ),
                confidence=0.80,
                reversible=True,
                provenance=(operator.kind.value, "recovery"),
            )
        )
        open_questions.extend(
            [
                "If recovery logic is specified first, what downstream control loop becomes non-standard?",
                "What does the architecture look like when normal execution is treated as a consequence of failure policy?",
            ]
        )
    else:
        commitments = _drop_weakest_commitment(commitments)
        commitments.append(
            Commitment(
                id=f"{branch_id}:load-bearing-ablation",
                kind=CommitmentKind.VERIFICATION_ASSERTION,
                statement=(
                    f"Ablate the imported mechanism; if the branch still reads like {baseline}, reject it. "
                    f"Replace any generic placeholder with a concrete {native_domain} component that fails closed "
                    "without the mechanism."
                ),
                confidence=0.86,
                reversible=True,
                provenance=(operator.kind.value, "recovery"),
            )
        )
        open_questions.extend(
            [
                "Which component fails immediately if the imported mechanism is removed?",
                "What generic commitment can be deleted without losing the architecture, and how should it be replaced?",
            ]
        )

    rejected_patterns = tuple(dict.fromkeys((*parent.rejected_patterns, baseline)))
    recovery_family = _recovery_operator_family(operator.kind)
    return BranchGenome(
        branch_id=branch_id,
        parent_id=parent.branch_id,
        source_candidate_index=parent.source_candidate_index,
        stage_cursor="recovery",
        commitments=tuple(commitments),
        open_questions=tuple(open_questions[-4:]),
        recovery_operators=tuple((*parent.recovery_operators, operator)),
        rejected_patterns=rejected_patterns,
        operator_family_history=tuple((*parent.operator_family_history, recovery_family)),
        metrics=BranchMetrics(),
        state_summary=BranchStateSummary(
            mechanism_purity=parent.state_summary.mechanism_purity,
            baseline_attractor=max(0.0, parent.state_summary.baseline_attractor - 0.12),
            transfer_slack=min(1.0, parent.state_summary.transfer_slack + 0.12),
            branch_fatigue=min(1.0, parent.state_summary.branch_fatigue + 0.08),
        ),
    )


def _crossover_branch(
    *,
    branch_id: str,
    left: BranchGenome,
    right: BranchGenome,
    left_candidate: Any,
    right_candidate: Any,
    structure: Any,
) -> BranchGenome:
    native_domain = str(getattr(structure, "native_domain", "")).replace("_", " ")
    left_mechanism = next(
        (
            commitment
            for commitment in left.commitments
            if commitment.kind == CommitmentKind.MECHANISM_CLAIM
        ),
        left.commitments[0],
    )
    right_binding = next(
        (
            commitment
            for commitment in right.commitments
            if commitment.kind == CommitmentKind.TARGET_BINDING
        ),
        right.commitments[-1],
    )
    crossover_mapping = Commitment(
        id=f"{branch_id}:crossover-mapping",
        kind=CommitmentKind.MAPPING_CLAIM,
        statement=(
            f"Fuse {left_candidate.source_domain} retention pressure with {right_candidate.source_domain} "
            f"binding detail so the {native_domain} architecture inherits two independently viable control laws."
        ),
        confidence=min(0.92, max(left_mechanism.confidence, right_binding.confidence)),
        reversible=True,
        provenance=("crossover", left.branch_id, right.branch_id),
    )
    crossover_guard = Commitment(
        id=f"{branch_id}:crossover-guard",
        kind=CommitmentKind.VERIFICATION_ASSERTION,
        statement=(
            "Reject the crossover if either parent can be deleted without materially changing the translated control path."
        ),
        confidence=0.85,
        reversible=True,
        provenance=("crossover", "guard"),
    )
    commitments = (
        left_mechanism,
        crossover_mapping,
        right_binding,
        crossover_guard,
    )
    open_questions = tuple(
        dict.fromkeys(
            (
                *left.open_questions[:2],
                *right.open_questions[:2],
                "Which branch-specific state becomes impossible if either parent mechanism is removed?",
            )
        )
    )[-4:]
    rejected_patterns = tuple(dict.fromkeys((*left.rejected_patterns, *right.rejected_patterns)))
    operator_history = tuple(
        (
            *left.recent_operator_families(2),
            *right.recent_operator_families(2),
            OperatorFamily.CRITIQUE,
        )
    )
    return BranchGenome(
        branch_id=branch_id,
        parent_id=left.branch_id,
        source_candidate_index=left.source_candidate_index,
        stage_cursor="crossover",
        commitments=commitments,
        open_questions=open_questions,
        recovery_operators=tuple(
            dict.fromkeys((*left.recovery_operators, *right.recovery_operators))
        ),
        rejected_patterns=rejected_patterns,
        operator_family_history=operator_history,
        metrics=BranchMetrics(),
        state_summary=BranchStateSummary(
            mechanism_purity=min(
                1.0,
                0.5 * left.state_summary.mechanism_purity
                + 0.5 * right.state_summary.mechanism_purity,
            ),
            baseline_attractor=max(
                0.0,
                min(left.state_summary.baseline_attractor, right.state_summary.baseline_attractor)
                - 0.05,
            ),
            transfer_slack=min(
                1.0,
                0.5 * left.state_summary.transfer_slack
                + 0.5 * right.state_summary.transfer_slack
                + 0.08,
            ),
            branch_fatigue=min(
                1.0,
                0.5 * left.state_summary.branch_fatigue
                + 0.5 * right.state_summary.branch_fatigue
                + 0.06,
            ),
        ),
        island_key=f"cross:{left.island_key or left.metrics.island_key}:{right.island_key or right.metrics.island_key}",
        crossover_parent_ids=(left.branch_id, right.branch_id),
        retrieval_expansion_hints=tuple(
            dict.fromkeys((*left.retrieval_expansion_hints, *right.retrieval_expansion_hints))
        ),
    )


def _recovery_operator_family(kind: RecoveryOperatorKind) -> OperatorFamily:
    if kind == RecoveryOperatorKind.ATTRACTOR_BREAKER:
        return OperatorFamily.ANTI_BASELINE
    if kind == RecoveryOperatorKind.SUBTRACTION_PROBE:
        return OperatorFamily.ABLATION
    if kind == RecoveryOperatorKind.ORDER_INVERSION:
        return OperatorFamily.CONSTRAINT
    return OperatorFamily.ABLATION


def _drop_weakest_commitment(commitments: list[Commitment]) -> list[Commitment]:
    removable = [
        commitment
        for commitment in commitments
        if commitment.kind not in {CommitmentKind.MECHANISM_CLAIM, CommitmentKind.TARGET_BINDING}
    ]
    pool = removable or commitments
    weakest = min(
        pool,
        key=lambda commitment: (
            len([token for token in fingerprint_tokens(commitment.statement) if len(token) > 4]),
            0
            if commitment.kind
            in {CommitmentKind.RESOURCE_POLICY, CommitmentKind.VERIFICATION_ASSERTION}
            else 1,
        ),
    )
    return [commitment for commitment in commitments if commitment.id != weakest.id]
