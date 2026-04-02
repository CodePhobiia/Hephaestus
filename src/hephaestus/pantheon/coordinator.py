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
    PantheonRound,
    PantheonScreening,
    PantheonState,
    PantheonVote,
)

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


def _votes_to_text(votes: Sequence[PantheonVote]) -> str:
    return json.dumps([vote.to_dict() for vote in votes], indent=2, ensure_ascii=False)


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

    @staticmethod
    def _apollo_vote(audit: ApolloAudit) -> PantheonVote:
        vetoed = audit.verdict != "VALID" or bool(audit.fatal_flaws)
        return PantheonVote(
            agent="apollo",
            decision="VETO" if vetoed else "ASSENT",
            veto_type="TRUTH" if vetoed else None,
            reasons=[*audit.reasons, *audit.fatal_flaws[:3], *audit.decorative_signals[:2]],
            must_change=[*audit.fatal_flaws, *audit.proof_obligations],
            must_preserve=[],
            confidence=audit.confidence,
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
        current_state = state or PantheonState(mode="pantheon")
        current_state.mode = "pantheon"
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
        translation: Translation,
        canon: AthenaCanon,
        *,
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        data = await self._forge_json(
            self._athena,
            prompts.ATHENA_REVIEW_PROMPT.format(
                canon=_canon_to_text(canon),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.ATHENA_REVIEW_SYSTEM,
            accounting=accounting,
            agent="athena",
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

    async def _hermes_review(
        self,
        translation: Translation,
        dossier: HermesDossier,
        *,
        accounting: PantheonAccounting,
    ) -> PantheonVote:
        data = await self._forge_json(
            self._hermes,
            prompts.HERMES_REVIEW_PROMPT.format(
                dossier=_dossier_to_text(dossier),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.HERMES_REVIEW_SYSTEM,
            accounting=accounting,
            agent="hermes",
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

    async def _apollo_audit(
        self,
        translation: Translation,
        canon: AthenaCanon,
        dossier: HermesDossier,
        *,
        accounting: PantheonAccounting,
    ) -> ApolloAudit:
        data = await self._forge_json(
            self._apollo,
            prompts.APOLLO_AUDIT_PROMPT.format(
                canon=_canon_to_text(canon),
                dossier=_dossier_to_text(dossier),
                candidate=_translation_to_text(translation),
            ),
            system=prompts.APOLLO_AUDIT_SYSTEM,
            accounting=accounting,
            agent="apollo",
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
            hermes_vote = await self._hermes_review(translation, state.dossier, accounting=state.accounting)
            apollo_audit = await self._apollo_audit(translation, state.canon, state.dossier, accounting=state.accounting)
            audits.append(apollo_audit)

            prune_reasons: list[str] = []
            if apollo_audit.verdict == "INVALID" or apollo_audit.fatal_flaws:
                prune_reasons.extend([*apollo_audit.fatal_flaws, *apollo_audit.proof_obligations[:2]])
            if translation.mechanism_is_decorative or apollo_audit.decorative_signals:
                prune_reasons.extend(
                    apollo_audit.decorative_signals[:2]
                    or ["Decorative mechanism collapsed under Apollo scrutiny."]
                )

            reality_bonus = hermes_vote.confidence if hermes_vote.decision == "ASSENT" else -(0.5 + hermes_vote.confidence)
            audit_bonus = apollo_audit.confidence if apollo_audit.verdict == "VALID" and not apollo_audit.fatal_flaws else -1.0
            priority = float(getattr(translation, "combined_score", 0.0) or 0.0) + reality_bonus + audit_bonus

            screening = PantheonScreening(
                candidate_id=candidate_id,
                invention_name=translation.invention_name,
                source_domain=translation.source_domain,
                reality_vote=hermes_vote,
                audit=apollo_audit,
                survived=False,
                priority_score=priority,
                prune_reasons=_dedupe(prune_reasons),
                summary=(
                    "Apollo cleared candidate for council."
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

        if not survivors and translations and self._allow_fail_closed:
            fallback_index, fallback_translation = max(
                enumerate(translations, start=1),
                key=lambda item: getattr(item[1], "combined_score", 0.0),
            )
            fallback_id = self._candidate_id(fallback_index, fallback_translation)
            screening = next((item for item in screenings if item.candidate_id == fallback_id), None)
            if screening is not None:
                screening.survived = True
                screening.summary = (
                    f"{screening.summary} Retained by fail-closed fallback so council can deliberate."
                ).strip()
            survivors = [fallback_translation]
            state.unresolved_vetoes = _dedupe([
                *state.unresolved_vetoes,
                "PRE_COUNCIL_PRUNED_ALL_CANDIDATES",
            ])

        state.screenings = screenings
        state.survivor_candidate_ids = [screening.candidate_id for screening in screenings if screening.survived]
        state.audits = audits
        return survivors, state

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
        accounting: PantheonAccounting,
    ) -> tuple[Translation | None, PantheonVote]:
        objection_reasons = [reason for vote in votes for reason in vote.reasons]
        must_change = [item for vote in votes for item in vote.must_change]
        must_preserve = [item for vote in votes for item in vote.must_preserve]
        try:
            t_start = time.monotonic()
            revised = await translator.reforge(
                prompt=prompts.HEPHAESTUS_REFORGE_PROMPT.format(
                    problem=problem,
                    structure=getattr(structure, "structure", ""),
                    canon=_canon_to_text(canon),
                    dossier=_dossier_to_text(dossier),
                    candidate=_translation_to_text(translation),
                    objections=_votes_to_text(votes),
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
                must_change=must_change,
                must_preserve=must_preserve,
                confidence=0.0,
            )
            return None, vote

        if not revised.architecture or revised.architecture == "Architecture generation failed":
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
        state: PantheonState | None = None,
    ) -> tuple[list[Translation], PantheonState]:
        current_state = state or previous_state or PantheonState(mode="pantheon")
        current_state.mode = "pantheon"
        current_state.final_verdict = current_state.final_verdict or "PENDING_VERIFICATION"
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
            current_state.failure_reason = "No translation candidates entered Pantheon deliberation."
            return [], current_state

        candidate_ids = list(current_state.survivor_candidate_ids)
        if len(candidate_ids) < len(survivors):
            candidate_ids = [
                self._candidate_id(index, translation)
                for index, translation in enumerate(survivors, start=1)
            ]

        winning: Translation | None = None
        all_audits: list[ApolloAudit] = list(current_state.audits)
        unresolved: list[str] = list(current_state.unresolved_vetoes)

        for candidate_id, original in zip(candidate_ids, survivors):
            candidate = original
            for round_index in range(1, self._max_rounds + 1):
                athena_vote = await self._athena_review(candidate, canon, accounting=current_state.accounting)
                hermes_vote = await self._hermes_review(candidate, dossier, accounting=current_state.accounting)
                apollo_audit = await self._apollo_audit(candidate, canon, dossier, accounting=current_state.accounting)
                all_audits.append(apollo_audit)
                apollo_vote = self._apollo_vote(apollo_audit)
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
                    unresolved = []
                    votes.append(hephaestus_vote)
                    current_state.rounds.append(
                        PantheonRound(
                            round_index=round_index,
                            candidate_id=candidate_id,
                            votes=votes,
                            consensus=True,
                            unresolved_vetoes=[],
                            revision_summary="Council assented after pipeline-native canon, dossier, and pre-audit screening.",
                        )
                    )
                    winning = candidate
                    current_state.consensus_achieved = True
                    current_state.winning_candidate_id = candidate_id
                    current_state.resolution = "consensus"
                    current_state.failure_reason = None
                    break

                revised, hephaestus_vote = await self._hephaestus_reforge(
                    translator=translator,
                    problem=problem,
                    structure=structure,
                    translation=candidate,
                    canon=canon,
                    dossier=dossier,
                    votes=votes,
                    accounting=current_state.accounting,
                )
                votes.append(hephaestus_vote)
                current_state.rounds.append(
                    PantheonRound(
                        round_index=round_index,
                        candidate_id=candidate_id,
                        votes=votes,
                        consensus=False,
                        unresolved_vetoes=unresolved_round,
                        revision_summary=(
                            "Hephaestus revised candidate against live vetoes after pre-council screening."
                            if revised is not None
                            else "Reforge failed; novelty-preserving revision unavailable."
                        ),
                    )
                )
                unresolved = _dedupe([*unresolved, *unresolved_round])
                if revised is None:
                    break
                candidate = revised

            if winning is not None:
                break

        current_state.audits = all_audits
        current_state.unresolved_vetoes = unresolved
        if winning is None and self._allow_fail_closed:
            current_state.final_verdict = "NO_OUTPUT"
            current_state.resolution = "fail_closed_rejection"
            current_state.failure_reason = "No candidate survived Pantheon council review and fail-closed was enabled."
            return [], current_state
        if winning is None:
            winning = survivors[0]
            current_state.winning_candidate_id = candidate_ids[0]
            current_state.resolution = "fallback_open"
            current_state.failure_reason = "No candidate achieved Pantheon consensus; returning the top survivor because fail-closed was disabled."
        if winning is not None:
            winning.pantheon_state = current_state.to_dict()
            return [winning], current_state
        return [], current_state

    def finalize_with_verified(self, state: PantheonState, verified_inventions: Sequence[Any]) -> PantheonState:
        if not verified_inventions:
            state.final_verdict = "NO_OUTPUT"
            if state.consensus_achieved:
                state.resolution = "verifier_rejected_consensus"
                state.failure_reason = "Pantheon consensus was reached, but verification produced no surviving invention."
            return state
        top = verified_inventions[0]
        state.final_verdict = str(getattr(top, "verdict", "UNKNOWN"))
        if state.consensus_achieved and getattr(top, "verdict", "UNKNOWN") == "INVALID":
            state.consensus_achieved = False
            state.resolution = "verifier_rejected_consensus"
            state.failure_reason = "Pantheon consensus selected an invention that verification later invalidated."
            state.unresolved_vetoes = [
                *state.unresolved_vetoes,
                "VERIFIER_INVALIDATED_TOP_INVENTION",
            ]
        return state


__all__ = ["PantheonCoordinator", "PantheonError"]
