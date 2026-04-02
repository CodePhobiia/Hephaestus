"""Policy knobs for the BranchGenome upgrade wave."""

from __future__ import annotations

from dataclasses import dataclass

from hephaestus.branchgenome.models import BranchMetrics, BranchStateSummary

_VALID_MODES = {"STANDARD", "AGGRESSIVE", "MAXIMUM"}
_VARIANT_ORDER = (
    "mechanism-pure",
    "target-feasible",
    "novelty-max",
    "constraint-tight",
)


@dataclass(frozen=True)
class BranchStrategy:
    """Bounded policy for seeding, assaying, promoting, pruning, and recovery."""

    mode: str
    max_seeded_branches: int
    max_promoted_branches: int
    max_recovery_branches: int
    max_recovery_operators_per_branch: int
    assay_perturbations_per_branch: int
    extra_token_budget_ratio: float
    per_branch_token_cap: int
    baseline_equivalent_overlap: float = 0.78
    duplicate_similarity_threshold: float = 0.82
    max_failed_perturbations: int = 2
    min_survival_score: float = -0.05
    min_quality_diversity_score: float = 0.46
    max_baseline_attractor: float = 0.74
    max_branch_fatigue: float = 0.82
    family_pressure_window: int = 4
    recovery_activation_threshold: float = 0.34
    recovery_collapse_threshold: float = 0.48
    min_option_preservation: float = 0.26
    max_crossover_branches: int = 2
    crossover_similarity_floor: float = 0.18
    crossover_similarity_ceiling: float = 0.62
    novelty_weight: float = 0.28
    spread_weight: float = 0.22
    verification_weight: float = 0.16
    option_preservation_weight: float = 0.22
    collapse_weight: float = 0.14
    rejection_weight: float = 0.12
    comfort_weight: float = 0.12
    genericity_weight: float = 0.10
    mechanism_purity_weight: float = 0.12
    baseline_attractor_weight: float = 0.12
    transfer_slack_weight: float = 0.08
    branch_fatigue_weight: float = 0.10
    specialization_weight: float = 0.05
    repetition_weight: float = 0.08
    diversity_credit_weight: float = 0.10
    load_bearing_creativity_weight: float = 0.14
    quality_diversity_weight: float = 0.18
    promotion_option_bonus: float = 0.30
    promotion_comfort_penalty: float = 0.18
    promotion_genericity_penalty: float = 0.12
    promotion_quality_diversity_bonus: float = 0.20

    def branch_variants(self) -> tuple[str, ...]:
        """Return the variant families allowed for this mode."""
        if self.mode == "STANDARD":
            return _VARIANT_ORDER[:2]
        if self.mode == "AGGRESSIVE":
            return _VARIANT_ORDER[:3]
        return _VARIANT_ORDER


def normalize_mode(mode: str) -> str:
    """Return a supported BranchGenome mode string."""
    normalized = (mode or "STANDARD").upper()
    if normalized not in _VALID_MODES:
        return "STANDARD"
    return normalized


def strategy_for_mode(
    mode: str,
    *,
    max_tokens_translate: int = 16000,
) -> BranchStrategy:
    """Construct a strategy with fixed hard caps."""
    normalized = normalize_mode(mode)
    if normalized == "AGGRESSIVE":
        return BranchStrategy(
            mode=normalized,
            max_seeded_branches=9,
            max_promoted_branches=4,
            max_recovery_branches=4,
            max_recovery_operators_per_branch=2,
            assay_perturbations_per_branch=4,
            extra_token_budget_ratio=0.40,
            per_branch_token_cap=max(900, int(max_tokens_translate * 0.45)),
            max_crossover_branches=2,
        )
    if normalized == "MAXIMUM":
        return BranchStrategy(
            mode=normalized,
            max_seeded_branches=12,
            max_promoted_branches=5,
            max_recovery_branches=6,
            max_recovery_operators_per_branch=2,
            assay_perturbations_per_branch=4,
            extra_token_budget_ratio=0.70,
            per_branch_token_cap=max(1100, int(max_tokens_translate * 0.55)),
            max_crossover_branches=3,
        )
    return BranchStrategy(
        mode=normalized,
        max_seeded_branches=6,
        max_promoted_branches=3,
        max_recovery_branches=2,
        max_recovery_operators_per_branch=1,
        assay_perturbations_per_branch=3,
        extra_token_budget_ratio=0.20,
        per_branch_token_cap=max(700, int(max_tokens_translate * 0.35)),
        max_crossover_branches=1,
    )


def compute_survival_score(
    metrics: BranchMetrics,
    state_summary: BranchStateSummary,
    strategy: BranchStrategy,
) -> float:
    """Compute the bounded heuristic survival score for a branch."""
    return _clamp_score(
        strategy.novelty_weight * metrics.novelty_hint
        + strategy.spread_weight * metrics.spread_score
        + strategy.verification_weight * metrics.verification_hint
        + strategy.option_preservation_weight * metrics.future_option_preservation
        + strategy.mechanism_purity_weight * state_summary.mechanism_purity
        + strategy.specialization_weight * metrics.specialization_pressure
        + strategy.diversity_credit_weight * metrics.diversity_credit
        + strategy.load_bearing_creativity_weight * metrics.load_bearing_creativity
        + strategy.quality_diversity_weight * metrics.quality_diversity_score
        - strategy.collapse_weight * metrics.collapse_risk
        - strategy.rejection_weight * metrics.rejection_overlap
        - strategy.comfort_weight * metrics.comfort_penalty
        - strategy.genericity_weight * metrics.genericity_penalty
        - strategy.baseline_attractor_weight * state_summary.baseline_attractor
        - strategy.transfer_slack_weight * state_summary.transfer_slack
        - strategy.branch_fatigue_weight * state_summary.branch_fatigue
        - strategy.repetition_weight * metrics.repetition_pressure
    )


def compute_promotion_score(
    metrics: BranchMetrics,
    state_summary: BranchStateSummary,
    strategy: BranchStrategy,
) -> float:
    """Bias promotion toward branches that preserve future non-obvious options."""
    return _clamp_score(
        compute_survival_score(metrics, state_summary, strategy)
        + strategy.promotion_option_bonus * metrics.future_option_preservation
        + strategy.promotion_quality_diversity_bonus * metrics.quality_diversity_score
        - strategy.promotion_comfort_penalty * metrics.comfort_penalty
        - strategy.promotion_genericity_penalty * metrics.genericity_penalty
    )


def _clamp_score(value: float) -> float:
    return max(-1.0, min(1.0, value))
