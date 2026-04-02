from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hephaestus.core.translator import Translation
from hephaestus.pantheon.coordinator import PantheonCoordinator


class _Harness:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self._outputs = outputs

    async def forge(self, prompt: str, system: str | None = None):
        payload = self._outputs.pop(0)
        return SimpleNamespace(output=json.dumps(payload), trace=SimpleNamespace(total_cost_usd=0.0))


class _TranslatorStub:
    def __init__(self, outputs: list[dict[str, object]] | None = None) -> None:
        self._harness = _Harness(outputs or [])

    def _parse_translation(self, raw: str):
        return json.loads(raw)


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
        translator=_TranslatorStub(),
        baseline_dossier=None,
    )
    assert len(translations) == 1
    assert state.consensus_achieved is True
    assert state.winning_candidate_id is not None
    assert state.rounds[-1].consensus is True


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
    assert len(state.rounds) == 2
    assert state.rounds[0].consensus is False
    assert state.rounds[1].consensus is True
