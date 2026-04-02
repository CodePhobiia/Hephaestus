from __future__ import annotations

from dataclasses import replace

from hephaestus.branchgenome import (
    BranchArena,
    BranchGenome,
    BranchMetrics,
    BranchStateSummary,
    BranchStatus,
    Commitment,
    CommitmentKind,
    OperatorFamily,
    RecoveryOperatorKind,
    branch_candidate_for_translation,
    seed_branches_from_translation_inputs,
    strategy_for_mode,
)
from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="Build a scheduler that degrades gracefully under load.",
        structure="Adaptive resource allocation with overload recovery.",
        constraints=["bounded memory", "graceful degradation"],
        mathematical_shape="online control with bounded resource budgets",
        native_domain="distributed_systems",
        problem_maps_to={"allocation", "control"},
    )


def _make_scored_candidate(index: int = 0) -> ScoredCandidate:
    lens = Lens(
        name=f"Lens {index}",
        domain="biology",
        subdomain="immune",
        axioms=["Distributed memory persists."],
        structural_patterns=[StructuralPattern("allocation", "Allocate under pressure", ["allocation"])],
        injection_prompt="Reason biologically.",
    )
    lens_score = LensScore(
        lens=lens,
        domain_distance=0.82 - 0.03 * index,
        structural_relevance=0.78,
        composite_score=0.74,
        matched_patterns=["allocation"],
    )
    candidate = SearchCandidate(
        source_domain=f"Immune System {index}",
        source_solution="Clonal memory response",
        mechanism="Successful responses get retained and amplified under later stress.",
        structural_mapping="Persistent responders map onto resilient schedulers.",
        lens_used=lens,
        lens_score=lens_score,
        confidence=0.85,
    )
    return ScoredCandidate(
        candidate=candidate,
        structural_fidelity=0.81 - 0.02 * index,
        domain_distance=lens_score.domain_distance,
        combined_score=0.73 - 0.04 * index,
        mechanism_novelty=0.74,
        strong_mappings=["Retained responders become faster future responders."],
        scoring_cost_usd=0.01,
    )


def _make_branch(
    branch_id: str,
    score: float,
    text: str,
    *,
    source_candidate_index: int = 0,
    family_history: tuple[OperatorFamily, ...] = (
        OperatorFamily.MECHANISM,
        OperatorFamily.BIND,
        OperatorFamily.CRITIQUE,
    ),
    state_summary: BranchStateSummary | None = None,
    repeated_family_streak: int = 1,
    spread: float = 0.7,
    verification: float = 0.6,
    novelty: float = 0.6,
    rejection_overlap: float = 0.0,
    collapse: float = 0.2,
    option_preservation: float = 0.55,
    genericity: float = 0.18,
    comfort: float = 0.22,
    promotion: float | None = None,
    island_key: str = "",
    archive_cell: str = "",
) -> BranchGenome:
    state = state_summary or BranchStateSummary(
        mechanism_purity=0.68,
        baseline_attractor=0.18,
        transfer_slack=0.28,
        branch_fatigue=0.22,
    )
    return BranchGenome(
        branch_id=branch_id,
        parent_id=None,
        source_candidate_index=source_candidate_index,
        stage_cursor="pre_translation",
        commitments=(
            Commitment(
                id=f"{branch_id}:mechanism",
                kind=CommitmentKind.MECHANISM_CLAIM,
                statement=text,
                confidence=0.8,
                reversible=True,
            ),
            Commitment(
                id=f"{branch_id}:binding",
                kind=CommitmentKind.TARGET_BINDING,
                statement="Bind the mechanism to a resilient scheduler architecture.",
                confidence=0.7,
                reversible=True,
            ),
        ),
        open_questions=("What is the smallest viable implementation?",),
        operator_family_history=family_history,
        metrics=BranchMetrics(
            spread_score=spread,
            verification_hint=verification,
            novelty_hint=novelty,
            rejection_overlap=rejection_overlap,
            collapse_risk=collapse,
            future_option_preservation=option_preservation,
            genericity_penalty=genericity,
            comfort_penalty=comfort,
            quality_diversity_score=0.5 + 0.25 * option_preservation,
            archive_cell=archive_cell,
            island_key=island_key,
            score_survival=score,
            score_promotion=promotion if promotion is not None else score + 0.15 * option_preservation,
            perturbations_run=4,
            perturbations_passed=4,
            specialization_pressure=0.2,
            repetition_pressure=0.0,
            repeated_family_streak=repeated_family_streak,
        ),
        state_summary=state,
        island_key=island_key,
        archive_cell=archive_cell,
    )


