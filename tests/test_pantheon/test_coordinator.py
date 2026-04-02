from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hephaestus.core.translator import Translation
from hephaestus.pantheon.coordinator import PantheonCoordinator
from hephaestus.pantheon.models import AthenaCanon, HermesDossier, PantheonState


class _Harness:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self._outputs = outputs

    async def forge(self, prompt: str, system: str | None = None):
        payload = self._outputs.pop(0)
        return SimpleNamespace(output=json.dumps(payload), trace=SimpleNamespace(total_cost_usd=0.0))


class _TranslatorStub:
    def __init__(self, outputs: list[dict[str, object]] | None = None) -> None:
        self._outputs = outputs or []

    async def reforge(self, *, prompt: str, structure: object, source_translation: Translation, system: str | None = None) -> Translation:
        payload = self._outputs.pop(0)
        return Translation(
            invention_name=str(payload.get("invention_name", source_translation.invention_name)),
            mapping=[],
            architecture=str(payload.get("architecture", source_translation.architecture)),
            mathematical_proof=str(payload.get("mathematical_proof", source_translation.mathematical_proof)),
            limitations=[str(item) for item in payload.get("limitations", source_translation.limitations)],
            implementation_notes=str(payload.get("implementation_notes", source_translation.implementation_notes)),
            key_insight=str(payload.get("key_insight", source_translation.key_insight)),
            source_candidate=source_translation.source_candidate,
            phase1_abstract_mechanism=str(payload.get("phase1_abstract_mechanism", source_translation.phase1_abstract_mechanism)),
            phase2_target_architecture=str(payload.get("phase2_target_architecture", source_translation.phase2_target_architecture)),
            mechanism_is_decorative=bool(payload.get("mechanism_is_decorative", False)),
            known_pattern_if_decorative=str(payload.get("known_pattern_if_decorative", "")),
            mechanism_differs_from_baseline=str(payload.get("mechanism_differs_from_baseline", source_translation.mechanism_differs_from_baseline)),
            subtraction_test=str(payload.get("subtraction_test", source_translation.subtraction_test)),
            baseline_comparison=str(payload.get("baseline_comparison", source_translation.baseline_comparison)),
            recovery_commitments=[str(item) for item in payload.get("recovery_commitments", source_translation.recovery_commitments)],
            future_option_preservation=str(payload.get("future_option_preservation", source_translation.future_option_preservation)),
        )


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
    athena = _Harness([
        {
            "structural_form": "canonical topology",
            "mandatory_constraints": ["preserve operator trust"],
            "decomposition_axes": ["trust propagation", "bounded revocation"],
            "anti_goals": ["centralized authority"],
            "success_criteria": ["bounded blast radius"],
            "false_framings": ["identity-first framing"],
            "confidence": 0.9,
        }
    ])
    hermes = _Harness([
        {
            "repo_reality_summary": "operators need incremental rollout",
            "ecosystem_constraints": ["must coexist with existing authz"],
            "user_operator_constraints": ["debuggability"],
            "adoption_risks": ["migration fatigue"],
            "implementation_leverage_points": ["existing graph index"],
            "confidence": 0.8,
        }
    ])
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
    hermes = _Harness([
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
    ])
    apollo = _Harness([
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
    ])
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
async def test_pantheon_deliberation_reaches_consensus() -> None:
    athena = _Harness([
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
    ])
    hermes = _Harness([
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
    ])
    apollo = _Harness([
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
    ])

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
        translator=_TranslatorStub([{}]),
        baseline_dossier=None,
    )
    assert len(translations) == 1
    assert state.consensus_achieved is True
    assert state.resolution == "consensus"
    assert state.winning_candidate_id is not None
    assert state.rounds[-1].consensus is True
    assert state.accounting.agent_call_counts == {
        "athena": 2,
        "hermes": 2,
        "apollo": 1,
    }


@pytest.mark.asyncio
async def test_pantheon_deliberation_reforges_after_veto() -> None:
    athena = _Harness([
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
    ])
    hermes = _Harness([
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
    ])
    apollo = _Harness([
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
    ])
    translator = _TranslatorStub([
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
        }
    ])

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
    assert state.resolution == "consensus"
    assert len(state.rounds) == 2
    assert state.rounds[0].consensus is False
    assert state.rounds[1].consensus is True
    assert state.accounting.agent_call_counts == {
        "athena": 3,
        "hermes": 3,
        "apollo": 2,
        "hephaestus": 1,
    }


@pytest.mark.asyncio
async def test_pantheon_fail_closed_rejects_when_enabled() -> None:
    athena = _Harness([
        {"structural_form": "shape", "confidence": 0.9},
        {
            "decision": "VETO",
            "veto_type": "STRUCTURAL",
            "reasons": ["bad structure"],
            "must_change": ["fix structure"],
            "must_preserve": [],
            "confidence": 0.9,
        },
    ])
    hermes = _Harness([
        {"repo_reality_summary": "grounded", "confidence": 0.8},
        {
            "decision": "VETO",
            "veto_type": "REALITY",
            "reasons": ["not deployable"],
            "must_change": ["address deployment"],
            "must_preserve": [],
            "confidence": 0.8,
        },
    ])
    apollo = _Harness([
        {
            "candidate_id": "cand-1",
            "verdict": "INVALID",
            "fatal_flaws": ["invalid"],
            "proof_obligations": [],
            "reasons": ["fails"],
            "confidence": 0.9,
        }
    ])

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
    assert "fail-closed" in (state.failure_reason or "")


@pytest.mark.asyncio
async def test_pantheon_fail_open_returns_survivor_when_disabled() -> None:
    athena = _Harness([
        {"structural_form": "shape", "confidence": 0.9},
        {
            "decision": "VETO",
            "veto_type": "STRUCTURAL",
            "reasons": ["bad structure"],
            "must_change": ["fix structure"],
            "must_preserve": [],
            "confidence": 0.9,
        },
    ])
    hermes = _Harness([
        {"repo_reality_summary": "grounded", "confidence": 0.8},
        {
            "decision": "VETO",
            "veto_type": "REALITY",
            "reasons": ["not deployable"],
            "must_change": ["address deployment"],
            "must_preserve": [],
            "confidence": 0.8,
        },
    ])
    apollo = _Harness([
        {
            "candidate_id": "cand-1",
            "verdict": "INVALID",
            "fatal_flaws": ["invalid"],
            "proof_obligations": [],
            "reasons": ["fails"],
            "confidence": 0.9,
        }
    ])

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
    assert translations[0].invention_name == "Base Invention"
    assert state.consensus_achieved is False
    assert state.winning_candidate_id == "candidate-1:Base Invention"
    assert state.resolution == "fallback_open"
