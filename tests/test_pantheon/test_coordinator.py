from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from hephaestus.core.translator import Translation
from hephaestus.pantheon.coordinator import PantheonCoordinator
from hephaestus.pantheon.models import AthenaCanon, HermesDossier, PantheonObjection, PantheonState


class _Harness:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self._outputs = outputs
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    async def forge(self, prompt: str, system: str | None = None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if not self._outputs:
            raise AssertionError("Harness was called more times than expected.")
        payload = self._outputs.pop(0)
        return SimpleNamespace(
            output=json.dumps(payload), trace=SimpleNamespace(total_cost_usd=0.0)
        )


class _TranslatorStub:
    def __init__(self, outputs: list[dict[str, object]] | None = None) -> None:
        self._outputs = outputs or []
        self.calls: list[dict[str, object]] = []

    async def reforge(
        self,
        *,
        prompt: str,
        structure: object,
        source_translation: Translation,
        system: str | None = None,
    ) -> Translation:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "source_translation": source_translation.invention_name,
            }
        )
        if not self._outputs:
            raise AssertionError("Translator reforge was called more times than expected.")
        payload = self._outputs.pop(0)
        translation = Translation(
            invention_name=str(payload.get("invention_name", source_translation.invention_name)),
            mapping=[],
            architecture=str(payload.get("architecture", source_translation.architecture)),
            mathematical_proof=str(
                payload.get("mathematical_proof", source_translation.mathematical_proof)
            ),
            limitations=[
                str(item) for item in payload.get("limitations", source_translation.limitations)
            ],
            implementation_notes=str(
                payload.get("implementation_notes", source_translation.implementation_notes)
            ),
            key_insight=str(payload.get("key_insight", source_translation.key_insight)),
            source_candidate=source_translation.source_candidate,
            phase1_abstract_mechanism=str(
                payload.get(
                    "phase1_abstract_mechanism", source_translation.phase1_abstract_mechanism
                )
            ),
            phase2_target_architecture=str(
                payload.get(
                    "phase2_target_architecture", source_translation.phase2_target_architecture
                )
            ),
            mechanism_is_decorative=bool(payload.get("mechanism_is_decorative", False)),
            known_pattern_if_decorative=str(payload.get("known_pattern_if_decorative", "")),
            mechanism_differs_from_baseline=str(
                payload.get(
                    "mechanism_differs_from_baseline",
                    source_translation.mechanism_differs_from_baseline,
                )
            ),
            subtraction_test=str(
                payload.get("subtraction_test", source_translation.subtraction_test)
            ),
            baseline_comparison=str(
                payload.get("baseline_comparison", source_translation.baseline_comparison)
            ),
            recovery_commitments=[
                str(item)
                for item in payload.get(
                    "recovery_commitments", source_translation.recovery_commitments
                )
            ],
            future_option_preservation=str(
                payload.get(
                    "future_option_preservation", source_translation.future_option_preservation
                )
            ),
        )
        translation.pantheon_reforge_metadata = payload.get("pantheon_reforge", {})
        return translation


def _translation(name: str = "Base Invention") -> Translation:
    source_candidate = SimpleNamespace(source_domain="Physics", combined_score=0.88)
    return Translation(
        invention_name=name,
        mapping=[],
        architecture="Base architecture",
        mathematical_proof="proof",
        limitations=["none"],
        implementation_notes="notes",
        key_insight="novel key insight",
        source_candidate=source_candidate,
    )


