"""Pantheon Mode state models.

Pantheon Mode wraps Genesis with a four-agent council:
- Hephaestus (forge / revision / novelty preservation)
- Athena (structural truth)
- Hermes (ecosystem / reality truth)
- Apollo (adversarial truth)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AthenaCanon:
    structural_form: str = ""
    mandatory_constraints: list[str] = field(default_factory=list)
    anti_goals: list[str] = field(default_factory=list)
    decomposition_axes: list[str] = field(default_factory=list)
    hidden_assumptions: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    false_framings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "structural_form": self.structural_form,
            "mandatory_constraints": list(self.mandatory_constraints),
            "anti_goals": list(self.anti_goals),
            "decomposition_axes": list(self.decomposition_axes),
            "hidden_assumptions": list(self.hidden_assumptions),
            "success_criteria": list(self.success_criteria),
            "false_framings": list(self.false_framings),
            "reasons": list(self.reasons),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AthenaCanon | None":
        if not isinstance(data, dict):
            return None
        return cls(
            structural_form=str(data.get("structural_form", "") or ""),
            mandatory_constraints=list(data.get("mandatory_constraints", []) or []),
            anti_goals=list(data.get("anti_goals", []) or []),
            decomposition_axes=list(data.get("decomposition_axes", []) or []),
            hidden_assumptions=list(data.get("hidden_assumptions", []) or []),
            success_criteria=list(data.get("success_criteria", []) or []),
            false_framings=list(data.get("false_framings", []) or []),
            reasons=list(data.get("reasons", []) or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )


@dataclass
class HermesDossier:
    repo_reality_summary: str = ""
    competitor_patterns: list[str] = field(default_factory=list)
    ecosystem_constraints: list[str] = field(default_factory=list)
    user_operator_constraints: list[str] = field(default_factory=list)
    adoption_risks: list[str] = field(default_factory=list)
    monetization_vectors: list[str] = field(default_factory=list)
    implementation_leverage_points: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_reality_summary": self.repo_reality_summary,
            "competitor_patterns": list(self.competitor_patterns),
            "ecosystem_constraints": list(self.ecosystem_constraints),
            "user_operator_constraints": list(self.user_operator_constraints),
            "adoption_risks": list(self.adoption_risks),
            "monetization_vectors": list(self.monetization_vectors),
            "implementation_leverage_points": list(self.implementation_leverage_points),
            "reasons": list(self.reasons),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "HermesDossier | None":
        if not isinstance(data, dict):
            return None
        return cls(
            repo_reality_summary=str(data.get("repo_reality_summary", "") or ""),
            competitor_patterns=list(data.get("competitor_patterns", []) or []),
            ecosystem_constraints=list(data.get("ecosystem_constraints", []) or []),
            user_operator_constraints=list(data.get("user_operator_constraints", []) or []),
            adoption_risks=list(data.get("adoption_risks", []) or []),
            monetization_vectors=list(data.get("monetization_vectors", []) or []),
            implementation_leverage_points=list(data.get("implementation_leverage_points", []) or []),
            reasons=list(data.get("reasons", []) or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )


@dataclass
class ApolloAudit:
    candidate_id: str = ""
    verdict: str = "PROVISIONAL"
    fatal_flaws: list[str] = field(default_factory=list)
    structural_weaknesses: list[str] = field(default_factory=list)
    decorative_signals: list[str] = field(default_factory=list)
    proof_obligations: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "verdict": self.verdict,
            "fatal_flaws": list(self.fatal_flaws),
            "structural_weaknesses": list(self.structural_weaknesses),
            "decorative_signals": list(self.decorative_signals),
            "proof_obligations": list(self.proof_obligations),
            "reasons": list(self.reasons),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ApolloAudit | None":
        if not isinstance(data, dict):
            return None
        return cls(
            candidate_id=str(data.get("candidate_id", "") or ""),
            verdict=str(data.get("verdict", "PROVISIONAL") or "PROVISIONAL"),
            fatal_flaws=list(data.get("fatal_flaws", []) or []),
            structural_weaknesses=list(data.get("structural_weaknesses", []) or []),
            decorative_signals=list(data.get("decorative_signals", []) or []),
            proof_obligations=list(data.get("proof_obligations", []) or []),
            reasons=list(data.get("reasons", []) or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )


@dataclass
class PantheonVote:
    agent: str
    decision: str
    veto_type: str | None = None
    reasons: list[str] = field(default_factory=list)
    must_change: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "decision": self.decision,
            "veto_type": self.veto_type,
            "reasons": list(self.reasons),
            "must_change": list(self.must_change),
            "must_preserve": list(self.must_preserve),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PantheonVote | None":
        if not isinstance(data, dict):
            return None
        return cls(
            agent=str(data.get("agent", "") or ""),
            decision=str(data.get("decision", "") or ""),
            veto_type=str(data.get("veto_type")) if data.get("veto_type") is not None else None,
            reasons=list(data.get("reasons", []) or []),
            must_change=list(data.get("must_change", []) or []),
            must_preserve=list(data.get("must_preserve", []) or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
        )


@dataclass
class PantheonScreening:
    candidate_id: str
    invention_name: str = ""
    source_domain: str = ""
    reality_vote: PantheonVote | None = None
    audit: ApolloAudit | None = None
    survived: bool = False
    priority_score: float = 0.0
    prune_reasons: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "invention_name": self.invention_name,
            "source_domain": self.source_domain,
            "reality_vote": self.reality_vote.to_dict() if self.reality_vote is not None else None,
            "audit": self.audit.to_dict() if self.audit is not None else None,
            "survived": self.survived,
            "priority_score": self.priority_score,
            "prune_reasons": list(self.prune_reasons),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PantheonScreening | None":
        if not isinstance(data, dict):
            return None
        return cls(
            candidate_id=str(data.get("candidate_id", "") or ""),
            invention_name=str(data.get("invention_name", "") or ""),
            source_domain=str(data.get("source_domain", "") or ""),
            reality_vote=PantheonVote.from_dict(data.get("reality_vote")),
            audit=ApolloAudit.from_dict(data.get("audit")),
            survived=bool(data.get("survived", False)),
            priority_score=float(data.get("priority_score", 0.0) or 0.0),
            prune_reasons=list(data.get("prune_reasons", []) or []),
            summary=str(data.get("summary", "") or ""),
        )


@dataclass
class PantheonRound:
    round_index: int
    candidate_id: str
    votes: list[PantheonVote] = field(default_factory=list)
    consensus: bool = False
    unresolved_vetoes: list[str] = field(default_factory=list)
    revision_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "candidate_id": self.candidate_id,
            "votes": [vote.to_dict() for vote in self.votes],
            "consensus": self.consensus,
            "unresolved_vetoes": list(self.unresolved_vetoes),
            "revision_summary": self.revision_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PantheonRound | None":
        if not isinstance(data, dict):
            return None
        votes = [
            vote
            for vote in (
                PantheonVote.from_dict(item)
                for item in data.get("votes", []) or []
            )
            if vote is not None
        ]
        return cls(
            round_index=int(data.get("round_index", 0) or 0),
            candidate_id=str(data.get("candidate_id", "") or ""),
            votes=votes,
            consensus=bool(data.get("consensus", False)),
            unresolved_vetoes=list(data.get("unresolved_vetoes", []) or []),
            revision_summary=str(data.get("revision_summary", "") or ""),
        )


@dataclass
class PantheonAccounting:
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_seconds: float = 0.0
    agent_call_counts: dict[str, int] = field(default_factory=dict)
    agent_cost_usd: dict[str, float] = field(default_factory=dict)
    agent_input_tokens: dict[str, int] = field(default_factory=dict)
    agent_output_tokens: dict[str, int] = field(default_factory=dict)
    agent_duration_seconds: dict[str, float] = field(default_factory=dict)

    def record(
        self,
        *,
        agent: str,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_seconds: float = 0.0,
    ) -> None:
        self.total_cost_usd += float(cost_usd or 0.0)
        self.total_input_tokens += int(input_tokens or 0)
        self.total_output_tokens += int(output_tokens or 0)
        self.total_duration_seconds += float(duration_seconds or 0.0)
        self.agent_call_counts[agent] = self.agent_call_counts.get(agent, 0) + 1
        self.agent_cost_usd[agent] = self.agent_cost_usd.get(agent, 0.0) + float(cost_usd or 0.0)
        self.agent_input_tokens[agent] = self.agent_input_tokens.get(agent, 0) + int(input_tokens or 0)
        self.agent_output_tokens[agent] = self.agent_output_tokens.get(agent, 0) + int(output_tokens or 0)
        self.agent_duration_seconds[agent] = (
            self.agent_duration_seconds.get(agent, 0.0) + float(duration_seconds or 0.0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_duration_seconds": self.total_duration_seconds,
            "agent_call_counts": dict(self.agent_call_counts),
            "agent_cost_usd": dict(self.agent_cost_usd),
            "agent_input_tokens": dict(self.agent_input_tokens),
            "agent_output_tokens": dict(self.agent_output_tokens),
            "agent_duration_seconds": dict(self.agent_duration_seconds),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PantheonAccounting":
        if not isinstance(data, dict):
            return cls()
        return cls(
            total_cost_usd=float(data.get("total_cost_usd", 0.0) or 0.0),
            total_input_tokens=int(data.get("total_input_tokens", 0) or 0),
            total_output_tokens=int(data.get("total_output_tokens", 0) or 0),
            total_duration_seconds=float(data.get("total_duration_seconds", 0.0) or 0.0),
            agent_call_counts=dict(data.get("agent_call_counts", {}) or {}),
            agent_cost_usd=dict(data.get("agent_cost_usd", {}) or {}),
            agent_input_tokens=dict(data.get("agent_input_tokens", {}) or {}),
            agent_output_tokens=dict(data.get("agent_output_tokens", {}) or {}),
            agent_duration_seconds=dict(data.get("agent_duration_seconds", {}) or {}),
        )


@dataclass
class PantheonState:
    mode: str = "inactive"
    canon: AthenaCanon | None = None
    dossier: HermesDossier | None = None
    initial_structure: dict[str, Any] | None = None
    pipeline_structure: dict[str, Any] | None = None
    screenings: list[PantheonScreening] = field(default_factory=list)
    survivor_candidate_ids: list[str] = field(default_factory=list)
    audits: list[ApolloAudit] = field(default_factory=list)
    rounds: list[PantheonRound] = field(default_factory=list)
    winning_candidate_id: str | None = None
    consensus_achieved: bool = False
    final_verdict: str = "UNKNOWN"
    resolution: str = "inactive"
    failure_reason: str | None = None
    unresolved_vetoes: list[str] = field(default_factory=list)
    accounting: PantheonAccounting = field(default_factory=PantheonAccounting)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "canon": self.canon.to_dict() if self.canon is not None else None,
            "dossier": self.dossier.to_dict() if self.dossier is not None else None,
            "initial_structure": dict(self.initial_structure) if isinstance(self.initial_structure, dict) else None,
            "pipeline_structure": dict(self.pipeline_structure) if isinstance(self.pipeline_structure, dict) else None,
            "screenings": [screening.to_dict() for screening in self.screenings],
            "survivor_candidate_ids": list(self.survivor_candidate_ids),
            "audits": [audit.to_dict() for audit in self.audits],
            "rounds": [round_.to_dict() for round_ in self.rounds],
            "winning_candidate_id": self.winning_candidate_id,
            "consensus_achieved": self.consensus_achieved,
            "final_verdict": self.final_verdict,
            "resolution": self.resolution,
            "failure_reason": self.failure_reason,
            "unresolved_vetoes": list(self.unresolved_vetoes),
            "accounting": self.accounting.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PantheonState | None":
        if not isinstance(data, dict):
            return None
        screenings = [
            screening
            for screening in (
                PantheonScreening.from_dict(item)
                for item in data.get("screenings", []) or []
            )
            if screening is not None
        ]
        audits = [
            audit
            for audit in (
                ApolloAudit.from_dict(item)
                for item in data.get("audits", []) or []
            )
            if audit is not None
        ]
        rounds = [
            round_
            for round_ in (
                PantheonRound.from_dict(item)
                for item in data.get("rounds", []) or []
            )
            if round_ is not None
        ]
        return cls(
            mode=str(data.get("mode", "inactive") or "inactive"),
            canon=AthenaCanon.from_dict(data.get("canon")),
            dossier=HermesDossier.from_dict(data.get("dossier")),
            initial_structure=(
                dict(data.get("initial_structure", {}) or {})
                if isinstance(data.get("initial_structure"), dict)
                else None
            ),
            pipeline_structure=(
                dict(data.get("pipeline_structure", {}) or {})
                if isinstance(data.get("pipeline_structure"), dict)
                else None
            ),
            screenings=screenings,
            survivor_candidate_ids=list(data.get("survivor_candidate_ids", []) or []),
            audits=audits,
            rounds=rounds,
            winning_candidate_id=(
                str(data.get("winning_candidate_id"))
                if data.get("winning_candidate_id") is not None
                else None
            ),
            consensus_achieved=bool(data.get("consensus_achieved", False)),
            final_verdict=str(data.get("final_verdict", "UNKNOWN") or "UNKNOWN"),
            resolution=str(data.get("resolution", "inactive") or "inactive"),
            failure_reason=(
                str(data.get("failure_reason"))
                if data.get("failure_reason") is not None
                else None
            ),
            unresolved_vetoes=list(data.get("unresolved_vetoes", []) or []),
            accounting=PantheonAccounting.from_dict(data.get("accounting")),
        )


__all__ = [
    "ApolloAudit",
    "AthenaCanon",
    "HermesDossier",
    "PantheonAccounting",
    "PantheonRound",
    "PantheonScreening",
    "PantheonState",
    "PantheonVote",
]