def test_commitment_hash_stability() -> None:
    left = Commitment(
        id="same",
        kind=CommitmentKind.MECHANISM_CLAIM,
        statement="Retain successful response paths.",
        confidence=0.8,
        reversible=True,
        provenance=("seed",),
    )
    right = Commitment(
        id="same",
        kind=CommitmentKind.MECHANISM_CLAIM,
        statement="Retain successful response paths.",
        confidence=0.8,
        reversible=True,
        provenance=("seed",),
    )

    assert left == right
    assert hash(left) == hash(right)


def test_seed_branches_respects_standard_budget() -> None:
    structure = _make_structure()
    scored = [_make_scored_candidate(i) for i in range(4)]
    strategy = strategy_for_mode("STANDARD")

    arena = seed_branches_from_translation_inputs(scored, structure, strategy)

    assert len(arena.branches) == strategy.max_seeded_branches
    assert all(branch.stage_cursor == "pre_translation" for branch in arena.branches.values())
    assert arena.branches["bg-0-mechanism-pure"].operator_family_history[:2] == (
        OperatorFamily.MECHANISM,
        OperatorFamily.MECHANISM,
    )
    assert arena.branches["bg-0-target-feasible"].operator_family_history == (
        OperatorFamily.BIND,
        OperatorFamily.CONCRETIZE,
        OperatorFamily.CONSTRAINT,
    )


def test_prune_over_budget_removes_weaker_duplicate_and_token_overrun() -> None:
    strategy = strategy_for_mode("STANDARD")
    arena = BranchArena()
    strong = _make_branch("strong", 0.72, "Retain successful response paths under later load.")
    weak_dup = _make_branch("weak-dup", 0.40, "Retain successful response paths under later load.")
    costly = _make_branch("costly", 0.55, "Inject expensive extra branching detail.")
    costly.metrics.token_cost_estimate = strategy.per_branch_token_cap + 1

    arena.add_branch(strong)
    arena.add_branch(weak_dup)
    arena.add_branch(costly)

    pruned = arena.prune_over_budget(strategy)

    assert {branch.branch_id for branch in pruned} == {"weak-dup", "costly"}
    assert arena.branches["strong"].status == BranchStatus.ACTIVE
    assert arena.branches["weak-dup"].status == BranchStatus.PRUNED


def test_prune_over_budget_removes_high_fatigue_branch() -> None:
    strategy = strategy_for_mode("STANDARD")
    arena = BranchArena()
    resilient = _make_branch("resilient", 0.70, "Preserve retained response paths under later load.")
    fatigued = _make_branch(
        "fatigued",
        0.41,
        "Keep revisiting the same baseline-adjacent mechanism.",
        family_history=(
            OperatorFamily.MECHANISM,
            OperatorFamily.MECHANISM,
            OperatorFamily.MECHANISM,
            OperatorFamily.CRITIQUE,
        ),
        state_summary=BranchStateSummary(
            mechanism_purity=0.55,
            baseline_attractor=0.40,
            transfer_slack=0.35,
            branch_fatigue=strategy.max_branch_fatigue + 0.05,
        ),
        repeated_family_streak=3,
    )
    fatigued.metrics.repetition_pressure = 0.67

    arena.add_branch(resilient)
    arena.add_branch(fatigued)

    pruned = arena.prune_over_budget(strategy)

    assert [branch.branch_id for branch in pruned] == ["fatigued"]
    assert arena.branches["fatigued"].status == BranchStatus.PRUNED


def test_observability_snapshot_exposes_family_and_state_metrics() -> None:
    arena = BranchArena()
    mechanism_branch = _make_branch(
        "mechanism",
        0.83,
        "Retain successful response paths under repeated overload signatures.",
        family_history=(
            OperatorFamily.MECHANISM,
            OperatorFamily.MECHANISM,
            OperatorFamily.CRITIQUE,
        ),
        state_summary=BranchStateSummary(
            mechanism_purity=0.81,
            baseline_attractor=0.14,
            transfer_slack=0.20,
            branch_fatigue=0.18,
        ),
        repeated_family_streak=2,
    )
    bind_branch = _make_branch(
        "binding",
        0.55,
        "Bind retained response paths into a concrete scheduler architecture.",
        family_history=(
            OperatorFamily.BIND,
            OperatorFamily.CONCRETIZE,
            OperatorFamily.CONSTRAINT,
        ),
        state_summary=BranchStateSummary(
            mechanism_purity=0.62,
            baseline_attractor=0.32,
            transfer_slack=0.26,
            branch_fatigue=0.34,
        ),
    )

    arena.add_branch(mechanism_branch)
    arena.add_branch(bind_branch)
    arena.promote_top_k(1)

    snapshot = arena.observability_snapshot()

    assert snapshot["family_frequency"]["mechanism"] == 2
    assert snapshot["family_frequency"]["bind"] == 1
    assert snapshot["repeated_family_streaks"]["mechanism"] == 2
    assert snapshot["avg_baseline_attractor"] > 0.0
    assert snapshot["avg_branch_fatigue"] > 0.0
    assert snapshot["promoted_family_patterns"] == {"mechanism > mechanism > critique": 1}