@pytest.mark.asyncio
async def test_prepare_pipeline_revises_structure_and_emits_guidance() -> None:
    athena = _Harness(
        [
            {
                "structural_form": "canonical topology",
                "mandatory_constraints": ["preserve operator trust"],
                "decomposition_axes": ["trust propagation", "bounded revocation"],
                "anti_goals": ["centralized authority"],
                "success_criteria": ["bounded blast radius"],
                "false_framings": ["identity-first framing"],
                "confidence": 0.9,
            }
        ]
    )
    hermes = _Harness(
        [
            {
                "repo_reality_summary": "operators need incremental rollout",
                "ecosystem_constraints": ["must coexist with existing authz"],
                "user_operator_constraints": ["debuggability"],
                "adoption_risks": ["migration fatigue"],
                "implementation_leverage_points": ["existing graph index"],
                "confidence": 0.8,
            }
        ]
    )
    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=_Harness([]),
    )

    revised, state = await coordinator.prepare_pipeline(
        problem="test problem",
        structure=SimpleNamespace(
            structure="original topology",
            mathematical_shape="graph propagation",
            constraints=["original"],
            problem_maps_to={"routing"},
            native_domain="distributed_systems",
        ),
    )
    guidance = coordinator.translation_guidance(state)

    assert revised.structure == "canonical topology"
    assert "preserve operator trust" in revised.constraints
    assert "trust_propagation" in revised.problem_maps_to
    assert state.initial_structure is not None
    assert state.pipeline_structure is not None
    assert guidance is not None
    assert guidance.structural_form == "canonical topology"
    assert guidance.reality_summary == "operators need incremental rollout"


@pytest.mark.asyncio
async def test_screen_translations_prunes_apollo_invalid_before_council() -> None:
    hermes = _Harness(
        [
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["deployable"],
                "confidence": 0.9,
            },
            {
                "agent": "hermes",
                "decision": "VETO",
                "veto_type": "REALITY",
                "reasons": ["too much migration"],
                "confidence": 0.4,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "VALID",
                "fatal_flaws": [],
                "decorative_signals": [],
                "proof_obligations": [],
                "reasons": ["holds"],
                "confidence": 0.8,
            },
            {
                "candidate_id": "cand-2",
                "verdict": "INVALID",
                "fatal_flaws": ["missing causal chain"],
                "decorative_signals": [],
                "proof_obligations": ["show mechanism"],
                "reasons": ["fails"],
                "confidence": 0.9,
            },
        ]
    )
    coordinator = PantheonCoordinator(
        athena_harness=_Harness([]),
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_survivors_to_council=1,
    )
    state = PantheonState(
        mode="pantheon",
        canon=AthenaCanon(structural_form="canonical"),
        dossier=HermesDossier(repo_reality_summary="real"),
    )

    survivors, state = await coordinator.screen_translations(
        translations=[_translation("A"), _translation("B")],
        state=state,
    )

    assert [item.invention_name for item in survivors] == ["A"]
    assert len(state.screenings) == 2
    assert state.screenings[0].survived is True
    assert state.screenings[1].survived is False
    assert "missing causal chain" in state.screenings[1].prune_reasons
    assert len(state.survivor_candidate_ids) == 1


@pytest.mark.asyncio
async def test_pantheon_independent_ballots_mask_peer_issues_on_first_pass() -> None:
    athena = _Harness(
        [
            {
                "agent": "athena",
                "decision": "ASSENT",
                "reasons": ["structurally valid"],
                "must_change": [],
                "must_preserve": ["novel key insight"],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["rollout is manageable"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "VALID",
                "fatal_flaws": [],
                "structural_weaknesses": [],
                "decorative_signals": [],
                "proof_obligations": [],
                "reasons": ["truth-preserving"],
                "confidence": 0.9,
            }
        ]
    )
    candidate = _translation()
    candidate_id = "candidate-1:Base Invention"
    state = PantheonState(
        mode="pantheon",
        canon=AthenaCanon(structural_form="shape"),
        dossier=HermesDossier(repo_reality_summary="grounded"),
        survivor_candidate_ids=[candidate_id],
        objection_ledger=[
            PantheonObjection(
                objection_id="obj-hermes-screening",
                candidate_id=candidate_id,
                agent="hermes",
                issue_type="REALITY",
                severity="REPAIRABLE",
                claim_text="Needs a staged rollout path.",
                statement="Needs a staged rollout path.",
                required_change="Add a staged rollout path.",
                closure_test="The rollout plan can be staged without breaking operators.",
                discharge_test="The rollout plan can be staged without breaking operators.",
                evidence=["Initial screening flagged migration risk."],
                must_preserve=["operator value"],
                opened_by="hermes",
            )
        ],
    )
    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=1,
    )
    translator = _TranslatorStub([])

    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[candidate],
        translator=translator,
        baseline_dossier=None,
        state=state,
    )

    assert len(translations) == 1
    assert state.consensus_achieved is True
    assert state.debate_skip_reason == "independent_ballots_clear"
    assert "MASKED ISSUE LEDGER FOR THIS CANDIDATE:\n[]" in athena.prompts[0]
    assert translator.calls == []


