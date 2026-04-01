"""
Tests for append-only failure persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.analytics.failure_log import (
    FailureLog,
    FailureRecord,
    VerifierCritique,
    detect_baseline_overlaps,
)
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.core.verifier import AdversarialResult, VerifiedInvention
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_lens() -> Lens:
    return Lens(
        name="Immune System",
        domain="biology",
        subdomain="immune",
        axioms=["Distributed memory", "Thresholded activation"],
        structural_patterns=[
            StructuralPattern("clonal", "Amplify successful responses", ["allocation"])
        ],
        injection_prompt="Reason as an immune system.",
    )


def _make_scored_candidate(source_domain: str = "Immune System — T-Cell Memory") -> ScoredCandidate:
    lens = _make_lens()
    score = LensScore(
        lens=lens,
        domain_distance=0.85,
        structural_relevance=0.8,
        composite_score=0.7,
        matched_patterns=["allocation"],
    )
    candidate = SearchCandidate(
        source_domain=source_domain,
        source_solution="Memory cells cache successful responses",
        mechanism="Clonal expansion reinforces known good paths",
        structural_mapping="Task cache maps to immune memory",
        lens_used=lens,
        lens_score=score,
        confidence=0.88,
        cost_usd=0.01,
    )
    return ScoredCandidate(
        candidate=candidate,
        structural_fidelity=0.82,
        domain_distance=0.85,
        combined_score=0.67,
        fidelity_reasoning="Strong cross-domain mapping",
        scoring_cost_usd=0.01,
    )


def _make_translation(name: str = "Immune-Memory Scheduler") -> Translation:
    return Translation(
        invention_name=name,
        mapping=[
            ElementMapping(
                source_element="Memory cell",
                target_element="Task cache entry",
                mechanism="Both preserve successful responses for rapid reuse",
            )
        ],
        architecture=(
            "The scheduler maintains a memory layer that caches successful task execution "
            "patterns and routes similar tasks directly into the remembered path."
        ),
        mathematical_proof="M maps to C under structural isomorphism",
        limitations=["Requires careful invalidation of stale cache entries"],
        implementation_notes="Use a distributed cache plus health signals",
        key_insight="Persist successful execution patterns and reactivate them quickly",
        source_candidate=_make_scored_candidate(),
        cost_usd=0.02,
    )


def _make_verified_invention(
    *,
    verdict: str = "INVALID",
    fatal_flaws: list[str] | None = None,
    feasibility_rating: str = "LOW",
    novelty_score: float = 0.33,
) -> VerifiedInvention:
    flaws = fatal_flaws if fatal_flaws is not None else ["Mapping collapses under stale cache."]
    attack = AdversarialResult(
        attack_valid=bool(flaws),
        fatal_flaws=flaws,
        structural_weaknesses=["Recovery semantics are underspecified"],
        strongest_objection="The cache becomes a single stale point of failure",
        novelty_risk=0.65,
        verdict=verdict,
    )
    return VerifiedInvention(
        invention_name="Immune-Memory Scheduler",
        translation=_make_translation(),
        novelty_score=novelty_score,
        structural_validity=0.42,
        implementation_feasibility=0.35,
        feasibility_rating=feasibility_rating,
        adversarial_result=attack,
        prior_art_status="POSSIBLE_PRIOR_ART",
        validity_notes="The mapping loses fidelity once cache invalidation starts dominating.",
        feasibility_notes="Requires stronger invalidation guarantees than the analogy provides.",
        novelty_notes="Similar cache-first schedulers likely exist already.",
    )


class TestBaselineOverlapDetection:
    def test_detects_substring_and_token_overlap(self):
        invention_text = (
            "The design caches successful task execution patterns and reuses them on "
            "later matching requests."
        )
        baselines = [
            "task execution patterns",
            "totally unrelated baseline",
        ]

        overlaps = detect_baseline_overlaps(invention_text, baselines)

        assert overlaps == ["task execution patterns"]


class TestFailureRecord:
    def test_from_verified_invention_infers_reasons_and_critique(self):
        invention = _make_verified_invention()

        record = FailureRecord.from_verified_invention(
            invention,
            target_domain="distributed_systems",
            problem="Need a fault-tolerant scheduler",
            baselines=["caches successful task execution patterns"],
            timestamp=datetime(2026, 4, 1, 12, tzinfo=UTC),
        )

        assert record.problem == "Need a fault-tolerant scheduler"
        assert record.domain_pair == (
            "Immune System — T-Cell Memory",
            "distributed_systems",
        )
        assert record.rejection_reasons == [
            "fatal_flaws",
            "verdict_invalid",
            "low_feasibility",
            "baseline_overlap",
        ]
        assert record.baseline_overlaps == ["caches successful task execution patterns"]
        assert record.verifier_critique.verdict == "INVALID"
        assert "stale point of failure" in record.verifier_critique.strongest_objection
        assert record.timestamp == "2026-04-01T12:00:00+00:00"

    def test_round_trip_serialization(self):
        record = FailureRecord(
            invention_name="Rejected invention",
            source_domain="biology",
            target_domain="distributed_systems",
            rejection_reasons=["verdict_derivative"],
            verifier_critique=VerifierCritique(verdict="DERIVATIVE"),
        )

        restored = FailureRecord.from_dict(record.to_dict())

        assert restored.invention_name == record.invention_name
        assert restored.domain_pair == record.domain_pair
        assert restored.rejection_reasons == ["verdict_derivative"]


class TestFailureLog:
    def test_append_and_query_round_trip(self, tmp_path):
        log = FailureLog(tmp_path / "failures")
        record = FailureRecord(
            invention_name="Rejected invention",
            source_domain="biology",
            target_domain="distributed_systems",
            rejection_reasons=["verdict_derivative"],
            verifier_critique=VerifierCritique(verdict="DERIVATIVE"),
            timestamp="2026-04-01T08:00:00+00:00",
            baseline_overlaps=["obvious retry queue"],
        )

        path = log.append(record)
        queried = log.query()

        assert path.name == "2026-04-01.jsonl"
        assert path.exists()
        assert len(queried) == 1
        assert queried[0].invention_name == "Rejected invention"
        assert queried[0].baseline_overlaps == ["obvious retry queue"]

    def test_append_rejected_inventions_only_persists_rejected(self, tmp_path):
        log = FailureLog(tmp_path / "failures")
        rejected = _make_verified_invention()
        accepted = _make_verified_invention(
            verdict="NOVEL",
            fatal_flaws=[],
            feasibility_rating="HIGH",
            novelty_score=0.9,
        )

        records = log.append_rejected_inventions(
            [accepted, rejected],
            target_domain="distributed_systems",
        )

        queried = log.query()

        assert len(records) == 1
        assert len(queried) == 1
        assert queried[0].invention_name == rejected.invention_name
        assert "verdict_invalid" in queried[0].rejection_reasons

    def test_query_filters_by_reason_domain_pair_and_time(self, tmp_path):
        log = FailureLog(tmp_path / "failures")
        first = FailureRecord(
            invention_name="Older failure",
            source_domain="biology",
            target_domain="distributed_systems",
            rejection_reasons=["fatal_flaws"],
            verifier_critique=VerifierCritique(verdict="INVALID"),
            timestamp="2026-04-01T09:00:00+00:00",
        )
        second = FailureRecord(
            invention_name="Newer derivative",
            source_domain="economics",
            target_domain="distributed_systems",
            rejection_reasons=["verdict_derivative", "baseline_overlap"],
            verifier_critique=VerifierCritique(verdict="DERIVATIVE"),
            baseline_overlaps=["dynamic pricing scheduler"],
            timestamp="2026-04-02T09:00:00+00:00",
        )
        log.append_many([first, second])

        by_reason = log.query(rejection_reason="baseline_overlap")
        by_pair = log.query(domain_pair=("economics", "distributed_systems"))
        by_time = log.query(
            since="2026-04-02T00:00:00+00:00",
            verdict="DERIVATIVE",
            limit=1,
        )

        assert [record.invention_name for record in by_reason] == ["Newer derivative"]
        assert [record.invention_name for record in by_pair] == ["Newer derivative"]
        assert [record.invention_name for record in by_time] == ["Newer derivative"]

    def test_query_returns_empty_when_log_dir_missing(self, tmp_path):
        log = FailureLog(tmp_path / "missing")

        assert log.query() == []
