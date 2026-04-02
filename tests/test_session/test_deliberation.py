"""Tests for typed deliberation graph runtime state."""

from __future__ import annotations

from hephaestus.session.deliberation import DeliberationGraph, RuntimeRouter


def test_deliberation_graph_roundtrip_and_candidate_refresh() -> None:
    graph = DeliberationGraph(workflow_kind="genesis", goal="test goal")
    graph.record_stage("search", "Found candidates.")
    graph.ensure_candidate(
        "candidate-1:test",
        source_domain="biology",
        status="alive",
        route="search",
    )
    claim = graph.add_claim(
        "candidate-1:test",
        "The mechanism preserves adaptive state across retries.",
        kind="mechanism",
        stage="translate",
    )
    evidence = graph.add_evidence(
        kind="prior_art",
        summary="No direct prior art found.",
        source_url="https://example.com/prior-art",
    )
    graph.link_evidence(evidence.evidence_id, [claim.claim_id])
    graph.add_verifier_check(
        "candidate-1:test",
        layer="deterministic",
        name="claim_evidence_coverage",
        status="passed",
        score=1.0,
    )
    graph.mark_final("candidate-1:test", reason="verification_complete")

    restored = DeliberationGraph.from_dict(graph.to_dict())

    assert restored is not None
    assert restored.final_candidate_id == "candidate-1:test"
    assert restored.stop_reason == "verification_complete"
    assert restored.candidates[0].status == "finalist"
    assert restored.candidates[0].evidence_coverage == 1.0
    assert restored.claims[0].evidence_refs == [evidence.evidence_id]


def test_runtime_router_narrows_frontier_for_clear_leader() -> None:
    class _Scored:
        def __init__(self, score: float) -> None:
            self.combined_score = score

    frontier, reason = RuntimeRouter.recommend_translation_frontier(
        [_Scored(0.91), _Scored(0.68), _Scored(0.62)],
        configured_top_n=3,
        pantheon_enabled=False,
    )

    assert frontier == 2
    assert "narrower" in reason.lower()
