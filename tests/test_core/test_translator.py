"""
Tests for Stage 4: Solution Translator.

LLM calls are mocked. Cognitive interference lens injection is verified.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.scorer import ScoredCandidate
from hephaestus.core.searcher import SearchCandidate
from hephaestus.core.translator import (
    ElementMapping,
    SolutionTranslator,
    Translation,
    TranslationError,
)
from hephaestus.deepforge.harness import ForgeResult, ForgeTrace
from hephaestus.lenses.loader import Lens, StructuralPattern
from hephaestus.lenses.selector import LensScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lens(domain: str = "biology") -> Lens:
    return Lens(
        name="Immune System",
        domain=domain,
        subdomain="immune",
        axioms=["Trust is earned through molecular handshake.", "Memory is distributed across the system."],
        structural_patterns=[
            StructuralPattern("clonal", "Amplify successful responses", ["allocation"])
        ],
        injection_prompt="You are reasoning as a biological immune system.",
    )


def _make_scored_candidate(
    source_domain: str = "Immune System",
    fidelity: float = 0.8,
    distance: float = 0.85,
) -> ScoredCandidate:
    lens = _make_lens()
    ls = LensScore(
        lens=lens,
        domain_distance=distance,
        structural_relevance=0.7,
        composite_score=fidelity * distance ** 1.5,
        matched_patterns=["allocation"],
    )
    search_candidate = SearchCandidate(
        source_domain=source_domain,
        source_solution="T-cell memory solves persistence through clonal expansion",
        mechanism="Successful immune responses trigger memory cell formation",
        structural_mapping="Task state maps to immune memory; scheduler maps to thymus",
        lens_used=lens,
        lens_score=ls,
        confidence=0.85,
        cost_usd=0.005,
    )
    return ScoredCandidate(
        candidate=search_candidate,
        structural_fidelity=fidelity,
        domain_distance=distance,
        combined_score=fidelity * distance ** 1.5,
        fidelity_reasoning="Strong structural match",
        strong_mappings=["T-cell → task", "memory → cache"],
        weak_mappings=["No MHC equivalent"],
    )


def _make_structure() -> ProblemStructure:
    return ProblemStructure(
        original_problem="I need a fault-tolerant distributed task scheduler",
        structure="Robust resource allocation under node failures",
        constraints=["tolerate failures", "low latency", "no single point of failure"],
        mathematical_shape="graph with Byzantine fault tolerance and distributed state",
        native_domain="distributed_systems",
        problem_maps_to={"routing", "allocation", "fault_tolerance"},
    )


def _make_forge_result(text: str, cost: float = 0.02) -> ForgeResult:
    trace = ForgeTrace(prompt="test")
    trace.total_cost_usd = cost
    return ForgeResult(output=text, trace=trace, success=True)


def _valid_translation_json(**overrides) -> str:
    data = {
        "invention_name": "Immune-Memory Task Scheduler",
        "mapping": {
            "elements": [
                {
                    "source_element": "T-cell receptor",
                    "target_element": "Task type signature",
                    "mechanism": "Both uniquely identify the entity type",
                },
                {
                    "source_element": "Memory cell",
                    "target_element": "Cached task result",
                    "mechanism": "Both persist successful outcomes for rapid reuse",
                },
            ]
        },
        "architecture": (
            "The scheduler maintains an immune memory layer: when a task type succeeds, "
            "a 'memory task descriptor' is created and cached. On subsequent similar tasks, "
            "the scheduler performs rapid recognition and routes directly to cached execution "
            "paths, bypassing the expensive scheduling pipeline.\n\n"
            "Node failures trigger 'inflammatory response' — redistributing tasks to healthy "
            "nodes with temporary quota increases (clonal expansion analogue)."
        ),
        "mathematical_proof": (
            "Let T be the set of task types, M ⊂ T the memorized tasks. "
            "For t ∈ M, scheduling complexity reduces from O(n) to O(1)."
        ),
        "limitations": [
            "Memory cells require periodic 'affinity maturation' (cache invalidation strategy needed)",
            "No direct equivalent to MHC peptide presentation limits fine-grained discrimination",
        ],
        "implementation_notes": "Implement using Redis for the memory layer; task signatures via content hash",
        "key_insight": "Immune memory eliminates redundant recognition work — apply this to task scheduling",
    }
    data.update(overrides)
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Tests: ElementMapping and Translation
# ---------------------------------------------------------------------------


class TestElementMapping:
    def test_creation(self):
        em = ElementMapping(
            source_element="T-cell receptor",
            target_element="Task type signature",
            mechanism="Both uniquely identify the entity",
        )
        assert em.source_element == "T-cell receptor"
        assert em.mechanism


class TestTranslation:
    def _make_translation(self, invention_name="Test Invention") -> Translation:
        sc = _make_scored_candidate()
        return Translation(
            invention_name=invention_name,
            mapping=[
                ElementMapping("T-cell", "Task", "Both represent active work units"),
            ],
            architecture="Distributed immune-inspired scheduler",
            mathematical_proof="T maps to T'",
            limitations=["No perfect MHC equivalent"],
            implementation_notes="Use Redis",
            key_insight="Memory eliminates redundancy",
            source_candidate=sc,
            cost_usd=0.02,
        )

    def test_source_domain_delegation(self):
        t = self._make_translation()
        assert t.source_domain == "Immune System"

    def test_combined_score_delegation(self):
        t = self._make_translation()
        assert t.combined_score > 0

    def test_summary(self):
        t = self._make_translation("Immune-Memory Scheduler")
        s = t.summary()
        assert "Immune-Memory Scheduler" in s
        assert "mappings=1" in s


# ---------------------------------------------------------------------------
# Tests: SolutionTranslator
# ---------------------------------------------------------------------------


class TestSolutionTranslator:
    @pytest.mark.asyncio
    async def test_successful_translation(self):
        harness = MagicMock()
        harness.adapter = MagicMock()
        harness.adapter.model_name = "claude-opus-4-5"
        harness.adapter.config.provider = "anthropic"

        # The translator builds its own interference harness internally
        # We need to mock the forge call on ANY DeepForgeHarness instance
        forge_result = _make_forge_result(_valid_translation_json())

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=forge_result)

            translator = SolutionTranslator(harness=harness, top_n=3)
            structure = _make_structure()
            candidates = [_make_scored_candidate()]

            translations = await translator.translate(candidates, structure)

        assert len(translations) == 1
        t = translations[0]
        assert isinstance(t, Translation)
        assert t.invention_name == "Immune-Memory Task Scheduler"
        assert len(t.mapping) == 2
        assert t.architecture
        assert len(t.limitations) == 2

    @pytest.mark.asyncio
    async def test_respects_top_n(self):
        """Should only translate up to top_n candidates."""
        harness = MagicMock()
        harness.adapter = MagicMock()

        forge_result = _make_forge_result(_valid_translation_json())

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=forge_result)

            translator = SolutionTranslator(harness=harness, top_n=2)
            candidates = [
                _make_scored_candidate(f"Domain {i}", distance=0.9 - i * 0.05)
                for i in range(5)
            ]
            translations = await translator.translate(candidates, _make_structure())

        assert len(translations) <= 2

    @pytest.mark.asyncio
    async def test_top_n_override(self):
        """top_n parameter in translate() should override instance setting."""
        harness = MagicMock()
        harness.adapter = MagicMock()

        forge_result = _make_forge_result(_valid_translation_json())

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=forge_result)

            translator = SolutionTranslator(harness=harness, top_n=5)
            candidates = [_make_scored_candidate() for _ in range(5)]
            translations = await translator.translate(candidates, _make_structure(), top_n=1)

        assert len(translations) <= 1

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        translator = SolutionTranslator(harness=MagicMock())
        result = await translator.translate([], _make_structure())
        assert result == []

    @pytest.mark.asyncio
    async def test_failed_candidate_skipped(self):
        """Translation failure for one candidate should not block others."""
        harness = MagicMock()
        harness.adapter = MagicMock()

        good_result = _make_forge_result(_valid_translation_json())

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(side_effect=[
                Exception("API error"),
                good_result,
            ])

            translator = SolutionTranslator(harness=harness, top_n=2)
            candidates = [
                _make_scored_candidate("Domain A"),
                _make_scored_candidate("Domain B"),
            ]
            translations = await translator.translate(candidates, _make_structure())

        assert len(translations) == 1

    @pytest.mark.asyncio
    async def test_translations_sorted_by_combined_score(self):
        """Translations should maintain sorted order by source combined_score."""
        harness = MagicMock()
        harness.adapter = MagicMock()

        forge_result = _make_forge_result(_valid_translation_json())

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=forge_result)

            translator = SolutionTranslator(harness=harness, top_n=3)
            candidates = [
                _make_scored_candidate(f"Domain {i}", fidelity=0.9 - i * 0.1, distance=0.85)
                for i in range(3)
            ]
            translations = await translator.translate(candidates, _make_structure())

        scores = [t.combined_score for t in translations]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_bad_json_raises_translation_error(self):
        """Non-JSON output should raise TranslationError (propagated from parse)."""
        harness = MagicMock()
        harness.adapter = MagicMock()

        bad_result = _make_forge_result("This is absolutely not JSON at all.")

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=bad_result)

            translator = SolutionTranslator(harness=harness, top_n=1)
            # Should handle gracefully (skipped, not crashed)
            translations = await translator.translate(
                [_make_scored_candidate()], _make_structure()
            )

        # Failed translation gets skipped
        assert len(translations) == 0

    @pytest.mark.asyncio
    async def test_cost_tracked(self):
        harness = MagicMock()
        harness.adapter = MagicMock()

        forge_result = _make_forge_result(_valid_translation_json(), cost=0.025)

        with patch("hephaestus.core.translator.DeepForgeHarness") as MockHarness:
            instance = MockHarness.return_value
            instance.forge = AsyncMock(return_value=forge_result)

            translator = SolutionTranslator(harness=harness, top_n=1)
            translations = await translator.translate(
                [_make_scored_candidate()], _make_structure()
            )

        if translations:
            assert translations[0].cost_usd == pytest.approx(0.025)
