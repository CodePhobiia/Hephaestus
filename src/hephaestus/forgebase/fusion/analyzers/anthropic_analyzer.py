"""Anthropic-backed FusionAnalyzer for structural analogy reasoning.

Uses the Anthropic SDK for structured JSON extraction with repair.
Analogy-specific prompts ask Claude to determine genuine structural
analogies, map components, identify breaks, and suggest transfers.
Low temperature (0.1) for analytical precision.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from hephaestus.forgebase.domain.enums import AnalogyVerdict
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.extraction.models import DomainContextPack
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.models import (
    AnalogicalMap,
    AnalogyBreak,
    BridgeCandidate,
    ComponentMapping,
    ConstraintMapping,
    TransferOpportunity,
)
from hephaestus.forgebase.service.id_generator import IdGenerator

logger = logging.getLogger(__name__)

# Prompt constants
PROMPT_ID = "fusion_analysis"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

SYSTEM_PROMPT = """\
You are a structural analogy analyst specializing in cross-domain knowledge transfer.

Given candidate bridge pairs between two knowledge domains, determine for each:
1. Is there a genuine structural analogy? (verdict: strong_analogy, weak_analogy, no_analogy, or invalid)
2. What components in domain A map to components in domain B?
3. Where does the analogy break down?
4. What knowledge could transfer from one domain to the other?

Be rigorous. A structural analogy requires shared relational structure, not just surface similarity.
Explicitly say "no_analogy" when there is none — false positives are worse than false negatives.

Return your analysis as a JSON object with an "analyses" array.
"""

USER_PROMPT_TEMPLATE = """\
Analyze these candidate bridge pairs for structural analogies.

{problem_section}

## Left Domain Context
{left_context}

## Right Domain Context
{right_context}

## Candidates
{candidates_section}

