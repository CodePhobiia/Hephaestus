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


@dataclass
class PantheonState:
    mode: str = "inactive"
    canon: AthenaCanon | None = None
    dossier: HermesDossier | None = None
    audits: list[ApolloAudit] = field(default_factory=list)
    rounds: list[PantheonRound] = field(default_factory=list)
    winning_candidate_id: str | None = None
    consensus_achieved: bool = False
    final_verdict: str = "UNKNOWN"
    unresolved_vetoes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "canon": self.canon.to_dict() if self.canon is not None else None,
            "dossier": self.dossier.to_dict() if self.dossier is not None else None,
            "audits": [audit.to_dict() for audit in self.audits],
            "rounds": [round_.to_dict() for round_ in self.rounds],
            "winning_candidate_id": self.winning_candidate_id,
            "consensus_achieved": self.consensus_achieved,
            "final_verdict": self.final_verdict,
            "unresolved_vetoes": list(self.unresolved_vetoes),
        }


__all__ = [
    "ApolloAudit",
    "AthenaCanon",
    "HermesDossier",
    "PantheonRound",
    "PantheonState",
    "PantheonVote",
]
