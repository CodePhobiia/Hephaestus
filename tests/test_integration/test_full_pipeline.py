"""Integration tests for the full invention pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestGenesisIntegration:
    """Tests that exercise the full pipeline with mocked adapters."""

    @pytest.fixture
    def mock_decomposer(self):
        decomposer = MagicMock()
        result = MagicMock()
        result.mathematical_shape = "allocation under constraints"
        result.native_domain = "computer science"
        result.structural_patterns = ["allocation", "scheduling"]
        result.key_constraints = ["bounded resources"]
        decomposer.decompose = AsyncMock(return_value=result)
        return decomposer, result

    @pytest.fixture
    def mock_searcher(self):
        from hephaestus.core.searcher import SearchCandidate
        from hephaestus.lenses.loader import Lens, StructuralPattern
        from hephaestus.lenses.selector import LensScore

        lens = Lens(
            name="Immune System",
            domain="biology",
            subdomain="immunology",
            axioms=["Memory persists."],
            structural_patterns=[
                StructuralPattern("allocation", "Allocate resources", ["allocation"])
            ],
            injection_prompt="You are reasoning as Immune System.",
        )
        lens_score = LensScore(
            lens=lens,
            domain_distance=0.85,
            structural_relevance=0.8,
            composite_score=0.72,
            matched_patterns=["allocation"],
        )
        candidate = SearchCandidate(
            source_domain="Immune System",
            source_solution="T-cell memory",
            mechanism="Immune memory stores successful responses",
            structural_mapping="Maps to task scheduling",
            lens_used=lens,
            lens_score=lens_score,
            confidence=0.85,
        )
        searcher = MagicMock()
        searcher.search = AsyncMock(return_value=[candidate])
        return searcher, [candidate]

    @pytest.fixture
    def mock_scorer(self):
        from hephaestus.core.scorer import ScoredCandidate

        scored = MagicMock(spec=ScoredCandidate)
        scored.structural_fidelity = 0.82
        scored.domain_distance = 0.85
        scored.combined_score = 0.72
        scored.fidelity_reasoning = "Strong match"
        scored.strong_mappings = ["mapping"]
        scored.weak_mappings = []
        # Proxy to the underlying candidate
        scored.candidate = MagicMock()
        scored.candidate.source_domain = "Immune System"
        scored.candidate.source_solution = "T-cell memory"
        scored.candidate.mechanism = "Immune memory"
        scored.candidate.lens_used = MagicMock()
        scored.candidate.lens_score = MagicMock()

        scorer = MagicMock()
        scorer.score = AsyncMock(return_value=[scored])
        return scorer, [scored]

    @pytest.fixture
    def mock_translator(self):
        from hephaestus.core.translator import ElementMapping, Translation

        translation = MagicMock(spec=Translation)
        translation.invention_name = "Immune-Memory Scheduler"
        translation.source_domain = "Immune System"
        translation.mapping = [
            ElementMapping("T-cell", "task signature", "Both classify work"),
        ]
        translation.architecture = "Use immune memory for scheduling"
        translation.key_insight = "Prior success = reusable scheduling primitive"
        translation.limitations = ["No MHC equivalent"]
        translation.implementation_notes = "Use Redis"
        translation.mathematical_proof = "Maps cleanly"
        translation.source_candidate = MagicMock()
        translation.source_candidate.domain_distance = 0.85
        translation.source_candidate.structural_fidelity = 0.82

        translator = MagicMock()
        translator.translate = AsyncMock(return_value=translation)
        return translator, translation

    @pytest.fixture
    def mock_verifier(self):
        result = MagicMock()
        result.novelty_score = 0.89
        result.verdict = "NOVEL"
        result.structural_validity = 0.85
        result.feasibility_rating = "HIGH"
        result.validity_notes = "Verified"
        result.recommended_next_steps = ["Prototype"]
        result.adversarial_result = MagicMock()
        result.adversarial_result.fatal_flaws = []
        result.adversarial_result.structural_weaknesses = []

        verifier = MagicMock()
        verifier.verify = AsyncMock(return_value=result)
        return verifier, result

    def test_config_creation(self):
        """GenesisConfig can be created with minimal args."""
        from hephaestus.core.genesis import GenesisConfig

        config = GenesisConfig(
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        assert config.num_candidates == 8
        assert config.divergence_intensity == "STANDARD"

    def test_genesis_creation(self):
        """Genesis can be instantiated from config."""
        from hephaestus.core.genesis import Genesis, GenesisConfig

        config = GenesisConfig(
            anthropic_api_key="test-key",
            openai_api_key="test-key",
        )
        genesis = Genesis(config)
        assert genesis is not None

    def test_pipeline_stages_enum(self):
        """PipelineStage has all expected stages."""
        from hephaestus.core.genesis import PipelineStage

        stages = [s.name for s in PipelineStage]
        assert "DECOMPOSING" in stages
        assert "SEARCHING" in stages
        assert "SCORING" in stages
        assert "TRANSLATING" in stages
        assert "VERIFYING" in stages
        assert "COMPLETE" in stages
        assert "FAILED" in stages

    def test_output_formatter_roundtrip(self):
        """InventionReport can be formatted to all output types."""
        from hephaestus.output.formatter import InventionReport, OutputFormatter

        report = InventionReport(
            problem="Load balancer for traffic spikes",
            structural_form="allocation under constraints",
            invention_name="Immune-Memory Scheduler",
            source_domain="Immune System",
            domain_distance=0.85,
            structural_fidelity=0.82,
            novelty_score=0.89,
            mechanism="T-cell memory for scheduling",
            translation="T-cell → task signature",
            architecture="Redis-based immune memory layer",
            where_analogy_breaks="No MHC equivalent",
            cost_usd=1.23,
            models_used=["claude-opus-4-6", "gpt-5"],
            depth=3,
            wall_time_seconds=45.2,
        )

        formatter = OutputFormatter()

        md = formatter.to_markdown(report)
        assert "Immune-Memory Scheduler" in md
        assert "CONFIDENCE" in md
        assert "ROADMAP" in md

        json_out = formatter.to_json(report)
        assert "Immune-Memory Scheduler" in json_out

        plain = formatter.to_plain(report)
        assert "Immune-Memory Scheduler" in plain
        assert "CONFIDENCE" in plain

    def test_session_lifecycle(self):
        """Session can record invention pipeline results."""
        from hephaestus.session.schema import Session, SessionMeta

        meta = SessionMeta(name="Integration Test", model="claude-opus-4-6")
        session = Session(meta=meta)

        session.append_entry("user", "Load balancer for traffic spikes")
        session.add_invention(
            invention_name="Immune-Memory Scheduler",
            source_domain="Immune System",
            architecture="Redis-based",
            key_insight="Prior success = reusable",
            mapping_summary="T-cell → task",
            score=0.89,
        )

        assert len(session.transcript) == 1
        assert len(session.inventions) == 1

        # Round-trip
        data = session.to_dict()
        restored = Session.from_dict(data)
        assert restored.inventions[0].invention_name == "Immune-Memory Scheduler"

    def test_layered_config_integration(self, tmp_path, monkeypatch):
        """LayeredConfig resolves with env vars and project config."""
        from hephaestus.config.layered import LayeredConfig

        # Use env vars (highest precedence, no file mocking needed)
        monkeypatch.setenv("HEPHAESTUS_DEPTH", "7")
        monkeypatch.setenv("HEPHAESTUS_INTENSITY", "AGGRESSIVE")

        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 7
        assert cfg.divergence_intensity == "AGGRESSIVE"
        assert "env" in lc.config_sources()["depth"].lower()
