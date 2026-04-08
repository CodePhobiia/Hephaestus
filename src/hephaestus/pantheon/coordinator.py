"""Pantheon Mode coordinator.

Wraps the standard Genesis pipeline with a four-agent council:
- Hephaestus (existing translation/forge engine)
- Athena (structural canon)
- Hermes (reality dossier)
- Apollo (adversarial truth audit)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Sequence
from copy import copy
from dataclasses import is_dataclass, replace
from typing import Any

from hephaestus.core.json_utils import loads_lenient
from hephaestus.core.translator import Translation, TranslationGuidance
from hephaestus.deepforge.harness import DeepForgeHarness
from hephaestus.pantheon import prompts
from hephaestus.pantheon.models import (
    PANTHEON_ISSUE_TYPES,
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
_ISSUE_TYPE_BY_AGENT = {
    "athena": "STRUCTURAL",
    "hermes": "REALITY",
    "apollo": "TRUTH",
    "hephaestus": "NOVELTY",
    "verifier": "TRUTH",
}
_ISSUE_ORDER = {"REALITY": 0, "STRUCTURAL": 1, "TRUTH": 2, "NOVELTY": 3}


class PantheonError(RuntimeError):
    """Raised when Pantheon Mode fails irrecoverably."""


def _extract_outermost_json(text: str) -> str:
    """Extract the outermost JSON object using brace-depth counting.

    Handles nested objects correctly, unlike a non-greedy regex.
    """
    start = text.find("{")
    if start == -1:
        raise PantheonError(f"No JSON object found: {text[:240]}")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise PantheonError(f"Unbalanced braces in JSON: {text[:240]}")


def _json_block(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    json_str = _extract_outermost_json(cleaned)
    parsed = loads_lenient(json_str, label="pantheon")
    if parsed is None:
        raise PantheonError(f"Pantheon JSON parse failed on invalid JSON: {json_str[:200]}")
    return parsed


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
    return json.dumps(
        dossier.to_dict() if dossier is not None else {}, indent=2, ensure_ascii=False
    )


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
        "problem_maps_to": sorted(
            str(item) for item in (getattr(structure, "problem_maps_to", set()) or set())
        ),
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
            elif token.endswith("ed") and len(token) > 4 or token.endswith("es") and len(token) > 4:
                token = token[:-2]
            elif token.endswith("s") and len(token) > 4:
                token = token[:-1]
            if token and token not in _STOPWORDS:
                tokens.add(token)
    return tuple(sorted(tokens))


def _similarity_score(
    left: PantheonObjection, right_statement: str, right_change: str, right_test: str
) -> float:
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


def _issue_type(issue_type: Any, *, agent: str = "", default: str | None = None) -> str:
    fallback = default or _ISSUE_TYPE_BY_AGENT.get(str(agent or "").lower(), "STRUCTURAL")
    value = str(issue_type or fallback).upper()
    return value if value in PANTHEON_ISSUE_TYPES else fallback


def _strongest_severity(severities: Sequence[str]) -> str | None:
    strongest: str | None = None
    strongest_rank = -1
    for severity in severities:
        rank = _SEVERITY_ORDER.get(_severity(severity), -1)
        if rank > strongest_rank:
            strongest = _severity(severity)
            strongest_rank = rank
    return strongest


def _severity_weight(severity: str) -> float:
    return {
        "ADVISORY": 0.2,
        "REPAIRABLE": 1.0,
        "FATAL": 2.5,
    }.get(_severity(severity), 0.0)


def _decision_from_objections(objections: Sequence[PantheonObjection]) -> str:
    strongest = _strongest_severity([objection.severity for objection in objections])
    if strongest == "FATAL":
        return "VETO"
    if strongest == "REPAIRABLE":
        return "CONCERN"
    return "ASSENT"


def _objection_summary(objection: PantheonObjection) -> str:
    return (
        f"{objection.objection_id}:{objection.issue_type}:{objection.severity}:"
        f"{objection.claim_text or objection.statement}"
    )


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
        olympus_context: str = "",
    ) -> None:
        self._athena = athena_harness
        self._hermes = hermes_harness
        self._apollo = apollo_harness
        self._max_rounds = max(1, max_rounds)
        self._require_unanimity = require_unanimity
        self._allow_fail_closed = allow_fail_closed
        self._max_survivors_to_council = max(1, max_survivors_to_council)
        self._olympus_context = olympus_context
        normalized_mode = str(resolution_mode or "TASK_SENSITIVE").upper()
        self._resolution_mode = (
            normalized_mode if normalized_mode in {"STRICT", "TASK_SENSITIVE"} else "TASK_SENSITIVE"
        )

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
        import asyncio as _asyncio

        # Inject Olympus repo context into every Pantheon agent's system prompt
        if self._olympus_context:
            system = self._olympus_context + "\n\n" + system

        t_start = time.monotonic()
        pantheon_timeout = 2400.0
        try:
            result = await _asyncio.wait_for(
                harness.forge(prompt, system=system),
                timeout=pantheon_timeout,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"Pantheon {agent} timed out after {pantheon_timeout:.0f}s during _forge_json"
            ) from exc
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
                -_ISSUE_ORDER.get(objection.issue_type, 0),
                -objection.last_seen_round,
                objection.objection_id,
            ),
        )

    @staticmethod
    def _objections_to_text(objections: Sequence[PantheonObjection]) -> str:
        return json.dumps(
            [objection.to_dict() for objection in objections], indent=2, ensure_ascii=False
        )

    @staticmethod
    def _masked_objections_to_text(objections: Sequence[PantheonObjection]) -> str:
        payload = [
            {
                "issue_id": objection.objection_id,
                "issue_type": objection.issue_type,
                "severity": objection.severity,
                "claim_text": objection.claim_text or objection.statement,
                "evidence": list(objection.evidence[:2]),
                "must_preserve": list(objection.must_preserve[:2]),
                "discharge_test": objection.discharge_test or objection.closure_test,
                "status": objection.status,
                "opened_by": objection.opened_by or objection.agent,
            }
            for objection in objections
        ]
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @staticmethod
    def _must_preserve_anchors(
        translation: Translation, objections: Sequence[PantheonObjection]
    ) -> list[str]:
        anchors = [
            translation.key_insight,
            translation.future_option_preservation,
            *list(translation.recovery_commitments),
        ]
        for objection in objections:
            anchors.extend(objection.must_preserve)
        return _dedupe(anchors)

    @staticmethod
    def _changed_claims(reforge: PantheonReforgeRecord | None) -> list[str]:
        if reforge is None:
            return []
        return _dedupe([*reforge.changes_made, *reforge.addressed_objection_ids])

    def _find_existing_objection(
        self,
        state: PantheonState,
        *,
        candidate_id: str,
        agent: str,
        issue_type: str,
        statement: str,
        required_change: str,
        closure_test: str,
    ) -> PantheonObjection | None:
        best_match: PantheonObjection | None = None
        best_score = 0.0
        for objection in state.objection_ledger:
            if objection.candidate_id != candidate_id or objection.agent != agent:
                continue
            if objection.issue_type != issue_type:
                continue
            score = _similarity_score(objection, statement, required_change, closure_test)
            if score > best_score:
                best_match = objection
                best_score = score
        return best_match if best_score >= 0.85 else None

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
        objection_specs: Sequence[dict[str, Any]],
    ) -> list[PantheonObjection]:
        registered: list[PantheonObjection] = []
        for item in objection_specs:
            agent = str(item.get("agent", "") or "")
            issue_type = _issue_type(item.get("issue_type"), agent=agent)
            severity = _severity(item.get("severity"), default="REPAIRABLE")
            statement = str(
                item.get("statement", item.get("claim_text", "")) or item.get("claim_text", "")
            ).strip()
            claim_text = str(item.get("claim_text", statement) or statement).strip()
            required_change = str(item.get("required_change", statement) or statement).strip()
            closure_test = str(
                item.get("closure_test", item.get("discharge_test", required_change or statement))
                or item.get("discharge_test", required_change or statement)
                or (required_change or statement)
            ).strip()
            discharge_test = str(item.get("discharge_test", closure_test) or closure_test).strip()
            evidence = _safe_list(item.get("evidence"))
            must_preserve = _safe_list(item.get("must_preserve"))
            if not agent or not statement:
                continue
            existing = self._find_existing_objection(
                state,
                candidate_id=candidate_id,
                agent=agent,
                issue_type=issue_type,
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
                    issue_type=issue_type,
                    severity=severity,
                    claim_text=claim_text,
                    statement=statement,
                    required_change=required_change,
                    closure_test=closure_test,
                    discharge_test=discharge_test,
                    evidence=evidence,
                    must_preserve=must_preserve,
                    opened_by=agent,
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
                objection.issue_type = issue_type
                objection.severity = _strongest_severity([existing.severity, severity]) or severity
                if len(claim_text) >= len(objection.claim_text):
                    objection.claim_text = claim_text
                if len(statement) >= len(objection.statement):
                    objection.statement = statement
                if len(required_change) >= len(objection.required_change):
                    objection.required_change = required_change
                if len(closure_test) >= len(objection.closure_test):
                    objection.closure_test = closure_test
                if len(discharge_test) >= len(objection.discharge_test):
                    objection.discharge_test = discharge_test
                objection.evidence = _dedupe([*objection.evidence, *evidence])
                objection.must_preserve = _dedupe([*objection.must_preserve, *must_preserve])
                objection.status = "OPEN"
                objection.last_seen_round = round_index
                objection.last_updated_round = round_index
                objection.resolved_round = None
                objection.waived_round = None
                objection.last_stage = stage
            registered.append(objection)
        state.issue_count_opened = sum(
            1 for objection in state.objection_ledger if objection.status == "OPEN"
        )
        return registered

    def _resolve_missing_open_objections(
        self,
        *,
        state: PantheonState,
        candidate_id: str,
        round_index: int,
        seen_ids: set[str],
        stage: str,
        explicitly_addressed_ids: set[str] | None = None,
    ) -> list[str]:
        resolved: list[str] = []
        for objection in state.objection_ledger:
            if objection.candidate_id != candidate_id or objection.status != "OPEN":
                continue
            if objection.objection_id in seen_ids:
                continue
            if objection.severity == "FATAL":
                if explicitly_addressed_ids and objection.objection_id in explicitly_addressed_ids:
                    pass  # explicitly addressed in reforge
                else:
                    continue  # never auto-resolve fatal — requires explicit discharge
            objection.status = "RESOLVED"
            objection.last_updated_round = round_index
            objection.resolved_round = round_index
            objection.last_stage = stage
            resolved.append(objection.objection_id)
        if resolved:
            state.issue_count_discharged += len(resolved)
            state.issue_count_opened = sum(
                1 for objection in state.objection_ledger if objection.status == "OPEN"
            )
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
        if waived:
            state.issue_count_opened = sum(
                1 for objection in state.objection_ledger if objection.status == "OPEN"
            )
        return waived

    def _review_objection_specs(
        self,
        *,
        agent: str,
        data: dict[str, Any],
        default_veto_type: str | None,
    ) -> list[dict[str, Any]]:
        reasons = _safe_list(data.get("reasons"))
        must_change = _safe_list(data.get("must_change"))
        must_preserve = _safe_list(data.get("must_preserve"))
        raw_objections = data.get("objections", [])
        specs: list[dict[str, Any]] = []
        if isinstance(raw_objections, list):
            for item in raw_objections:
                if not isinstance(item, dict):
                    continue
                statement = str(
                    item.get("statement", item.get("claim_text", "")) or item.get("claim_text", "")
                ).strip()
                claim_text = str(item.get("claim_text", statement) or statement).strip()
                required_change = str(item.get("required_change", statement) or statement).strip()
                closure_test = str(
                    item.get(
                        "closure_test", item.get("discharge_test", required_change or statement)
                    )
                    or item.get("discharge_test", required_change or statement)
                    or (required_change or statement)
                ).strip()
                if not statement:
                    continue
                specs.append(
                    {
                        "agent": agent,
                        "issue_type": _issue_type(
                            item.get("issue_type"), agent=agent, default=default_veto_type
                        ),
                        "severity": _severity(item.get("severity"), default="REPAIRABLE"),
                        "claim_text": claim_text,
                        "statement": statement,
                        "evidence": _safe_list(item.get("evidence")),
                        "must_preserve": _safe_list(item.get("must_preserve")),
                        "required_change": required_change,
                        "closure_test": closure_test,
                        "discharge_test": str(
                            item.get("discharge_test", closure_test) or closure_test
                        ),
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
                statement = (
                    reasons[index] if index < len(reasons) else reasons[0] if reasons else change
                )
                specs.append(
                    {
                        "agent": agent,
                        "issue_type": _issue_type(None, agent=agent, default=default_veto_type),
                        "severity": default_severity,
                        "claim_text": statement,
                        "statement": statement,
                        "evidence": reasons[:1],
                        "must_preserve": must_preserve,
                        "required_change": change,
                        "closure_test": change,
                        "discharge_test": change,
                    }
                )
            return specs

        if reasons:
            reason = reasons[0]
            specs.append(
                {
                    "agent": agent,
                    "issue_type": _issue_type(None, agent=agent, default=default_veto_type),
                    "severity": default_severity,
                    "claim_text": reason,
                    "statement": reason,
                    "evidence": reasons[:1],
                    "must_preserve": must_preserve,
                    "required_change": reason,
                    "closure_test": reason,
                    "discharge_test": reason,
                }
            )
        elif decision != "ASSENT":
            fallback = f"{agent} raised an unresolved {str(default_veto_type or 'council').lower()} objection."
            specs.append(
                {
                    "agent": agent,
                    "issue_type": _issue_type(None, agent=agent, default=default_veto_type),
                    "severity": default_severity,
                    "claim_text": fallback,
                    "statement": fallback,
                    "evidence": [],
                    "must_preserve": must_preserve,
                    "required_change": fallback,
                    "closure_test": fallback,
                    "discharge_test": fallback,
                }
            )
        return specs

    def _apollo_objection_specs(
        self, audit: ApolloAudit, raw_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raw_objections = raw_data.get("objections", [])
        specs: list[dict[str, Any]] = []
        if isinstance(raw_objections, list):
            for item in raw_objections:
                if not isinstance(item, dict):
                    continue
                statement = str(
                    item.get("statement", item.get("claim_text", "")) or item.get("claim_text", "")
                ).strip()
                claim_text = str(item.get("claim_text", statement) or statement).strip()
                required_change = str(item.get("required_change", statement) or statement).strip()
                closure_test = str(
                    item.get(
                        "closure_test", item.get("discharge_test", required_change or statement)
                    )
                    or item.get("discharge_test", required_change or statement)
                    or (required_change or statement)
                ).strip()
                if not statement:
                    continue
                specs.append(
                    {
                        "agent": "apollo",
                        "issue_type": _issue_type(
                            item.get("issue_type"), agent="apollo", default="TRUTH"
                        ),
                        "severity": _severity(item.get("severity"), default="REPAIRABLE"),
                        "claim_text": claim_text,
                        "statement": statement,
                        "evidence": _safe_list(item.get("evidence")),
                        "must_preserve": _safe_list(item.get("must_preserve")),
                        "required_change": required_change,
                        "closure_test": closure_test,
                        "discharge_test": str(
                            item.get("discharge_test", closure_test) or closure_test
                        ),
                    }
                )
        if specs:
            return specs

        for flaw in audit.fatal_flaws:
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "TRUTH",
                    "severity": "FATAL",
                    "claim_text": flaw,
                    "statement": flaw,
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else flaw,
                    "closure_test": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else f"Apollo no longer detects: {flaw}",
                    "discharge_test": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else f"Apollo no longer detects: {flaw}",
                }
            )
        for signal in audit.decorative_signals:
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "NOVELTY",
                    "severity": "FATAL",
                    "claim_text": signal,
                    "statement": signal,
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": "Replace decorative or incoherent mechanism with an explicit causal mechanism.",
                    "closure_test": "Apollo confirms the mechanism is causal, non-decorative, and structurally coherent.",
                    "discharge_test": "Apollo confirms the mechanism is causal, non-decorative, and structurally coherent.",
                }
            )
        for weakness in audit.structural_weaknesses:
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "TRUTH",
                    "severity": "REPAIRABLE",
                    "claim_text": weakness,
                    "statement": weakness,
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else weakness,
                    "closure_test": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else weakness,
                    "discharge_test": audit.proof_obligations[0]
                    if audit.proof_obligations
                    else weakness,
                }
            )
        seen_repairs = {item["required_change"] for item in specs}
        for obligation in audit.proof_obligations:
            if obligation in seen_repairs:
                continue
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "TRUTH",
                    "severity": "REPAIRABLE",
                    "claim_text": obligation,
                    "statement": f"Proof obligation remains open: {obligation}",
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": obligation,
                    "closure_test": obligation,
                    "discharge_test": obligation,
                }
            )
        if not specs and audit.verdict == "INVALID":
            basis = (
                audit.reasons[0] if audit.reasons else "Apollo found a fatal truth contradiction."
            )
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "TRUTH",
                    "severity": "FATAL",
                    "claim_text": basis,
                    "statement": basis,
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": basis,
                    "closure_test": basis,
                    "discharge_test": basis,
                }
            )
        elif not specs and audit.verdict == "PROVISIONAL":
            basis = (
                audit.reasons[0] if audit.reasons else "Apollo requires additional causal proof."
            )
            specs.append(
                {
                    "agent": "apollo",
                    "issue_type": "TRUTH",
                    "severity": "REPAIRABLE",
                    "claim_text": basis,
                    "statement": basis,
                    "evidence": audit.reasons[:2],
                    "must_preserve": [],
                    "required_change": basis,
                    "closure_test": basis,
                    "discharge_test": basis,
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
        ballot_kind: str,
    ) -> PantheonVote:
        must_change = _dedupe(
            [objection.required_change for objection in registered_objections]
            + _safe_list(data.get("must_change"))
        )
        reasons = _dedupe(
            [
                *(_safe_list(data.get("reasons"))),
                *[objection.statement for objection in registered_objections],
            ]
        )
        must_preserve = _dedupe(
            [
                *(_safe_list(data.get("must_preserve"))),
                *[item for objection in registered_objections for item in objection.must_preserve],
            ]
        )
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
        veto_type = (
            default_veto_type
            if strongest == "FATAL" and default_veto_type is not None
            else (str(data.get("veto_type")) if data.get("veto_type") is not None else None)
        )
        return PantheonVote(
            agent=agent,
            decision=decision,
            veto_type=veto_type,
            reasons=reasons,
            must_change=must_change,
            must_preserve=must_preserve,
            objection_ids=[objection.objection_id for objection in registered_objections],
            issue_types=_dedupe(objection.issue_type for objection in registered_objections),
            ballot_kind=ballot_kind,
            confidence=_safe_float(data.get("confidence")),
        )

    @staticmethod
    def _disagreement_rate(
        votes: Sequence[PantheonVote], open_objections: Sequence[PantheonObjection]
    ) -> float:
        if not votes:
            return 0.0
        decisions = {vote.decision for vote in votes}
        issue_types = {objection.issue_type for objection in open_objections}
        score = 0.0
        if len(decisions) > 1:
            score += min(0.6, 0.3 * (len(decisions) - 1))
        if issue_types:
            score += min(0.3, 0.1 * len(issue_types))
        if any(objection.severity == "FATAL" for objection in open_objections):
            score += 0.2
        return min(1.0, score)

    @staticmethod
    def _screening_margin(state: PantheonState, candidate_id: str) -> float:
        ranked = sorted(
            (screening for screening in state.screenings if screening.survived),
            key=lambda screening: screening.priority_score,
            reverse=True,
        )
        if not ranked:
            return 0.0
        if len(ranked) == 1:
            return ranked[0].priority_score
        for index, screening in enumerate(ranked):
            if screening.candidate_id != candidate_id:
                continue
            competitor = ranked[index + 1] if index + 1 < len(ranked) else ranked[0]
            if competitor.candidate_id == candidate_id:
                return screening.priority_score
            return screening.priority_score - competitor.priority_score
        return 0.0

    @staticmethod
    def _novelty_drift(original: Translation, revised: Translation) -> float:
        left = set(
            _keyword_tokens(
                original.key_insight, original.future_option_preservation, original.subtraction_test
            )
        )
        right = set(
            _keyword_tokens(
                revised.key_insight, revised.future_option_preservation, revised.subtraction_test
            )
        )
        if not left and not right:
            return 0.0
        overlap = len(left & right) / max(1, len(left | right))
        return max(0.0, 1.0 - overlap)

    @staticmethod
    def _repair_issue_clusters(
        open_objections: Sequence[PantheonObjection],
    ) -> list[tuple[str, list[PantheonObjection]]]:
        clusters: dict[str, list[PantheonObjection]] = {}
        for objection in open_objections:
            cluster_key = objection.issue_type
            clusters.setdefault(cluster_key, []).append(objection)
        ranked_clusters = sorted(
            clusters.items(),
            key=lambda item: (
                max(_SEVERITY_ORDER.get(objection.severity, 0) for objection in item[1]),
                len(item[1]),
                _ISSUE_ORDER.get(item[0], 0),
            ),
            reverse=True,
        )
        return ranked_clusters[:3]

    @staticmethod
    def _repair_branch_score(
        *,
        original: Translation,
        revised: Translation,
        targeted: Sequence[PantheonObjection],
        record: PantheonReforgeRecord,
    ) -> float:
        addressed = set(record.addressed_objection_ids)
        remaining = set(record.remaining_open_objection_ids)
        score = 0.0
        for objection in targeted:
            weight = _severity_weight(objection.severity)
            if objection.objection_id in addressed:
                score += weight * 1.3
            if objection.objection_id not in remaining:
                score += weight
        score -= 2.0 * PantheonCoordinator._novelty_drift(original, revised)
        if not record.novelty_core_preserved.strip():
            score -= 1.0
        if revised.mechanism_is_decorative:
            score -= 2.0
        return score

    def _should_skip_council(
        self,
        *,
        state: PantheonState,
        candidate_id: str,
        votes: Sequence[PantheonVote],
        open_objections: Sequence[PantheonObjection],
    ) -> str | None:
        if open_objections:
            return None
        if not votes or any(vote.decision != "ASSENT" for vote in votes):
            return None
        if min(vote.confidence for vote in votes) < 0.65:
            return None
        margin = self._screening_margin(state, candidate_id)
        if len(state.survivor_candidate_ids) > 1 and margin < 0.25:
            return None
        return "independent_ballots_clear"

    @staticmethod
    def _blocking_truth_issues(
        open_objections: Sequence[PantheonObjection],
    ) -> list[PantheonObjection]:
        return [
            objection
            for objection in open_objections
            if objection.issue_type in {"TRUTH", "NOVELTY"} and objection.severity == "FATAL"
        ]

    @staticmethod
    def _blocking_consensus_issues(
        open_objections: Sequence[PantheonObjection],
    ) -> list[PantheonObjection]:
        return [
            objection
            for objection in open_objections
            if (
                (objection.issue_type in {"TRUTH", "NOVELTY"} and objection.severity != "ADVISORY")
                or (objection.issue_type == "STRUCTURAL" and objection.severity != "ADVISORY")
            )
        ]

    @staticmethod
    def _forward_candidate_score(
        candidate: Translation, open_objections: Sequence[PantheonObjection]
    ) -> float:
        penalty = sum(_severity_weight(objection.severity) for objection in open_objections)
        return float(getattr(candidate, "combined_score", 0.0) or 0.0) - penalty

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
            constraints="\n".join(
                f"- {item}" for item in getattr(structure, "constraints", [])[:12]
            )
            or "- none",
            baseline=getattr(baseline_dossier, "summary", "")
            if baseline_dossier is not None
            else "",
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
            constraints="\n".join(
                f"- {item}" for item in getattr(structure, "constraints", [])[:12]
            )
            or "- none",
            baseline=getattr(baseline_dossier, "summary", "")
            if baseline_dossier is not None
            else "",
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
        constraints = _dedupe(
            [
                *list(getattr(structure, "constraints", []) or []),
                *canon.mandatory_constraints,
            ]
        )
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
        revised.pantheon_canon = canon
        revised.pantheon_hidden_assumptions = list(canon.hidden_assumptions)
        revised.pantheon_success_criteria = list(canon.success_criteria)
        revised.pantheon_anti_goals = list(canon.anti_goals)
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
        current_state = state or PantheonState(
            mode="pantheon", resolution_mode=self._resolution_mode
        )
        current_state.mode = "pantheon"
        current_state.resolution_mode = self._resolution_mode
        current_state.initial_structure = current_state.initial_structure or _structure_snapshot(
            structure
        )

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
        peer_visible: bool,
        changed_claims: Sequence[str],
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        visible_objections = (
            self._candidate_objections(state, candidate_id=candidate_id) if peer_visible else []
        )
        own_open = self._candidate_objections(
            state, candidate_id=candidate_id, agent="athena", status="OPEN"
        )
        data = await self._forge_json(
            self._athena,
            prompts.ATHENA_REVIEW_PROMPT.format(
                canon=_canon_to_text(canon),
                objection_ledger=self._masked_objections_to_text(visible_objections),
                open_objections=self._masked_objections_to_text(own_open),
                must_preserve=json.dumps(
                    self._must_preserve_anchors(translation, visible_objections or own_open),
                    indent=2,
                    ensure_ascii=False,
                ),
                changed_claims=json.dumps(list(changed_claims), indent=2, ensure_ascii=False),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.ATHENA_REVIEW_SYSTEM,
            accounting=accounting,
            agent="athena",
        )
        objection_specs = self._review_objection_specs(
            agent="athena", data=data, default_veto_type="STRUCTURAL"
        )
        objections = self._register_objections(
            state=state,
            candidate_id=candidate_id,
            round_index=round_index,
            stage=stage,
            objection_specs=objection_specs,
        )
        return self._build_vote(
            agent="athena",
            data=data,
            default_veto_type="STRUCTURAL",
            registered_objections=objections,
            ballot_kind=stage,
        )

    async def _hermes_review(
        self,
        *,
        translation: Translation,
        dossier: HermesDossier,
        candidate_id: str,
        round_index: int,
        state: PantheonState,
        stage: str,
        peer_visible: bool,
        changed_claims: Sequence[str],
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        visible_objections = (
            self._candidate_objections(state, candidate_id=candidate_id) if peer_visible else []
        )
        own_open = self._candidate_objections(
            state, candidate_id=candidate_id, agent="hermes", status="OPEN"
        )
        data = await self._forge_json(
            self._hermes,
            prompts.HERMES_REVIEW_PROMPT.format(
                dossier=_dossier_to_text(dossier),
                objection_ledger=self._masked_objections_to_text(visible_objections),
                open_objections=self._masked_objections_to_text(own_open),
                must_preserve=json.dumps(
                    self._must_preserve_anchors(translation, visible_objections or own_open),
                    indent=2,
                    ensure_ascii=False,
                ),
                changed_claims=json.dumps(list(changed_claims), indent=2, ensure_ascii=False),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.HERMES_REVIEW_SYSTEM,
            accounting=accounting,
            agent="hermes",
        )
        objection_specs = self._review_objection_specs(
            agent="hermes", data=data, default_veto_type="REALITY"
        )
        objections = self._register_objections(
            state=state,
            candidate_id=candidate_id,
            round_index=round_index,
            stage=stage,
            objection_specs=objection_specs,
        )
        return self._build_vote(
            agent="hermes",
            data=data,
            default_veto_type="REALITY",
            registered_objections=objections,
            ballot_kind=stage,
        )

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
        peer_visible: bool,
        changed_claims: Sequence[str],
        accounting: PantheonAccounting,
    ) -> tuple[ApolloAudit, PantheonVote]:
        visible_objections = (
            self._candidate_objections(state, candidate_id=candidate_id) if peer_visible else []
        )
        own_open = self._candidate_objections(
            state, candidate_id=candidate_id, agent="apollo", status="OPEN"
        )
        data = await self._forge_json(
            self._apollo,
            prompts.APOLLO_AUDIT_PROMPT.format(
                canon=_canon_to_text(canon),
                dossier=_dossier_to_text(dossier),
                objection_ledger=self._masked_objections_to_text(visible_objections),
                open_objections=self._masked_objections_to_text(own_open),
                must_preserve=json.dumps(
                    self._must_preserve_anchors(translation, visible_objections or own_open),
                    indent=2,
                    ensure_ascii=False,
                ),
                changed_claims=json.dumps(list(changed_claims), indent=2, ensure_ascii=False),
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
            veto_type="TRUTH"
            if any(objection.severity == "FATAL" for objection in objections)
            else None,
            reasons=_dedupe([*audit.reasons, *[objection.statement for objection in objections]]),
            must_change=_dedupe(
                [*audit.proof_obligations, *[objection.required_change for objection in objections]]
            ),
            must_preserve=[],
            objection_ids=[objection.objection_id for objection in objections],
            issue_types=_dedupe(objection.issue_type for objection in objections),
            ballot_kind=stage,
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
            hermes_task = self._hermes_review(
                translation=translation,
                dossier=state.dossier,
                candidate_id=candidate_id,
                round_index=0,
                state=state,
                stage="screening",
                peer_visible=False,
                changed_claims=[],
                accounting=state.accounting,
            )
            apollo_task = self._apollo_audit(
                translation=translation,
                canon=state.canon,
                dossier=state.dossier,
                candidate_id=candidate_id,
                round_index=0,
                state=state,
                stage="screening",
                peer_visible=False,
                changed_claims=[],
                accounting=state.accounting,
            )
            hermes_vote, (apollo_audit, apollo_vote) = await asyncio.gather(
                hermes_task, apollo_task
            )
            audits.append(apollo_audit)

            candidate_objections = self._candidate_objections(
                state, candidate_id=candidate_id, status="OPEN"
            )
            fatal_objections = [
                objection for objection in candidate_objections if objection.severity == "FATAL"
            ]
            prune_reasons = [objection.statement for objection in fatal_objections]
            if translation.mechanism_is_decorative and not prune_reasons:
                prune_reasons.append("Decorative mechanism collapsed before council.")

            reality_bonus = (
                hermes_vote.confidence
                if hermes_vote.decision == "ASSENT"
                else -0.25
                if hermes_vote.decision == "CONCERN"
                else -(0.5 + hermes_vote.confidence)
            )
            audit_bonus = (
                apollo_vote.confidence
                if apollo_vote.decision == "ASSENT"
                else -0.25
                if apollo_vote.decision == "CONCERN"
                else -1.0
            )
            priority = (
                float(getattr(translation, "combined_score", 0.0) or 0.0)
                + reality_bonus
                + audit_bonus
            )

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

        ranked.sort(
            key=lambda item: (item[0], getattr(item[2], "combined_score", 0.0)), reverse=True
        )
        survivors: list[Translation] = []
        for _, _, translation, screening in ranked[: self._max_survivors_to_council]:
            screening.survived = True
            survivors.append(translation)

        state.screenings = screenings
        state.survivor_candidate_ids = [
            screening.candidate_id for screening in screenings if screening.survived
        ]
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

    async def _reforge_branch(
        self,
        *,
        translator: Any,
        problem: str,
        structure: Any,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        targeted_objections: Sequence[PantheonObjection],
        masked_objections: Sequence[PantheonObjection],
        accounting: PantheonAccounting,
        branch_label: str,
        state: PantheonState,
    ) -> tuple[Translation | None, PantheonReforgeRecord | None]:
        targeted_payload = [objection.to_dict() for objection in targeted_objections]
        targeted_ids = [objection.objection_id for objection in targeted_objections]
        masked_ids = [objection.objection_id for objection in masked_objections]
        must_preserve = self._must_preserve_anchors(
            translation, [*targeted_objections, *masked_objections]
        )
        try:
            t_start = time.monotonic()
            revised = await translator.reforge(
                prompt=prompts.HEPHAESTUS_REFORGE_PROMPT.format(
                    problem=problem,
                    structure=getattr(structure, "structure", ""),
                    canon=_canon_to_text(canon),
                    dossier=_dossier_to_text(dossier),
                    candidate=_translation_to_text(translation),
                    branch_label=branch_label,
                    targeted_objections=json.dumps(targeted_payload, indent=2, ensure_ascii=False),
                    masked_objections=self._masked_objections_to_text(masked_objections),
                    must_preserve=json.dumps(must_preserve, indent=2, ensure_ascii=False),
                ),
                structure=structure,
                source_translation=translation,
                system=prompts.HEPHAESTUS_REFORGE_SYSTEM,
            )
            if (
                getattr(getattr(revised, "trace", None), "pantheon_owned", False) is False
                and getattr(revised, "trace", None) is not None
            ):
                revised.trace.pantheon_owned = True
            self._record_accounting(
                accounting,
                agent="hephaestus",
                trace=getattr(revised, "trace", None) or type("Trace", (), {})(),
                duration_seconds=time.monotonic() - t_start,
            )
        except Exception as exc:
            logger.warning("Pantheon reforge failed: %s", exc)
            return None, None

        if not revised.architecture or revised.architecture == "Architecture generation failed":
            return None, None

        metadata = getattr(revised, "pantheon_reforge_metadata", {}) or {}

        # Canonicalize model-returned objection IDs against the actual ledger.
        # The model may echo alias IDs that don't match canonical objection_id values.
        raw_addressed = list(metadata.get("addressed_objection_ids", []) or [])
        raw_remaining = list(metadata.get("remaining_open_objection_ids", []) or [])

        canonical_ids = {obj.objection_id for obj in state.objection_ledger}
        all_targeted_set = set(targeted_ids)

        def _canonicalize_ids(raw_ids: list[str]) -> list[str]:
            """Map model-returned IDs to canonical objection_id values. Unrecognized IDs are dropped."""
            result: list[str] = []
            for raw_id in raw_ids:
                raw_id = str(raw_id).strip()
                if not raw_id:
                    continue
                # Exact match
                if raw_id in canonical_ids:
                    result.append(raw_id)
                    continue
                # Fuzzy match against targeted objections
                best_match: str | None = None
                best_score = 0.0
                for objection in state.objection_ledger:
                    if objection.objection_id not in all_targeted_set:
                        continue
                    score = _similarity_score(
                        objection,
                        raw_id,
                        raw_id,
                        raw_id,
                    )
                    if score > best_score:
                        best_match = objection.objection_id
                        best_score = score
                if best_match is not None and best_score >= 0.7:
                    result.append(best_match)
                elif len(all_targeted_set) == 1:
                    # Some model/tooling paths return ephemeral branch-local IDs
                    # instead of ledger-canonical objection IDs. When a repair
                    # branch only targeted a single objection, preserve the
                    # discharge signal by binding that alias to the sole target.
                    result.append(next(iter(all_targeted_set)))
                else:
                    logger.debug(
                        "Reforge returned unrecognized objection ID %r (no canonical match >= 0.7)",
                        raw_id,
                    )
            return result

        addressed_ids = _canonicalize_ids(raw_addressed)
        remaining_ids = _canonicalize_ids(raw_remaining)

        reforge_record = PantheonReforgeRecord(
            branch_label=branch_label,
            targeted_objection_ids=targeted_ids,
            targeted_issue_types=_dedupe(objection.issue_type for objection in targeted_objections),
            addressed_objection_ids=addressed_ids,
            remaining_open_objection_ids=remaining_ids,
            masked_open_objection_ids=masked_ids,
            changes_made=list(
                metadata.get("changes_made", []) or self._reforge_changes(translation, revised)
            ),
            novelty_core_preserved=str(
                metadata.get(
                    "novelty_core_preserved", revised.key_insight or translation.key_insight
                )
                or ""
            ),
        )
        reforge_record.branch_score = self._repair_branch_score(
            original=translation,
            revised=revised,
            targeted=targeted_objections,
            record=reforge_record,
        )
        return revised, reforge_record

    async def _adjudicate_repair_pair(
        self,
        *,
        branch_a: Translation,
        record_a: PantheonReforgeRecord,
        branch_b: Translation,
        record_b: PantheonReforgeRecord,
        accounting: PantheonAccounting,
    ) -> tuple[str, float]:
        issue_ids = _dedupe(
            [
                *record_a.targeted_objection_ids,
                *record_b.targeted_objection_ids,
                *record_a.remaining_open_objection_ids,
                *record_b.remaining_open_objection_ids,
            ]
        )
        must_preserve = _dedupe(
            [
                branch_a.key_insight,
                branch_a.future_option_preservation,
                branch_b.key_insight,
                branch_b.future_option_preservation,
            ]
        )
        data = await self._forge_json(
            self._apollo,
            prompts.APOLLO_BRANCH_AUDIT_PROMPT.format(
                issue_ids=json.dumps(issue_ids, indent=2, ensure_ascii=False),
                must_preserve=json.dumps(must_preserve, indent=2, ensure_ascii=False),
                branch_a=_translation_to_text(branch_a),
                branch_b=_translation_to_text(branch_b),
            ),
            system=prompts.APOLLO_BRANCH_AUDIT_SYSTEM,
            accounting=accounting,
            agent="apollo",
        )
        winner = str(data.get("winner", "TIE") or "TIE").upper()
        if winner not in {"A", "B", "TIE"}:
            winner = "TIE"
        return winner, _safe_float(data.get("margin"))

    async def _hephaestus_reforge(
        self,
        *,
        state: PantheonState,
        translator: Any,
        problem: str,
        structure: Any,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        open_objections: Sequence[PantheonObjection],
        accounting: PantheonAccounting,
    ) -> tuple[Translation | None, PantheonVote, PantheonReforgeRecord | None, int]:
        objection_ids = [objection.objection_id for objection in open_objections]
        must_preserve = self._must_preserve_anchors(translation, open_objections)
        clusters = self._repair_issue_clusters(open_objections)
        if not clusters:
            vote = PantheonVote(
                agent="hephaestus",
                decision="VETO",
                veto_type="NOVELTY",
                reasons=["Reforge was requested without any open issues to repair."],
                must_change=[],
                must_preserve=must_preserve,
                objection_ids=[],
                issue_types=[],
                ballot_kind="repair",
                confidence=0.0,
            )
            return None, vote, None, 0

        attempts: list[tuple[Translation, PantheonReforgeRecord]] = []
        for branch_index, (cluster_key, targeted) in enumerate(clusters, start=1):
            masked = [
                objection
                for objection in open_objections
                if objection.objection_id not in {item.objection_id for item in targeted}
            ]
            revised, reforge_record = await self._reforge_branch(
                translator=translator,
                problem=problem,
                structure=structure,
                translation=translation,
                canon=canon,
                dossier=dossier,
                targeted_objections=targeted,
                masked_objections=masked,
                accounting=accounting,
                branch_label=f"{cluster_key.lower()}-repair-{branch_index}",
                state=state,
            )
            if revised is None or reforge_record is None:
                continue
            attempts.append((revised, reforge_record))

        state.branches_spawned_for_repair += len(clusters)
        if not attempts:
            vote = PantheonVote(
                agent="hephaestus",
                decision="VETO",
                veto_type="NOVELTY",
                reasons=["Reforge failed to produce a valid architecture JSON output."],
                must_change=[objection.required_change for objection in open_objections],
                must_preserve=must_preserve,
                objection_ids=objection_ids,
                issue_types=_dedupe(objection.issue_type for objection in open_objections),
                ballot_kind="repair",
                confidence=0.0,
            )
            return None, vote, None, len(clusters)

        attempts.sort(key=lambda item: item[1].branch_score, reverse=True)
        selected_revised, selected_record = attempts[0]
        if len(attempts) > 1:
            runner_revised, runner_record = attempts[1]
            margin = selected_record.branch_score - runner_record.branch_score
            if margin < 0.35:
                try:
                    winner, adjudicator_margin = await self._adjudicate_repair_pair(
                        branch_a=selected_revised,
                        record_a=selected_record,
                        branch_b=runner_revised,
                        record_b=runner_record,
                        accounting=accounting,
                    )
                    state.adjudicator_margin = adjudicator_margin
                    if winner == "B":
                        selected_revised, selected_record = runner_revised, runner_record
                except Exception as exc:
                    logger.warning("Pantheon branch adjudication failed: %s", exc)
            else:
                state.adjudicator_margin = margin

        state.novelty_drift = max(
            state.novelty_drift, self._novelty_drift(translation, selected_revised)
        )
        vote = PantheonVote(
            agent="hephaestus",
            decision="ASSENT",
            veto_type=None,
            reasons=[
                "Reforged candidate against targeted issue clusters while preserving the novelty core."
            ],
            must_change=[],
            must_preserve=must_preserve,
            objection_ids=selected_record.addressed_objection_ids,
            issue_types=selected_record.targeted_issue_types,
            ballot_kind="repair",
            confidence=0.78,
        )
        return selected_revised, vote, selected_record, len(clusters)

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
        blocking_truth = self._blocking_truth_issues(open_objections)
        if blocking_truth:
            return None

        blocking_consensus = self._blocking_consensus_issues(open_objections)
        reality_repairable = [
            objection
            for objection in open_objections
            if objection.issue_type == "REALITY" and objection.severity != "ADVISORY"
        ]

        all_assent = all(vote.decision == "ASSENT" for vote in votes)
        no_veto = all(vote.decision != "VETO" for vote in votes)
        assent_count = sum(1 for vote in votes if vote.decision == "ASSENT")

        if all_assent and not open_objections:
            return "UNANIMOUS_CONSENSUS"

        allow_qualified = self._resolution_mode == "TASK_SENSITIVE" or not self._require_unanimity
        if (
            allow_qualified
            and no_veto
            and not blocking_consensus
            and not reality_repairable
            and assent_count >= 2
        ):
            return "QUALIFIED_CONSENSUS"

        allow_salvage = self._resolution_mode == "TASK_SENSITIVE" or not self._allow_fail_closed
        if (
            allow_salvage
            and no_veto
            and not blocking_consensus
            and round_index >= self._max_rounds
            and round_index >= 1
        ):
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
        phase: str,
        votes: list[PantheonVote],
        resolved_ids: list[str],
        open_objections: list[PantheonObjection],
        outcome_tier: str,
        disagreement_rate: float,
        branch_candidates_considered: int = 0,
        reforge_record: PantheonReforgeRecord | None = None,
    ) -> tuple[list[Translation], PantheonState]:
        waiver_ids: list[str] = []
        if outcome_tier == "QUALIFIED_CONSENSUS":
            waiver_ids = [
                objection.objection_id
                for objection in open_objections
                if objection.severity == "ADVISORY"
            ]
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
            issue_types=_dedupe(objection.issue_type for objection in waived),
            ballot_kind=phase,
            confidence=0.85,
        )
        votes.append(hephaestus_vote)
        state.rounds.append(
            PantheonRound(
                round_index=round_index,
                candidate_id=candidate_id,
                phase=phase,
                votes=votes,
                consensus=True,
                outcome_tier=outcome_tier,
                disagreement_rate=disagreement_rate,
                branch_candidates_considered=branch_candidates_considered,
                unresolved_vetoes=[],
                open_objection_ids=[objection.objection_id for objection in open_objections],
                resolved_objection_ids=resolved_ids,
                waived_objection_ids=[objection.objection_id for objection in waived],
                caveats=caveats,
                revision_summary=f"Council converged via {outcome_tier.lower()} after objection discharge.",
                reforge=reforge_record,
            )
        )
        state.consensus_achieved = True
        state.winning_candidate_id = candidate_id
        state.forwarded_candidate_ids = []
        state.resolution = self._resolution_name(outcome_tier)
        state.outcome_tier = outcome_tier
        if state.final_verdict in {"", "UNKNOWN"}:
            state.final_verdict = "PENDING_VERIFICATION"
        state.caveats = caveats
        state.failure_reason = None
        state.unresolved_vetoes = []
        state.consensus_without_verification = True

        # Strict Invariants Block
        for objection in state.objection_ledger:
            if objection.status == "OPEN":
                objection.resolved_round = None
                objection.waived_round = None
            elif objection.status == "RESOLVED":
                objection.waived_round = None

        fatals_open = any(
            obj.status == "OPEN" and obj.severity == "FATAL" for obj in state.objection_ledger
        )
        if fatals_open and state.consensus_achieved:
            state.consensus_achieved = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            state.resolution = "fail_closed_rejection"
            state.final_verdict = "NO_OUTPUT"
            state.failure_reason = (
                "Invariant violation: Consensus claimed while FATAL objections remain OPEN."
            )
            state.forwarded_candidate_ids = []
            return [], state

        candidate.pantheon_state = state.to_dict()
        return [candidate], state

    def _forward_with_open_issues(
        self,
        *,
        state: PantheonState,
        candidates: Sequence[tuple[str, Translation, list[PantheonObjection]]],
    ) -> tuple[list[Translation], PantheonState]:
        ranked = sorted(
            candidates,
            key=lambda item: self._forward_candidate_score(item[1], item[2]),
            reverse=True,
        )[:2]
        forwarded = [candidate for _, candidate, _ in ranked]
        state.consensus_achieved = False
        state.winning_candidate_id = ranked[0][0] if ranked else None
        state.forwarded_candidate_ids = [candidate_id for candidate_id, _, _ in ranked]
        state.resolution = "forward_with_open_issues"
        state.outcome_tier = "FORWARDED_WITH_OPEN_ISSUES"
        state.failure_reason = "Pantheon forwarded unresolved non-fatal issues to verification instead of failing closed."
        state.final_verdict = "PENDING_VERIFICATION"
        state.caveats = _dedupe(
            self._caveat_text(objection) for _, _, objections in ranked for objection in objections
        )
        state.unresolved_vetoes = _dedupe(
            _objection_summary(objection) for _, _, objections in ranked for objection in objections
        )
        # Strict Invariants Block
        for objection in state.objection_ledger:
            if objection.status == "OPEN":
                objection.resolved_round = None
                objection.waived_round = None
            elif objection.status == "RESOLVED":
                objection.waived_round = None

        fatals_open = any(
            obj.status == "OPEN" and obj.severity == "FATAL" for obj in state.objection_ledger
        )
        if (
            fatals_open
            and state.final_verdict != "NO_OUTPUT"
            and state.outcome_tier != "FAIL_CLOSED_REJECTION"
        ):
            # Cannot progress past FATAL objections
            state.consensus_achieved = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            state.resolution = "fail_closed_rejection"
            state.final_verdict = "NO_OUTPUT"
            state.failure_reason = (
                "Invariant violation: Forwarded to verification with FATAL objections open."
            )
            state.forwarded_candidate_ids = []
            return [], state

        for candidate in forwarded:
            candidate.pantheon_state = state.to_dict()
        return forwarded, state

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
        current_state = (
            state
            or previous_state
            or PantheonState(mode="pantheon", resolution_mode=self._resolution_mode)
        )
        current_state.mode = "pantheon"
        current_state.resolution_mode = self._resolution_mode
        current_state.debate_invoked = False
        current_state.debate_skip_reason = None
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
        if canon is None:
            raise RuntimeError(
                "PantheonState.canon is None — prepare_pipeline must run before deliberate()"
            )
        if dossier is None:
            raise RuntimeError(
                "PantheonState.dossier is None — prepare_pipeline must run before deliberate()"
            )

        survivors = list(translations[: self._max_survivors_to_council])
        if not survivors:
            current_state.final_verdict = "NO_OUTPUT"
            current_state.resolution = "no_candidates"
            current_state.outcome_tier = "FAIL_CLOSED_REJECTION"
            current_state.failure_reason = (
                "No translation candidates entered Pantheon deliberation."
            )
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
        forward_candidates: list[tuple[str, Translation, list[PantheonObjection]]] = []

        for candidate_id, original in zip(candidate_ids, survivors, strict=True):
            candidate = original
            incoming_reforge: PantheonReforgeRecord | None = None
            for round_index in range(1, self._max_rounds + 1):
                phase = "independent_ballot" if round_index == 1 else "council"
                peer_visible = round_index > 1
                changed_claims = self._changed_claims(incoming_reforge)
                athena_task = self._athena_review(
                    translation=candidate,
                    canon=canon,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage=phase,
                    peer_visible=peer_visible,
                    changed_claims=changed_claims,
                    accounting=current_state.accounting,
                )
                hermes_task = self._hermes_review(
                    translation=candidate,
                    dossier=dossier,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage=phase,
                    peer_visible=peer_visible,
                    changed_claims=changed_claims,
                    accounting=current_state.accounting,
                )
                apollo_task = self._apollo_audit(
                    translation=candidate,
                    canon=canon,
                    dossier=dossier,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    state=current_state,
                    stage=phase,
                    peer_visible=peer_visible,
                    changed_claims=changed_claims,
                    accounting=current_state.accounting,
                )
                athena_vote, hermes_vote, (apollo_audit, apollo_vote) = await asyncio.gather(
                    athena_task, hermes_task, apollo_task
                )
                all_audits.append(apollo_audit)
                votes = [athena_vote, hermes_vote, apollo_vote]

                seen_ids = set()
                for vote in votes:
                    seen_ids.update(vote.objection_ids)
                addressed_ids_set = (
                    set(incoming_reforge.addressed_objection_ids)
                    if incoming_reforge is not None
                    else set()
                )
                resolved_ids = self._resolve_missing_open_objections(
                    state=current_state,
                    candidate_id=candidate_id,
                    round_index=round_index,
                    seen_ids=seen_ids,
                    stage="council",
                    explicitly_addressed_ids=addressed_ids_set,
                )
                open_objections = self._candidate_objections(
                    current_state,
                    candidate_id=candidate_id,
                    status="OPEN",
                )
                disagreement_rate = self._disagreement_rate(votes, open_objections)
                if round_index == 1:
                    current_state.independent_disagreement_rate = disagreement_rate
                unresolved_round = [_objection_summary(objection) for objection in open_objections]
                outcome_tier = self._determine_outcome_tier(
                    votes=votes,
                    open_objections=open_objections,
                    round_index=round_index,
                )
                if round_index == 1 and outcome_tier is not None:
                    current_state.debate_skip_reason = (
                        self._should_skip_council(
                            state=current_state,
                            candidate_id=candidate_id,
                            votes=votes,
                            open_objections=open_objections,
                        )
                        or "independent_ballots_resolved_without_council"
                    )

                if outcome_tier is not None:
                    current_state.audits = all_audits
                    return self._finalize_success(
                        state=current_state,
                        candidate_id=candidate_id,
                        candidate=candidate,
                        round_index=round_index,
                        phase=phase,
                        votes=votes,
                        resolved_ids=resolved_ids,
                        open_objections=open_objections,
                        outcome_tier=outcome_tier,
                        disagreement_rate=disagreement_rate,
                        branch_candidates_considered=1 if incoming_reforge is not None else 0,
                        reforge_record=incoming_reforge,
                    )

                if round_index == 1:
                    current_state.debate_invoked = True

                if round_index >= self._max_rounds:
                    current_state.rounds.append(
                        PantheonRound(
                            round_index=round_index,
                            candidate_id=candidate_id,
                            phase=phase,
                            votes=votes,
                            consensus=False,
                            outcome_tier="PENDING",
                            disagreement_rate=disagreement_rate,
                            branch_candidates_considered=1 if incoming_reforge is not None else 0,
                            unresolved_vetoes=unresolved_round,
                            open_objection_ids=[
                                objection.objection_id for objection in open_objections
                            ],
                            resolved_objection_ids=resolved_ids,
                            waived_objection_ids=[],
                            caveats=[],
                            revision_summary="Council review exhausted its budget with unresolved issues still open.",
                            reforge=incoming_reforge,
                        )
                    )
                    current_state.unresolved_vetoes = unresolved_round
                    if not self._blocking_truth_issues(open_objections):
                        forward_candidates.append((candidate_id, candidate, open_objections))
                    break

                (
                    revised,
                    hephaestus_vote,
                    reforge_record,
                    branch_count,
                ) = await self._hephaestus_reforge(
                    state=current_state,
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
                        phase=phase,
                        votes=votes,
                        consensus=False,
                        outcome_tier="PENDING",
                        disagreement_rate=disagreement_rate,
                        branch_candidates_considered=branch_count,
                        unresolved_vetoes=unresolved_round,
                        open_objection_ids=[
                            objection.objection_id for objection in open_objections
                        ],
                        resolved_objection_ids=resolved_ids,
                        waived_objection_ids=[],
                        caveats=[],
                        revision_summary=(
                            "Hephaestus applied targeted repair branches against masked issue clusters."
                            if revised is not None
                            else "Reforge failed; novelty-preserving revision unavailable."
                        ),
                        reforge=reforge_record,
                    )
                )
                current_state.unresolved_vetoes = unresolved_round
                if revised is None:
                    if not self._blocking_truth_issues(open_objections):
                        forward_candidates.append((candidate_id, candidate, open_objections))
                    break
                candidate = revised
                incoming_reforge = reforge_record

        current_state.audits = all_audits
        if forward_candidates:
            return self._forward_with_open_issues(
                state=current_state,
                candidates=forward_candidates,
            )
        open_fatal = [
            objection
            for objection in current_state.objection_ledger
            if objection.status == "OPEN"
            and objection.severity == "FATAL"
            and objection.issue_type in {"TRUTH", "NOVELTY"}
        ]
        current_state.unresolved_vetoes = [
            _objection_summary(objection) for objection in open_fatal
        ]
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

    def finalize_with_verified(
        self, state: PantheonState, verified_inventions: Sequence[Any]
    ) -> PantheonState:
        if not verified_inventions:
            state.final_verdict = "NO_OUTPUT"
            state.consensus_achieved = False
            state.consensus_without_verification = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            state.verifier_overrode_council = bool(state.winning_candidate_id)
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
                    issue_type="TRUTH",
                    severity="FATAL",
                    claim_text="Final verification produced no surviving invention.",
                    statement="Final verification produced no surviving invention.",
                    required_change="Resolve the verifier failure or return no output.",
                    closure_test="A verifier-approved invention survives the final verification pass.",
                    discharge_test="A verifier-approved invention survives the final verification pass.",
                    evidence=[],
                    must_preserve=[],
                    opened_by="verifier",
                    status="OPEN",
                    opened_round=max((round_.round_index for round_ in state.rounds), default=0)
                    + 1,
                    last_seen_round=max((round_.round_index for round_ in state.rounds), default=0)
                    + 1,
                    last_updated_round=max(
                        (round_.round_index for round_ in state.rounds), default=0
                    )
                    + 1,
                    opened_stage="verification",
                    last_stage="verification",
                )
                state.objection_ledger.append(verifier_objection)
                state.unresolved_vetoes = _dedupe(
                    [*state.unresolved_vetoes, _objection_summary(verifier_objection)]
                )
            if state.winning_candidate_id:
                state.resolution = "verifier_rejected_consensus"
                state.failure_reason = "Pantheon consensus was reached, but verification produced no surviving invention."
            return state

        top = verified_inventions[0]
        state.final_verdict = str(getattr(top, "verdict", "UNKNOWN"))
        if getattr(top, "verdict", "UNKNOWN") == "INVALID":
            state.consensus_achieved = False
            state.consensus_without_verification = False
            state.outcome_tier = "FAIL_CLOSED_REJECTION"
            state.resolution = "verifier_rejected_consensus"
            state.failure_reason = (
                "Pantheon consensus selected an invention that verification later invalidated."
            )
            state.verifier_overrode_council = True
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
                issue_type="TRUTH",
                severity="FATAL",
                claim_text="Final verification invalidated the Pantheon-selected invention.",
                statement="Final verification invalidated the Pantheon-selected invention.",
                required_change="Resolve the verifier invalidation before returning the invention.",
                closure_test="The selected invention passes final verification with a non-invalid verdict.",
                discharge_test="The selected invention passes final verification with a non-invalid verdict.",
                evidence=[],
                must_preserve=[],
                opened_by="verifier",
                status="OPEN",
                opened_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                last_seen_round=max((round_.round_index for round_ in state.rounds), default=0) + 1,
                last_updated_round=max((round_.round_index for round_ in state.rounds), default=0)
                + 1,
                opened_stage="verification",
                last_stage="verification",
            )
            state.objection_ledger.append(verifier_objection)
            state.unresolved_vetoes = _dedupe(
                [*state.unresolved_vetoes, _objection_summary(verifier_objection)]
            )
        return state


__all__ = ["PantheonCoordinator", "PantheonError"]