def test_spawn_recovery_branches_adds_bounded_rescue_wave() -> None:
    strategy = replace(strategy_for_mode("AGGRESSIVE"), max_recovery_branches=5)
    structure = _make_structure()
    scored = [_make_scored_candidate(i) for i in range(3)]
    arena = BranchArena()

    breaker = _make_branch(
        "breaker",
        0.44,
        "Retain successful response paths without collapsing into a queue or cache analogue.",
        source_candidate_index=0,
        option_preservation=0.52,
        genericity=0.30,
        comfort=0.46,
        collapse=0.33,
    )
    subtraction = _make_branch(
        "subtraction",
        0.42,
        "Restate the mechanism in target-domain language and keep it distinct from baseline dispatch.",
        source_candidate_index=1,
        option_preservation=0.49,
        genericity=0.20,
        comfort=0.23,
        collapse=0.52,
        rejection_overlap=0.26,
    )
    inversion_ablation = _make_branch(
        "inversion-ablation",
        0.40,
        "Derive steady-state routing from the recovery state machine instead of the other way around.",
        source_candidate_index=2,
        option_preservation=0.58,
        genericity=0.16,
        comfort=0.18,
        collapse=0.59,
        verification=0.45,
        spread=0.44,
    )

    arena.add_branch(breaker)
    arena.add_branch(subtraction)
    arena.add_branch(inversion_ablation)

    recovered = arena.spawn_recovery_branches(
        strategy,
        structure=structure,
        scored_candidates=scored,
    )

    assert len(recovered) <= strategy.max_recovery_branches
    assert all(branch.parent_id is not None for branch in recovered)
    assert all(branch.stage_cursor == "recovery" for branch in recovered)

    kinds = {branch.recovery_operators[-1].kind for branch in recovered}
    assert kinds == {
        RecoveryOperatorKind.ATTRACTOR_BREAKER,
        RecoveryOperatorKind.SUBTRACTION_PROBE,
        RecoveryOperatorKind.ORDER_INVERSION,
        RecoveryOperatorKind.LOAD_BEARING_ABLATION,
    }


def test_promote_top_k_prefers_option_preserving_branch_when_scores_are_close() -> None:
    arena = BranchArena()
    conservative = _make_branch(
        "conservative",
        0.61,
        "Use a familiar queue-style scheduler with modest tuning.",
        option_preservation=0.24,
        comfort=0.42,
        genericity=0.36,
        promotion=0.58,
    )
    option_preserving = _make_branch(
        "option-preserving",
        0.59,
        "Keep the recovery state explicit so later translation can still choose a non-obvious control path.",
        option_preservation=0.71,
        comfort=0.14,
        genericity=0.12,
        promotion=0.67,
    )
    arena.add_branch(conservative)
    arena.add_branch(option_preserving)

    promoted = arena.promote_top_k(1)

    assert [branch.branch_id for branch in promoted] == ["option-preserving"]


def test_promote_top_k_preserves_distinct_archive_cells() -> None:
    arena = BranchArena()
    first = _make_branch(
        "first",
        0.62,
        "Retain explicit recovery memory.",
        promotion=0.81,
        island_key="biology:mechanism",
        archive_cell="biology:mechanism|n3|q3|l2",
    )
    second = _make_branch(
        "second",
        0.61,
        "Fuse verification state into admission decisions.",
        promotion=0.78,
        island_key="economics:bind",
        archive_cell="economics:bind|n3|q3|l3",
    )
    duplicate = _make_branch(
        "duplicate",
        0.60,
        "A near-duplicate elite from the same archive cell.",
        promotion=0.77,
        island_key="biology:mechanism",
        archive_cell="biology:mechanism|n3|q3|l2",
    )
    arena.add_branch(first)
    arena.add_branch(second)
    arena.add_branch(duplicate)

    promoted = arena.promote_top_k(2)

    assert {branch.branch_id for branch in promoted} == {"first", "second"}
    assert set(arena.positive_archive.values()) == {"first", "second"}


def test_branch_candidate_for_translation_attaches_branch_metadata() -> None:
    branch = _make_branch("bg-0", 0.64, "Keep retained response paths load-bearing.")
    candidate = _make_scored_candidate()

    promoted = branch_candidate_for_translation(branch, candidate)

    assert promoted is not candidate
    assert promoted.branch_genome.branch_id == "bg-0"
    assert promoted.branch_rank_score == branch.metrics.score_promotion