@pytest.mark.asyncio
async def test_pantheon_deliberation_reaches_consensus() -> None:
    athena = _Harness(
        [
            {
                "structural_form": "right structure",
                "mandatory_constraints": ["c1"],
                "confidence": 0.9,
            },
            {
                "agent": "athena",
                "decision": "ASSENT",
                "reasons": ["structurally valid"],
                "must_change": [],
                "must_preserve": ["novel key insight"],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {
                "repo_reality_summary": "practical and grounded",
                "confidence": 0.8,
            },
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["real-world viable"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "VALID",
                "fatal_flaws": [],
                "structural_weaknesses": [],
                "decorative_signals": [],
                "proof_obligations": [],
                "reasons": ["survives scrutiny"],
                "confidence": 0.9,
            }
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=2,
    )
    translator = _TranslatorStub([{}])
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=translator,
        baseline_dossier=None,
    )
    assert len(translations) == 1
    assert state.consensus_achieved is True
    assert state.resolution == "unanimous_consensus"
    assert state.outcome_tier == "UNANIMOUS_CONSENSUS"
    assert state.debate_invoked is False
    assert state.debate_skip_reason == "independent_ballots_clear"
    assert state.winning_candidate_id is not None
    assert state.rounds[-1].consensus is True
    assert state.rounds[-1].phase == "independent_ballot"
    assert state.rounds[-1].outcome_tier == "UNANIMOUS_CONSENSUS"
    assert translator.calls == []
    assert state.accounting.agent_call_counts == {
        "athena": 2,
        "hermes": 2,
        "apollo": 1,
    }


@pytest.mark.asyncio
async def test_pantheon_deliberation_reforges_after_veto() -> None:
    athena = _Harness(
        [
            {
                "structural_form": "right structure",
                "mandatory_constraints": ["c1"],
                "confidence": 0.9,
            },
            {
                "agent": "athena",
                "decision": "VETO",
                "veto_type": "STRUCTURAL",
                "reasons": ["wrong abstraction"],
                "must_change": ["tighten architecture"],
                "must_preserve": ["novel key insight"],
                "confidence": 0.9,
            },
            {
                "agent": "athena",
                "decision": "ASSENT",
                "reasons": ["fixed"],
                "must_change": [],
                "must_preserve": ["novel key insight"],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {
                "repo_reality_summary": "practical and grounded",
                "confidence": 0.8,
            },
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["real-world viable"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["still viable"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "INVALID",
                "fatal_flaws": ["missing causal link"],
                "structural_weaknesses": [],
                "decorative_signals": [],
                "proof_obligations": ["make state transition explicit"],
                "reasons": ["fails scrutiny"],
                "confidence": 0.9,
            },
            {
                "candidate_id": "cand-1",
                "verdict": "VALID",
                "fatal_flaws": [],
                "structural_weaknesses": [],
                "decorative_signals": [],
                "proof_obligations": [],
                "reasons": ["now valid"],
                "confidence": 0.9,
            },
        ]
    )
    translator = _TranslatorStub(
        [
            {
                "invention_name": "Reforged Invention",
                "architecture": "Reforged architecture",
                "mapping": {"elements": []},
                "mathematical_proof": "proof",
                "limitations": ["none"],
                "implementation_notes": "notes",
                "key_insight": "novel key insight",
                "phase1_abstract_mechanism": "abstract mechanism",
                "phase2_target_architecture": "Reforged architecture",
                "mechanism_is_decorative": False,
                "known_pattern_if_decorative": "",
                "mechanism_differs_from_baseline": "yes",
                "subtraction_test": "clean",
                "baseline_comparison": "better",
                "recovery_commitments": ["preserved novelty core"],
                "future_option_preservation": "keeps future option open",
                "pantheon_reforge": {
                    "addressed_objection_ids": ["obj-apollo-a"],
                    "remaining_open_objection_ids": [],
                    "changes_made": [
                        "Made the causal state transition explicit without collapsing the mechanism."
                    ],
                    "novelty_core_preserved": "novel key insight",
                },
            },
            {
                "invention_name": "Structural Patch Branch",
                "architecture": "Structural patch architecture",
                "mapping": {"elements": []},
                "mathematical_proof": "proof",
                "limitations": ["none"],
                "implementation_notes": "notes",
                "key_insight": "novel key insight",
                "phase1_abstract_mechanism": "abstract mechanism",
                "phase2_target_architecture": "Structural patch architecture",
                "mechanism_is_decorative": False,
                "known_pattern_if_decorative": "",
                "mechanism_differs_from_baseline": "yes",
                "subtraction_test": "clean",
                "baseline_comparison": "better",
                "recovery_commitments": ["preserved novelty core"],
                "future_option_preservation": "keeps future option open",
                "pantheon_reforge": {
                    "addressed_objection_ids": ["obj-athena-b"],
                    "remaining_open_objection_ids": [],
                    "changes_made": ["Tightened the architecture around the state transition."],
                    "novelty_core_preserved": "novel key insight",
                },
            },
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=2,
    )
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=translator,
        baseline_dossier=None,
    )
    assert len(translations) == 1
    assert translations[0].invention_name == "Reforged Invention"
    assert state.consensus_achieved is True
    assert state.resolution == "unanimous_consensus"
    assert state.outcome_tier == "UNANIMOUS_CONSENSUS"
    assert len(state.rounds) == 2
    assert state.debate_invoked is True
    assert state.rounds[0].consensus is False
    assert state.rounds[0].phase == "independent_ballot"
    assert state.rounds[0].branch_candidates_considered == 2
    assert state.rounds[1].consensus is True
    assert state.rounds[1].phase == "council"
    assert any(objection.status == "RESOLVED" for objection in state.objection_ledger)
    assert state.branches_spawned_for_repair == 2
    assert len(translator.calls) == 2
    assert state.accounting.agent_call_counts == {
        "athena": 3,
        "hermes": 3,
        "apollo": 2,
        "hephaestus": 2,
    }


@pytest.mark.asyncio
async def test_pantheon_fail_closed_rejects_when_enabled() -> None:
    athena = _Harness(
        [
            {"structural_form": "shape", "confidence": 0.9},
            {
                "decision": "VETO",
                "veto_type": "STRUCTURAL",
                "reasons": ["bad structure"],
                "must_change": ["fix structure"],
                "must_preserve": [],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {"repo_reality_summary": "grounded", "confidence": 0.8},
            {
                "decision": "VETO",
                "veto_type": "REALITY",
                "reasons": ["not deployable"],
                "must_change": ["address deployment"],
                "must_preserve": [],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "INVALID",
                "fatal_flaws": ["invalid"],
                "proof_obligations": [],
                "reasons": ["fails"],
                "confidence": 0.9,
            }
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=1,
        allow_fail_closed=True,
    )
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=_TranslatorStub([{}]),
        baseline_dossier=None,
    )

    assert translations == []
    assert state.consensus_achieved is False
    assert state.winning_candidate_id is None
    assert state.resolution == "fail_closed_rejection"
    assert state.outcome_tier == "FAIL_CLOSED_REJECTION"
    assert "fail-closed" in (state.failure_reason or "")


@pytest.mark.asyncio
async def test_pantheon_still_fail_closes_fatal_truth_when_fail_closed_disabled() -> None:
    athena = _Harness(
        [
            {"structural_form": "shape", "confidence": 0.9},
            {
                "decision": "VETO",
                "veto_type": "STRUCTURAL",
                "reasons": ["bad structure"],
                "must_change": ["fix structure"],
                "must_preserve": [],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {"repo_reality_summary": "grounded", "confidence": 0.8},
            {
                "decision": "VETO",
                "veto_type": "REALITY",
                "reasons": ["not deployable"],
                "must_change": ["address deployment"],
                "must_preserve": [],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "INVALID",
                "fatal_flaws": ["invalid"],
                "proof_obligations": [],
                "reasons": ["fails"],
                "confidence": 0.9,
            }
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=1,
        allow_fail_closed=False,
    )
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=_TranslatorStub([{}]),
        baseline_dossier=None,
    )

    assert translations == []
    assert state.consensus_achieved is False
    assert state.outcome_tier == "FAIL_CLOSED_REJECTION"
    assert state.resolution == "fail_closed_rejection"


@pytest.mark.asyncio
async def test_pantheon_qualified_consensus_preserves_advisory_caveat() -> None:
    athena = _Harness(
        [
            {"structural_form": "shape", "confidence": 0.9},
            {
                "agent": "athena",
                "decision": "ASSENT",
                "reasons": ["structurally sound"],
                "must_change": [],
                "must_preserve": ["novel key insight"],
                "objections": [
                    {
                        "severity": "ADVISORY",
                        "statement": "Observe the first deployment cohort for control-loop oscillation.",
                        "required_change": "Track control-loop oscillation during the first rollout cohort.",
                        "closure_test": "Operational telemetry shows no runaway oscillation in the first rollout cohort.",
                    }
                ],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {"repo_reality_summary": "grounded", "confidence": 0.8},
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["deployable"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "VALID",
                "fatal_flaws": [],
                "structural_weaknesses": [],
                "decorative_signals": [],
                "proof_obligations": [],
                "reasons": ["truth-preserving"],
                "confidence": 0.9,
            }
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=1,
    )
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=_TranslatorStub([{}]),
        baseline_dossier=None,
    )

    assert len(translations) == 1
    assert state.consensus_achieved is True
    assert state.outcome_tier == "QUALIFIED_CONSENSUS"
    assert state.resolution == "qualified_consensus"
    assert state.caveats
    assert any(objection.status == "WAIVED" for objection in state.objection_ledger)


@pytest.mark.asyncio
async def test_pantheon_forwards_repairable_truth_candidate_with_open_issues() -> None:
    athena = _Harness(
        [
            {"structural_form": "shape", "confidence": 0.9},
            {
                "agent": "athena",
                "decision": "ASSENT",
                "reasons": ["structurally right"],
                "must_change": [],
                "must_preserve": ["novel key insight"],
                "confidence": 0.9,
            },
        ]
    )
    hermes = _Harness(
        [
            {"repo_reality_summary": "grounded", "confidence": 0.8},
            {
                "agent": "hermes",
                "decision": "ASSENT",
                "reasons": ["practical enough"],
                "must_change": [],
                "must_preserve": ["operator value"],
                "confidence": 0.8,
            },
        ]
    )
    apollo = _Harness(
        [
            {
                "candidate_id": "cand-1",
                "verdict": "PROVISIONAL",
                "fatal_flaws": [],
                "structural_weaknesses": ["causal proof is underspecified"],
                "decorative_signals": [],
                "proof_obligations": ["Make the state transition proof explicit."],
                "reasons": ["under-proven but coherent"],
                "confidence": 0.8,
            }
        ]
    )

    coordinator = PantheonCoordinator(
        athena_harness=athena,
        hermes_harness=hermes,
        apollo_harness=apollo,
        max_rounds=1,
        allow_fail_closed=False,
    )
    translations, state = await coordinator.deliberate(
        problem="test problem",
        structure=SimpleNamespace(structure="shape", mathematical_shape="shape", constraints=[]),
        translations=[_translation()],
        translator=_TranslatorStub([{}]),
        baseline_dossier=None,
    )

    assert len(translations) == 1
    assert state.consensus_achieved is False
    assert state.outcome_tier == "FORWARDED_WITH_OPEN_ISSUES"
    assert state.resolution == "forward_with_open_issues"
    assert state.forwarded_candidate_ids == [state.winning_candidate_id]
    assert state.caveats
    assert any("Make the state transition proof explicit." in caveat for caveat in state.caveats)
