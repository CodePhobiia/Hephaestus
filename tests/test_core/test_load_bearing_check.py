"""
Tests for the load-bearing domain check.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.core.load_bearing_check import (
    DomainLoadBearingAssessment,
    check_load_bearing_domains,
    check_source_domain_subtraction,
)
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.core.translator import ElementMapping, Translation
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


def _make_lens(
    name: str = "Immune System",
    domain: str = "biology",
    axioms: list[str] | None = None,
) -> Lens:
    return Lens(
        name=name,
        domain=domain,
        subdomain=domain,
        axioms=axioms or [
            "Memory persists successful responses.",
            "Clonal expansion reinforces effective defenses.",
        ],
        structural_patterns=[
            StructuralPattern("allocation", "Allocate resources under pressure", ["allocation"])
        ],
        injection_prompt=f"You are reasoning as {name}.",
    )


def _make_scored_candidate(
    *,
    source_domain: str,
    source_solution: str,
    mechanism: str,
    lens: Lens,
) -> ScoredCandidate:
    lens_score = LensScore(
        lens=lens,
        domain_distance=0.85,
        structural_relevance=0.8,
        composite_score=0.72,
        matched_patterns=["allocation"],
    )
    candidate = SearchCandidate(
        source_domain=source_domain,
        source_solution=source_solution,
        mechanism=mechanism,
        structural_mapping="Structural mapping exists",
        lens_used=lens,
        lens_score=lens_score,
        confidence=0.85,
    )
    return ScoredCandidate(
        candidate=candidate,
        structural_fidelity=0.82,
        domain_distance=0.85,
        combined_score=0.72,
        fidelity_reasoning="Strong structural match",
        strong_mappings=["mapping"],
        weak_mappings=[],
    )


def _make_load_bearing_translation() -> Translation:
    lens = _make_lens(
        name="Immune System",
        domain="biology",
        axioms=[
            "Immune memory persists successful responses.",
            "Clonal expansion amplifies useful defenses.",
        ],
    )
    candidate = _make_scored_candidate(
        source_domain="Immune System — T-Cell Memory",
        source_solution="T-cell memory persists successful responses through clonal expansion",
        mechanism="Immune memory stores successful responses and recalls them rapidly",
        lens=lens,
    )
    return Translation(
        invention_name="Immune-Memory Scheduler",
        mapping=[
            ElementMapping(
                "T-cell receptor",
                "task signature",
                "Both classify incoming work before a response is selected.",
            ),
            ElementMapping(
                "memory cell",
                "cached execution plan",
                "Both store proven responses so the next encounter can skip rediscovery.",
            ),
            ElementMapping(
                "clonal expansion",
                "elastic worker pool",
                "Both rapidly amplify capacity once a promising response is found.",
            ),
        ],
        architecture=(
            "The scheduler keeps an immune memory layer keyed by task signature. "
            "When a task family succeeds, the system promotes the cached execution plan "
            "into a fast path. During load spikes it triggers clonal expansion in the "
            "elastic worker pool, temporarily over-allocating healthy workers to the same "
            "task signature until the queue clears."
        ),
        mathematical_proof="Successful task signatures map onto immune recall classes.",
        limitations=[
            "There is no perfect MHC equivalent for exposing every task feature.",
            "Clonal expansion needs a cooldown policy to avoid runaway worker growth.",
        ],
        implementation_notes=(
            "Use Redis for the cached execution plan, per-signature counters for recall, "
            "and autoscaling hooks to grow the elastic worker pool."
        ),
        key_insight=(
            "Immune memory turns prior success into a reusable execution primitive for "
            "future task signatures."
        ),
        source_candidate=candidate,
    )


def _make_decorative_source_translation() -> Translation:
    lens = _make_lens(
        name="Volcanology",
        domain="geology",
        axioms=["Pressure accumulates until it is released."],
    )
    candidate = _make_scored_candidate(
        source_domain="Volcanology — Eruption Dynamics",
        source_solution="Volcanoes release accumulated pressure through eruptions",
        mechanism="Pressure accumulates until a sudden release event occurs",
        lens=lens,
    )
    return Translation(
        invention_name="Burst Autoscaler",
        mapping=[
            ElementMapping(
                "magma pressure",
                "queue depth",
                "Both build up over time before an intervention occurs.",
            ),
            ElementMapping(
                "eruption",
                "burst response",
                "Both release built-up pressure once a threshold is crossed.",
            ),
        ],
        architecture=(
            "Monitor queue depth and request latency. When queue depth crosses the threshold, "
            "pre-warm workers and apply rate limits until backlog returns to normal."
        ),
        mathematical_proof="Queue depth crossing a threshold triggers scaling.",
        limitations=["Rate limits can reduce throughput during sustained bursts."],
        implementation_notes=(
            "Use queue metrics, autoscaling policies, and pre-warmed workers."
        ),
        key_insight="Threshold-based autoscaling handles burst traffic.",
        source_candidate=candidate,
    )


def _make_decorative_target_translation() -> Translation:
    lens = _make_lens(
        name="Ant Colony",
        domain="biology",
        axioms=[
            "Pheromone trails reinforce successful paths.",
            "Trails evaporate when they stop being useful.",
        ],
    )
    candidate = _make_scored_candidate(
        source_domain="Ant Colony Routing",
        source_solution="Ant colonies reinforce successful paths with pheromone trails",
        mechanism="Agents reinforce successful paths by depositing pheromones",
        lens=lens,
    )
    return Translation(
        invention_name="Pheromone Controller",
        mapping=[
            ElementMapping(
                "pheromone trail",
                "system signal",
                "Both bias future movement toward previously successful paths.",
            ),
            ElementMapping(
                "scout ant",
                "control agent",
                "Both explore options and report what seems promising.",
            ),
            ElementMapping(
                "food source",
                "desired outcome",
                "Both define what counts as success.",
            ),
        ],
        architecture=(
            "Use pheromone trails. Scout ants reinforce successful paths. "
            "Pheromone trails evaporate when a path becomes stale."
        ),
        mathematical_proof="Reinforced paths dominate over time.",
        limitations=["Pheromone trails can lock onto a local optimum."],
        implementation_notes="",
        key_insight="Pheromone reinforcement stabilizes path discovery.",
        source_candidate=candidate,
    )


class TestDomainLoadBearingAssessment:
    def test_creation(self):
        assessment = DomainLoadBearingAssessment(
            domain_name="biology",
            is_load_bearing=True,
            mechanism_survives_without_domain=False,
            reasons=["Source logic still appears at runtime."],
            confidence=0.82,
        )

        assert assessment.domain_name == "biology"
        assert assessment.is_load_bearing
        assert assessment.confidence == pytest.approx(0.82)


class TestCheckSourceDomainSubtraction:
    def test_detects_load_bearing_source_domain(self):
        assessment = check_source_domain_subtraction(_make_load_bearing_translation())

        assert assessment.is_load_bearing
        assert not assessment.mechanism_survives_without_domain
        assert any("source-derived operators" in reason for reason in assessment.reasons)

    def test_detects_decorative_source_domain(self):
        assessment = check_source_domain_subtraction(_make_decorative_source_translation())

        assert not assessment.is_load_bearing
        assert assessment.mechanism_survives_without_domain
        assert any("largely intact" in reason for reason in assessment.reasons)


class TestCheckLoadBearingDomains:
    @pytest.mark.asyncio
    async def test_passes_when_both_domains_are_structurally_necessary(self):
        result = await check_load_bearing_domains(_make_load_bearing_translation())

        assert result.passed
        assert result.source_assessment.is_load_bearing
        assert result.target_assessment.is_load_bearing
        assert "load-bearing=PASS" in result.summary()

    @pytest.mark.asyncio
    async def test_fails_when_target_domain_is_decorative(self):
        result = await check_load_bearing_domains(_make_decorative_target_translation())

        assert not result.passed
        assert result.source_assessment.is_load_bearing
        assert not result.target_assessment.is_load_bearing
        assert any(
            "target-side mapping is too generic" in reason.lower()
            for reason in result.reasons
        )

    @pytest.mark.asyncio
    async def test_optional_critique_can_override_heuristic_result(self):
        critique_harness = MagicMock()
        critique_harness.forge = AsyncMock(
            return_value=MagicMock(
                output=(
                    "```json\n"
                    "{\n"
                    '  "source_domain_load_bearing": false,\n'
                    '  "source_mechanism_survives_without_domain": true,\n'
                    '  "source_reasons": ["The source analogy can be removed without changing the execution logic."],\n'
                    '  "target_domain_load_bearing": true,\n'
                    '  "target_mechanism_survives_without_domain": false,\n'
                    '  "target_reasons": ["The target implementation remains concrete."],\n'
                    '  "overall_pass": false\n'
                    "}\n"
                    "```"
                )
            )
        )

        result = await check_load_bearing_domains(
            _make_load_bearing_translation(),
            critique_harness=critique_harness,
        )

        assert not result.passed
        assert result.critique_used
        assert not result.source_assessment.is_load_bearing
        assert result.source_assessment.method == "heuristic+critique"
        assert result.source_assessment.reasons == [
            "The source analogy can be removed without changing the execution logic."
        ]
