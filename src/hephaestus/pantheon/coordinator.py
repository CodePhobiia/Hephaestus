"""Pantheon Mode coordinator.

Wraps the standard Genesis pipeline with a four-agent council:
- Hephaestus (existing translation/forge engine)
- Athena (structural canon)
- Hermes (reality dossier)
- Apollo (adversarial truth audit)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from typing import Any, Sequence

from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.deepforge.harness import DeepForgeHarness
from hephaestus.pantheon.models import (
    ApolloAudit,
    AthenaCanon,
    HermesDossier,
    PantheonRound,
    PantheonState,
    PantheonVote,
)
from hephaestus.pantheon import prompts

logger = logging.getLogger(__name__)


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
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


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


def _votes_to_text(votes: Sequence[PantheonVote]) -> str:
    return json.dumps([vote.to_dict() for vote in votes], indent=2, ensure_ascii=False)


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
    ) -> None:
        self._athena = athena_harness
        self._hermes = hermes_harness
        self._apollo = apollo_harness
        self._max_rounds = max(1, max_rounds)
        self._require_unanimity = require_unanimity
        self._allow_fail_closed = allow_fail_closed
        self._max_survivors_to_council = max(1, max_survivors_to_council)

    async def _forge_json(self, harness: DeepForgeHarness, prompt: str, *, system: str) -> dict[str, Any]:
        result = await harness.forge(prompt, system=system)
        return _json_block(result.output)

    async def athena_canon_pass(self, *, problem: str, structure: Any, baseline_dossier: Any = None) -> AthenaCanon:
        prompt = prompts.ATHENA_CANON_PROMPT.format(
            problem=problem,
            structure=getattr(structure, "structure", ""),
            mathematical_shape=getattr(structure, "mathematical_shape", ""),
            constraints="\n".join(f"- {item}" for item in getattr(structure, "constraints", [])[:12]) or "- none",
            baseline=getattr(baseline_dossier, "summary", "") if baseline_dossier is not None else "",
        )
        data = await self._forge_json(self._athena, prompt, system=prompts.ATHENA_CANON_SYSTEM)
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

    async def hermes_dossier_pass(self, *, problem: str, structure: Any, baseline_dossier: Any = None) -> HermesDossier:
        prompt = prompts.HERMES_DOSSIER_PROMPT.format(
            problem=problem,
            structure=getattr(structure, "structure", ""),
            mathematical_shape=getattr(structure, "mathematical_shape", ""),
            constraints="\n".join(f"- {item}" for item in getattr(structure, "constraints", [])[:12]) or "- none",
            baseline=getattr(baseline_dossier, "summary", "") if baseline_dossier is not None else "",
        )
        data = await self._forge_json(self._hermes, prompt, system=prompts.HERMES_DOSSIER_SYSTEM)
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

    async def _athena_review(self, translation: Translation, canon: AthenaCanon) -> PantheonVote:
        data = await self._forge_json(
            self._athena,
            prompts.ATHENA_REVIEW_PROMPT.format(
                canon=_canon_to_text(canon),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.ATHENA_REVIEW_SYSTEM,
        )
        return PantheonVote(
            agent="athena",
            decision=str(data.get("decision", "VETO")).upper(),
            veto_type=str(data.get("veto_type")) if data.get("veto_type") is not None else None,
            reasons=_safe_list(data.get("reasons")),
            must_change=_safe_list(data.get("must_change")),
            must_preserve=_safe_list(data.get("must_preserve")),
            confidence=_safe_float(data.get("confidence")),
        )

    async def _hermes_review(self, translation: Translation, dossier: HermesDossier) -> PantheonVote:
        data = await self._forge_json(
            self._hermes,
            prompts.HERMES_REVIEW_PROMPT.format(
                dossier=_dossier_to_text(dossier),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.HERMES_REVIEW_SYSTEM,
        )
        return PantheonVote(
            agent="hermes",
            decision=str(data.get("decision", "VETO")).upper(),
            veto_type=str(data.get("veto_type")) if data.get("veto_type") is not None else None,
            reasons=_safe_list(data.get("reasons")),
            must_change=_safe_list(data.get("must_change")),
            must_preserve=_safe_list(data.get("must_preserve")),
            confidence=_safe_float(data.get("confidence")),
        )

    async def _apollo_audit(self, translation: Translation, canon: AthenaCanon, dossier: HermesDossier) -> ApolloAudit:
        data = await self._forge_json(
            self._apollo,
            prompts.APOLLO_AUDIT_PROMPT.format(
                canon=_canon_to_text(canon),
                dossier=_dossier_to_text(dossier),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.APOLLO_AUDIT_SYSTEM,
        )
        return ApolloAudit(
            candidate_id=str(data.get("candidate_id", translation.invention_name)),
            verdict=str(data.get("verdict", "PROVISIONAL")).upper(),
            fatal_flaws=_safe_list(data.get("fatal_flaws")),
            structural_weaknesses=_safe_list(data.get("structural_weaknesses")),
            decorative_signals=_safe_list(data.get("decorative_signals")),
            proof_obligations=_safe_list(data.get("proof_obligations")),
            reasons=_safe_list(data.get("reasons")),
            confidence=_safe_float(data.get("confidence")),
        )

    async def _hephaestus_reforge(
        self,
        *,
        translator: Any,
        problem: str,
        structure: Any,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        votes: Sequence[PantheonVote],
    ) -> tuple[Translation | None, PantheonVote]:
        objection_reasons = [reason for vote in votes for reason in vote.reasons]
        must_change = [item for vote in votes for item in vote.must_change]
        must_preserve = [item for vote in votes for item in vote.must_preserve]
        t_start = time.monotonic()
        result = await translator._harness.forge(
            prompts.HEPHAESTUS_REFORGE_PROMPT.format(
                problem=problem,
                structure=getattr(structure, "structure", ""),
                canon=_canon_to_text(canon),
                dossier=_dossier_to_text(dossier),
                candidate=_translation_to_text(translation),
                objections=_votes_to_text(votes),
            ),
            system=prompts.HEPHAESTUS_REFORGE_SYSTEM,
        )
        parsed = translator._parse_translation(result.output)
        if not parsed.get("architecture"):
            vote = PantheonVote(
                agent="hephaestus",
                decision="VETO",
                veto_type="NOVELTY",
                reasons=["Reforge failed to produce a valid architecture JSON output."],
                must_change=must_change,
                must_preserve=must_preserve,
                confidence=0.0,
            )
            return None, vote

        source_candidate = translation.source_candidate
        mappings: list[ElementMapping] = []
        for element in parsed.get("mapping", {}).get("elements", []):
            if isinstance(element, dict):
                mappings.append(
                    ElementMapping(
                        source_element=str(element.get("source_element", "")),
                        target_element=str(element.get("target_element", "")),
                        mechanism=str(element.get("mechanism", "")),
                    )
                )
        revised = Translation(
            invention_name=str(parsed.get("invention_name", translation.invention_name)),
            mapping=mappings,
            architecture=str(parsed.get("architecture", translation.architecture)),
            mathematical_proof=str(parsed.get("mathematical_proof", translation.mathematical_proof)),
            limitations=_safe_list(parsed.get("limitations")),
            implementation_notes=str(parsed.get("implementation_notes", translation.implementation_notes)),
            key_insight=str(parsed.get("key_insight", translation.key_insight)),
            source_candidate=source_candidate,
            phase1_abstract_mechanism=str(parsed.get("phase1_abstract_mechanism", translation.phase1_abstract_mechanism)),
            phase2_target_architecture=str(parsed.get("phase2_target_architecture", translation.phase2_target_architecture)),
            mechanism_is_decorative=bool(parsed.get("mechanism_is_decorative", False)),
            known_pattern_if_decorative=str(parsed.get("known_pattern_if_decorative", "")),
            mechanism_differs_from_baseline=str(parsed.get("mechanism_differs_from_baseline", translation.mechanism_differs_from_baseline)),
            subtraction_test=str(parsed.get("subtraction_test", translation.subtraction_test)),
            baseline_comparison=str(parsed.get("baseline_comparison", translation.baseline_comparison)),
            recovery_commitments=[str(x) for x in parsed.get("recovery_commitments", []) if str(x).strip()],
            future_option_preservation=str(parsed.get("future_option_preservation", translation.future_option_preservation)),
            cost_usd=result.trace.total_cost_usd,
            duration_seconds=time.monotonic() - t_start,
            trace=result.trace,
            bundle_proof=translation.bundle_proof,
            bundle_lineage=translation.bundle_lineage,
            selection_mode=translation.selection_mode,
            bundle_role=translation.bundle_role,
            reference_signature=translation.reference_signature,
            research_signature=translation.research_signature,
            branch_signature=translation.branch_signature,
            guard_results=list(translation.guard_results),
            guard_failed=translation.guard_failed,
            recomposition_events=list(translation.recomposition_events),
        )
        vote = PantheonVote(
            agent="hephaestus",
            decision="ASSENT",
            veto_type=None,
            reasons=["Reforged candidate while preserving novelty core.", *objection_reasons[:3]],
            must_change=[],
            must_preserve=must_preserve,
            confidence=0.78,
        )
        return revised, vote

    async def deliberate(
        self,
        *,
        problem: str,
        structure: Any,
        translations: Sequence[Translation],
        translator: Any,
        baseline_dossier: Any = None,
        previous_state: PantheonState | None = None,
    ) -> tuple[list[Translation], PantheonState]:
        state = PantheonState(mode="pantheon")
        canon = await self.athena_canon_pass(problem=problem, structure=structure, baseline_dossier=baseline_dossier)
        dossier = await self.hermes_dossier_pass(problem=problem, structure=structure, baseline_dossier=baseline_dossier)
        state.canon = canon
        state.dossier = dossier

        survivors = list(translations[: self._max_survivors_to_council])
        if not survivors:
            return [], state

        winning: Translation | None = None
        all_audits: list[ApolloAudit] = []
        unresolved: list[str] = []

        for idx, original in enumerate(survivors, start=1):
            candidate = original
            candidate_id = f"candidate-{idx}:{candidate.invention_name}"
            for round_index in range(1, self._max_rounds + 1):
                athena_vote = await self._athena_review(candidate, canon)
                hermes_vote = await self._hermes_review(candidate, dossier)
                apollo_audit = await self._apollo_audit(candidate, canon, dossier)
                all_audits.append(apollo_audit)
                apollo_vote = PantheonVote(
                    agent="apollo",
                    decision="ASSENT" if apollo_audit.verdict == "VALID" and not apollo_audit.fatal_flaws else "VETO",
                    veto_type=None if apollo_audit.verdict == "VALID" and not apollo_audit.fatal_flaws else "TRUTH",
                    reasons=[*apollo_audit.reasons, *apollo_audit.fatal_flaws[:3]],
                    must_change=[*apollo_audit.fatal_flaws, *apollo_audit.proof_obligations],
                    must_preserve=[],
                    confidence=apollo_audit.confidence,
                )
                votes = [athena_vote, hermes_vote, apollo_vote]
                unresolved_round = [
                    vote.veto_type or vote.agent
                    for vote in votes
                    if vote.decision != "ASSENT"
                ]
                consensus_reached = False
                if not unresolved_round:
                    consensus_reached = True
                elif not self._require_unanimity:
                    assent_count = sum(1 for vote in votes if vote.decision == "ASSENT")
                    truth_veto = any(vote.veto_type == "TRUTH" for vote in votes if vote.decision != "ASSENT")
                    consensus_reached = assent_count >= 2 and not truth_veto

                if consensus_reached:
                    hephaestus_vote = PantheonVote(
                        agent="hephaestus",
                        decision="ASSENT",
                        veto_type=None,
                        reasons=["Novelty core preserved and council assented."],
                        must_change=[],
                        must_preserve=[candidate.key_insight] if candidate.key_insight else [],
                        confidence=0.85,
                    )
                    votes.append(hephaestus_vote)
                    state.rounds.append(
                        PantheonRound(
                            round_index=round_index,
                            candidate_id=candidate_id,
                            votes=votes,
                            consensus=True,
                            unresolved_vetoes=[],
                            revision_summary="Council unanimously assented.",
                        )
                    )
                    winning = candidate
                    state.consensus_achieved = True
                    state.winning_candidate_id = candidate_id
                    break

                revised, hephaestus_vote = await self._hephaestus_reforge(
                    translator=translator,
                    problem=problem,
                    structure=structure,
                    translation=candidate,
                    canon=canon,
                    dossier=dossier,
                    votes=votes,
                )
                votes.append(hephaestus_vote)
                state.rounds.append(
                    PantheonRound(
                        round_index=round_index,
                        candidate_id=candidate_id,
                        votes=votes,
                        consensus=False,
                        unresolved_vetoes=unresolved_round,
                        revision_summary="Hephaestus revised candidate against live vetoes."
                        if revised is not None
                        else "Reforge failed; novelty-preserving revision unavailable.",
                    )
                )
                unresolved = unresolved_round
                if revised is None:
                    break
                candidate = revised

            if winning is not None:
                break

        state.audits = all_audits
        state.unresolved_vetoes = unresolved
        if winning is None and self._allow_fail_closed:
            winning = survivors[0]
            state.winning_candidate_id = f"candidate-1:{winning.invention_name}"
        if winning is not None:
            winning.pantheon_state = state.to_dict()
            return [winning], state
        return [], state

    def finalize_with_verified(self, state: PantheonState, verified_inventions: Sequence[Any]) -> PantheonState:
        if not verified_inventions:
            state.final_verdict = "NO_OUTPUT"
            return state
        top = verified_inventions[0]
        state.final_verdict = str(getattr(top, "verdict", "UNKNOWN"))
        if state.consensus_achieved and getattr(top, "verdict", "UNKNOWN") == "INVALID":
            state.consensus_achieved = False
            state.unresolved_vetoes = [
                *state.unresolved_vetoes,
                "VERIFIER_INVALIDATED_TOP_INVENTION",
            ]
        return state


__all__ = ["PantheonCoordinator", "PantheonError"]
