"""Pantheon Mode coordinator.

Wraps the standard Genesis pipeline with a four-agent council:
- Hephaestus (existing translation/forge engine)
- Athena (structural canon)
- Hermes (reality dossier)
- Apollo (adversarial truth audit)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from copy import copy
from dataclasses import is_dataclass, replace
from typing import Any, Sequence

from hephaestus.core.translator import Translation, TranslationGuidance
from hephaestus.deepforge.harness import DeepForgeHarness
from hephaestus.pantheon import prompts
from hephaestus.pantheon.models import (
    ApolloAudit,
    AthenaCanon,
    HermesDossier,
    PantheonAccounting,
    PantheonObjection,
    PantheonReforgeRecord,
    PantheonRound,
    PantheonScreening,
    PantheonState,
    PantheonVote,
)

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "must",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "with",
}
_SEVERITY_ORDER = {"ADVISORY": 0, "REPAIRABLE": 1, "FATAL": 2}


class PantheonError(RuntimeError):
    """Raised when Pantheon Mode fails irrecoverably."""


def _json_block(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise PantheonError(f"No JSON object found: {raw[:240]}")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise PantheonError(f"Pantheon JSON parse failed: {exc}") from exc


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _canon_to_text(canon: AthenaCanon | None) -> str:
    return json.dumps(canon.to_dict() if canon is not None else {}, indent=2, ensure_ascii=False)


def _dossier_to_text(dossier: HermesDossier | None) -> str:
    return json.dumps(dossier.to_dict() if dossier is not None else {}, indent=2, ensure_ascii=False)


def _translation_to_text(translation: Translation) -> str:
    payload = {
        "invention_name": translation.invention_name,
        "architecture": translation.architecture,
        "key_insight": translation.key_insight,
        "limitations": translation.limitations,
        "baseline_comparison": translation.baseline_comparison,
        "mechanism_differs_from_baseline": translation.mechanism_differs_from_baseline,
        "source_domain": translation.source_domain,
        "novelty_signal": getattr(translation.source_candidate, "combined_score", 0.0),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _structure_snapshot(structure: Any) -> dict[str, Any]:
    return {
        "structure": str(getattr(structure, "structure", "") or ""),
        "mathematical_shape": str(getattr(structure, "mathematical_shape", "") or ""),
        "constraints": list(getattr(structure, "constraints", []) or []),
        "problem_maps_to": sorted(str(item) for item in (getattr(structure, "problem_maps_to", set()) or set())),
        "native_domain": str(getattr(structure, "native_domain", "") or ""),
    }


def _clone_structure(obj: Any, **updates: Any) -> Any:
    if is_dataclass(obj):
        return replace(obj, **updates)
    clone = copy(obj)
    for key, value in updates.items():
        setattr(clone, key, value)
    return clone


def _normalize_text(value: str) -> str:
    lowered = str(value or "").lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _keyword_tokens(*values: str) -> tuple[str, ...]:
    tokens: set[str] = set()
    for value in values:
        for token in re.findall(r"[a-z0-9]+", _normalize_text(value)):
            if len(token) < 3 or token in _STOPWORDS:
                continue
            if token.endswith("ing") and len(token) > 5:
                token = token[:-3]
            elif token.endswith("ed") and len(token) > 4:
                token = token[:-2]
            elif token.endswith("es") and len(token) > 4:
                token = token[:-2]
            elif token.endswith("s") and len(token) > 4:
                token = token[:-1]
            if token and token not in _STOPWORDS:
                tokens.add(token)
    return tuple(sorted(tokens))


def _similarity_score(left: PantheonObjection, right_statement: str, right_change: str, right_test: str) -> float:
    left_primary = _normalize_text(left.required_change or left.statement)
    left_secondary = _normalize_text(left.closure_test or left.statement)
    right_primary = _normalize_text(right_change or right_statement)
    right_secondary = _normalize_text(right_test or right_statement)
    if not left_primary or not right_primary:
        return 0.0
    if left_primary == right_primary or left_secondary == right_secondary:
        return 1.0
    if left_primary in right_primary or right_primary in left_primary:
        return 0.92
    left_tokens = set(_keyword_tokens(left.statement, left.required_change, left.closure_test))
    right_tokens = set(_keyword_tokens(right_statement, right_change, right_test))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        overlap += 0.12
    return overlap


def _severity(severity: Any, default: str = "REPAIRABLE") -> str:
    value = str(severity or default).upper()
    return value if value in _SEVERITY_ORDER else default


def _strongest_severity(severities: Sequence[str]) -> str | None:
    strongest: str | None = None
    strongest_rank = -1
    for severity in severities:
        rank = _SEVERITY_ORDER.get(_severity(severity), -1)
        if rank > strongest_rank:
            strongest = _severity(severity)
            strongest_rank = rank
    return strongest


def _decision_from_objections(objections: Sequence[PantheonObjection]) -> str:
    strongest = _strongest_severity([objection.severity for objection in objections])
    if strongest == "FATAL":
        return "VETO"
    if strongest == "REPAIRABLE":
        return "CONCERN"
    return "ASSENT"


def _objection_summary(objection: PantheonObjection) -> str:
    return f"{objection.objection_id}:{objection.severity}:{objection.statement}"


class PantheonCoordinator:
    """Coordinates Athena/Hermes/Apollo around Hephaestus output."""

    def __init__(
        self,
        *,
        athena_harness: DeepForgeHarness,
        hermes_harness: DeepForgeHarness,
        apollo_harness: DeepForgeHarness,
        max_rounds: int = 4,
        require_unanimity: bool = True,
        allow_fail_closed: bool = True,
        max_survivors_to_council: int = 2,
        resolution_mode: str = "TASK_SENSITIVE",
    ) -> None:
        self._athena = athena_harness
        self._hermes = hermes_harness
        self._apollo = apollo_harness
        self._max_rounds = max(1, max_rounds)
        self._require_unanimity = require_unanimity
        self._allow_fail_closed = allow_fail_closed
        self._max_survivors_to_council = max(1, max_survivors_to_council)
        normalized_mode = str(resolution_mode or "TASK_SENSITIVE").upper()
        self._resolution_mode = normalized_mode if normalized_mode in {"STRICT", "TASK_SENSITIVE"} else "TASK_SENSITIVE"

    @staticmethod
    def _record_accounting(
        accounting: PantheonAccounting,
        *,
        agent: str,
        trace: Any,
        duration_seconds: float,
    ) -> None:
        accounting.record(
            agent=agent,
            cost_usd=getattr(trace, "total_cost_usd", 0.0),
            input_tokens=getattr(trace, "total_input_tokens", 0),
            output_tokens=getattr(trace, "total_output_tokens", 0),
            duration_seconds=duration_seconds,
        )

    async def _forge_json(
        self,
        harness: DeepForgeHarness,
        prompt: str,
        *,
        system: str,
        accounting: PantheonAccounting,
        agent: str,
    ) -> dict[str, Any]:
        t_start = time.monotonic()
        result = await harness.forge(prompt, system=system)
        self._record_accounting(
            accounting,
            agent=agent,
            trace=result.trace,
            duration_seconds=time.monotonic() - t_start,
        )
        return _json_block(result.output)

    @staticmethod
    def _candidate_id(index: int, translation: Translation) -> str:
        lens_id = getattr(translation, "lens_id", "") or translation.invention_name
        return f"candidate-{index}:{lens_id}"

    def _candidate_objections(
        self,
        state: PantheonState,
        *,
        candidate_id: str,
        agent: str | None = None,
        status: str | None = None,
    ) -> list[PantheonObjection]:
        objections = [
            objection
            for objection in state.objection_ledger
            if objection.candidate_id == candidate_id
            and (agent is None or objection.agent == agent)
            and (status is None or objection.status == status)
        ]
        return sorted(
            objections,
            key=lambda objection: (
                objection.status != "OPEN",
                -_SEVERITY_ORDER.get(objection.severity, 0),
                -objection.last_seen_round,
                objection.objection_id,
            ),
        )

    @staticmethod
    def _objections_to_text(objections: Sequence[PantheonObjection]) -> str:
        return json.dumps([objection.to_dict() for objection in objections], indent=2, ensure_ascii=False)

    def _find_existing_objection(
        self,
        state: PantheonState,
        *,
        candidate_id: str,
        agent: str,
        statement: str,
        required_change: str,
        closure_test: str,
    ) -> PantheonObjection | None:
        best_match: PantheonObjection | None = None
        best_score = 0.0
        for objection in state.objection_ledger:
            if objection.candidate_id != candidate_id or objection.agent != agent:
                continue
            score = _similarity_score(objection, statement, required_change, closure_test)
            if score > best_score:
                best_match = objection
                best_score = score
        return best_match if best_score >= 0.72 else None

    def _new_objection_id(
        self,
        *,
        candidate_id: str,
        agent: str,
        severity: str,
        statement: str,
        required_change: str,
        closure_test: str,
    ) -> str:
        signature = "|".join(
            [
                _normalize_text(candidate_id),
                _normalize_text(agent),
                _severity(severity),
                " ".join(_keyword_tokens(required_change or statement, closure_test)),
                _normalize_text(required_change or statement)[:160],
                _normalize_text(closure_test or statement)[:160],
            ]
        )
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
        return f"obj-{agent}-{digest}"

    def _register_objections(
        self,
        *,
        state: PantheonState,
        candidate_id: str,
        round_index: int,
        stage: str,
        objection_specs: Sequence[dict[str, str]],
    ) -> list[PantheonObjection]:
        registered: list[PantheonObjection] = []
        for item in objection_specs:
            agent = str(item.get("agent", "") or "")
            severity = _severity(item.get("severity"), default="REPAIRABLE")
            statement = str(item.get("statement", "") or "").strip()
            required_change = str(item.get("required_change", statement) or statement).strip()
            closure_test = str(item.get("closure_test", required_change or statement) or (required_change or statement)).strip()
            if not agent or not statement:
                continue
            existing = self._find_existing_objection(
                state,
                candidate_id=candidate_id,
                agent=agent,
                statement=statement,
                required_change=required_change,
                closure_test=closure_test,
            )
            if existing is None:
                objection = PantheonObjection(
                    objection_id=self._new_objection_id(
                        candidate_id=candidate_id,
                        agent=agent,
                        severity=severity,
                        statement=statement,
                        required_change=required_change,
                        closure_test=closure_test,
                    ),
                    candidate_id=candidate_id,
                    agent=agent,
                    severity=severity,
                    statement=statement,
                    required_change=required_change,
                    closure_test=closure_test,
                    status="OPEN",
                    opened_round=round_index,
                    last_seen_round=round_index,
                    last_updated_round=round_index,
                    opened_stage=stage,
                    last_stage=stage,
                )
                state.objection_ledger.append(objection)
            else:
                objection = existing
                objection.severity = _strongest_severity([existing.severity, severity]) or severity
                if len(statement) >= len(objection.statement):
                    objection.statement = statement
                if len(required_change) >= len(objection.required_change):
                    objection.required_change = required_change
                if len(closure_test) >= len(objection.closure_test):
                    objection.closure_test = closure_test
                objection.status = "OPEN"
                objection.last_seen_round = round_index
                objection.last_updated_round = round_index
                objection.resolved_round = None
                objection.waived_round = None
                objection.last_stage = stage
            registered.append(objection)
        return registered

    def _resolve_missing_open_objections(
        self,
        *,
        state: PantheonState,
        candidate_id: str,
        round_index: int,
        seen_ids: set[str],
        stage: str,
    ) -> list[str]:
        resolved: list[str] = []
        for objection in state.objection_ledger:
            if objection.candidate_id != candidate_id or objection.status != "OPEN":
                continue
            if objection.objection_id in seen_ids:
                continue
            objection.status = "RESOLVED"
            objection.last_updated_round = round_index
            objection.resolved_round = round_index
            objection.last_stage = stage
            resolved.append(objection.objection_id)
        return resolved

    def _waive_objections(
        self,
        *,
        state: PantheonState,
        objection_ids: Sequence[str],
        round_index: int,
        stage: str,
    ) -> list[PantheonObjection]:
        waived: list[PantheonObjection] = []
        wanted = set(objection_ids)
        for objection in state.objection_ledger:
            if objection.objection_id not in wanted or objection.status != "OPEN":
                continue
            objection.status = "WAIVED"
            objection.last_updated_round = round_index
            objection.waived_round = round_index
            objection.last_stage = stage
            waived.append(objection)
        return waived

    def _review_objection_specs(
        self,
        *,
        agent: str,
        data: dict[str, Any],
        default_veto_type: str | None,
    ) -> list[dict[str, str]]:
        reasons = _safe_list(data.get("reasons"))
        must_change = _safe_list(data.get("must_change"))
        raw_objections = data.get("objections", [])
        specs: list[dict[str, str]] = []
        if isinstance(raw_objections, list):
            for item in raw_objections:
                if not isinstance(item, dict):
                    continue
                statement = str(item.get("statement", "") or "").strip()
                required_change = str(item.get("required_change", statement) or statement).strip()
                closure_test = str(item.get("closure_test", required_change or statement) or (required_change or statement)).strip()
                if not statement:
                    continue
                specs.append(
                    {
                        "agent": agent,
                        "severity": _severity(item.get("severity"), default="REPAIRABLE"),
                        "statement": statement,
                        "required_change": required_change,
                        "closure_test": closure_test,
                    }
                )
        if specs:
            return specs

        decision = str(data.get("decision", "ASSENT") or "ASSENT").upper()
        if decision == "ASSENT" and not must_change:
            return []

        default_severity = "ADVISORY"
        if decision in {"VETO", "CONCERN"}:
            default_severity = "REPAIRABLE"
        if default_veto_type == "TRUTH" and decision == "VETO":
            default_severity = "FATAL"

        if must_change:
            for index, change in enumerate(must_change):
                statement = reasons[index] if index < len(reasons) else reasons[0] if reasons else change
                specs.append(
                    {
                        "agent": agent,
                        "severity": default_severity,
                        "statement": statement,
                        "required_change": change,
                        "closure_test": change,
                    }
                )
            return specs

        if reasons:
            reason = reasons[0]
            specs.append(
                {
                    "agent": agent,
                    "severity": default_severity,
                    "statement": reason,
                    "required_change": reason,
                    "closure_test": reason,
                }
            )
        elif decision != "ASSENT":
            fallback = f"{agent} raised an unresolved {str(default_veto_type or 'council').lower()} objection."
            specs.append(
                {
                    "agent": agent,
                    "severity": default_severity,
                    "statement": fallback,
                    "required_change": fallback,
                    "closure_test": fallback,
                }
            )
        return specs

    def _apollo_objection_specs(self, audit: ApolloAudit, raw_data: dict[str, Any]) -> list[dict[str, str]]:
        raw_objections = raw_data.get("objections", [])
        specs: list[dict[str, str]] = []
        if isinstance(raw_objections, list):
            for item in raw_objections:
                if not isinstance(item, dict):
                    continue
                statement = str(item.get("statement", "") or "").strip()
                required_change = str(item.get("required_change", statement) or statement).strip()
                closure_test = str(item.get("closure_test", required_change or statement) or (required_change or statement)).strip()
                if not statement:
                    continue
                specs.append(
                    {
                        "agent": "apollo",
                        "severity": _severity(item.get("severity"), default="REPAIRABLE"),
                        "statement": statement,
                        "required_change": required_change,
                        "closure_test": closure_test,
                    }
                )
        if specs:
            return specs

        for flaw in audit.fatal_flaws:
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "FATAL",
                    "statement": flaw,
                    "required_change": audit.proof_obligations[0] if audit.proof_obligations else flaw,
                    "closure_test": audit.proof_obligations[0] if audit.proof_obligations else f"Apollo no longer detects: {flaw}",
                }
            )
        for signal in audit.decorative_signals:
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "FATAL",
                    "statement": signal,
                    "required_change": "Replace decorative or incoherent mechanism with an explicit causal mechanism.",
                    "closure_test": "Apollo confirms the mechanism is causal, non-decorative, and structurally coherent.",
                }
            )
        for weakness in audit.structural_weaknesses:
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "REPAIRABLE",
                    "statement": weakness,
                    "required_change": audit.proof_obligations[0] if audit.proof_obligations else weakness,
                    "closure_test": audit.proof_obligations[0] if audit.proof_obligations else weakness,
                }
            )
        seen_repairs = {item["required_change"] for item in specs}
        for obligation in audit.proof_obligations:
            if obligation in seen_repairs:
                continue
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "REPAIRABLE",
                    "statement": f"Proof obligation remains open: {obligation}",
                    "required_change": obligation,
                    "closure_test": obligation,
                }
            )
        if not specs and audit.verdict == "INVALID":
            basis = audit.reasons[0] if audit.reasons else "Apollo found a fatal truth contradiction."
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "FATAL",
                    "statement": basis,
                    "required_change": basis,
                    "closure_test": basis,
                }
            )
        elif not specs and audit.verdict == "PROVISIONAL":
            basis = audit.reasons[0] if audit.reasons else "Apollo requires additional causal proof."
            specs.append(
                {
                    "agent": "apollo",
                    "severity": "REPAIRABLE",
                    "statement": basis,
                    "required_change": basis,
                    "closure_test": basis,
                }
            )
        return specs

    def _build_vote(
        self,
        *,
        agent: str,
        data: dict[str, Any],
        default_veto_type: str | None,
        registered_objections: Sequence[PantheonObjection],
    ) -> PantheonVote:
        must_change = _dedupe([objection.required_change for objection in registered_objections] + _safe_list(data.get("must_change")))
        reasons = _dedupe([*(_safe_list(data.get("reasons"))), *[objection.statement for objection in registered_objections]])
        must_preserve = _safe_list(data.get("must_preserve"))
        strongest = _strongest_severity([objection.severity for objection in registered_objections])
        if strongest == "FATAL":
            decision = "VETO"
        elif strongest == "REPAIRABLE":
            decision = "CONCERN"
        elif strongest == "ADVISORY":
            decision = "ASSENT"
        else:
            raw_decision = str(data.get("decision", "ASSENT") or "ASSENT").upper()
            decision = raw_decision if raw_decision in {"ASSENT", "CONCERN", "VETO"} else "ASSENT"
        veto_type = default_veto_type if strongest == "FATAL" and default_veto_type is not None else (str(data.get("veto_type")) if data.get("veto_type") is not None else None)
        return PantheonVote(
            agent=agent,
            decision=decision,
            veto_type=veto_type,
            reasons=reasons,
            must_change=must_change,
            must_preserve=must_preserve,
            objection_ids=[objection.objection_id for objection in registered_objections],
            confidence=_safe_float(data.get("confidence")),
        )

    async def athena_canon_pass(
        self,
        *,
        problem: str,
        structure: Any,
        baseline_dossier: Any = None,
        accounting: PantheonAccounting,
    ) -> AthenaCanon:
        prompt = prompts.ATHENA_CANON_PROMPT.format(
            problem=problem,
            structure=getattr(structure, "structure", ""),
            mathematical_shape=getattr(structure, "mathematical_shape", ""),
            constraints="\n".join(f"- {item}" for item in getattr(structure, "constraints", [])[:12]) or "- none",
            baseline=getattr(baseline_dossier, "summary", "") if baseline_dossier is not None else "",
        )
        data = await self._forge_json(
            self._athena,
            prompt,
            system=prompts.ATHENA_CANON_SYSTEM,
            accounting=accounting,
            agent="athena",
        )
        return AthenaCanon(
            structural_form=str(data.get("structural_form", "")),
            mandatory_constraints=_safe_list(data.get("mandatory_constraints")),
            anti_goals=_safe_list(data.get("anti_goals")),
            decomposition_axes=_safe_list(data.get("decomposition_axes")),
            hidden_assumptions=_safe_list(data.get("hidden_assumptions")),
            success_criteria=_safe_list(data.get("success_criteria")),
            false_framings=_safe_list(data.get("false_framings")),
            reasons=_safe_list(data.get("reasons")),
            confidence=_safe_float(data.get("confidence")),
        )

    async def hermes_dossier_pass(
        self,
        *,
        problem: str,
        structure: Any,
        baseline_dossier: Any = None,
        accounting: PantheonAccounting,
    ) -> HermesDossier:
        prompt = prompts.HERMES_DOSSIER_PROMPT.format(
            problem=problem,
            structure=getattr(structure, "structure", ""),
            mathematical_shape=getattr(structure, "mathematical_shape", ""),
            constraints="\n".join(f"- {item}" for item in getattr(structure, "constraints", [])[:12]) or "- none",
            baseline=getattr(baseline_dossier, "summary", "") if baseline_dossier is not None else "",
        )
        data = await self._forge_json(
            self._hermes,
            prompt,
            system=prompts.HERMES_DOSSIER_SYSTEM,
            accounting=accounting,
            agent="hermes",
        )
        return HermesDossier(
            repo_reality_summary=str(data.get("repo_reality_summary", "")),
            competitor_patterns=_safe_list(data.get("competitor_patterns")),
            ecosystem_constraints=_safe_list(data.get("ecosystem_constraints")),
            user_operator_constraints=_safe_list(data.get("user_operator_constraints")),
            adoption_risks=_safe_list(data.get("adoption_risks")),
            monetization_vectors=_safe_list(data.get("monetization_vectors")),
            implementation_leverage_points=_safe_list(data.get("implementation_leverage_points")),
            reasons=_safe_list(data.get("reasons")),
            confidence=_safe_float(data.get("confidence")),
        )

    def apply_athena_canon(self, structure: Any, canon: AthenaCanon) -> Any:
        constraints = _dedupe([
            *list(getattr(structure, "constraints", []) or []),
            *canon.mandatory_constraints,
        ])
        problem_maps_to = set(getattr(structure, "problem_maps_to", set()) or set())
        problem_maps_to.update(
            item.strip().lower().replace(" ", "_")
            for item in canon.decomposition_axes
            if item.strip()
        )

        mathematical_shape = str(getattr(structure, "mathematical_shape", "") or "")
        if canon.decomposition_axes:
            axes_summary = ", ".join(canon.decomposition_axes[:4])
            if axes_summary and axes_summary not in mathematical_shape:
                mathematical_shape = (
                    f"{mathematical_shape} | canonical_axes={axes_summary}"
                    if mathematical_shape
                    else f"canonical_axes={axes_summary}"
                )

        revised = _clone_structure(
            structure,
            structure=canon.structural_form or getattr(structure, "structure", ""),
            constraints=constraints,
            mathematical_shape=mathematical_shape,
            problem_maps_to=problem_maps_to,
        )
        setattr(revised, "pantheon_canon", canon)
        setattr(revised, "pantheon_hidden_assumptions", list(canon.hidden_assumptions))
        setattr(revised, "pantheon_success_criteria", list(canon.success_criteria))
        setattr(revised, "pantheon_anti_goals", list(canon.anti_goals))
        return revised

    def translation_guidance(self, state: PantheonState | None) -> TranslationGuidance | None:
        if state is None or (state.canon is None and state.dossier is None):
            return None
        canon = state.canon or AthenaCanon()
        dossier = state.dossier or HermesDossier()
        return TranslationGuidance(
            structural_form=canon.structural_form,
            mandatory_constraints=list(canon.mandatory_constraints),
            anti_goals=list(canon.anti_goals),
            success_criteria=list(canon.success_criteria),
            false_framings=list(canon.false_framings),
            reality_summary=dossier.repo_reality_summary,
            ecosystem_constraints=list(dossier.ecosystem_constraints),
            user_operator_constraints=list(dossier.user_operator_constraints),
            adoption_risks=list(dossier.adoption_risks),
            implementation_leverage_points=list(dossier.implementation_leverage_points),
        )

    async def prepare_pipeline(
        self,
        *,
        problem: str,
        structure: Any,
        baseline_dossier: Any = None,
        state: PantheonState | None = None,
    ) -> tuple[Any, PantheonState]:
        current_state = state or PantheonState(mode="pantheon", resolution_mode=self._resolution_mode)
        current_state.mode = "pantheon"
        current_state.resolution_mode = self._resolution_mode
        current_state.initial_structure = current_state.initial_structure or _structure_snapshot(structure)

        canon = current_state.canon or await self.athena_canon_pass(
            problem=problem,
            structure=structure,
            baseline_dossier=baseline_dossier,
            accounting=current_state.accounting,
        )
        revised_structure = self.apply_athena_canon(structure, canon)
        dossier = current_state.dossier or await self.hermes_dossier_pass(
            problem=problem,
            structure=revised_structure,
            baseline_dossier=baseline_dossier,
            accounting=current_state.accounting,
        )

        current_state.canon = canon
        current_state.dossier = dossier
        current_state.pipeline_structure = _structure_snapshot(revised_structure)
        return revised_structure, current_state

    async def _athena_review(
        self,
        *,
        translation: Translation,
        canon: AthenaCanon,
        candidate_id: str,
        round_index: int,
        state: PantheonState,
        stage: str,
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        data = await self._forge_json(
            self._athena,
            prompts.ATHENA_REVIEW_PROMPT.format(
                canon=_canon_to_text(canon),
                objection_ledger=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id)),
                open_objections=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id, agent="athena", status="OPEN")),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.ATHENA_REVIEW_SYSTEM,
            accounting=accounting,
            agent="athena",
        )
        objection_specs = self._review_objection_specs(agent="athena", data=data, default_veto_type="STRUCTURAL")
        objections = self._register_objections(
            state=state,
            candidate_id=candidate_id,
            round_index=round_index,
            stage=stage,
            objection_specs=objection_specs,
        )
        return self._build_vote(agent="athena", data=data, default_veto_type="STRUCTURAL", registered_objections=objections)

    async def _hermes_review(
        self,
        *,
        translation: Translation,
        dossier: HermesDossier,
        candidate_id: str,
        round_index: int,
        state: PantheonState,
        stage: str,
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        data = await self._forge_json(
            self._hermes,
            prompts.HERMES_REVIEW_PROMPT.format(
                dossier=_dossier_to_text(dossier),
                objection_ledger=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id)),
                open_objections=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id, agent="hermes", status="OPEN")),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.HERMES_REVIEW_SYSTEM,
            accounting=accounting,
            agent="hermes",
        )
        objection_specs = self._review_objection_specs(agent="hermes", data=data, default_veto_type="REALITY")
        objections = self._register_objections(
            state=state,
            candidate_id=candidate_id,
            round_index=round_index,
            stage=stage,
            objection_specs=objection_specs,
        )
        return self._build_vote(agent="hermes", data=data, default_veto_type="REALITY", registered_objections=objections)

    async def _apollo_audit(
        self,
        *,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        candidate_id: str,
        round_index: int,
        state: PantheonState,
        stage: str,
        accounting: PantheonAccounting,
    ) -> tuple[ApolloAudit, PantheonVote]:
        data = await self._forge_json(
            self._apollo,
            prompts.APOLLO_AUDIT_PROMPT.format(
                canon=_canon_to_text(canon),
                dossier=_dossier_to_text(dossier),
                objection_ledger=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id)),
                open_objections=self._objections_to_text(self._candidate_objections(state, candidate_id=candidate_id, agent="apollo", status="OPEN")),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.APOLLO_AUDIT_SYSTEM,
            accounting=accounting,
            agent="apollo",
        )
        audit = ApolloAudit(
            candidate_id=str(data.get("candidate_id", candidate_id) or candidate_id),
            verdict=str(data.get("verdict", "PROVISIONAL") or "PROVISIONAL").upper(),
            fatal_flaws=_safe_list(data.get("fatal_flaws")),
            structural_weaknesses=_safe_list(data.get("structural_weaknesses")),
            decorative_signals=_safe_list(data.get("decorative_signals")),
            proof_obligations=_safe_list(data.get("proof_obligations")),
            reasons=_safe_list(data.get("reasons")),
            confidence=_safe_float(data.get("confidence")),
        )
        objection_specs = self._apollo_objection_specs(audit, data)
        objections = self._register_objections(
            state=state,
            candidate_id=candidate_id,
            round_index=round_index,
            stage=stage,
            objection_specs=objection_specs,
        )
        vote = PantheonVote(
            agent="apollo",
            decision=_decision_from_objections(objections),
            veto_type="TRUTH" if any(objection.severity == "FATAL" for objection in objections) else None,
            reasons=_dedupe([*audit.reasons, *[objection.statement for objection in objections]]),
            must_change=_dedupe([*audit.proof_obligations, *[objection.required_change for objection in objections]]),
            must_preserve=[],
            objection_ids=[objection.objection_id for objection in objections],
            confidence=audit.confidence,
        )
        return audit, vote

    async def screen_translations(
        self,
        *,
        translations: Sequence[Translation],
        state: PantheonState,
    ) -> tuple[list[Translation], PantheonState]:
        if not translations or state.canon is None or state.dossier is None:
            return list(translations), state

        screenings: list[PantheonScreening] = []
        ranked: list[tuple[float, int, Translation, PantheonScreening]] = []
        audits = list(state.audits)

        for index, translation in enumerate(translations, start=1):
            candidate_id = self._candidate_id(index, translation)
            hermes_vote = await self._hermes_review(
                translation=translation,
                dossier=state.dossier,
                candidate_id=candidate_id,
                round_index=0,
                state=state,
                stage="screening",
                accounting=state.accounting,
            )
            apollo_audit, apollo_vote = await self._apollo_audit(
                translation=translation,
                canon=state.canon,
                dossier=state.dossier,
                candidate_id=candidate_id,
                round_index=0,
                state=state,
                stage="screening",
                accounting=state.accounting,
            )
            audits.append(apollo_audit)

            candidate_objections = self._candidate_objections(state, candidate_id=candidate_id, status="OPEN")
            fatal_objections = [objection for objection in candidate_objections if objection.severity == "FATAL"]
            prune_reasons = [objection.statement for objection in fatal_objections]
            if translation.mechanism_is_decorative and not prune_reasons:
                prune_reasons.append("Decorative mechanism collapsed before council.")

            reality_bonus = hermes_vote.confidence if hermes_vote.decision == "ASSENT" else -0.25 if hermes_vote.decision == "CONCERN" else -(0.5 + hermes_vote.confidence)
            audit_bonus = apollo_vote.confidence if apollo_vote.decision == "ASSENT" else -0.25 if apollo_vote.decision == "CONCERN" else -1.0
            priority = float(getattr(translation, "combined_score", 0.0) or 0.0) + reality_bonus + audit_bonus

            screening = PantheonScreening(
                candidate_id=candidate_id,
                invention_name=translation.invention_name,
                source_domain=translation.source_domain,
                reality_vote=hermes_vote,
                audit=apollo_audit,
                objection_ids=_dedupe([*hermes_vote.objection_ids, *apollo_vote.objection_ids]),
                survived=False,
                priority_score=priority,
                prune_reasons=_dedupe(prune_reasons),
                summary=(
                    "Candidate survived pre-council screening."
                    if not prune_reasons
                    else f"Pruned before council: {'; '.join(_dedupe(prune_reasons)[:3])}"
                ),
            )
            screenings.append(screening)
            if not screening.prune_reasons:
                ranked.append((priority, index, translation, screening))

        ranked.sort(key=lambda item: (item[0], getattr(item[2], "combined_score", 0.0)), reverse=True)
        survivors: list[Translation] = []
        for _, _, translation, screening in ranked[: self._max_survivors_to_council]:
            screening.survived = True
            survivors.append(translation)

        state.screenings = screenings
        state.survivor_candidate_ids = [screening.candidate_id for screening in screenings if screening.survived]
        state.audits = audits
        if not survivors:
            state.unresolved_vetoes = _dedupe(
                _objection_summary(objection)
                for objection in state.objection_ledger
                if objection.status == "OPEN" and objection.severity == "FATAL"
            )
        return survivors, state

    @staticmethod
    def _reforge_changes(original: Translation, revised: Translation) -> list[str]:
        changes: list[str] = []
        comparisons = [
            ("architecture", original.architecture, revised.architecture),
            ("mathematical_proof", original.mathematical_proof, revised.mathematical_proof),
            ("implementation_notes", original.implementation_notes, revised.implementation_notes),
            ("key_insight", original.key_insight, revised.key_insight),
            ("baseline_comparison", original.baseline_comparison, revised.baseline_comparison),
            ("subtraction_test", original.subtraction_test, revised.subtraction_test),
        ]
        for label, before, after in comparisons:
            if str(before or "").strip() != str(after or "").strip():
                changes.append(f"Updated {label.replace('_', ' ')}.")
        if list(original.limitations) != list(revised.limitations):
            changes.append("Reworked limitations and caveat handling.")
        return changes or ["Applied a targeted structural patch without changing the novelty core."]

    async def _hephaestus_reforge(
        self,
        *,
        translator: Any,
        problem: str,
        structure: Any,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        open_objections: Sequence[PantheonObjection],
        accounting: PantheonAccounting,
    ) -> tuple[Translation | None, PantheonVote, PantheonReforgeRecord | None]:
        objection_payload = [objection.to_dict() for objection in open_objections]
        objection_ids = [objection.objection_id for objection in open_objections]
        must_preserve = [item for item in [translation.key_insight, *translation.recovery_commitments] if str(item).strip()]
        try:
            t_start = time.monotonic()
            revised = await translator.reforge(
                prompt=prompts.HEPHAESTUS_REFORGE_PROMPT.format(
                    problem=problem,
                    structure=getattr(structure, "structure", ""),
                    canon=_canon_to_text(canon),
                    dossier=_dossier_to_text(dossier),
                    candidate=_translation_to_text(translation),
                    objections=json.dumps(objection_payload, indent=2, ensure_ascii=False),
                ),
                structure=structure,
                source_translation=translation,
                system=prompts.HEPHAESTUS_REFORGE_SYSTEM,
            )
            if getattr(getattr(revised, "trace", None), "pantheon_owned", False) is False and getattr(revised, "trace", None) is not None:
                setattr(revised.trace, "pantheon_owned", True)
            self._record_accounting(
                accounting,
                agent="hephaestus",
                trace=getattr(revised, "trace", None) or type("Trace", (), {})(),
                duration_seconds=time.monotonic() - t_start,
            )
        except Exception as exc:
            logger.warning("Pantheon reforge failed: %s", exc)
            vote = PantheonVote(
                agent="hephaestus",
                decision="VETO",
                veto_type="NOVELTY",
                reasons=["Reforge failed to produce a valid architecture JSON output."],
                must_change=[objection.required_change for objection in open_objections],
                must_preserve=must_preserve,
                objection_ids=objection_ids,
                confidence=0.0,
            )
            return None, vote, None

        if not revised.architecture or revised.architecture == "Architecture generation failed":
            vote = PantheonVote(
                agent="hephaestus",
                decision="VETO",
                veto_type="NOVELTY",
                reasons=["Reforge failed to produce a valid architecture JSON output."],
                must_change=[objection.required_change for objection in open_objections],
                must_preserve=must_preserve,
                objection_ids=objection_ids,
                confidence=0.0,
            )
            return None, vote, None

        metadata = getattr(revised, "pantheon_reforge_metadata", {}) or {}
        reforge_record = PantheonReforgeRecord(
            addressed_objection_ids=list(metadata.get("addressed_objection_ids", []) or objection_ids),
            remaining_open_objection_ids=list(metadata.get("remaining_open_objection_ids", []) or []),
            changes_made=list(metadata.get("changes_made", []) or self._reforge_changes(translation, revised)),
            novelty_core_preserved=str(metadata.get("novelty_core_preserved", revised.key_insight or translation.key_insight) or ""),
        )
        vote = PantheonVote(
            agent="hephaestus",
            decision="ASSENT",
            veto_type=None,
            reasons=["Reforged candidate against explicit objection IDs while preserving the novelty core."],
            must_change=[],
            must_preserve=must_preserve,
            objection_ids=reforge_record.addressed_objection_ids,
            confidence=0.78,
        )
        return revised, vote, reforge_record

    def _caveat_text(self, objection: PantheonObjection) -> str:
        return (
            f"[{objection.objection_id}] {objection.statement} "
            f"(required_change: {objection.required_change}; closure_test: {objection.closure_test})"
        )

    def _determine_outcome_tier(
        self,
        *,
        votes: Sequence[PantheonVote],
        open_objections: Sequence[PantheonObjection],
        round_index: int,
    ) -> str | None:
        fatal_open = [objection for objection in open_objections if objection.severity == "FATAL"]
        repairable_open = [objection for objection in open_objections if objection.severity == "REPAIRABLE"]
        advisory_open = [objection for objection in open_objections if objection.severity == "ADVISORY"]
        if fatal_open:
            return None

        all_assent = all(vote.decision == "ASSENT" for vote in votes)
        no_veto = all(vote.decision != "VETO" for vote in votes)
        assent_count = sum(1 for vote in votes if vote.decision == "ASSENT")

        if all_assent and not repairable_open and not advisory_open:
            return "UNANIMOUS_CONSENSUS"

        allow_qualified = self._resolution_mode == "TASK_SENSITIVE" or not self._require_unanimity
        if allow_qualified and no_veto and not repairable_open and assent_count >= 2:
            return "QUALIFIED_CONSENSUS"

        allow_salvage = (
            self._resolution_mode == "TASK_SENSITIVE"
            or not self._allow_fail_closed
        )
        if allow_salvage and no_veto and round_index >= self._max_rounds and round_index >= 1:
            return "SALVAGED_CONSENSUS"
        return None

    @staticmethod
    def _resolution_name(outcome_tier: str) -> str:
        return str(outcome_tier or "").strip().lower()

    def _finalize_success(
        self,
        *,
        state: PantheonState,
        candidate_id: str,
        candidate: Translation,
        round_index: int,
        votes: list[PantheonVote],
        resolved_ids: list[str],
        open_objections: list[PantheonObjection],
        outcome_tier: str,
    ) -> tuple[list[Translation], PantheonState]:
        waiver_ids: list[str] = []
        if outcome_tier == "QUALIFIED_CONSENSUS":
            waiver_ids = [objection.objection_id for objection in open_objections if objection.severity == "ADVISORY"]
        elif outcome_tier == "SALVAGED_CONSENSUS":
            waiver_ids = [objection.objection_id for objection in open_objections]
        waived = self._waive_objections(
            state=state,
            objection_ids=waiver_ids,
            round_index=round_index,
            stage="council",
        )
        caveats = [self._caveat_text(objection) for objection in waived]
        hephaestus_vote = PantheonVote(
            agent="hephaestus",
            decision="ASSENT",
            veto_type=None,
            reasons=[f"Hephaestus preserved the novelty core through {outcome_tier.lower()}."],
            must_change=[],
            must_preserve=[candidate.key_insight] if candidate.key_insight else [],
            objection_ids=[objection.objection_id for objection in waived],
            confidence=0.85,
        )
        votes.append(hephaestus_vote)
        state.rounds.append(
            PantheonRound(
                round_index=round_index,
                candidate_id=candidate_id,
                votes=votes,
                consensus=True,
                outcome_tier=outcome_tier,
                unresolved_vetoes=[],
                open_objection_ids=[objection.objection_id for objection in open_objections],
                resolved_objection_ids=resolved_ids,
                waived_objection_ids=[objection.objection_id for objection in waived],
                caveats=caveats,
                revision_summary=f"Council converged via {outcome_tier.lower()} after objection discharge.",
            )
        )
        state.consensus_achieved = True
        state.winning_candidate_id = candidate_id
        state.resolution = self._resolution_name(outcome_tier)
        state.outcome_tier = outcome_tier
        if state.final_verdict in {"", "UNKNOWN"}:
            state.final_verdict = "PENDING_VERIFICATION"
        state.caveats = caveats
        state.failure_reason = None
        state.unresolved_vetoes = []
        candidate.pantheon_state = state.to_dict()
        return [candidate], state

    async def deliberate(
        self,
        *,
        problem: str,
        structure: Any,
        translations: Sequence[Translation],
        translator: Any,
        baseline_dossier: Any = None,
        previous_state: PantheonState | None = None,
        state: PantheonState | None = None,
    ) -> tuple[list[Translation], PantheonState]:
        current_state = state or previous_state or PantheonState(mode="pantheon", resolution_mode=self._resolution_mode)
        current_state.mode = "pantheon"
        current_state.resolution_mode = self._resolution_mode
        if current_state.final_verdict in {"", "UNKNOWN"}:
            current_state.final_verdict = "PENDING_VERIFICATION"
        current_state.outcome_tier = current_state.outcome_tier or "PENDING"
        if current_state.canon is None or current_state.dossier is None:
            _, current_state = await self.prepare_pipeline(
                problem=problem,
                structure=structure,
                baseline_dossier=baseline_dossier,
                state=current_state,
            )

        canon = current_state.canon
        dossier = current_state.dossier
        assert canon is not None
        assert dossier is not None

        survivors = list(translations[: self._max_survivors_to_council])
        if not survivors:
            current_state.final_verdict = "NO_OUTPUT"
            current_state.resolution = "no_candidates"
            current_state.outcome_tier = "FAIL_CLOSED_REJECTION"
            current_state.failure_reason = "No translation candidates entered Pantheon deliberation."
            current_state.unresolved_vetoes = _dedupe(
                _objection_summary(objection)
                for objection in current_state.objection_ledger
                if objection.status == "OPEN" and objection.severity == "FATAL"
            )
            return [], current_state

        candidate_ids = list(current_state.survivor_candidate_ids)
        if len(candidate_ids) < len(survivors):
            candidate_ids = [
                self._candidate_id(index, translation)
                for index, translation in enumerate(survivors, start=1)
            ]

        all_audits: list[ApolloAudit] = list(current_state.audits)

        for candidate_id, original in zip(candidate_ids, survivors):
            candidate = original
            for round_index in range(1, self._max_rounds + 1):
                athena_vote = await self._athena_review(
                    translation=candidate,
                    canon=canon,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage="council",
                    accounting=current_state.accounting,
                )
                hermes_vote = await self._hermes_review(
                    translation=candidate,
                    dossier=dossier,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage="council",
                    accounting=current_state.accounting,
                )
                apollo_audit, apollo_vote = await self._apollo_audit(
                    translation=candidate,
                    canon=canon,
                    dossier=dossier,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage="council",
                    accounting=current_state.accounting,
                )
                all_audits.append(apollo_audit)
                votes = [athena_vote, hermes_vote, apollo_vote]

                seen_ids = set()
                for vote in votes:
                    seen_ids.update(vote.objection_ids)
                resolved_ids = self._resolve_missing_open_objections(
                    state=current_state,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    seen_ids=seen_ids,
                    stage="council",
                )
                open_objections = self._candidate_objections(
                    current_state,
                    candidate_id=candidate_id,
                    status="OPEN",
                )
                unresolved_round = [_objection_summary(objection) for objection in open_objections]
                outcome_tier = self._determine_outcome_tier(
                    votes=votes,
                    open_objections=open_objections,
                    round_index=round_index,
                )

                if outcome_tier is not None:
                    current_state.audits = all_audits
                    return self._finalize_success(
                        state=current_state,
                        candidate_id=candidate_id,
                        candidate=candidate,
                        round_index=round_index,
                        votes=votes,
                        resolved_ids=resolved_ids,
                        open_objections=open_objections,
                        outcome_tier=outcome_tier,
                    )

                revised, hephaestus_vote, reforge_record = await self._hephaestus_reforge(
                    translator=translator,
                    problem=problem,
                    structure=structure,
                    translation=candidate,
                    canon=canon,
                    dossier=dossier,
                    open_objections=open_objections,
                    accounting=current_state.accounting,
                )
                votes.append(hephaestus_vote)
                current_state.rounds.append(
                    PantheonRound(
                        round_index=round_index,
                        candidate_id=candidate_id,
                        votes=votes,
                        consensus=False,
                        outcome_tier="PENDING",
                        unresolved_vetoes=unresolved_round,
                        open_objection_ids=[objection.objection_id for objection in open_objections],
                        resolved_objection_ids=resolved_ids,
                        waived_objection_ids=[],
                        caveats=[],
                        revision_summary=(
                            "Hephaestus applied a patch-oriented reforge against the live objection ledger."
                            if revised is not None
                            else "Reforge failed; novelty-preserving revision unavailable."
                        ),
                        reforge=reforge_record,
                    )
                )
                current_state.unresolved_vetoes = unresolved_round
                if revised is None:
                    break
                candidate = revised

        current_state.audits = all_audits
        open_fatal = [
            objection
            for objection in current_state.objection_ledger
            if objection.status == "OPEN" and objection.severity == "FATAL"
        ]
        current_state.unresolved_vetoes = [_objection_summary(objection) for objection in open_fatal]
        current_state.final_verdict = "NO_OUTPUT"
        current_state.consensus_achieved = False
        current_state.outcome_tier = "FAIL_CLOSED_REJECTION"
        current_state.resolution = "fail_closed_rejection"
        if open_fatal:
            current_state.failure_reason = (
                "Pantheon fail-closed because fatal truth objections remained open: "
                + "; ".join(objection.statement for objection in open_fatal[:3])
            )
        else:
            current_state.failure_reason = (
                "No candidate reached a truthful Pantheon consensus tier before round exhaustion."
            )
        return [], current_state

    def finalize_with_verified(self, state: PantheonState, verified_inventions: Sequence[Any]) -> PantheonState:
        if not verified_inventions:
            state.final_verdict = "NO_OUTPUT"
            state.consensus_achieved = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            if state.winning_candidate_id:
                verifier_objection = PantheonObjection(
                    objection_id=self._new_objection_id(
                        candidate_id=state.winning_candidate_id,
                        agent="verifier",
                        severity="FATAL",
                        statement="Final verification produced no surviving invention.",
                        required_change="Resolve the verifier failure or return no output.",
                        closure_test="A verifier-approved invention survives the final verification pass.",
                    ),
                    candidate_id=state.winning_candidate_id,
                    agent="verifier",
                    severity="FATAL",
                    statement="Final verification produced no surviving invention.",
                    required_change="Resolve the verifier failure or return no output.",
                    closure_test="A verifier-approved invention survives the final verification pass.",
                    status="OPEN",
                    opened_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                    last_seen_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                    last_updated_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                    opened_stage="verification",
                    last_stage="verification",
                )
                state.objection_ledger.append(verifier_objection)
                state.unresolved_vetoes = _dedupe([*state.unresolved_vetoes, _objection_summary(verifier_objection)])
            if state.winning_candidate_id:
                state.resolution = "verifier_rejected_consensus"
                state.failure_reason = "Pantheon consensus was reached, but verification produced no surviving invention."
            return state

        top = verified_inventions[0]
        state.final_verdict = str(getattr(top, "verdict", "UNKNOWN"))
        if getattr(top, "verdict", "UNKNOWN") == "INVALID":
            state.consensus_achieved = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            state.resolution = "verifier_rejected_consensus"
            state.failure_reason = "Pantheon consensus selected an invention that verification later invalidated."
            verifier_objection = PantheonObjection(
                objection_id=self._new_objection_id(
                    candidate_id=state.winning_candidate_id or "unknown",
                    agent="verifier",
                    severity="FATAL",
                    statement="Final verification invalidated the Pantheon-selected invention.",
                    required_change="Resolve the verifier invalidation before returning the invention.",
                    closure_test="The selected invention passes final verification with a non-invalid verdict.",
                ),
                candidate_id=state.winning_candidate_id or "",
                agent="verifier",
                severity="FATAL",
                statement="Final verification invalidated the Pantheon-selected invention.",
                required_change="Resolve the verifier invalidation before returning the invention.",
                closure_test="The selected invention passes final verification with a non-invalid verdict.",
                status="OPEN",
                opened_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                last_seen_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                last_updated_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                opened_stage="verification",
                last_stage="verification",
            )
            state.objection_ledger.append(verifier_objection)
            state.unresolved_vetoes = _dedupe([*state.unresolved_vetoes, _objection_summary(verifier_objection)])
        return state


__all__ = ["PantheonCoordinator", "PantheonError"]
