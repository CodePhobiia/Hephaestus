"""Deterministic perturbation assay for BranchGenome."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hephaestus.branchgenome.ledger import RejectionLedger, fingerprint_branch, fingerprint_tokens
from hephaestus.branchgenome.models import (
    BranchGenome,
    BranchMetrics,
    BranchStateSummary,
    CommitmentKind,
    OperatorFamily,
)
from hephaestus.novelty import NoveltyVector
from hephaestus.branchgenome.strategy import (
    BranchStrategy,
    compute_promotion_score,
    compute_survival_score,
)

_GENERIC_BASELINES = {
    "cache",
    "caching",
    "queue",
    "retry",
    "retries",
    "parallel",
    "execution",
    "observer",
    "state",
    "machine",
    "load",
    "balancing",
    "scheduler",
    "pub",
    "sub",
}

_PERTURBATIONS = (
    "target-domain-only rewrite",
    "constraint order shuffled",
    "one hard constraint emphasized",
    "source-domain vocabulary suppressed",
)


def render_partial_prompt(branch: BranchGenome, structure: Any) -> str:
    """Render a compact, deterministic prompt for perturbation checks."""
    family_lines = [f"- {family.value}" for family in branch.recent_operator_families()] or ["- none"]
    commitment_lines = [
        f"- [{commitment.kind.value}] {commitment.statement}"
        for commitment in branch.commitments
    ]
    recovery_lines = [
        (
            f"- [{operator.kind.value}] trigger: {operator.trigger}; "
            f"intervention: {operator.intervention}; preserve: {operator.preservation_goal}"
        )
        for operator in branch.recovery_operators
    ] or ["- none"]
    open_question_lines = [f"- {question}" for question in branch.open_questions] or ["- none"]
    rejected_lines = [f"- {pattern}" for pattern in branch.rejected_patterns] or ["- none"]
    constraint_lines = [f"- {constraint}" for constraint in getattr(structure, "constraints", [])[:6]] or ["- none"]

    return "\n".join(
        [
            "TARGET PROBLEM",
            str(getattr(structure, "structure", "")),
            "NATIVE DOMAIN",
            str(getattr(structure, "native_domain", "")),
            "CONSTRAINTS",
            *constraint_lines,
            "OPERATOR FAMILY TRACE",
            *family_lines,
            "COMMITMENTS",
            *commitment_lines,
            "RECOVERY OPERATORS",
            *recovery_lines,
            "OPEN QUESTIONS",
            *open_question_lines,
            "REJECTION PRESSURE",
            *rejected_lines,
        ]
    )


def assay_branch(
    branch: BranchGenome,
    *,
    structure: Any,
    candidate: Any,
    strategy: BranchStrategy,
    banned_patterns: Sequence[str] = (),
    ledger: RejectionLedger | None = None,
) -> BranchMetrics:
    """Run the deterministic perturbation assay for a branch."""
    base_render = render_partial_prompt(branch, structure)
    perturbations = _PERTURBATIONS[: strategy.assay_perturbations_per_branch]

    rendered_variants: list[str] = []
    perturbation_passes = 0
    max_baseline_overlap = 0.0
    for perturbation in perturbations:
        rendered = _apply_perturbation(base_render, perturbation, structure, candidate)
        rendered_variants.append(rendered)
        checks = _run_checks(
            rendered=rendered,
            branch=branch,
            structure=structure,
            candidate=candidate,
            banned_patterns=banned_patterns,
        )
        max_baseline_overlap = max(max_baseline_overlap, checks["baseline_overlap"])
        if checks["all_passed"]:
            perturbation_passes += 1

    run_count = len(rendered_variants)
    pass_rate = perturbation_passes / run_count if run_count else 0.0
    diversity = _average_pairwise_distance([base_render, *rendered_variants])

    fingerprint = fingerprint_branch(branch)
    rejection_overlap = ledger.overlap(fingerprint) if ledger is not None else 0.0
    positive_overlap = ledger.positive_overlap(fingerprint) if ledger is not None else 0.0
    specificity = _specificity_score(base_render)
    genericity = _genericity_score(base_render, banned_patterns)
    token_cost_estimate = sum(max(1, len(rendered.split())) for rendered in rendered_variants)
    specialization_pressure, repetition_pressure, repeated_family_streak = _operator_family_pressures(
        branch,
        strategy.family_pressure_window,
    )

    future_option_preservation = _future_option_preservation_score(
        branch=branch,
        specificity=specificity,
        genericity=genericity,
        rejection_overlap=rejection_overlap,
    )
    comfort_penalty = _comfort_penalty_score(
        genericity=genericity,
        diversity=diversity,
        max_baseline_overlap=max_baseline_overlap,
        candidate=candidate,
    )

    novelty_hint = min(
        1.0,
        max(
            0.0,
            0.45 * float(getattr(candidate, "domain_distance", 0.0))
            + 0.35 * float(getattr(candidate, "mechanism_novelty", 0.5))
            + 0.20 * (1.0 - genericity),
        ),
    )
    spread_score = min(1.0, max(0.0, 0.65 * pass_rate + 0.35 * diversity))
    collapse_risk = min(
        1.0,
        max(
            0.0,
            0.40 * (1.0 - pass_rate)
            + 0.20 * max_baseline_overlap
            + 0.15 * max(0.0, 0.55 - specificity)
            + 0.15 * comfort_penalty
            + 0.10 * genericity,
        ),
    )
    verification_hint = min(
        1.0,
        max(
            0.0,
            0.55 * float(getattr(candidate, "structural_fidelity", 0.0))
            + 0.25 * pass_rate
            + 0.20 * (1.0 - max_baseline_overlap),
        ),
    )
    novelty_vector = _novelty_vector(
        branch=branch,
        candidate=candidate,
        max_baseline_overlap=max_baseline_overlap,
        rejection_overlap=rejection_overlap,
        positive_overlap=positive_overlap,
        pass_rate=pass_rate,
    )
    load_bearing_creativity = novelty_vector.load_bearing_score()
    diversity_credit = _clamp01(
        0.50 * novelty_vector.branch_family_distance
        + 0.30 * novelty_vector.source_domain_distance
        + 0.20 * novelty_vector.critic_disagreement
    )
    archive_novelty = novelty_vector.creativity_score()
    archive_quality = _clamp01(
        0.40 * verification_hint
        + 0.25 * future_option_preservation
        + 0.20 * load_bearing_creativity
        + 0.15 * pass_rate
    )
    quality_diversity_score = _clamp01(0.52 * archive_quality + 0.48 * archive_novelty)
    island_key = _island_key(branch, candidate)
    archive_cell = _archive_cell(
        island_key=island_key,
        novelty=archive_novelty,
        quality=archive_quality,
        load_bearing=load_bearing_creativity,
    )
    retrieval_expansion_readiness = _clamp01(
        0.45 * max(0.0, novelty_vector.evaluator_gain - novelty_vector.mechanism_distance)
        + 0.35 * collapse_risk
        + 0.20 * comfort_penalty
    )
    branch.island_key = island_key
    branch.archive_cell = archive_cell
    branch.retrieval_expansion_hints = _retrieval_expansion_hints(
        branch=branch,
        candidate=candidate,
        collapse_risk=collapse_risk,
        comfort_penalty=comfort_penalty,
        novelty_vector=novelty_vector,
    )

    state_summary = _branch_state_summary(
        branch=branch,
        strategy=strategy,
        pass_rate=pass_rate,
        specificity=specificity,
        genericity=genericity,
        max_baseline_overlap=max_baseline_overlap,
        rejection_overlap=rejection_overlap,
        repetition_pressure=repetition_pressure,
        token_cost_estimate=token_cost_estimate,
    )

    metrics = BranchMetrics(
        novelty_hint=novelty_hint,
        spread_score=spread_score,
        rejection_overlap=rejection_overlap,
        positive_overlap=positive_overlap,
        collapse_risk=collapse_risk,
        verification_hint=verification_hint,
        future_option_preservation=future_option_preservation,
        genericity_penalty=genericity,
        comfort_penalty=comfort_penalty,
        diversity_credit=diversity_credit,
        load_bearing_creativity=load_bearing_creativity,
        quality_diversity_score=quality_diversity_score,
        archive_novelty=archive_novelty,
        archive_quality=archive_quality,
        archive_cell=archive_cell,
        island_key=island_key,
        retrieval_expansion_readiness=retrieval_expansion_readiness,
        novelty_vector=novelty_vector,
        token_cost_estimate=token_cost_estimate,
        runtime_ms_estimate=run_count * 15,
        perturbations_run=run_count,
        perturbations_passed=perturbation_passes,
        specialization_pressure=specialization_pressure,
        repetition_pressure=repetition_pressure,
        repeated_family_streak=repeated_family_streak,
    )
    branch.state_summary = state_summary
    metrics.score_survival = compute_survival_score(metrics, state_summary, strategy)
    metrics.score_promotion = compute_promotion_score(metrics, state_summary, strategy)
    return metrics


def branch_similarity(left: BranchGenome, right: BranchGenome) -> float:
    """Return lexical similarity between two branch commitment sets."""
    left_tokens = fingerprint_tokens(left.commitment_text())
    right_tokens = fingerprint_tokens(right.commitment_text())
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _apply_perturbation(
    rendered: str,
    perturbation: str,
    structure: Any,
    candidate: Any,
) -> str:
    text = rendered
    if perturbation == "target-domain-only rewrite":
        source_tokens = str(getattr(candidate, "source_domain", "")).replace("—", " ").split()
        for token in source_tokens[:4]:
            if len(token) > 2:
                text = text.replace(token, str(getattr(structure, "native_domain", "target")).replace("_", " "))
        return text
    if perturbation == "constraint order shuffled":
        lines = text.splitlines()
        try:
            idx = lines.index("CONSTRAINTS")
        except ValueError:
            return text
        tail_start = idx + 1
        end = len(lines)
        for i in range(tail_start, len(lines)):
            if lines[i] == "OPERATOR FAMILY TRACE":
                end = i
                break
        shuffled = list(reversed(lines[tail_start:end]))
        return "\n".join(lines[:tail_start] + shuffled + lines[end:])
    if perturbation == "one hard constraint emphasized":
        constraints = getattr(structure, "constraints", [])
        if constraints:
            return f"MANDATORY CONSTRAINT: {constraints[0]}\n{text}"
        return text
    if perturbation == "source-domain vocabulary suppressed":
        source_tokens = (
            str(getattr(candidate, "source_domain", "")) + " " + str(getattr(candidate, "source_solution", ""))
        ).replace("—", " ").replace("-", " ").split()
        mutated = text
        for token in source_tokens[:8]:
            if len(token) > 3:
                mutated = mutated.replace(token, "")
                mutated = mutated.replace(token.lower(), "")
        return "\n".join(line.rstrip() for line in mutated.splitlines())
    return text


def _run_checks(
    *,
    rendered: str,
    branch: BranchGenome,
    structure: Any,
    candidate: Any,
    banned_patterns: Sequence[str],
) -> dict[str, Any]:
    headers = {"TARGET PROBLEM", "NATIVE DOMAIN", "COMMITMENTS", "OPEN QUESTIONS"}
    parseable = all(header in rendered for header in headers)

    baseline_overlap = _genericity_score(rendered, banned_patterns)
    distinct_from_baseline = baseline_overlap < 0.58

    has_mechanism = any(commitment.kind == CommitmentKind.MECHANISM_CLAIM for commitment in branch.commitments)
    has_binding = any(
        commitment.kind in {CommitmentKind.MAPPING_CLAIM, CommitmentKind.TARGET_BINDING}
        for commitment in branch.commitments
    )
    load_bearing = has_mechanism and has_binding and _specificity_score(rendered) >= 0.40

    target_phrase = str(getattr(structure, "native_domain", "")).replace("_", " ")
    candidate_words = set(
        str(getattr(candidate, "source_domain", "")).lower().replace("—", " ").replace("-", " ").split()
    )
    rendered_tokens = set(rendered.lower().split())
    target_coherent = target_phrase in rendered.lower() or any(
        token.lower() in rendered_tokens for token in str(getattr(structure, "constraints", [""])[0]).split()
    )
    target_coherent = target_coherent and len(rendered_tokens - candidate_words) >= 12

    all_passed = parseable and distinct_from_baseline and load_bearing and target_coherent
    return {
        "parseable": parseable,
        "distinct_from_baseline": distinct_from_baseline,
        "load_bearing": load_bearing,
        "target_coherent": target_coherent,
        "baseline_overlap": baseline_overlap,
        "all_passed": all_passed,
    }


def _specificity_score(text: str) -> float:
    tokens = [token for token in fingerprint_tokens(text) if len(token) > 4]
    if not tokens:
        return 0.0
    long_tokens = [token for token in tokens if len(token) > 7]
    return min(1.0, 0.35 + (len(long_tokens) / max(1, len(tokens))))


def _genericity_score(text: str, banned_patterns: Sequence[str]) -> float:
    tokens = fingerprint_tokens(text)
    if not tokens:
        return 1.0

    banned_tokens: set[str] = set(_GENERIC_BASELINES)
    for pattern in banned_patterns:
        banned_tokens.update(fingerprint_tokens(pattern))
    overlap = len(tokens & banned_tokens) / len(tokens)
    return min(1.0, overlap)


def _future_option_preservation_score(
    *,
    branch: BranchGenome,
    specificity: float,
    genericity: float,
    rejection_overlap: float,
) -> float:
    question_tokens = fingerprint_tokens(" ".join(branch.open_questions))
    kind_diversity = len({commitment.kind for commitment in branch.commitments}) / max(1, len(CommitmentKind))
    question_pressure = min(1.0, 0.30 * len(branch.open_questions) + 0.04 * len(question_tokens))
    recovery_pressure = min(1.0, 0.45 * len(branch.recovery_operators))
    anti_baseline = 1.0 - max(genericity, rejection_overlap)
    return min(
        1.0,
        max(
            0.0,
            0.24 * kind_diversity
            + 0.24 * question_pressure
            + 0.22 * specificity
            + 0.20 * recovery_pressure
            + 0.10 * anti_baseline,
        ),
    )


def _comfort_penalty_score(
    *,
    genericity: float,
    diversity: float,
    max_baseline_overlap: float,
    candidate: Any,
) -> float:
    mechanism_novelty = float(getattr(candidate, "mechanism_novelty", 0.5))
    return min(
        1.0,
        max(
            0.0,
            0.40 * genericity
            + 0.20 * max_baseline_overlap
            + 0.20 * (1.0 - diversity)
            + 0.20 * (1.0 - mechanism_novelty),
        ),
    )


def _branch_state_summary(
    *,
    branch: BranchGenome,
    strategy: BranchStrategy,
    pass_rate: float,
    specificity: float,
    genericity: float,
    max_baseline_overlap: float,
    rejection_overlap: float,
    repetition_pressure: float,
    token_cost_estimate: int,
) -> BranchStateSummary:
    mechanism_tokens = fingerprint_tokens(
        " ".join(
            commitment.statement
            for commitment in branch.commitments
            if commitment.kind in {
                CommitmentKind.MECHANISM_CLAIM,
                CommitmentKind.MAPPING_CLAIM,
                CommitmentKind.TARGET_BINDING,
            }
        )
    )
    all_commitment_tokens = fingerprint_tokens(branch.commitment_text())
    mechanism_focus = len(mechanism_tokens) / len(all_commitment_tokens) if all_commitment_tokens else 0.0

    binding_text = " ".join(
        commitment.statement
        for commitment in branch.commitments
        if commitment.kind == CommitmentKind.TARGET_BINDING
    )
    recent_families = set(branch.recent_operator_families(strategy.family_pressure_window))
    binding_depth = min(
        1.0,
        0.45 * float(OperatorFamily.BIND in recent_families)
        + 0.35 * float(OperatorFamily.CONCRETIZE in recent_families)
        + 0.20 * _specificity_score(binding_text or branch.commitment_text()),
    )
    open_question_ratio = min(1.0, len(branch.open_questions) / 3.0)
    token_pressure = max(
        0.0,
        min(
            1.0,
            (token_cost_estimate / max(1, strategy.per_branch_token_cap) - 0.40) / 0.60,
        ),
    )

    return BranchStateSummary(
        mechanism_purity=_clamp01(
            0.55 * mechanism_focus + 0.25 * specificity + 0.20 * (1.0 - max_baseline_overlap)
        ),
        baseline_attractor=_clamp01(
            0.55 * max_baseline_overlap + 0.25 * rejection_overlap + 0.20 * genericity
        ),
        transfer_slack=_clamp01(
            0.50 * open_question_ratio + 0.35 * (1.0 - binding_depth) + 0.15 * (1.0 - pass_rate)
        ),
        branch_fatigue=_clamp01(
            0.45 * (1.0 - pass_rate) + 0.35 * repetition_pressure + 0.20 * token_pressure
        ),
    )


def _operator_family_pressures(
    branch: BranchGenome,
    window: int,
) -> tuple[float, float, int]:
    families = branch.recent_operator_families(window)
    if not families:
        return 0.0, 0.0, 0

    counts: dict[OperatorFamily, int] = {}
    for family in families:
        counts[family] = counts.get(family, 0) + 1
    dominant_share = max(counts.values()) / len(families)
    uniform_share = 1.0 / len(families)
    specialization_pressure = (
        0.0 if len(families) <= 1 else _clamp01((dominant_share - uniform_share) / max(1e-6, 1.0 - uniform_share))
    )
    repeated_family_streak = _max_repeated_family_streak(families)
    repetition_pressure = 0.0 if len(families) <= 1 else _clamp01((repeated_family_streak - 1) / (len(families) - 1))
    return specialization_pressure, repetition_pressure, repeated_family_streak


def _max_repeated_family_streak(families: Sequence[OperatorFamily]) -> int:
    if not families:
        return 0
    best = 1
    current = 1
    for previous, current_family in zip(families, families[1:]):
        if current_family == previous:
            current += 1
            best = max(best, current)
            continue
        current = 1
    return best


def _average_pairwise_distance(texts: Sequence[str]) -> float:
    if len(texts) < 2:
        return 0.0

    token_sets = [fingerprint_tokens(text) for text in texts]
    distances: list[float] = []
    for idx, left in enumerate(token_sets):
        for right in token_sets[idx + 1 :]:
            union = left | right
            similarity = len(left & right) / len(union) if union else 1.0
            distances.append(1.0 - similarity)
    if not distances:
        return 0.0
    return sum(distances) / len(distances)


def _novelty_vector(
    *,
    branch: BranchGenome,
    candidate: Any,
    max_baseline_overlap: float,
    rejection_overlap: float,
    positive_overlap: float,
    pass_rate: float,
) -> NoveltyVector:
    family_distance = _branch_family_distance(branch)
    mechanism_distance = _clamp01(float(getattr(candidate, "mechanism_novelty", 0.0)))
    evaluator_gain = _clamp01(
        0.50 * float(getattr(candidate, "structural_fidelity", 0.0))
        + 0.25 * float(getattr(candidate, "combined_score", 0.0))
        + 0.25 * pass_rate
    )
    subtraction_delta = _subtraction_delta(branch, candidate, pass_rate)
    critic_disagreement = _critic_disagreement(branch, candidate)
    return NoveltyVector(
        banality_similarity=max_baseline_overlap,
        prior_art_similarity=max(rejection_overlap, positive_overlap),
        branch_family_distance=family_distance,
        source_domain_distance=_clamp01(float(getattr(candidate, "domain_distance", 0.0))),
        mechanism_distance=mechanism_distance,
        evaluator_gain=evaluator_gain,
        subtraction_delta=subtraction_delta,
        critic_disagreement=critic_disagreement,
    )


def _branch_family_distance(branch: BranchGenome) -> float:
    families = branch.recent_operator_families()
    if not families:
        return 0.0
    return _clamp01(len(set(families)) / len(families))


def _subtraction_delta(branch: BranchGenome, candidate: Any, pass_rate: float) -> float:
    verification_commitments = sum(
        1 for commitment in branch.commitments if commitment.kind == CommitmentKind.VERIFICATION_ASSERTION
    )
    operator_bonus = 0.20 * sum(
        1 for operator in branch.recovery_operators if operator.kind.name.endswith(("PROBE", "ABLATION"))
    )
    candidate_bonus = 0.20 * float(not bool(getattr(candidate, "would_engineer_reach_for_this", True)))
    return _clamp01(0.20 * pass_rate + 0.20 * verification_commitments + operator_bonus + candidate_bonus)


def _critic_disagreement(branch: BranchGenome, candidate: Any) -> float:
    strong = list(getattr(candidate, "strong_mappings", []) or [])
    weak = list(getattr(candidate, "weak_mappings", []) or [])
    mapping_pressure = len(weak) / max(1, len(strong) + len(weak))
    novelty_gap = abs(
        float(getattr(candidate, "structural_fidelity", 0.0)) - float(getattr(candidate, "mechanism_novelty", 0.0))
    )
    question_pressure = min(1.0, len(branch.open_questions) / 4.0)
    return _clamp01(0.40 * novelty_gap + 0.35 * mapping_pressure + 0.25 * question_pressure)


def _island_key(branch: BranchGenome, candidate: Any) -> str:
    if branch.island_key:
        return branch.island_key
    lens = getattr(candidate, "lens_used", None)
    source_family = (
        str(getattr(lens, "domain_family", "") or getattr(lens, "domain", "") or getattr(candidate, "source_domain", ""))
        .strip()
        .replace(" ", "_")
        .lower()
    ) or "unknown"
    lead_family = branch.operator_family_history[0].value if branch.operator_family_history else "untyped"
    return f"{source_family}:{lead_family}"


def _archive_cell(*, island_key: str, novelty: float, quality: float, load_bearing: float) -> str:
    novelty_bucket = int(_clamp01(novelty) * 4)
    quality_bucket = int(_clamp01(quality) * 4)
    load_bucket = int(_clamp01(load_bearing) * 4)
    return f"{island_key}|n{novelty_bucket}|q{quality_bucket}|l{load_bucket}"


def _retrieval_expansion_hints(
    *,
    branch: BranchGenome,
    candidate: Any,
    collapse_risk: float,
    comfort_penalty: float,
    novelty_vector: NoveltyVector,
) -> tuple[str, ...]:
    hints: list[str] = []
    if novelty_vector.evaluator_gain > novelty_vector.mechanism_distance:
        hints.append(
            "Retrieve structurally distant mechanisms that solve the same control problem with a less obvious organizing primitive."
        )
    if comfort_penalty >= 0.34:
        baseline = str(getattr(candidate, "target_domain_equivalent", "") or "nearest target-domain baseline")
        hints.append(f"Exclude {baseline} analogues and expand into domains that avoid queue/cache/retry comfort patterns.")
    if collapse_risk >= 0.48:
        hints.append("Prefer recovery-first or failure-derived control mechanisms instead of steady-state-first analogies.")
    if branch.recovery_operators:
        hints.append("Retrieve implementation-heavy exemplars that keep subtraction-test commitments load-bearing.")
    return tuple(dict.fromkeys(hints))


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
