"""Anthropic-backed compiler backend.

Uses the Anthropic SDK to make structured extraction calls with JSON
schema enforcement. Includes a repair pass that re-calls with error
context if JSON parsing fails.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.models import (
    ConceptEvidence,
    EvidenceGrade,
    ExtractedClaim,
    ExtractedConcept,
    OpenQuestion,
    SourceCardContent,
    SynthesizedClaim,
    SynthesizedPage,
)
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version

logger = logging.getLogger(__name__)

# Lazy import — set at module level on first use of _get_client()
anthropic: Any = None


class AnthropicCompilerBackend(CompilerBackend):
    """Compiler backend using Anthropic Claude for structured extraction."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
        temperature: float = 0.1,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._client: Any = None  # Lazy-loaded Anthropic client

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Lazily create and cache the Anthropic async client."""
        if self._client is None:
            import os

            global anthropic
            if anthropic is None:
                try:
                    import anthropic as _anthropic

                    anthropic = _anthropic
                except ImportError as err:
                    raise RuntimeError(
                        "anthropic SDK not installed. Install it with: pip install anthropic"
                    ) from err

            key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Provide api_key to the "
                    "constructor or set the ANTHROPIC_API_KEY environment variable."
                )
            self._client = anthropic.AsyncAnthropic(api_key=key)
        return self._client

    # ------------------------------------------------------------------
    # Core LLM call with JSON extraction and repair
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict,
        prompt_id: str,
        prompt_version: str,
        schema_version: int,
    ) -> tuple[dict, BackendCallRecord]:
        """Make an LLM call, parse JSON, and retry with repair on failure.

        Returns the parsed dict and a :class:`BackendCallRecord` with
        timing, token counts, and provenance information.
        """
        client = self._get_client()
        start = time.monotonic()
        repair_invoked = False
        last_error: str | None = None

        for attempt in range(1 + self._max_retries):
            try:
                if attempt > 0:
                    repair_invoked = True
                    user_prompt_final = (
                        f"{user_prompt}\n\n"
                        f"IMPORTANT: Your previous response had a parsing error: "
                        f"{last_error}\n"
                        f"Please provide a valid JSON response matching the schema."
                    )
                else:
                    user_prompt_final = user_prompt

                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    temperature=self._temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt_final}],
                )

                raw_text = response.content[0].text
                parsed = self._extract_json(raw_text)

                duration = int((time.monotonic() - start) * 1000)
                record = BackendCallRecord(
                    model_name=self._model,
                    backend_kind="anthropic",
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    repair_invoked=repair_invoked,
                    input_tokens=getattr(response.usage, "input_tokens", 0),
                    output_tokens=getattr(response.usage, "output_tokens", 0),
                    duration_ms=duration,
                    raw_output_ref=None,
                )
                return parsed, record

            except json.JSONDecodeError as exc:
                last_error = str(exc)
                logger.warning(
                    "JSON parse error on attempt %d/%d: %s",
                    attempt + 1,
                    1 + self._max_retries,
                    exc,
                )
                continue
            except Exception as exc:
                last_error = str(exc)
                logger.error(
                    "LLM call error on attempt %d/%d: %s",
                    attempt + 1,
                    1 + self._max_retries,
                    exc,
                )
                if attempt == self._max_retries:
                    raise
                continue

        raise RuntimeError(f"Failed after {1 + self._max_retries} attempts: {last_error}")

    # ------------------------------------------------------------------
    # JSON extraction helper
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines: list[str] = []
            inside = False
            for line in lines:
                if line.strip().startswith("```") and not inside:
                    inside = True
                    continue
                elif line.strip() == "```" and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)
        return json.loads(text)

    # ------------------------------------------------------------------
    # Helper: parse EntityId / Version from metadata with defaults
    # ------------------------------------------------------------------

    @staticmethod
    def _source_id_from_meta(source_metadata: dict) -> EntityId:
        raw = source_metadata.get("source_id", "source_00000000000000000000000001")
        if isinstance(raw, EntityId):
            return raw
        return EntityId(raw)

    @staticmethod
    def _source_version_from_meta(source_metadata: dict) -> Version:
        raw = source_metadata.get("source_version", 1)
        if isinstance(raw, Version):
            return raw
        return Version(raw)

    # ==================================================================
    # Tier 1: per-source extraction
    # ==================================================================

    async def extract_claims(
        self,
        source_text: str,
        source_metadata: dict,
    ) -> tuple[list[ExtractedClaim], BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import claim_extraction as prompts

        user_prompt = prompts.USER_PROMPT_TEMPLATE.format(
            source_text=source_text,
            source_metadata=json.dumps(source_metadata),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        source_id = self._source_id_from_meta(source_metadata)
        source_ver = self._source_version_from_meta(source_metadata)

        claims: list[ExtractedClaim] = []
        for item in parsed.get("claims", []):
            claims.append(
                ExtractedClaim(
                    statement=item["statement"],
                    segment_ref=EvidenceSegmentRef(
                        source_id=source_id,
                        source_version=source_ver,
                        segment_start=item.get("segment_start", 0),
                        segment_end=item.get("segment_end", 0),
                        section_key=item.get("section_key"),
                        preview_text=item.get("evidence_segment", "")[:200],
                    ),
                    confidence=item.get("confidence", 0.5),
                    claim_type=item.get("claim_type", "factual"),
                )
            )
        return claims, record

    async def extract_concepts(
        self,
        source_text: str,
        source_metadata: dict,
    ) -> tuple[list[ExtractedConcept], BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import concept_extraction as prompts

        user_prompt = prompts.USER_PROMPT_TEMPLATE.format(
            source_text=source_text,
            source_metadata=json.dumps(source_metadata),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        source_id = self._source_id_from_meta(source_metadata)
        source_ver = self._source_version_from_meta(source_metadata)

        concepts: list[ExtractedConcept] = []
        for item in parsed.get("concepts", []):
            evidence_segments: list[EvidenceSegmentRef] = []
            for seg in item.get("evidence_segments", []):
                evidence_segments.append(
                    EvidenceSegmentRef(
                        source_id=source_id,
                        source_version=source_ver,
                        segment_start=seg.get("segment_start", 0),
                        segment_end=seg.get("segment_end", 0),
                        section_key=seg.get("section_key"),
                        preview_text=seg.get("preview_text", "")[:200],
                    )
                )

            kind_str = item.get("kind", "concept")
            try:
                kind = CandidateKind(kind_str)
            except ValueError:
                kind = CandidateKind.CONCEPT

            concepts.append(
                ExtractedConcept(
                    name=item["name"],
                    aliases=item.get("aliases", []),
                    kind=kind,
                    evidence_segments=evidence_segments,
                    salience=item.get("salience", 0.5),
                )
            )
        return concepts, record

    async def generate_source_card(
        self,
        source_text: str,
        source_metadata: dict,
        extracted_claims: list[ExtractedClaim],
        extracted_concepts: list[ExtractedConcept],
    ) -> tuple[SourceCardContent, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import source_card as prompts

        claims_data = [
            {"statement": c.statement, "confidence": c.confidence, "type": c.claim_type}
            for c in extracted_claims
        ]
        concepts_data = [
            {"name": c.name, "aliases": c.aliases, "kind": c.kind.value, "salience": c.salience}
            for c in extracted_concepts
        ]

        user_prompt = prompts.USER_PROMPT_TEMPLATE.format(
            source_text=source_text,
            source_metadata=json.dumps(source_metadata),
            extracted_claims=json.dumps(claims_data),
            extracted_concepts=json.dumps(concepts_data),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        card = SourceCardContent(
            summary=parsed.get("summary", ""),
            key_claims=parsed.get("key_claims", []),
            methods=parsed.get("methods", []),
            limitations=parsed.get("limitations", []),
            evidence_quality=parsed.get("evidence_quality", "unknown"),
            concepts_mentioned=parsed.get("concepts_mentioned", []),
        )
        return card, record

    async def grade_evidence(
        self,
        claim: str,
        segment_ref: EvidenceSegmentRef,
        source_text: str,
    ) -> tuple[EvidenceGrade, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import evidence_grading as prompts

        user_prompt = prompts.USER_PROMPT_TEMPLATE.format(
            claim=claim,
            evidence_segment=segment_ref.preview_text,
            source_text=source_text,
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        grade = EvidenceGrade(
            strength=parsed.get("strength", 0.0),
            methodology_quality=parsed.get("methodology_quality", "unknown"),
            reasoning=parsed.get("reasoning", ""),
        )
        return grade, record

    # ==================================================================
    # Tier 2: vault-wide synthesis
    # ==================================================================

    def _parse_synthesized_page(self, parsed: dict) -> SynthesizedPage:
        """Parse a synthesized page response shared by concept, mechanism,
        comparison, and timeline page methods."""
        claims: list[SynthesizedClaim] = []
        for item in parsed.get("claims", []):
            support_str = item.get("support_type", "synthesized")
            try:
                support_type = SupportType(support_str)
            except ValueError:
                support_type = SupportType.SYNTHESIZED

            claims.append(
                SynthesizedClaim(
                    statement=item["statement"],
                    support_type=support_type,
                    confidence=item.get("confidence", 0.5),
                    derived_from_claims=item.get("derived_from_claims", []),
                )
            )

        return SynthesizedPage(
            title=parsed.get("title", ""),
            content_markdown=parsed.get("content_markdown", ""),
            claims=claims,
            related_concepts=parsed.get("related_concepts", []),
        )

    @staticmethod
    def _format_evidence(evidence: list[ConceptEvidence]) -> str:
        """Format ConceptEvidence list into a string for prompts."""
        if not evidence:
            return "(no evidence provided)"
        parts: list[str] = []
        for ev in evidence:
            parts.append(
                f"Source: {ev.source_title} (ID: {ev.source_id})\nClaims: {json.dumps(ev.claims)}\n"
            )
        return "\n".join(parts)

    async def synthesize_concept_page(
        self,
        concept_name: str,
        evidence: list[ConceptEvidence],
        existing_claims: list[str],
        related_concepts: list[str],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import synthesis as prompts

        user_prompt = prompts.CONCEPT_PAGE_USER_PROMPT_TEMPLATE.format(
            concept_name=concept_name,
            evidence=self._format_evidence(evidence),
            existing_claims=json.dumps(existing_claims),
            related_concepts=json.dumps(related_concepts),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.CONCEPT_PAGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.CONCEPT_PAGE_OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        page = self._parse_synthesized_page(parsed)
        return page, record

    async def synthesize_mechanism_page(
        self,
        mechanism_name: str,
        causal_claims: list[str],
        source_evidence: list[ConceptEvidence],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import synthesis as prompts

        user_prompt = prompts.MECHANISM_PAGE_USER_PROMPT_TEMPLATE.format(
            mechanism_name=mechanism_name,
            causal_claims=json.dumps(causal_claims),
            source_evidence=self._format_evidence(source_evidence),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.MECHANISM_PAGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.MECHANISM_PAGE_OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        page = self._parse_synthesized_page(parsed)
        return page, record

    async def synthesize_comparison_page(
        self,
        entities: list[str],
        comparison_data: list[dict],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import synthesis as prompts

        user_prompt = prompts.COMPARISON_PAGE_USER_PROMPT_TEMPLATE.format(
            entities=json.dumps(entities),
            comparison_data=json.dumps(comparison_data),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.COMPARISON_PAGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.COMPARISON_PAGE_OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        page = self._parse_synthesized_page(parsed)
        return page, record

    async def synthesize_timeline_page(
        self,
        topic: str,
        temporal_claims: list[str],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import synthesis as prompts

        user_prompt = prompts.TIMELINE_PAGE_USER_PROMPT_TEMPLATE.format(
            topic=topic,
            temporal_claims=json.dumps(temporal_claims),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.TIMELINE_PAGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.TIMELINE_PAGE_OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        page = self._parse_synthesized_page(parsed)
        return page, record

    async def identify_open_questions(
        self,
        contested_claims: list[str],
        evidence_gaps: list[str],
        policy: object,
    ) -> tuple[list[OpenQuestion], BackendCallRecord]:
        from hephaestus.forgebase.compiler.prompts import synthesis as prompts

        user_prompt = prompts.OPEN_QUESTIONS_USER_PROMPT_TEMPLATE.format(
            contested_claims=json.dumps(contested_claims),
            evidence_gaps=json.dumps(evidence_gaps),
        )

        parsed, record = await self._call_llm(
            system_prompt=prompts.OPEN_QUESTIONS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=prompts.OPEN_QUESTIONS_OUTPUT_SCHEMA,
            prompt_id=prompts.PROMPT_ID,
            prompt_version=prompts.PROMPT_VERSION,
            schema_version=prompts.SCHEMA_VERSION,
        )

        questions: list[OpenQuestion] = []
        for item in parsed.get("questions", []):
            questions.append(
                OpenQuestion(
                    question=item["question"],
                    context=item.get("context", ""),
                    conflicting_claims=item.get("conflicting_claims", []),
                    evidence_gap=item.get("evidence_gap", ""),
                )
            )
        return questions, record