Return JSON matching this schema:
{{
  "analyses": [
    {{
      "candidate_id": "<id of the candidate>",
      "verdict": "strong_analogy" | "weak_analogy" | "no_analogy" | "invalid",
      "bridge_concept": "<concise description of the bridging structural concept>",
      "mapped_components": [
        {{
          "left_component": "<component in left domain>",
          "right_component": "<analogous component in right domain>",
          "mapping_confidence": <0.0-1.0>
        }}
      ],
      "mapped_constraints": [
        {{
          "left_constraint": "<constraint in left domain>",
          "right_constraint": "<constraint in right domain>",
          "preserved": <true if the constraint maps cleanly>
        }}
      ],
      "analogy_breaks": [
        {{
          "description": "<where the analogy breaks down>",
          "severity": "high" | "medium" | "low",
          "category": "structural_mismatch" | "scale_difference" | "domain_assumption" | "temporal_mismatch"
        }}
      ],
      "confidence": <0.0-1.0>,
      "transfer": {{
        "mechanism": "<how knowledge transfers>",
        "rationale": "<why this transfer is valuable>",
        "caveats": ["<caveat 1>", ...],
        "caveat_categories": ["<category 1>", ...]
      }} or null if no transfer opportunity
    }}
  ]
}}
"""


class AnthropicFusionAnalyzer(FusionAnalyzer):
    """FusionAnalyzer using Anthropic Claude for structural analogy reasoning."""

    def __init__(
        self,
        id_gen: IdGenerator,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
        temperature: float = 0.1,
        max_retries: int = 2,
    ) -> None:
        self._id_gen = id_gen
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._client: Any = None

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Lazily create and cache the Anthropic async client."""
        if self._client is None:
            import os

            try:
                import anthropic
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
        system: str,
        user: str,
    ) -> tuple[dict, BackendCallRecord]:
        """Make an LLM call, parse JSON, and retry with repair on failure.

        Returns the parsed dict and a BackendCallRecord with timing,
        token counts, and provenance.
        """
        client = self._get_client()
        start = time.monotonic()
        repair_invoked = False
        last_error: str | None = None
        total_input_tokens = 0
        total_output_tokens = 0

        for attempt in range(1 + self._max_retries):
            try:
                if attempt > 0:
                    repair_invoked = True
                    prompt = (
                        f"{user}\n\n"
                        f"IMPORTANT: Your previous response had a parsing error: "
                        f"{last_error}\n"
                        f"Please provide a valid JSON response matching the schema."
                    )
                else:
                    prompt = user

                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    temperature=self._temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )

                total_input_tokens += getattr(response.usage, "input_tokens", 0)
                total_output_tokens += getattr(response.usage, "output_tokens", 0)

                raw_text = response.content[0].text.strip()
                raw_text = self._extract_json_text(raw_text)
                parsed = json.loads(raw_text)

                duration = int((time.monotonic() - start) * 1000)
                record = BackendCallRecord(
                    model_name=self._model,
                    backend_kind="anthropic",
                    prompt_id=PROMPT_ID,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                    repair_invoked=repair_invoked,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
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

        raise RuntimeError(f"LLM call failed after {1 + self._max_retries} attempts: {last_error}")

    # ------------------------------------------------------------------
    # JSON extraction helper
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json_text(text: str) -> str:
        """Strip markdown code-block fences if present."""
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
        return text

    # ------------------------------------------------------------------
    # Prompt formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_context(pack: DomainContextPack) -> str:
        """Format a DomainContextPack into a text summary for the prompt."""
        parts: list[str] = []
        if pack.concepts:
            parts.append("Concepts:")
            for entry in pack.concepts[:10]:
                parts.append(f"  - {entry.text}")
        if pack.mechanisms:
            parts.append("Mechanisms:")
            for entry in pack.mechanisms[:10]:
                parts.append(f"  - {entry.text}")
        if pack.open_questions:
            parts.append("Open questions:")
            for entry in pack.open_questions[:5]:
                parts.append(f"  - {entry.text}")
        return "\n".join(parts) if parts else "(no context available)"

    @staticmethod
    def _format_candidates(candidates: list[BridgeCandidate]) -> str:
        """Format candidates into a structured text block for the prompt."""
        parts: list[str] = []
        for i, c in enumerate(candidates):
            parts.append(
                f"Candidate {i + 1} (ID: {c.candidate_id}):\n"
                f"  Left ({c.left_kind.value}): {c.left_text}\n"
                f"  Right ({c.right_kind.value}): {c.right_text}\n"
                f"  Similarity: {c.similarity_score:.3f}\n"
                f"  Problem relevance: {c.problem_relevance}"
            )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_analyses(
        self,
        parsed: dict,
        candidates: list[BridgeCandidate],
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity]]:
        """Parse LLM response into AnalogicalMaps and TransferOpportunities."""
        # Build a lookup for candidate provenance by ID string
        candidate_lookup: dict[str, BridgeCandidate] = {str(c.candidate_id): c for c in candidates}

        maps: list[AnalogicalMap] = []
        transfers: list[TransferOpportunity] = []

        for item in parsed.get("analyses", []):
            cand_id_str = item.get("candidate_id", "")
            candidate = candidate_lookup.get(cand_id_str)

            # Parse verdict with fallback
            verdict_str = item.get("verdict", "no_analogy")
            try:
                verdict = AnalogyVerdict(verdict_str)
            except ValueError:
                verdict = AnalogyVerdict.NO_ANALOGY

            # Parse component mappings
            mapped_components: list[ComponentMapping] = []
            for comp in item.get("mapped_components", []):
                mapped_components.append(
                    ComponentMapping(
                        left_component=comp.get("left_component", ""),
                        right_component=comp.get("right_component", ""),
                        left_ref=candidate.left_entity_ref if candidate else None,
                        right_ref=candidate.right_entity_ref if candidate else None,
                        mapping_confidence=comp.get("mapping_confidence", 0.0),
                    )
                )

            # Parse constraint mappings
            mapped_constraints: list[ConstraintMapping] = []
            for const in item.get("mapped_constraints", []):
                mapped_constraints.append(
                    ConstraintMapping(
                        left_constraint=const.get("left_constraint", ""),
                        right_constraint=const.get("right_constraint", ""),
                        preserved=const.get("preserved", True),
                    )
                )

            # Parse analogy breaks
            analogy_breaks: list[AnalogyBreak] = []
            for brk in item.get("analogy_breaks", []):
                analogy_breaks.append(
                    AnalogyBreak(
                        description=brk.get("description", ""),
                        severity=brk.get("severity", "low"),
                        category=brk.get("category", "structural_mismatch"),
                    )
                )

            amap = AnalogicalMap(
                map_id=self._id_gen.generate("amap"),
                bridge_concept=item.get("bridge_concept", ""),
                left_structure=candidate.left_text if candidate else "",
                right_structure=candidate.right_text if candidate else "",
                mapped_components=mapped_components,
                mapped_constraints=mapped_constraints,
                analogy_breaks=analogy_breaks,
                confidence=item.get("confidence", 0.0),
                verdict=verdict,
                problem_relevance=candidate.problem_relevance if candidate else None,
                source_candidates=[candidate.candidate_id] if candidate else [],
                left_page_refs=[candidate.left_entity_ref] if candidate else [],
                right_page_refs=[candidate.right_entity_ref] if candidate else [],
                left_claim_refs=candidate.left_claim_refs if candidate else [],
                right_claim_refs=candidate.right_claim_refs if candidate else [],
            )
            maps.append(amap)

            # Generate transfer only for STRONG analogies with transfer data
            transfer_data = item.get("transfer")
            if verdict == AnalogyVerdict.STRONG_ANALOGY and transfer_data and candidate:
                transfers.append(
                    TransferOpportunity(
                        opportunity_id=self._id_gen.generate("txfr"),
                        from_vault_id=candidate.left_vault_id,
                        to_vault_id=candidate.right_vault_id,
                        mechanism=transfer_data.get("mechanism", ""),
                        rationale=transfer_data.get("rationale", ""),
                        caveats=transfer_data.get("caveats", []),
                        caveat_categories=transfer_data.get("caveat_categories", []),
                        analogical_map_id=amap.map_id,
                        confidence=item.get("confidence", 0.0),
                        problem_relevance=candidate.problem_relevance,
                        from_page_refs=[candidate.left_entity_ref],
                        to_page_refs=[candidate.right_entity_ref],
                        from_claim_refs=candidate.left_claim_refs,
                    )
                )

        return maps, transfers

    # ==================================================================
    # FusionAnalyzer interface
    # ==================================================================

    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        left_context: DomainContextPack,
        right_context: DomainContextPack,
        problem: str | None = None,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity], BackendCallRecord]:
        """Analyze bridge candidates for structural analogies via Claude."""
        if not candidates:
            record = BackendCallRecord(
                model_name=self._model,
                backend_kind="anthropic",
                prompt_id=PROMPT_ID,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                repair_invoked=False,
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
                raw_output_ref=None,
            )
            return [], [], record

        # Build prompt
        problem_section = (
            f"## Problem Context\n{problem}" if problem else "No specific problem context provided."
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            problem_section=problem_section,
            left_context=self._format_context(left_context),
            right_context=self._format_context(right_context),
            candidates_section=self._format_candidates(candidates),
        )

        parsed, record = await self._call_llm(SYSTEM_PROMPT, user_prompt)
        maps, transfers = self._parse_analyses(parsed, candidates)

        return maps, transfers, record
