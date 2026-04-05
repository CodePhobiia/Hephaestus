"""Tests for AnthropicLintAnalyzer — mocked, no real API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.forgebase.linting.analyzers.anthropic_analyzer import AnthropicLintAnalyzer


def _mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic response with the given text content."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return response


class TestAnthropicLintAnalyzer:
    """Tests for the Anthropic-backed LintAnalyzer."""

    async def test_detect_contradictions_parses_response(self):
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '{"results": [{"is_contradictory": true, "explanation": "Claims oppose", "confidence": 0.9}]}'
            )
        )
        analyzer._client = mock_client

        results = await analyzer.detect_contradictions([("A is true", "A is false")])
        assert len(results) == 1
        assert results[0].is_contradictory is True
        assert results[0].confidence == 0.9
        assert results[0].explanation == "Claims oppose"

    async def test_detect_contradictions_empty_input(self):
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        results = await analyzer.detect_contradictions([])
        assert results == []

    async def test_assess_source_gaps_parses_response(self):
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '{"is_gap": true, "severity": "critical", "explanation": "Only 1 source"}'
            )
        )
        analyzer._client = mock_client

        result = await analyzer.assess_source_gaps("SEI", 1, ["SEI degrades"])
        assert result.is_gap is True
        assert result.severity == "critical"
        assert result.explanation == "Only 1 source"

    async def test_check_resolvable_parses_response(self):
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '{"is_resolvable": true, "search_query": "SEI degradation studies", "confidence": 0.8}'
            )
        )
        analyzer._client = mock_client

        result = await analyzer.check_resolvable_by_search("SEI degrades", [])
        assert result.is_resolvable is True
        assert "SEI" in result.search_query
        assert result.confidence == 0.8

    async def test_repair_on_json_error(self):
        """First response is invalid JSON; second attempt succeeds."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _mock_response("not json at all"),
                _mock_response('{"is_gap": false, "severity": "minor", "explanation": "OK"}'),
            ]
        )
        analyzer._client = mock_client

        result = await analyzer.assess_source_gaps("test", 3, ["claim"])
        assert result.is_gap is False
        assert result.severity == "minor"

    async def test_raises_after_max_retries(self):
        """All attempts return invalid JSON => RuntimeError."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key", max_retries=1)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response("bad json"))
        analyzer._client = mock_client

        with pytest.raises(RuntimeError, match="failed after"):
            await analyzer.assess_source_gaps("test", 1, ["claim"])

    async def test_lazy_client_is_none_initially(self):
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        assert analyzer._client is None

    async def test_pads_short_contradiction_results(self):
        """LLM returns fewer results than input pairs => padding with defaults."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '{"results": [{"is_contradictory": false, "explanation": "OK", "confidence": 0.1}]}'
            )
        )
        analyzer._client = mock_client

        results = await analyzer.detect_contradictions([("A", "B"), ("C", "D"), ("E", "F")])
        assert len(results) == 3
        # First result from LLM
        assert results[0].is_contradictory is False
        assert results[0].confidence == 0.1
        # Padded results
        assert results[1].is_contradictory is False
        assert results[1].confidence == 0.0
        assert results[1].explanation == "No analysis available"
        assert results[2].is_contradictory is False
        assert results[2].confidence == 0.0

    async def test_handles_code_block_response(self):
        """LLM wraps JSON in markdown code fences => extraction works."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '```json\n{"is_gap": true, "severity": "moderate", "explanation": "Thin"}\n```'
            )
        )
        analyzer._client = mock_client

        result = await analyzer.assess_source_gaps("test", 1, ["claim"])
        assert result.is_gap is True
        assert result.severity == "moderate"
        assert result.explanation == "Thin"

    async def test_truncates_excess_contradiction_results(self):
        """LLM returns more results than pairs => truncated to match."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(
                '{"results": ['
                '{"is_contradictory": true, "explanation": "X", "confidence": 0.9},'
                '{"is_contradictory": false, "explanation": "Y", "confidence": 0.1},'
                '{"is_contradictory": true, "explanation": "Z", "confidence": 0.8}'
                "]}"
            )
        )
        analyzer._client = mock_client

        results = await analyzer.detect_contradictions([("A", "B")])
        assert len(results) == 1
        assert results[0].is_contradictory is True

    async def test_non_json_error_reraised_on_last_attempt(self):
        """Non-JSON errors (e.g., API errors) are re-raised on the final attempt."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key", max_retries=0)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=ConnectionError("network down"))
        analyzer._client = mock_client

        with pytest.raises(ConnectionError, match="network down"):
            await analyzer.assess_source_gaps("test", 1, ["claim"])

    async def test_default_values_when_fields_missing(self):
        """LLM response has missing fields => defaults are used."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response('{"results": [{}]}'))
        analyzer._client = mock_client

        results = await analyzer.detect_contradictions([("A", "B")])
        assert len(results) == 1
        assert results[0].is_contradictory is False
        assert results[0].explanation == ""
        assert results[0].confidence == 0.5

    async def test_source_gap_defaults_when_fields_missing(self):
        """Source gap response with missing fields => defaults used."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response("{}"))
        analyzer._client = mock_client

        result = await analyzer.assess_source_gaps("concept", 1, ["c"])
        assert result.is_gap is True
        assert result.severity == "moderate"
        assert result.explanation == ""

    async def test_resolvability_defaults_when_fields_missing(self):
        """Resolvability response with missing fields => defaults used."""
        analyzer = AnthropicLintAnalyzer(api_key="test-key")
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_response("{}"))
        analyzer._client = mock_client

        result = await analyzer.check_resolvable_by_search("claim", ["support"])
        assert result.is_resolvable is False
        assert result.search_query == ""
        assert result.confidence == 0.5
