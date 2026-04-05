"""Tests for AnthropicFusionAnalyzer -- mocked, no real API calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.forgebase.domain.enums import AnalogyVerdict
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.analyzers.anthropic_analyzer import (
    AnthropicFusionAnalyzer,
)
from tests.test_forgebase.test_fusion.conftest import make_bridge_candidate


def _mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic response with the given text content."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    response.usage = MagicMock(input_tokens=500, output_tokens=300)
    return response


def _strong_analogy_json(candidate_id: str, map_id: str = "amap_00000000000000000000000099") -> str:
    """Build a JSON response representing a STRONG analogy."""
    return json.dumps(
        {
            "analyses": [
                {
                    "candidate_id": candidate_id,
                    "verdict": "strong_analogy",
                    "bridge_concept": "Layered transport through constrained channels",
                    "mapped_components": [
                        {
                            "left_component": "cathode layer",
                            "right_component": "distribution tier",
                            "mapping_confidence": 0.85,
                        },
                    ],
                    "mapped_constraints": [
                        {
                            "left_constraint": "charge rate < 4C",
                            "right_constraint": "throughput < 10k/hr",
                            "preserved": True,
                        },
                    ],
                    "analogy_breaks": [
                        {
                            "description": "Scale differs by 6 orders",
                            "severity": "medium",
                            "category": "scale_difference",
                        },
                    ],
                    "confidence": 0.82,
                    "transfer": {
                        "mechanism": "Apply hub-spoke to ion transport",
                        "rationale": "Both exhibit layered flow",
                        "caveats": ["Scale mismatch"],
                        "caveat_categories": ["scale"],
                    },
                },
            ],
        }
    )


def _no_analogy_json(candidate_id: str) -> str:
    """Build a JSON response representing NO_ANALOGY."""
    return json.dumps(
        {
            "analyses": [
                {
                    "candidate_id": candidate_id,
                    "verdict": "no_analogy",
                    "bridge_concept": "No structural similarity detected",
                    "mapped_components": [],
                    "mapped_constraints": [],
                    "analogy_breaks": [],
                    "confidence": 0.15,
                    "transfer": None,
                },
            ],
        }
    )


class TestAnthropicFusionAnalyzerContract:
    """Verify subclass relationship."""

    def test_is_subclass_of_abc(self):
        assert issubclass(AnthropicFusionAnalyzer, FusionAnalyzer)

    def test_lazy_client_is_none_initially(self, id_gen):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        assert analyzer._client is None


class TestParsesStrongAnalogy:
    """LLM returns a STRONG analogy response -> parsed correctly."""

    async def test_parses_strong_analogy_response(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.75,
        )

        response_text = _strong_analogy_json(str(candidate.candidate_id))
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(response_text),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        amap = maps[0]
        assert amap.verdict == AnalogyVerdict.STRONG_ANALOGY
        assert amap.confidence == 0.82
        assert amap.bridge_concept == "Layered transport through constrained channels"
        assert len(amap.mapped_components) == 1
        assert amap.mapped_components[0].left_component == "cathode layer"
        assert amap.mapped_components[0].right_component == "distribution tier"
        assert amap.mapped_components[0].mapping_confidence == 0.85
        assert len(amap.mapped_constraints) == 1
        assert amap.mapped_constraints[0].preserved is True
        assert len(amap.analogy_breaks) == 1
        assert amap.analogy_breaks[0].category == "scale_difference"

        # Transfer generated for STRONG
        assert len(transfers) == 1
        t = transfers[0]
        assert t.mechanism == "Apply hub-spoke to ion transport"
        assert t.rationale == "Both exhibit layered flow"
        assert t.caveats == ["Scale mismatch"]
        assert t.analogical_map_id == amap.map_id

        # Call record
        assert record.backend_kind == "anthropic"
        assert record.input_tokens == 500
        assert record.output_tokens == 300


class TestParsesNoAnalogy:
    """LLM returns NO_ANALOGY -> parsed correctly, no transfer."""

    async def test_parses_no_analogy_response(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.2,
        )

        response_text = _no_analogy_json(str(candidate.candidate_id))
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(response_text),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY
        assert maps[0].confidence == 0.15
        assert maps[0].mapped_components == []
        assert len(transfers) == 0


class TestRepairOnJsonError:
    """First response is bad JSON; second attempt succeeds."""

    async def test_repair_on_json_error(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(
            api_key="test-key",
            id_gen=id_gen,
            max_retries=2,
        )
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.6,
        )

        good_response = _no_analogy_json(str(candidate.candidate_id))
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _mock_response("not valid json at all"),
                _mock_response(good_response),
            ],
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert record.repair_invoked is True
        # Two calls made
        assert mock_client.messages.create.call_count == 2


class TestRaisesAfterMaxRetries:
    """All attempts return bad JSON -> RuntimeError."""

    async def test_raises_after_max_retries(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(
            api_key="test-key",
            id_gen=id_gen,
            max_retries=1,
        )
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.6,
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response("bad json forever"),
        )
        analyzer._client = mock_client

        with pytest.raises(RuntimeError, match="failed after"):
            await analyzer.analyze_candidates(
                [candidate],
                left_context,
                right_context,
            )


class TestHandlesEmptyCandidates:
    """Empty candidates -> empty results, no LLM call."""

    async def test_handles_empty_candidates(
        self,
        id_gen,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        mock_client = AsyncMock()
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [],
            left_context,
            right_context,
        )

        assert maps == []
        assert transfers == []
        assert record.backend_kind == "anthropic"
        assert record.input_tokens == 0
        assert record.output_tokens == 0
        # No LLM call made
        mock_client.messages.create.assert_not_called()


class TestProblemAffectsAnalysis:
    """Problem string is included in the prompt."""

    async def test_problem_affects_analysis(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.7,
            problem_relevance=0.9,
        )

        response_text = _strong_analogy_json(str(candidate.candidate_id))
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(response_text),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
            problem="Improve battery longevity",
        )

        # Verify problem was included in the user prompt
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_content = messages[0]["content"]
        assert "Improve battery longevity" in user_content

        assert len(maps) == 1


class TestCodeBlockHandling:
    """LLM wraps JSON in markdown code fences -> still parsed."""

    async def test_handles_code_block_response(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.5,
        )

        inner_json = _no_analogy_json(str(candidate.candidate_id))
        code_block = f"```json\n{inner_json}\n```"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(code_block),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY


class TestProvenancePreservation:
    """Provenance refs from candidates are preserved in maps."""

    async def test_preserves_page_and_claim_refs(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.7,
        )

        response_text = _strong_analogy_json(str(candidate.candidate_id))
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(response_text),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        amap = maps[0]
        assert candidate.left_entity_ref in amap.left_page_refs
        assert candidate.right_entity_ref in amap.right_page_refs
        assert amap.left_claim_refs == candidate.left_claim_refs
        assert amap.right_claim_refs == candidate.right_claim_refs
        assert candidate.candidate_id in amap.source_candidates


class TestNonJsonErrorReraised:
    """Non-JSON errors (e.g. API errors) re-raised on final attempt."""

    async def test_non_json_error_reraised(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(
            api_key="test-key",
            id_gen=id_gen,
            max_retries=0,
        )
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.6,
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=ConnectionError("network down"),
        )
        analyzer._client = mock_client

        with pytest.raises(ConnectionError, match="network down"):
            await analyzer.analyze_candidates(
                [candidate],
                left_context,
                right_context,
            )


class TestDefaultVerdictFallback:
    """Unknown verdict string from LLM -> defaults to NO_ANALOGY."""

    async def test_unknown_verdict_defaults_to_no_analogy(
        self,
        id_gen,
        left_vault_id,
        right_vault_id,
        left_context,
        right_context,
    ):
        analyzer = AnthropicFusionAnalyzer(api_key="test-key", id_gen=id_gen)
        candidate = make_bridge_candidate(
            id_gen,
            left_vault_id,
            right_vault_id,
            similarity_score=0.5,
        )

        response_text = json.dumps(
            {
                "analyses": [
                    {
                        "candidate_id": str(candidate.candidate_id),
                        "verdict": "something_unknown",
                        "bridge_concept": "Unknown",
                        "mapped_components": [],
                        "mapped_constraints": [],
                        "analogy_breaks": [],
                        "confidence": 0.3,
                        "transfer": None,
                    },
                ],
            }
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(response_text),
        )
        analyzer._client = mock_client

        maps, transfers, record = await analyzer.analyze_candidates(
            [candidate],
            left_context,
            right_context,
        )

        assert len(maps) == 1
        assert maps[0].verdict == AnalogyVerdict.NO_ANALOGY
