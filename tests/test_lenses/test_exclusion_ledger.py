"""Tests for the adaptive exclusion ledger."""

from __future__ import annotations

from pathlib import Path

from hephaestus.lenses.exclusion_ledger import AdaptiveExclusionLedger


def test_family_fatigue_and_novelty_saturation_reduce_multiplier() -> None:
    ledger = AdaptiveExclusionLedger()
    ledger.register_selected(
        lens_ids=["biology_immune"],
        families=["biology"],
        novelty_axes=["memory", "selection"],
    )
    ledger.register_selected(
        lens_ids=["biology_swarm"],
        families=["biology"],
        novelty_axes=["memory", "coordination"],
    )

    decision = ledger.decide(
        families=["biology"],
        novelty_axes=["memory"],
        proof_token="proof_1",
    )

    assert decision.blocked is False
    assert decision.family_fatigue > 0.0
    assert decision.novelty_saturation > 0.0
    assert decision.multiplier < 1.0


def test_blocked_proofs_are_rejected_and_persisted(tmp_path: Path) -> None:
    ledger = AdaptiveExclusionLedger()
    ledger.block_proof("bundle_1", "stale bundle proof")
    decision = ledger.decide(
        families=["economics"],
        novelty_axes=["pricing"],
        proof_token="bundle_1",
    )

    assert decision.blocked is True
    assert "stale bundle proof" in decision.reasons[0]

    target = tmp_path / "ledger.json"
    ledger.save(target)
    loaded = AdaptiveExclusionLedger.load(target)
    assert loaded.is_proof_blocked("bundle_1") is True
