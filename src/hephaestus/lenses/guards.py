"""Runtime handoff guards for adaptive lens bundle execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hephaestus.lenses.cells import RuntimeReferenceState, build_reference_state

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((text or "").lower().replace("-", "_"))
        if len(token) > 2
    }


def _coverage_ratio(subject: set[str], reference: set[str]) -> float:
    if not reference:
        return 1.0
    return len(subject & reference) / len(reference)


@dataclass(frozen=True)
class GuardCheck:
    """Result of one deterministic handoff check."""

    name: str
    passed: bool
    severity: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class HandoffGuardResult:
    """Aggregate transition decision between two bundle members."""

    bundle_id: str | None
    current_lens_id: str
    previous_lens_id: str | None
    passed: bool
    requires_recomposition: bool
    invalidated_lens_ids: tuple[str, ...]
    checks: tuple[GuardCheck, ...]

    def summary(self) -> str:
        if self.passed:
            return f"guard pass for {self.current_lens_id}"
        failing = [check.name for check in self.checks if not check.passed]
        return f"guard fail for {self.current_lens_id}: {', '.join(failing[:4])}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "current_lens_id": self.current_lens_id,
            "previous_lens_id": self.previous_lens_id,
            "passed": self.passed,
            "requires_recomposition": self.requires_recomposition,
            "invalidated_lens_ids": list(self.invalidated_lens_ids),
            "checks": [check.to_dict() for check in self.checks],
        }


def evaluate_handoff_guards(
    *,
    structure: Any,
    candidate: Any,
    translation: Any,
    bundle_proof: Any | None,
    previous_translation: Any | None = None,
    current_reference_state: RuntimeReferenceState | None = None,
) -> HandoffGuardResult:
    """Run deterministic guards before accepting a bundle handoff."""

    reference_state = current_reference_state or build_reference_state(
        structure,
        branch_genome=getattr(candidate, "branch_genome", None),
    )
    reference_check = _reference_continuity_check(bundle_proof, reference_state)
    if previous_translation is None:
        invalidated = (getattr(candidate, "lens_id", ""),) if not reference_check.passed else ()
        return HandoffGuardResult(
            bundle_id=getattr(bundle_proof, "bundle_id", None),
            current_lens_id=str(getattr(candidate, "lens_id", "")),
            previous_lens_id=None,
            passed=reference_check.passed,
            requires_recomposition=not reference_check.passed,
            invalidated_lens_ids=invalidated,
            checks=(reference_check,),
        )

    checks = [
        reference_check,
        _abstraction_reset_check(previous_translation, candidate, translation),
        _constraint_carryover_check(structure, translation),
    ]
    counterexample = _counterexample_probe(structure, candidate, translation, bundle_proof)
    if counterexample is not None:
        checks.append(counterexample)

    failed = [check for check in checks if not check.passed]
    hard_fail = any(check.severity == "fail" for check in failed)
    invalidated = (getattr(candidate, "lens_id", ""),) if hard_fail else ()
    return HandoffGuardResult(
        bundle_id=getattr(bundle_proof, "bundle_id", None),
        current_lens_id=str(getattr(candidate, "lens_id", "")),
        previous_lens_id=str(getattr(previous_translation, "lens_id", ""))
        if previous_translation is not None
        else None,
        passed=not hard_fail,
        requires_recomposition=hard_fail,
        invalidated_lens_ids=invalidated,
        checks=tuple(checks),
    )


def _reference_continuity_check(
    bundle_proof: Any | None,
    reference_state: RuntimeReferenceState,
) -> GuardCheck:
    if bundle_proof is None:
        return GuardCheck(
            name="reference_continuity",
            passed=True,
            severity="info",
            detail="singleton mode does not require bundle reference continuity",
        )

    expected_reference = str(getattr(bundle_proof, "reference_signature", "") or "")
    expected_research = str(getattr(bundle_proof, "research_signature", "") or "")
    expected_branch = str(getattr(bundle_proof, "branch_signature", "") or "")
    passed = (
        expected_reference == reference_state.reference_signature
        and expected_research == reference_state.research_signature
        and (
            not expected_branch
            or not reference_state.branch_signature
            or expected_branch == reference_state.branch_signature
        )
    )
    detail = "bundle proof matches current reference/research state"
    if not passed:
        detail = "bundle proof reference state diverged from current runtime state"
    return GuardCheck(
        name="reference_continuity",
        passed=passed,
        severity="fail" if not passed else "info",
        detail=detail,
        evidence={
            "expected_reference_signature": expected_reference,
            "current_reference_signature": reference_state.reference_signature,
            "expected_research_signature": expected_research,
            "current_research_signature": reference_state.research_signature,
            "expected_branch_signature": expected_branch,
            "current_branch_signature": reference_state.branch_signature,
        },
    )


def _abstraction_reset_check(
    previous_translation: Any | None,
    candidate: Any,
    translation: Any,
) -> GuardCheck:
    if previous_translation is None:
        return GuardCheck(
            name="abstraction_reset",
            passed=True,
            severity="info",
            detail="no prior lens transition to reset",
        )

    previous_tokens = _tokenize(
        " ".join(
            filter(
                None,
                [
                    str(getattr(previous_translation, "source_domain", "") or ""),
                    str(getattr(previous_translation, "architecture", "") or ""),
                    str(getattr(previous_translation, "invention_name", "") or ""),
                ],
            )
        )
    )
    current_text = " ".join(
        filter(
            None,
            [
                str(getattr(candidate, "source_domain", "") or ""),
                str(getattr(translation, "architecture", "") or ""),
                str(getattr(translation, "key_insight", "") or ""),
                str(getattr(translation, "subtraction_test", "") or ""),
            ],
        )
    )
    current_tokens = _tokenize(current_text)
    overlap = _coverage_ratio(current_tokens, previous_tokens)
    passed = overlap <= 0.55 or bool(getattr(translation, "subtraction_test", ""))
    detail = "target-side wording was reset cleanly between lenses"
    if not passed:
        detail = "new lens handoff still carries too much prior-lens vocabulary"
    return GuardCheck(
        name="abstraction_reset",
        passed=passed,
        severity="fail" if not passed else "warn",
        detail=detail,
        evidence={
            "prior_token_overlap": round(overlap, 4),
            "previous_source_domain": getattr(previous_translation, "source_domain", ""),
            "current_source_domain": getattr(candidate, "source_domain", ""),
        },
    )


def _constraint_carryover_check(
    structure: Any,
    translation: Any,
) -> GuardCheck:
    constraints = list(getattr(structure, "constraints", []) or [])
    if not constraints:
        return GuardCheck(
            name="constraint_carryover",
            passed=True,
            severity="info",
            detail="no explicit hard constraints were attached to the problem",
        )

    translation_text = " ".join(
        filter(
            None,
            [
                str(getattr(translation, "architecture", "") or ""),
                str(getattr(translation, "implementation_notes", "") or ""),
                " ".join(getattr(translation, "limitations", []) or []),
            ],
        )
    )
    text_tokens = _tokenize(translation_text)
    matched = 0
    for constraint in constraints:
        if text_tokens & _tokenize(constraint):
            matched += 1
    ratio = matched / len(constraints)
    passed = ratio >= 0.5 or len(constraints) == 1
    detail = "translation preserved enough hard constraints to survive bundle handoff"
    if not passed:
        detail = "translation dropped too many hard constraints during handoff"
    return GuardCheck(
        name="constraint_carryover",
        passed=passed,
        severity="fail" if not passed else "warn",
        detail=detail,
        evidence={
            "constraint_match_ratio": round(ratio, 4),
            "constraint_count": len(constraints),
            "matched_constraints": matched,
        },
    )


def _counterexample_probe(
    structure: Any,
    candidate: Any,
    translation: Any,
    bundle_proof: Any | None,
) -> GuardCheck | None:
    branch = getattr(candidate, "branch_genome", None)
    rejected_patterns = tuple(getattr(branch, "rejected_patterns", ()) or ())
    recovery_operators = tuple(getattr(branch, "recovery_operators", ()) or ())
    if bundle_proof is None and not rejected_patterns and not recovery_operators:
        return None

    baseline_tokens = _tokenize(" ".join(rejected_patterns))
    baseline_tokens |= _tokenize(str(getattr(candidate, "target_domain_equivalent", "") or ""))
    bundle_card = getattr(bundle_proof, "derived_card", None)
    if bundle_card is not None:
        baseline_tokens |= _tokenize(
            " ".join(getattr(bundle_card, "disallowed_baselines", []) or [])
        )

    translation_tokens = _tokenize(
        " ".join(
            filter(
                None,
                [
                    str(getattr(translation, "architecture", "") or ""),
                    str(getattr(translation, "baseline_comparison", "") or ""),
                    str(getattr(translation, "mechanism_differs_from_baseline", "") or ""),
                    " ".join(getattr(translation, "recovery_commitments", []) or []),
                ],
            )
        )
    )
    baseline_overlap = (
        _coverage_ratio(translation_tokens, baseline_tokens) if baseline_tokens else 0.0
    )
    has_recovery_commitments = bool(getattr(translation, "recovery_commitments", []))
    passes = baseline_overlap <= 0.5 and (not recovery_operators or has_recovery_commitments)
    detail = (
        "counterexample probe found enough evidence that the architecture resists baseline collapse"
    )
    if not passes:
        detail = "counterexample probe indicates the bundle member collapsed into a rejected or obvious baseline"
    return GuardCheck(
        name="counterexample_probe",
        passed=passes,
        severity="fail" if not passes else "warn",
        detail=detail,
        evidence={
            "baseline_overlap": round(baseline_overlap, 4),
            "rejected_patterns": list(rejected_patterns),
            "recovery_operator_count": len(recovery_operators),
            "has_recovery_commitments": has_recovery_commitments,
        },
    )


__all__ = [
    "GuardCheck",
    "HandoffGuardResult",
    "evaluate_handoff_guards",
]
