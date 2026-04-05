"""Typed deliberation graph and runtime orchestration state."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

_UTC = UTC


def _now() -> str:
    return datetime.now(_UTC).isoformat()


def _slug(value: str, *, limit: int = 24) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    if not normalized:
        return "node"
    return normalized[:limit].strip("-") or "node"


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part) for part in parts if part is not None and str(part) != "")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10] if raw else uuid4().hex[:10]
    return f"{prefix}-{_slug(raw or prefix)}-{digest}"


@dataclass
class RuntimeAccountingSnapshot:
    """Aggregated runtime metrics for one stage or route."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    call_count: int = 0

    def record(
        self,
        *,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_seconds: float = 0.0,
        calls: int = 1,
    ) -> None:
        self.cost_usd += float(cost_usd or 0.0)
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.duration_seconds += float(duration_seconds or 0.0)
        self.call_count += int(calls or 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_seconds": self.duration_seconds,
            "call_count": self.call_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RuntimeAccountingSnapshot:
        if not isinstance(data, dict):
            return cls()
        return cls(
            cost_usd=float(data.get("cost_usd", 0.0) or 0.0),
            input_tokens=int(data.get("input_tokens", 0) or 0),
            output_tokens=int(data.get("output_tokens", 0) or 0),
            duration_seconds=float(data.get("duration_seconds", 0.0) or 0.0),
            call_count=int(data.get("call_count", 0) or 0),
        )


@dataclass
class RuntimeAccounting:
    """Run-level accounting split by stage and selected routes."""

    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_seconds: float = 0.0
    stage_totals: dict[str, RuntimeAccountingSnapshot] = field(default_factory=dict)
    route_totals: dict[str, RuntimeAccountingSnapshot] = field(default_factory=dict)
    model_call_counts: dict[str, int] = field(default_factory=dict)

    def record(
        self,
        *,
        stage: str,
        route: str | None = None,
        model: str | None = None,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_seconds: float = 0.0,
        calls: int = 1,
    ) -> None:
        self.total_cost_usd += float(cost_usd or 0.0)
        self.total_input_tokens += int(input_tokens or 0)
        self.total_output_tokens += int(output_tokens or 0)
        self.total_duration_seconds += float(duration_seconds or 0.0)

        stage_key = str(stage or "unknown")
        self.stage_totals.setdefault(stage_key, RuntimeAccountingSnapshot()).record(
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            calls=calls,
        )

        if route:
            route_key = str(route)
            self.route_totals.setdefault(route_key, RuntimeAccountingSnapshot()).record(
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_seconds=duration_seconds,
                calls=calls,
            )

        if model:
            model_key = str(model)
            self.model_call_counts[model_key] = self.model_call_counts.get(model_key, 0) + int(
                calls or 0
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_duration_seconds": self.total_duration_seconds,
            "stage_totals": {
                stage: snapshot.to_dict() for stage, snapshot in self.stage_totals.items()
            },
            "route_totals": {
                route: snapshot.to_dict() for route, snapshot in self.route_totals.items()
            },
            "model_call_counts": dict(self.model_call_counts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RuntimeAccounting:
        if not isinstance(data, dict):
            return cls()
        return cls(
            total_cost_usd=float(data.get("total_cost_usd", 0.0) or 0.0),
            total_input_tokens=int(data.get("total_input_tokens", 0) or 0),
            total_output_tokens=int(data.get("total_output_tokens", 0) or 0),
            total_duration_seconds=float(data.get("total_duration_seconds", 0.0) or 0.0),
            stage_totals={
                str(stage): RuntimeAccountingSnapshot.from_dict(snapshot)
                for stage, snapshot in dict(data.get("stage_totals", {}) or {}).items()
            },
            route_totals={
                str(route): RuntimeAccountingSnapshot.from_dict(snapshot)
                for route, snapshot in dict(data.get("route_totals", {}) or {}).items()
            },
            model_call_counts={
                str(model): int(count or 0)
                for model, count in dict(data.get("model_call_counts", {}) or {}).items()
            },
        )


@dataclass
class RuntimeBudgetPolicy:
    """Budget/routing profile chosen for a deliberation run."""

    policy_id: str = field(default_factory=lambda: f"bp-{uuid4().hex[:12]}")
    profile: str = "balanced"
    translation_frontier: int = 0
    verification_depth: str = "standard"
    pantheon_enabled: bool = False
    prior_art_enabled: bool = True
    hard_cap_usd: float | None = None
    reason: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "profile": self.profile,
            "translation_frontier": self.translation_frontier,
            "verification_depth": self.verification_depth,
            "pantheon_enabled": self.pantheon_enabled,
            "prior_art_enabled": self.prior_art_enabled,
            "hard_cap_usd": self.hard_cap_usd,
            "reason": self.reason,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RuntimeBudgetPolicy | None:
        if not isinstance(data, dict):
            return None
        return cls(
            policy_id=str(
                data.get("policy_id", f"bp-{uuid4().hex[:12]}") or f"bp-{uuid4().hex[:12]}"
            ),
            profile=str(data.get("profile", "balanced") or "balanced"),
            translation_frontier=int(data.get("translation_frontier", 0) or 0),
            verification_depth=str(data.get("verification_depth", "standard") or "standard"),
            pantheon_enabled=bool(data.get("pantheon_enabled", False)),
            prior_art_enabled=bool(data.get("prior_art_enabled", True)),
            hard_cap_usd=(
                float(data.get("hard_cap_usd")) if data.get("hard_cap_usd") is not None else None
            ),
            reason=str(data.get("reason", "") or ""),
            notes=list(data.get("notes", []) or []),
        )


@dataclass
class RuntimeRouteDecision:
    """One router decision taken during a run."""

    decision_id: str
    stage: str
    selected_route: str
    reason: str
    timestamp: str = field(default_factory=_now)
    candidate_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "stage": self.stage,
            "selected_route": self.selected_route,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "candidate_refs": list(self.candidate_refs),
            "evidence_refs": list(self.evidence_refs),
            "estimated_cost_usd": self.estimated_cost_usd,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RuntimeRouteDecision | None:
        if not isinstance(data, dict):
            return None
        return cls(
            decision_id=str(data.get("decision_id", "") or ""),
            stage=str(data.get("stage", "") or ""),
            selected_route=str(data.get("selected_route", "") or ""),
            reason=str(data.get("reason", "") or ""),
            timestamp=str(data.get("timestamp", _now()) or _now()),
            candidate_refs=list(data.get("candidate_refs", []) or []),
            evidence_refs=list(data.get("evidence_refs", []) or []),
            estimated_cost_usd=float(data.get("estimated_cost_usd", 0.0) or 0.0),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class StageEvent:
    """Observable stage transition for replay or reporting."""

    stage: str
    status: str
    message: str
    timestamp: str = field(default_factory=_now)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StageEvent | None:
        if not isinstance(data, dict):
            return None
        return cls(
            stage=str(data.get("stage", "") or ""),
            status=str(data.get("status", "") or ""),
            message=str(data.get("message", "") or ""),
            timestamp=str(data.get("timestamp", _now()) or _now()),
            payload=dict(data.get("payload", {}) or {}),
        )


@dataclass
class DeliberationEvidence:
    """Evidence node used to support or challenge claims."""

    evidence_id: str
    kind: str
    summary: str
    source_url: str = ""
    locator: str = ""
    claim_summary: str = ""
    raw_excerpt_hash: str = ""
    trust_tier: str = "internal"
    freshness: str = "stable"
    used_by_claims: list[str] = field(default_factory=list)
    captured_at: str = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "summary": self.summary,
            "source_url": self.source_url,
            "locator": self.locator,
            "claim_summary": self.claim_summary,
            "raw_excerpt_hash": self.raw_excerpt_hash,
            "trust_tier": self.trust_tier,
            "freshness": self.freshness,
            "used_by_claims": list(self.used_by_claims),
            "captured_at": self.captured_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeliberationEvidence | None:
        if not isinstance(data, dict):
            return None
        return cls(
            evidence_id=str(data.get("evidence_id", "") or ""),
            kind=str(data.get("kind", "") or ""),
            summary=str(data.get("summary", "") or ""),
            source_url=str(data.get("source_url", "") or ""),
            locator=str(data.get("locator", "") or ""),
            claim_summary=str(data.get("claim_summary", "") or ""),
            raw_excerpt_hash=str(data.get("raw_excerpt_hash", "") or ""),
            trust_tier=str(data.get("trust_tier", "internal") or "internal"),
            freshness=str(data.get("freshness", "stable") or "stable"),
            used_by_claims=list(data.get("used_by_claims", []) or []),
            captured_at=str(data.get("captured_at", _now()) or _now()),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class DeliberationClaim:
    """Claim node attached to one candidate."""

    claim_id: str
    candidate_id: str
    summary: str
    kind: str = "claim"
    stage: str = ""
    status: str = "asserted"
    evidence_refs: list[str] = field(default_factory=list)
    objection_refs: list[str] = field(default_factory=list)
    verifier_refs: list[str] = field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "candidate_id": self.candidate_id,
            "summary": self.summary,
            "kind": self.kind,
            "stage": self.stage,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "objection_refs": list(self.objection_refs),
            "verifier_refs": list(self.verifier_refs),
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeliberationClaim | None:
        if not isinstance(data, dict):
            return None
        confidence = data.get("confidence")
        return cls(
            claim_id=str(data.get("claim_id", "") or ""),
            candidate_id=str(data.get("candidate_id", "") or ""),
            summary=str(data.get("summary", "") or ""),
            kind=str(data.get("kind", "claim") or "claim"),
            stage=str(data.get("stage", "") or ""),
            status=str(data.get("status", "asserted") or "asserted"),
            evidence_refs=list(data.get("evidence_refs", []) or []),
            objection_refs=list(data.get("objection_refs", []) or []),
            verifier_refs=list(data.get("verifier_refs", []) or []),
            confidence=float(confidence) if confidence is not None else None,
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class DeliberationObjection:
    """Durable objection state tracked across stages."""

    objection_id: str
    candidate_id: str
    source_agent: str
    objection_type: str
    severity: str
    statement: str
    claim_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    must_change: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    disproof_test: str = ""
    status: str = "open"
    resolution_refs: list[str] = field(default_factory=list)
    introduced_round: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objection_id": self.objection_id,
            "candidate_id": self.candidate_id,
            "source_agent": self.source_agent,
            "objection_type": self.objection_type,
            "severity": self.severity,
            "statement": self.statement,
            "claim_refs": list(self.claim_refs),
            "evidence_refs": list(self.evidence_refs),
            "must_change": list(self.must_change),
            "must_preserve": list(self.must_preserve),
            "disproof_test": self.disproof_test,
            "status": self.status,
            "resolution_refs": list(self.resolution_refs),
            "introduced_round": self.introduced_round,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeliberationObjection | None:
        if not isinstance(data, dict):
            return None
        return cls(
            objection_id=str(data.get("objection_id", "") or ""),
            candidate_id=str(data.get("candidate_id", "") or ""),
            source_agent=str(data.get("source_agent", "") or ""),
            objection_type=str(data.get("objection_type", "") or ""),
            severity=str(data.get("severity", "major") or "major"),
            statement=str(data.get("statement", "") or ""),
            claim_refs=list(data.get("claim_refs", []) or []),
            evidence_refs=list(data.get("evidence_refs", []) or []),
            must_change=list(data.get("must_change", []) or []),
            must_preserve=list(data.get("must_preserve", []) or []),
            disproof_test=str(data.get("disproof_test", "") or ""),
            status=str(data.get("status", "open") or "open"),
            resolution_refs=list(data.get("resolution_refs", []) or []),
            introduced_round=int(data.get("introduced_round", 0) or 0),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class VerifierCheck:
    """Verifier stack result bound to a candidate."""

    check_id: str
    candidate_id: str
    layer: str
    name: str
    status: str
    score: float | None = None
    detail: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    objection_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "candidate_id": self.candidate_id,
            "layer": self.layer,
            "name": self.name,
            "status": self.status,
            "score": self.score,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "objection_refs": list(self.objection_refs),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VerifierCheck | None:
        if not isinstance(data, dict):
            return None
        score = data.get("score")
        return cls(
            check_id=str(data.get("check_id", "") or ""),
            candidate_id=str(data.get("candidate_id", "") or ""),
            layer=str(data.get("layer", "") or ""),
            name=str(data.get("name", "") or ""),
            status=str(data.get("status", "") or ""),
            score=float(score) if score is not None else None,
            detail=str(data.get("detail", "") or ""),
            evidence_refs=list(data.get("evidence_refs", []) or []),
            objection_refs=list(data.get("objection_refs", []) or []),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class CandidateStateCard:
    """Compact machine-readable branch state."""

    candidate_id: str
    parent_ids: list[str] = field(default_factory=list)
    fingerprint: str = ""
    source_domain: str = ""
    novelty_axes: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    unresolved_objections: int = 0
    structural_validity: float = 0.0
    feasibility: float = 0.0
    baseline_overlap: float = 0.0
    compute_spent_usd: float = 0.0
    route_history: list[str] = field(default_factory=list)
    status: str = "alive"
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_ids": list(self.parent_ids),
            "fingerprint": self.fingerprint,
            "source_domain": self.source_domain,
            "novelty_axes": list(self.novelty_axes),
            "evidence_coverage": self.evidence_coverage,
            "unresolved_objections": self.unresolved_objections,
            "structural_validity": self.structural_validity,
            "feasibility": self.feasibility,
            "baseline_overlap": self.baseline_overlap,
            "compute_spent_usd": self.compute_spent_usd,
            "route_history": list(self.route_history),
            "status": self.status,
            "score": self.score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CandidateStateCard | None:
        if not isinstance(data, dict):
            return None
        return cls(
            candidate_id=str(data.get("candidate_id", "") or ""),
            parent_ids=list(data.get("parent_ids", []) or []),
            fingerprint=str(data.get("fingerprint", "") or ""),
            source_domain=str(data.get("source_domain", "") or ""),
            novelty_axes=list(data.get("novelty_axes", []) or []),
            evidence_coverage=float(data.get("evidence_coverage", 0.0) or 0.0),
            unresolved_objections=int(data.get("unresolved_objections", 0) or 0),
            structural_validity=float(data.get("structural_validity", 0.0) or 0.0),
            feasibility=float(data.get("feasibility", 0.0) or 0.0),
            baseline_overlap=float(data.get("baseline_overlap", 0.0) or 0.0),
            compute_spent_usd=float(data.get("compute_spent_usd", 0.0) or 0.0),
            route_history=list(data.get("route_history", []) or []),
            status=str(data.get("status", "alive") or "alive"),
            score=float(data.get("score", 0.0) or 0.0),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class DeliberationGraph:
    """Typed state graph spanning search, objections, evidence, and runtime."""

    graph_id: str = field(default_factory=lambda: f"dg-{uuid4().hex}")
    workflow_kind: str = "genesis"
    goal: str = ""
    target_domain: str = ""
    plan: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    budget_policy: RuntimeBudgetPolicy | None = None
    accounting: RuntimeAccounting = field(default_factory=RuntimeAccounting)
    stage_events: list[StageEvent] = field(default_factory=list)
    routing_history: list[RuntimeRouteDecision] = field(default_factory=list)
    candidates: list[CandidateStateCard] = field(default_factory=list)
    claims: list[DeliberationClaim] = field(default_factory=list)
    evidence: list[DeliberationEvidence] = field(default_factory=list)
    objections: list[DeliberationObjection] = field(default_factory=list)
    verifier_checks: list[VerifierCheck] = field(default_factory=list)
    final_candidate_id: str = ""
    stop_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "workflow_kind": self.workflow_kind,
            "goal": self.goal,
            "target_domain": self.target_domain,
            "plan": list(self.plan),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "budget_policy": self.budget_policy.to_dict()
            if self.budget_policy is not None
            else None,
            "accounting": self.accounting.to_dict(),
            "stage_events": [event.to_dict() for event in self.stage_events],
            "routing_history": [item.to_dict() for item in self.routing_history],
            "candidates": [item.to_dict() for item in self.candidates],
            "claims": [item.to_dict() for item in self.claims],
            "evidence": [item.to_dict() for item in self.evidence],
            "objections": [item.to_dict() for item in self.objections],
            "verifier_checks": [item.to_dict() for item in self.verifier_checks],
            "final_candidate_id": self.final_candidate_id,
            "stop_reason": self.stop_reason,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeliberationGraph | None:
        if not isinstance(data, dict):
            return None
        return cls(
            graph_id=str(data.get("graph_id", f"dg-{uuid4().hex}") or f"dg-{uuid4().hex}"),
            workflow_kind=str(data.get("workflow_kind", "genesis") or "genesis"),
            goal=str(data.get("goal", "") or ""),
            target_domain=str(data.get("target_domain", "") or ""),
            plan=list(data.get("plan", []) or []),
            created_at=str(data.get("created_at", _now()) or _now()),
            updated_at=str(data.get("updated_at", _now()) or _now()),
            budget_policy=RuntimeBudgetPolicy.from_dict(data.get("budget_policy")),
            accounting=RuntimeAccounting.from_dict(data.get("accounting")),
            stage_events=[
                item
                for item in (
                    StageEvent.from_dict(entry) for entry in data.get("stage_events", []) or []
                )
                if item is not None
            ],
            routing_history=[
                item
                for item in (
                    RuntimeRouteDecision.from_dict(entry)
                    for entry in data.get("routing_history", []) or []
                )
                if item is not None
            ],
            candidates=[
                item
                for item in (
                    CandidateStateCard.from_dict(entry)
                    for entry in data.get("candidates", []) or []
                )
                if item is not None
            ],
            claims=[
                item
                for item in (
                    DeliberationClaim.from_dict(entry) for entry in data.get("claims", []) or []
                )
                if item is not None
            ],
            evidence=[
                item
                for item in (
                    DeliberationEvidence.from_dict(entry)
                    for entry in data.get("evidence", []) or []
                )
                if item is not None
            ],
            objections=[
                item
                for item in (
                    DeliberationObjection.from_dict(entry)
                    for entry in data.get("objections", []) or []
                )
                if item is not None
            ],
            verifier_checks=[
                item
                for item in (
                    VerifierCheck.from_dict(entry)
                    for entry in data.get("verifier_checks", []) or []
                )
                if item is not None
            ],
            final_candidate_id=str(data.get("final_candidate_id", "") or ""),
            stop_reason=str(data.get("stop_reason", "") or ""),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    def summary(self) -> str:
        return (
            f"{self.workflow_kind} deliberation | candidates={len(self.candidates)} "
            f"claims={len(self.claims)} evidence={len(self.evidence)} "
            f"objections={len(self.objections)} checks={len(self.verifier_checks)}"
        )

    def set_budget_policy(self, policy: RuntimeBudgetPolicy) -> RuntimeBudgetPolicy:
        self.budget_policy = policy
        self.touch()
        return policy

    def record_stage(
        self,
        stage: str,
        message: str,
        *,
        status: str = "completed",
        payload: dict[str, Any] | None = None,
    ) -> StageEvent:
        event = StageEvent(
            stage=str(stage),
            status=str(status),
            message=message,
            payload=dict(payload or {}),
        )
        self.stage_events.append(event)
        self.touch()
        return event

    def record_route_decision(
        self,
        stage: str,
        selected_route: str,
        reason: str,
        *,
        candidate_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        estimated_cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRouteDecision:
        decision = RuntimeRouteDecision(
            decision_id=_stable_id(
                "route", stage, selected_route, reason, len(self.routing_history)
            ),
            stage=str(stage),
            selected_route=str(selected_route),
            reason=str(reason),
            candidate_refs=list(candidate_refs or []),
            evidence_refs=list(evidence_refs or []),
            estimated_cost_usd=float(estimated_cost_usd or 0.0),
            metadata=dict(metadata or {}),
        )
        self.routing_history.append(decision)
        self.touch()
        return decision

    def record_accounting(
        self,
        *,
        stage: str,
        route: str | None = None,
        model: str | None = None,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_seconds: float = 0.0,
        calls: int = 1,
    ) -> None:
        self.accounting.record(
            stage=stage,
            route=route,
            model=model,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
            calls=calls,
        )
        self.touch()

    def ensure_candidate(
        self,
        candidate_id: str,
        *,
        parent_ids: list[str] | None = None,
        fingerprint: str | None = None,
        source_domain: str | None = None,
        novelty_axes: list[str] | None = None,
        score: float | None = None,
        status: str | None = None,
        route: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CandidateStateCard:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                if parent_ids is not None:
                    candidate.parent_ids = list(parent_ids)
                if fingerprint is not None:
                    candidate.fingerprint = fingerprint
                if source_domain is not None:
                    candidate.source_domain = source_domain
                if novelty_axes is not None:
                    candidate.novelty_axes = list(novelty_axes)
                if score is not None:
                    candidate.score = float(score or 0.0)
                if status is not None:
                    candidate.status = str(status)
                if route and route not in candidate.route_history:
                    candidate.route_history.append(route)
                if metadata:
                    candidate.metadata.update(metadata)
                self.touch()
                return candidate

        created = CandidateStateCard(
            candidate_id=candidate_id,
            parent_ids=list(parent_ids or []),
            fingerprint=str(fingerprint or ""),
            source_domain=str(source_domain or ""),
            novelty_axes=list(novelty_axes or []),
            score=float(score or 0.0),
            status=str(status or "alive"),
            route_history=[route] if route else [],
            metadata=dict(metadata or {}),
        )
        self.candidates.append(created)
        self.touch()
        return created

    def add_claim(
        self,
        candidate_id: str,
        summary: str,
        *,
        kind: str = "claim",
        stage: str = "",
        status: str = "asserted",
        evidence_refs: list[str] | None = None,
        objection_refs: list[str] | None = None,
        verifier_refs: list[str] | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeliberationClaim:
        claim = DeliberationClaim(
            claim_id=_stable_id("claim", candidate_id, stage, summary, len(self.claims)),
            candidate_id=candidate_id,
            summary=summary,
            kind=kind,
            stage=stage,
            status=status,
            evidence_refs=list(evidence_refs or []),
            objection_refs=list(objection_refs or []),
            verifier_refs=list(verifier_refs or []),
            confidence=confidence,
            metadata=dict(metadata or {}),
        )
        self.claims.append(claim)
        self.touch()
        self.refresh_candidate(candidate_id)
        return claim

    def add_evidence(
        self,
        *,
        kind: str,
        summary: str,
        source_url: str = "",
        locator: str = "",
        claim_summary: str = "",
        raw_excerpt_hash: str = "",
        trust_tier: str = "internal",
        freshness: str = "stable",
        used_by_claims: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeliberationEvidence:
        evidence = DeliberationEvidence(
            evidence_id=_stable_id("ev", kind, source_url, locator, summary, len(self.evidence)),
            kind=kind,
            summary=summary,
            source_url=source_url,
            locator=locator,
            claim_summary=claim_summary,
            raw_excerpt_hash=raw_excerpt_hash,
            trust_tier=trust_tier,
            freshness=freshness,
            used_by_claims=list(used_by_claims or []),
            metadata=dict(metadata or {}),
        )
        self.evidence.append(evidence)
        self.touch()
        return evidence

    def link_evidence(self, evidence_id: str, claim_ids: list[str]) -> None:
        evidence = next((item for item in self.evidence if item.evidence_id == evidence_id), None)
        if evidence is None:
            return
        for claim_id in claim_ids:
            if claim_id not in evidence.used_by_claims:
                evidence.used_by_claims.append(claim_id)
            claim = next((item for item in self.claims if item.claim_id == claim_id), None)
            if claim is not None and evidence_id not in claim.evidence_refs:
                claim.evidence_refs.append(evidence_id)
                self.refresh_candidate(claim.candidate_id)
        self.touch()

    def add_objection(
        self,
        candidate_id: str,
        *,
        source_agent: str,
        objection_type: str,
        severity: str,
        statement: str,
        claim_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        must_change: list[str] | None = None,
        must_preserve: list[str] | None = None,
        disproof_test: str = "",
        status: str = "open",
        resolution_refs: list[str] | None = None,
        introduced_round: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> DeliberationObjection:
        objection = DeliberationObjection(
            objection_id=_stable_id(
                "obj",
                candidate_id,
                source_agent,
                objection_type,
                statement,
                len(self.objections),
            ),
            candidate_id=candidate_id,
            source_agent=source_agent,
            objection_type=objection_type,
            severity=severity,
            statement=statement,
            claim_refs=list(claim_refs or []),
            evidence_refs=list(evidence_refs or []),
            must_change=list(must_change or []),
            must_preserve=list(must_preserve or []),
            disproof_test=disproof_test,
            status=status,
            resolution_refs=list(resolution_refs or []),
            introduced_round=int(introduced_round or 0),
            metadata=dict(metadata or {}),
        )
        self.objections.append(objection)
        for claim in self.claims:
            if (
                claim.claim_id in objection.claim_refs
                and objection.objection_id not in claim.objection_refs
            ):
                claim.objection_refs.append(objection.objection_id)
        self.touch()
        self.refresh_candidate(candidate_id)
        return objection

    def add_verifier_check(
        self,
        candidate_id: str,
        *,
        layer: str,
        name: str,
        status: str,
        score: float | None = None,
        detail: str = "",
        evidence_refs: list[str] | None = None,
        objection_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VerifierCheck:
        check = VerifierCheck(
            check_id=_stable_id("check", candidate_id, layer, name, len(self.verifier_checks)),
            candidate_id=candidate_id,
            layer=layer,
            name=name,
            status=status,
            score=score,
            detail=detail,
            evidence_refs=list(evidence_refs or []),
            objection_refs=list(objection_refs or []),
            metadata=dict(metadata or {}),
        )
        self.verifier_checks.append(check)
        self.touch()
        self.refresh_candidate(candidate_id)
        return check

    def refresh_candidate(self, candidate_id: str) -> CandidateStateCard | None:
        candidate = next(
            (item for item in self.candidates if item.candidate_id == candidate_id), None
        )
        if candidate is None:
            return None

        claim_ids = [claim.claim_id for claim in self.claims if claim.candidate_id == candidate_id]
        claim_count = len(claim_ids)
        supported_count = sum(
            1 for claim in self.claims if claim.candidate_id == candidate_id and claim.evidence_refs
        )
        candidate.evidence_coverage = supported_count / claim_count if claim_count else 0.0
        candidate.unresolved_objections = sum(
            1
            for objection in self.objections
            if objection.candidate_id == candidate_id and str(objection.status).lower() == "open"
        )

        check_scores = [
            float(check.score)
            for check in self.verifier_checks
            if check.candidate_id == candidate_id and check.score is not None
        ]
        structural_scores = [
            float(check.score)
            for check in self.verifier_checks
            if check.candidate_id == candidate_id
            and check.score is not None
            and check.name in {"validity_assessment", "load_bearing", "claim_evidence_coverage"}
        ]
        feasibility_scores = [
            float(check.score)
            for check in self.verifier_checks
            if check.candidate_id == candidate_id
            and check.score is not None
            and check.name in {"validity_assessment", "implementation_risk_review"}
        ]
        if structural_scores:
            candidate.structural_validity = max(structural_scores)
        elif check_scores:
            candidate.structural_validity = max(check_scores)
        if feasibility_scores:
            candidate.feasibility = max(feasibility_scores)

        baseline_flags = [
            check
            for check in self.verifier_checks
            if check.candidate_id == candidate_id and check.name == "quality_gate"
        ]
        if baseline_flags:
            candidate.baseline_overlap = max(
                float(check.metadata.get("baseline_overlap", 0.0) or 0.0)
                for check in baseline_flags
            )
        self.touch()
        return candidate

    def mark_final(self, candidate_id: str, *, reason: str = "") -> None:
        self.final_candidate_id = candidate_id
        if reason:
            self.stop_reason = reason
        candidate = self.ensure_candidate(candidate_id)
        candidate.status = "finalist"
        self.refresh_candidate(candidate_id)
        self.touch()


class RuntimeRouter:
    """Lightweight heuristic router for inference-time budget allocation."""

    @staticmethod
    def initial_policy(
        *,
        goal: str,
        use_pantheon_mode: bool,
        use_prior_art: bool,
        configured_translations: int,
    ) -> RuntimeBudgetPolicy:
        goal_len = len(goal.strip())
        profile = "balanced"
        notes: list[str] = []
        if use_pantheon_mode or goal_len >= 180:
            profile = "intensive"
            notes.append("Long or council-backed task justifies broader exploration.")
        elif goal_len <= 80 and configured_translations <= 2:
            profile = "economy"
            notes.append("Short prompt with narrow frontier can stay on the cheap path.")
        else:
            notes.append("Defaulting to balanced broad-then-deep orchestration.")
        return RuntimeBudgetPolicy(
            profile=profile,
            translation_frontier=max(1, int(configured_translations or 1)),
            verification_depth="deep" if (use_pantheon_mode or use_prior_art) else "standard",
            pantheon_enabled=bool(use_pantheon_mode),
            prior_art_enabled=bool(use_prior_art),
            reason=notes[0],
            notes=notes,
        )

    @staticmethod
    def recommend_translation_frontier(
        scored_candidates: list[Any],
        *,
        configured_top_n: int,
        pantheon_enabled: bool,
    ) -> tuple[int, str]:
        if not scored_candidates:
            return 0, "No scored candidates available."
        if configured_top_n <= 1 or len(scored_candidates) == 1:
            return 1, "Only one viable candidate needs translation."

        ordered = sorted(
            (float(getattr(item, "combined_score", 0.0) or 0.0) for item in scored_candidates),
            reverse=True,
        )
        top_score = ordered[0]
        runner_up = ordered[1] if len(ordered) > 1 else 0.0
        gap = top_score - runner_up
        close_frontier = sum(1 for score in ordered if top_score - score <= 0.08)

        if pantheon_enabled:
            frontier = min(configured_top_n, max(2, close_frontier))
            return frontier, "Preserving a competitive frontier for Pantheon screening."
        if gap >= 0.18:
            frontier = min(configured_top_n, 2)
            return frontier, "Dominant top candidate allows a narrower translation frontier."
        frontier = min(configured_top_n, max(2, close_frontier + 1))
        return frontier, "Top scores are clustered; keep a broader translation frontier."


__all__ = [
    "CandidateStateCard",
    "DeliberationClaim",
    "DeliberationEvidence",
    "DeliberationGraph",
    "DeliberationObjection",
    "RuntimeAccounting",
    "RuntimeAccountingSnapshot",
    "RuntimeBudgetPolicy",
    "RuntimeRouteDecision",
    "RuntimeRouter",
    "StageEvent",
    "VerifierCheck",
]
