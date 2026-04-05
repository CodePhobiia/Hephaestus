"""Tests for the ResearchAugmentor ABC and implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.forgebase.research.augmentor import (
    ContradictionResolution,
    DiscoveredSource,
    FreshnessCheck,
    ResearchAugmentor,
)
from hephaestus.forgebase.research.perplexity_augmentor import (
    NoOpAugmentor,
    PerplexityAugmentor,
)

# ---------------------------------------------------------------------------
# Data class construction tests
# ---------------------------------------------------------------------------


class TestDiscoveredSource:
    def test_create(self):
        src = DiscoveredSource(
            url="https://example.com/paper",
            title="A Relevant Paper",
            summary="Describes the mechanism in detail.",
            relevance=0.85,
            trust_tier="standard",
        )
        assert src.url == "https://example.com/paper"
        assert src.title == "A Relevant Paper"
        assert src.summary == "Describes the mechanism in detail."
        assert src.relevance == 0.85
        assert src.trust_tier == "standard"

    def test_default_trust_tier(self):
        src = DiscoveredSource(
            url="",
            title="T",
            summary="S",
            relevance=0.5,
        )
        assert src.trust_tier == "standard"


class TestContradictionResolution:
    def test_create(self):
        cr = ContradictionResolution(
            summary="Claim A is better supported by recent meta-analyses.",
            resolution="claim_a_stronger",
            supporting_evidence=["Meta-analysis 2024", "Review 2023"],
            confidence=0.8,
        )
        assert cr.summary == "Claim A is better supported by recent meta-analyses."
        assert cr.resolution == "claim_a_stronger"
        assert len(cr.supporting_evidence) == 2
        assert cr.confidence == 0.8

    def test_defaults(self):
        cr = ContradictionResolution(summary="test", resolution="both_valid")
        assert cr.supporting_evidence == []
        assert cr.confidence == 0.5


class TestFreshnessCheck:
    def test_create(self):
        now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
        fc = FreshnessCheck(
            is_stale=True,
            reason="Newer evidence published in 2026.",
            newer_evidence=["Study from Jan 2026"],
            checked_at=now,
        )
        assert fc.is_stale is True
        assert fc.reason == "Newer evidence published in 2026."
        assert len(fc.newer_evidence) == 1
        assert fc.checked_at == now

    def test_defaults(self):
        fc = FreshnessCheck(is_stale=False, reason="Still current.")
        assert fc.newer_evidence == []
        assert fc.checked_at is None


# ---------------------------------------------------------------------------
# NoOpAugmentor tests
# ---------------------------------------------------------------------------


class TestNoOpAugmentor:
    async def test_returns_empty_evidence(self):
        aug = NoOpAugmentor()
        result = await aug.find_supporting_evidence("concept", ["gap1"])
        assert result == []

    async def test_returns_insufficient_contradiction(self):
        aug = NoOpAugmentor()
        result = await aug.resolve_contradiction("A is true", "B is true", "ctx")
        assert isinstance(result, ContradictionResolution)
        assert result.resolution == "insufficient_evidence"

    async def test_returns_not_stale(self):
        aug = NoOpAugmentor()
        now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
        result = await aug.check_freshness("Some claim", now)
        assert isinstance(result, FreshnessCheck)
        assert result.is_stale is False


# ---------------------------------------------------------------------------
# PerplexityAugmentor tests
# ---------------------------------------------------------------------------


def _make_mock_client(*, available: bool = True) -> MagicMock:
    """Create a mock PerplexityClient."""
    client = MagicMock()
    client.available = MagicMock(return_value=available)
    return client


def _make_mock_dossier(
    summary: str = "Test summary",
    representative_systems: list[str] | None = None,
    standard_approaches: list[str] | None = None,
    citations: list | None = None,
) -> MagicMock:
    """Create a mock BaselineDossier."""
    dossier = MagicMock()
    dossier.summary = summary
    dossier.representative_systems = representative_systems or []
    dossier.standard_approaches = standard_approaches or []
    dossier.citations = citations or []
    return dossier


class TestPerplexityAugmentorUnavailable:
    async def test_find_evidence_returns_empty(self):
        client = _make_mock_client(available=False)
        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.find_supporting_evidence("concept", ["gap1"])
        assert result == []

    async def test_resolve_contradiction_returns_insufficient(self):
        client = _make_mock_client(available=False)
        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.resolve_contradiction("A", "B", "ctx")
        assert isinstance(result, ContradictionResolution)
        assert result.resolution == "insufficient_evidence"

    async def test_check_freshness_returns_not_stale(self):
        client = _make_mock_client(available=False)
        aug = PerplexityAugmentor(perplexity_client=client)
        now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
        result = await aug.check_freshness("Some claim", now)
        assert isinstance(result, FreshnessCheck)
        assert result.is_stale is False


class TestPerplexityAugmentorError:
    async def test_find_evidence_error_returns_empty(self):
        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(
            side_effect=RuntimeError("API exploded"),
        )
        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.find_supporting_evidence("concept", ["gap1"])
        assert result == []

    async def test_resolve_contradiction_error_returns_insufficient(self):
        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(
            side_effect=RuntimeError("API exploded"),
        )
        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.resolve_contradiction("A", "B", "ctx")
        assert isinstance(result, ContradictionResolution)
        assert result.resolution == "insufficient_evidence"
        assert "API exploded" in result.summary

    async def test_check_freshness_error_returns_not_stale(self):
        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(
            side_effect=RuntimeError("API exploded"),
        )
        aug = PerplexityAugmentor(perplexity_client=client)
        now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
        result = await aug.check_freshness("Some claim", now)
        assert isinstance(result, FreshnessCheck)
        assert result.is_stale is False
        assert "API exploded" in result.reason


class TestPerplexityAugmentorSuccess:
    async def test_find_evidence_returns_sources(self):
        dossier = _make_mock_dossier(
            representative_systems=["System A", "System B"],
        )
        citation = MagicMock()
        citation.url = "https://example.com"
        citation.title = "Example Citation"
        dossier.citations = [citation]

        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(return_value=dossier)

        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.find_supporting_evidence("concept", ["gap1"])

        assert len(result) == 3  # 2 systems + 1 citation
        assert all(isinstance(s, DiscoveredSource) for s in result)
        assert result[0].title == "System A"
        assert result[2].url == "https://example.com"

    async def test_resolve_contradiction_returns_resolution(self):
        dossier = _make_mock_dossier(
            summary="Claim A is stronger",
            standard_approaches=["approach1", "approach2"],
        )
        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(return_value=dossier)

        aug = PerplexityAugmentor(perplexity_client=client)
        result = await aug.resolve_contradiction("A", "B", "ctx")

        assert isinstance(result, ContradictionResolution)
        assert result.summary == "Claim A is stronger"
        assert result.supporting_evidence == ["approach1", "approach2"]

    async def test_check_freshness_returns_check(self):
        dossier = _make_mock_dossier(
            summary="No freshness issues",
            representative_systems=["Recent study 2026"],
        )
        client = _make_mock_client(available=True)
        client.build_baseline_dossier = AsyncMock(return_value=dossier)

        aug = PerplexityAugmentor(perplexity_client=client)
        now = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
        result = await aug.check_freshness("Some claim", now)

        assert isinstance(result, FreshnessCheck)
        assert result.is_stale is False
        assert result.reason == "No freshness issues"
        assert result.newer_evidence == ["Recent study 2026"]


class TestPerplexityAugmentorAvailableProperty:
    def test_available_when_client_is(self):
        client = _make_mock_client(available=True)
        aug = PerplexityAugmentor(perplexity_client=client)
        assert aug.available is True

    def test_not_available_when_client_is_not(self):
        client = _make_mock_client(available=False)
        aug = PerplexityAugmentor(perplexity_client=client)
        assert aug.available is False

    def test_not_available_when_no_client_and_import_fails(self):
        aug = PerplexityAugmentor(perplexity_client=None)
        with patch(
            "hephaestus.forgebase.research.perplexity_augmentor.PerplexityAugmentor._get_client",
            side_effect=RuntimeError("no client"),
        ):
            assert aug.available is False


class TestResearchAugmentorABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            ResearchAugmentor()  # type: ignore[abstract]
