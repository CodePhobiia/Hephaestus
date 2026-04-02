from __future__ import annotations

from hephaestus.branchgenome import (
    BranchGenome,
    Commitment,
    CommitmentKind,
    RejectionLedger,
    RecoveryOperator,
    RecoveryOperatorKind,
    assay_branch,
    render_partial_prompt,
    strategy_for_mode,
)
from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="Design a resilient allocator that learns from past overloads.",
        structure="Feedback-driven resource allocation under recurring overload.",
        constraints=["bounded memory", "fast recovery"],
        mathematical_shape="adaptive control under repeated shocks",
        native_domain="distributed_systems",
        problem_maps_to={"allocation", "control"},
    )


def _make_candidate() -> ScoredCandidate:
    lens = Lens(
        name="Immune Memory",
        domain="biology",
        subdomain="immune",
        axioms=["Memory persists after success."],
        structural_patterns=[StructuralPattern("allocation", "Allocate with memory", ["allocation"])],
        injection_prompt="Reason biologically.",
    )
    lens_score = LensScore(
        lens=lens,
        domain_distance=0.88,
        structural_relevance=0.80,
        composite_score=0.76,
        matched_patterns=["allocation"],
    )
    candidate = SearchCandidate(
        source_domain="Immune System",
        source_solution="Clonal immune memory",
        mechanism="Successful responses are retained and recalled under later stress.",
        structural_mapping="Retained responders map to fast recovery primitives.",
        lens_used=lens,
        lens_score=lens_score,
    )
    return ScoredCandidate(
        candidate=candidate,
        structural_fidelity=0.84,
        domain_distance=0.88,
        combined_score=0.78,
        mechanism_novelty=0.74,
        strong_mappings=["Retained responders shorten later recovery time."],
    )


def _make_branch() -> BranchGenome:
    return BranchGenome(
        branch_id="bg-immune",
        parent_id=None,
        source_candidate_index=0,
        stage_cursor="pre_translation",
        commitments=(
            Commitment(
                id="mechanism",
                kind=CommitmentKind.MECHANISM_CLAIM,
                statement="Retain successful recovery paths so the system responds faster to repeated overload signatures.",
                confidence=0.85,
                reversible=True,
            ),
            Commitment(
                id="mapping",
                kind=CommitmentKind.MAPPING_CLAIM,
                statement="Map retained responders onto explicit fast-path recovery state.",
                confidence=0.78,
                reversible=True,
            ),
            Commitment(
                id="binding",
                kind=CommitmentKind.TARGET_BINDING,
                statement="Bind the mechanism to a concrete distributed scheduler with bounded memory and explicit decay.",
                confidence=0.80,
                reversible=True,
            ),
        ),
        open_questions=("What is the minimal viable decay policy?",),
        rejected_patterns=("naive caching",),
    )


def test_assay_branch_scores_survival_and_uses_strategy(tmp_path) -> None:
    structure = _make_structure()
    candidate = _make_candidate()
    branch = _make_branch()
    strategy = strategy_for_mode("STANDARD")
    ledger = RejectionLedger(tmp_path / "branchgenome.jsonl")

    metrics = assay_branch(
        branch,
        structure=structure,
        candidate=candidate,
        strategy=strategy,
        banned_patterns=("queue-based retry loop",),
        ledger=ledger,
    )

    assert metrics.perturbations_run == strategy.assay_perturbations_per_branch
    assert 0 <= metrics.perturbations_passed <= metrics.perturbations_run
    assert 0.0 <= metrics.spread_score <= 1.0
    assert 0.0 <= metrics.collapse_risk <= 1.0
    assert 0.0 <= metrics.future_option_preservation <= 1.0
    assert 0.0 <= metrics.genericity_penalty <= 1.0
    assert 0.0 <= metrics.comfort_penalty <= 1.0
    assert -1.0 <= metrics.score_survival <= 1.0
    assert -1.0 <= metrics.score_promotion <= 1.0


def test_assay_branch_penalizes_rejected_fingerprint_overlap(tmp_path) -> None:
    structure = _make_structure()
    candidate = _make_candidate()
    branch = _make_branch()
    strategy = strategy_for_mode("STANDARD")
    ledger = RejectionLedger(tmp_path / "branchgenome.jsonl")
    ledger.record(
        "retain successful recovery paths overload signatures bounded memory explicit decay",
        "decorative",
        "Collapsed into an obvious cache analogue.",
    )

    metrics = assay_branch(
        branch,
        structure=structure,
        candidate=candidate,
        strategy=strategy,
        banned_patterns=(),
        ledger=ledger,
    )

    assert metrics.rejection_overlap > 0.2


def test_render_partial_prompt_includes_recovery_operator_section() -> None:
    structure = _make_structure()
    branch = _make_branch()
    branch.recovery_operators = (
        RecoveryOperator(
            kind=RecoveryOperatorKind.SUBTRACTION_PROBE,
            trigger="Branch can survive by metaphor.",
            intervention="Strip the source vocabulary and restate the mechanism in target terms only.",
            preservation_goal="Keep a measurable difference after the analogy words are removed.",
        ),
    )

    rendered = render_partial_prompt(branch, structure)

    assert "RECOVERY OPERATORS" in rendered
    assert "subtraction_probe" in rendered
    assert "Keep a measurable difference" in rendered
