"""Tests for the async SDK client."""

from __future__ import annotations

from hephaestus.sdk.async_client import HephaestusClient, InventionResult


class TestInventionResult:
    def test_creation(self):
        r = InventionResult(
            invention_name="Test",
            source_domain="biology",
            domain_distance=0.8,
            structural_fidelity=0.7,
            novelty_score=0.85,
            key_insight="insight",
            architecture="arch",
            limitations=["limit1"],
            verdict="NOVEL",
            feasibility="HIGH",
            cost_usd=1.0,
            duration_seconds=30.0,
        )
        assert r.invention_name == "Test"
        assert r.novelty_score == 0.85

    def test_defaults(self):
        r = InventionResult(
            invention_name="X",
            source_domain="Y",
            domain_distance=0.0,
            structural_fidelity=0.0,
            novelty_score=0.0,
            key_insight="",
            architecture="",
            limitations=[],
            verdict="",
            feasibility="",
            cost_usd=0.0,
            duration_seconds=0.0,
        )
        assert r.raw_report is None


class TestHephaestusClient:
    def test_creation_defaults(self):
        c = HephaestusClient()
        assert c.model == "both"
        assert c.depth == 3
        assert c.candidates == 8
        assert c.intensity == "STANDARD"

    def test_creation_custom(self):
        c = HephaestusClient(
            anthropic_key="test",
            openai_key="test",
            model="opus",
            depth=5,
        )
        assert c.model == "opus"
        assert c.depth == 5

    def test_extract_result_no_invention(self):
        from unittest.mock import MagicMock

        report = MagicMock()
        report.top_invention = None
        report.total_cost_usd = 0.5
        report.total_duration_seconds = 10.0

        c = HephaestusClient()
        result = c._extract_result(report)
        assert result.verdict == "FAILED"
        assert result.cost_usd == 0.5

    def test_extract_result_with_invention(self):
        from unittest.mock import MagicMock

        trans = MagicMock()
        trans.source_candidate.domain_distance = 0.85
        trans.source_candidate.structural_fidelity = 0.82
        trans.key_insight = "Big insight"
        trans.architecture = "Some arch"
        trans.limitations = ["Limit 1"]

        top = MagicMock()
        top.invention_name = "Cool Invention"
        top.source_domain = "biology"
        top.novelty_score = 0.9
        top.verdict = "NOVEL"
        top.feasibility_rating = "HIGH"
        top.translation = trans

        report = MagicMock()
        report.top_invention = top
        report.total_cost_usd = 1.5
        report.total_duration_seconds = 45.0

        c = HephaestusClient()
        result = c._extract_result(report)
        assert result.invention_name == "Cool Invention"
        assert result.novelty_score == 0.9
        assert result.key_insight == "Big insight"
