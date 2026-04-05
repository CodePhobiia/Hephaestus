"""Tests for the Anthropic compiler backend.

Uses mocked Anthropic client to verify JSON parsing, repair logic,
dataclass mapping, and BackendCallRecord population without real API calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from hephaestus.forgebase.compiler.backends.anthropic_backend import (
    AnthropicCompilerBackend,
)
from hephaestus.forgebase.compiler.models import (
    EvidenceGrade,
    ExtractedClaim,
    ExtractedConcept,
    OpenQuestion,
    SourceCardContent,
    SynthesizedPage,
)
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _make_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Anthropic response object."""
    content_block = SimpleNamespace(text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[content_block], usage=usage)


def _make_backend_with_mock_client(responses: list):
    """Create a backend with a pre-injected mock client.

    *responses* is a list of mock Anthropic response objects.  They will be
    returned sequentially by the mock ``messages.create`` method.
    """
    backend = AnthropicCompilerBackend(api_key="test-key", model="claude-test")
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=responses)
    backend._client = mock_client
    return backend, mock_client


SOURCE_ID = "source_00000000000000000000000001"
SOURCE_META = {"source_id": SOURCE_ID, "source_version": 1}


# ===================================================================
# Test: extract_claims parses response
# ===================================================================


class TestExtractClaims:
    @pytest.mark.asyncio
    async def test_extract_claims_parses_response(self):
        payload = json.dumps(
            {
                "claims": [
                    {
                        "statement": "Caffeine improves alertness.",
                        "evidence_segment": "Caffeine is known to improve alertness",
                        "segment_start": 0,
                        "segment_end": 38,
                        "confidence": 0.92,
                        "claim_type": "factual",
                    },
                    {
                        "statement": "High doses cause anxiety.",
                        "evidence_segment": "High doses have been linked to anxiety",
                        "segment_start": 40,
                        "segment_end": 77,
                        "confidence": 0.75,
                        "claim_type": "limitation",
                    },
                ]
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        claims, record = await backend.extract_claims(
            "Caffeine is known to improve alertness. High doses have been linked to anxiety.",
            SOURCE_META,
        )

        assert len(claims) == 2
        assert isinstance(claims[0], ExtractedClaim)
        assert claims[0].statement == "Caffeine improves alertness."
        assert claims[0].confidence == 0.92
        assert claims[0].claim_type == "factual"
        assert claims[0].segment_ref.segment_start == 0
        assert claims[0].segment_ref.segment_end == 38
        assert claims[0].segment_ref.source_id == EntityId(SOURCE_ID)
        assert claims[0].segment_ref.source_version == Version(1)

        assert claims[1].statement == "High doses cause anxiety."
        assert claims[1].claim_type == "limitation"

    @pytest.mark.asyncio
    async def test_extract_claims_empty_source(self):
        payload = json.dumps({"claims": []})
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        claims, record = await backend.extract_claims("", SOURCE_META)
        assert claims == []
        assert isinstance(record, BackendCallRecord)


# ===================================================================
# Test: extract_concepts parses response
# ===================================================================


class TestExtractConcepts:
    @pytest.mark.asyncio
    async def test_extract_concepts_parses_response(self):
        payload = json.dumps(
            {
                "concepts": [
                    {
                        "name": "Solid Electrolyte Interphase",
                        "aliases": ["SEI", "SEI layer"],
                        "kind": "mechanism",
                        "evidence_segments": [
                            {
                                "segment_start": 10,
                                "segment_end": 55,
                                "preview_text": "The SEI layer forms on battery anodes",
                            }
                        ],
                        "salience": 0.95,
                    }
                ]
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        concepts, record = await backend.extract_concepts(
            "Some text about the SEI layer and batteries.",
            SOURCE_META,
        )

        assert len(concepts) == 1
        assert isinstance(concepts[0], ExtractedConcept)
        assert concepts[0].name == "Solid Electrolyte Interphase"
        assert concepts[0].aliases == ["SEI", "SEI layer"]
        assert concepts[0].kind == CandidateKind.MECHANISM
        assert concepts[0].salience == 0.95
        assert len(concepts[0].evidence_segments) == 1
        seg = concepts[0].evidence_segments[0]
        assert seg.segment_start == 10
        assert seg.segment_end == 55
        assert seg.source_id == EntityId(SOURCE_ID)


# ===================================================================
# Test: generate_source_card parses response
# ===================================================================


class TestGenerateSourceCard:
    @pytest.mark.asyncio
    async def test_generate_source_card_parses_response(self):
        payload = json.dumps(
            {
                "summary": "Novel findings on battery degradation.",
                "key_claims": ["Claim A", "Claim B"],
                "methods": ["XRD analysis", "Electrochemical cycling"],
                "limitations": ["Small sample size"],
                "evidence_quality": "strong",
                "concepts_mentioned": ["SEI", "Li-ion"],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        card, record = await backend.generate_source_card(
            source_text="Battery text.",
            source_metadata=SOURCE_META,
            extracted_claims=[],
            extracted_concepts=[],
        )

        assert isinstance(card, SourceCardContent)
        assert card.summary == "Novel findings on battery degradation."
        assert card.key_claims == ["Claim A", "Claim B"]
        assert card.methods == ["XRD analysis", "Electrochemical cycling"]
        assert card.limitations == ["Small sample size"]
        assert card.evidence_quality == "strong"
        assert card.concepts_mentioned == ["SEI", "Li-ion"]


# ===================================================================
# Test: grade_evidence parses response
# ===================================================================


class TestGradeEvidence:
    @pytest.mark.asyncio
    async def test_grade_evidence_parses_response(self):
        payload = json.dumps(
            {
                "strength": 0.85,
                "methodology_quality": "strong",
                "reasoning": "Well-controlled experiment with large sample.",
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        seg_ref = EvidenceSegmentRef(
            source_id=EntityId(SOURCE_ID),
            source_version=Version(1),
            segment_start=0,
            segment_end=50,
            section_key=None,
            preview_text="Some evidence text",
        )
        grade, record = await backend.grade_evidence(
            claim="Caffeine improves alertness.",
            segment_ref=seg_ref,
            source_text="Full source text here.",
        )

        assert isinstance(grade, EvidenceGrade)
        assert grade.strength == 0.85
        assert grade.methodology_quality == "strong"
        assert grade.reasoning == "Well-controlled experiment with large sample."


# ===================================================================
# Test: synthesize_concept_page
# ===================================================================


class TestSynthesizeConceptPage:
    @pytest.mark.asyncio
    async def test_synthesize_concept_page_parses_response(self):
        payload = json.dumps(
            {
                "title": "Solid Electrolyte Interphase",
                "content_markdown": "# SEI\n\nThe SEI is a passivation layer.",
                "claims": [
                    {
                        "statement": "SEI forms during first charge cycle.",
                        "support_type": "synthesized",
                        "confidence": 0.88,
                        "derived_from_claims": ["claim A", "claim B"],
                    }
                ],
                "related_concepts": ["Li-ion battery", "Anode"],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        page, record = await backend.synthesize_concept_page(
            concept_name="Solid Electrolyte Interphase",
            evidence=[],
            existing_claims=["claim A", "claim B"],
            related_concepts=["Li-ion battery", "Anode"],
            policy=None,
        )

        assert isinstance(page, SynthesizedPage)
        assert page.title == "Solid Electrolyte Interphase"
        assert "passivation layer" in page.content_markdown
        assert len(page.claims) == 1
        assert page.claims[0].support_type == SupportType.SYNTHESIZED
        assert page.claims[0].confidence == 0.88
        assert page.related_concepts == ["Li-ion battery", "Anode"]


# ===================================================================
# Test: synthesize_mechanism_page
# ===================================================================


class TestSynthesizeMechanismPage:
    @pytest.mark.asyncio
    async def test_synthesize_mechanism_page_parses_response(self):
        payload = json.dumps(
            {
                "title": "Lithium Plating",
                "content_markdown": "# Lithium Plating\n\nProcess description.",
                "claims": [],
                "related_concepts": ["Dendrite growth"],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        page, record = await backend.synthesize_mechanism_page(
            mechanism_name="Lithium Plating",
            causal_claims=["Li deposits on anode"],
            source_evidence=[],
            policy=None,
        )

        assert isinstance(page, SynthesizedPage)
        assert page.title == "Lithium Plating"


# ===================================================================
# Test: synthesize_comparison_page
# ===================================================================


class TestSynthesizeComparisonPage:
    @pytest.mark.asyncio
    async def test_synthesize_comparison_page_parses_response(self):
        payload = json.dumps(
            {
                "title": "Comparison: Li-ion vs Solid-State",
                "content_markdown": "# Comparison\n\nBoth are battery types.",
                "claims": [],
                "related_concepts": ["Battery"],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        page, record = await backend.synthesize_comparison_page(
            entities=["Li-ion", "Solid-State"],
            comparison_data=[],
            policy=None,
        )

        assert isinstance(page, SynthesizedPage)
        assert "Comparison" in page.title


# ===================================================================
# Test: synthesize_timeline_page
# ===================================================================


class TestSynthesizeTimelinePage:
    @pytest.mark.asyncio
    async def test_synthesize_timeline_page_parses_response(self):
        payload = json.dumps(
            {
                "title": "Timeline: mRNA Vaccines",
                "content_markdown": "# Timeline\n\nKey events.",
                "claims": [],
                "related_concepts": ["mRNA"],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        page, record = await backend.synthesize_timeline_page(
            topic="mRNA Vaccines",
            temporal_claims=["First mRNA vaccine approved in 2020"],
            policy=None,
        )

        assert isinstance(page, SynthesizedPage)
        assert "Timeline" in page.title


# ===================================================================
# Test: identify_open_questions
# ===================================================================


class TestIdentifyOpenQuestions:
    @pytest.mark.asyncio
    async def test_identify_open_questions_parses_response(self):
        payload = json.dumps(
            {
                "questions": [
                    {
                        "question": "What is the optimal SEI thickness?",
                        "context": "Sources disagree on ideal thickness range.",
                        "conflicting_claims": ["<5nm is optimal", ">10nm is needed"],
                        "evidence_gap": "No controlled thickness studies.",
                    },
                    {
                        "question": "Does temperature affect SEI stability?",
                        "context": "Limited high-temperature data.",
                    },
                ]
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        questions, record = await backend.identify_open_questions(
            contested_claims=["<5nm is optimal", ">10nm is needed"],
            evidence_gaps=["No high-temperature data"],
            policy=None,
        )

        assert len(questions) == 2
        assert isinstance(questions[0], OpenQuestion)
        assert questions[0].question == "What is the optimal SEI thickness?"
        assert questions[0].conflicting_claims == ["<5nm is optimal", ">10nm is needed"]
        assert questions[0].evidence_gap == "No controlled thickness studies."
        # Second question has no conflicting_claims or evidence_gap
        assert questions[1].conflicting_claims == []
        assert questions[1].evidence_gap == ""


# ===================================================================
# Test: repair on JSON error
# ===================================================================


class TestRepairLogic:
    @pytest.mark.asyncio
    async def test_repair_on_json_error(self):
        """First call returns invalid JSON, second returns valid JSON.
        Verify repair_invoked=True in the record."""
        invalid_response = _make_response("this is not json at all")
        valid_response = _make_response(json.dumps({"claims": []}))
        backend, mock_client = _make_backend_with_mock_client([invalid_response, valid_response])

        claims, record = await backend.extract_claims("some text", SOURCE_META)

        assert record.repair_invoked is True
        assert claims == []
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """All calls return invalid JSON. Verify RuntimeError after exhaustion."""
        bad_responses = [
            _make_response("not json")
            for _ in range(4)  # 1 initial + 3 retries (max_retries=2 means 3 total)
        ]
        backend, _ = _make_backend_with_mock_client(bad_responses)

        with pytest.raises(RuntimeError, match="Failed after"):
            await backend.extract_claims("some text", SOURCE_META)


# ===================================================================
# Test: _extract_json handles code blocks
# ===================================================================


class TestExtractJson:
    def test_plain_json(self):
        text = '{"claims": []}'
        result = AnthropicCompilerBackend._extract_json(text)
        assert result == {"claims": []}

    def test_json_in_code_block(self):
        text = '```json\n{"claims": [{"statement": "test"}]}\n```'
        result = AnthropicCompilerBackend._extract_json(text)
        assert result == {"claims": [{"statement": "test"}]}

    def test_json_in_bare_code_block(self):
        text = '```\n{"value": 42}\n```'
        result = AnthropicCompilerBackend._extract_json(text)
        assert result == {"value": 42}

    def test_json_with_whitespace(self):
        text = '  \n  {"key": "val"}  \n  '
        result = AnthropicCompilerBackend._extract_json(text)
        assert result == {"key": "val"}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            AnthropicCompilerBackend._extract_json("not json")


# ===================================================================
# Test: lazy client creation
# ===================================================================


class TestLazyClientCreation:
    def test_client_not_created_at_init(self):
        backend = AnthropicCompilerBackend(api_key="test-key")
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_client_created_on_first_call(self):
        """Verify client is created lazily when _get_client() is called."""
        backend = AnthropicCompilerBackend(api_key="test-key")
        assert backend._client is None

        with patch(
            "hephaestus.forgebase.compiler.backends.anthropic_backend.anthropic"
        ) as mock_mod:
            mock_client_instance = AsyncMock()
            mock_mod.AsyncAnthropic.return_value = mock_client_instance

            client = backend._get_client()

            assert client is mock_client_instance
            mock_mod.AsyncAnthropic.assert_called_once_with(api_key="test-key")
            assert backend._client is mock_client_instance

    @pytest.mark.asyncio
    async def test_client_reused_on_subsequent_calls(self):
        """Second call should reuse the same client."""
        backend = AnthropicCompilerBackend(api_key="test-key")

        with patch(
            "hephaestus.forgebase.compiler.backends.anthropic_backend.anthropic"
        ) as mock_mod:
            mock_client_instance = AsyncMock()
            mock_mod.AsyncAnthropic.return_value = mock_client_instance

            client1 = backend._get_client()
            client2 = backend._get_client()

            assert client1 is client2
            # Only one instantiation
            assert mock_mod.AsyncAnthropic.call_count == 1


# ===================================================================
# Test: BackendCallRecord populated
# ===================================================================


class TestBackendCallRecord:
    @pytest.mark.asyncio
    async def test_backend_call_record_populated(self):
        payload = json.dumps({"claims": []})
        backend, _ = _make_backend_with_mock_client(
            [_make_response(payload, input_tokens=150, output_tokens=75)]
        )

        _, record = await backend.extract_claims("test", SOURCE_META)

        assert isinstance(record, BackendCallRecord)
        assert record.model_name == "claude-test"
        assert record.backend_kind == "anthropic"
        assert record.prompt_id == "claim_extraction"
        assert record.prompt_version == "1.0.0"
        assert record.schema_version == 1
        assert record.repair_invoked is False
        assert record.input_tokens == 150
        assert record.output_tokens == 75
        assert record.duration_ms >= 0
        assert record.raw_output_ref is None

    @pytest.mark.asyncio
    async def test_record_for_synthesis_method(self):
        payload = json.dumps(
            {
                "title": "Test",
                "content_markdown": "# Test",
                "claims": [],
                "related_concepts": [],
            }
        )
        backend, _ = _make_backend_with_mock_client([_make_response(payload)])

        _, record = await backend.synthesize_concept_page("Test", [], [], [], None)

        assert record.prompt_id == "synthesis"
        assert record.backend_kind == "anthropic"


# ===================================================================
# Test: error handling
# ===================================================================


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_api_error_retried_and_raised(self):
        """If the API itself raises an exception, it should retry and eventually raise."""
        backend = AnthropicCompilerBackend(api_key="test-key", model="claude-test", max_retries=1)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("API connection error"))
        backend._client = mock_client

        with pytest.raises(RuntimeError, match="API connection error"):
            await backend.extract_claims("test", SOURCE_META)

        # Should have tried 1 + 1 = 2 times
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        backend = AnthropicCompilerBackend(api_key=None)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "hephaestus.forgebase.compiler.backends.anthropic_backend.anthropic", create=True
            ),
            pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not set"),
        ):
            backend._get_client()
