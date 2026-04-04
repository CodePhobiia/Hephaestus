"""Anthropic-backed LintAnalyzer for lint-specific reasoning.

Uses the Anthropic SDK for structured extraction with JSON output
parsing and repair.  Each method maps to one detector family in the
lint subsystem:

* contradiction detection
* source-gap assessment
* search-resolvability check

The class lazily initialises an ``AsyncAnthropic`` client and includes
automatic retry with JSON repair prompts when parsing fails.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from hephaestus.forgebase.linting.analyzer import (
    ContradictionResult,
    LintAnalyzer,
    ResolvabilityAssessment,
    SourceGapAssessment,
)

logger = logging.getLogger(__name__)


class AnthropicLintAnalyzer(LintAnalyzer):
    """Lint analyzer using Anthropic Claude for reasoning."""

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
            except ImportError:
                raise RuntimeError(
                    "anthropic SDK not installed. "
                    "Install it with: pip install anthropic"
                )

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

    async def _call_llm(self, system: str, user: str) -> dict:
        """Make an LLM call, parse JSON, and retry with repair on failure.

        On each retry the previous JSON parse error is appended to the
        user prompt so the model can self-correct.  Markdown code-block
        fences (````` ```json ... ``` `````) are stripped before parsing.
        """
        client = self._get_client()
        last_error: str | None = None

        for attempt in range(1 + self._max_retries):
            try:
                if attempt == 0:
                    prompt = user
                else:
                    prompt = (
                        f"{user}\n\n"
                        f"Previous JSON error: {last_error}. "
                        f"Return valid JSON."
                    )

                response = await client.messages.create(
                    model=self._model,
                    max_tokens=2048,
                    temperature=self._temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )

                text = response.content[0].text.strip()
                text = self._extract_json_text(text)
                return json.loads(text)

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

        raise RuntimeError(
            f"LLM call failed after {1 + self._max_retries} attempts: {last_error}"
        )

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

    # ==================================================================
    # LintAnalyzer interface
    # ==================================================================

    async def detect_contradictions(
        self,
        claim_pairs: list[tuple[str, str]],
    ) -> list[ContradictionResult]:
        """Analyse claim pairs for contradictions via LLM."""
        if not claim_pairs:
            return []

        system = (
            "You are a precise knowledge contradiction detector. "
            "Analyze pairs of claims and determine if they contradict each other. "
            "Return JSON with an array of results."
        )

        pairs_text = "\n".join(
            f'Pair {i + 1}: A: "{a}" vs B: "{b}"'
            for i, (a, b) in enumerate(claim_pairs)
        )

        user = (
            f"Analyze these claim pairs for contradictions:\n\n{pairs_text}\n\n"
            f'Return JSON: {{"results": [{{"is_contradictory": bool, '
            f'"explanation": str, "confidence": float}}]}}'
        )

        parsed = await self._call_llm(system, user)

        results: list[ContradictionResult] = []
        for item in parsed.get("results", []):
            results.append(
                ContradictionResult(
                    is_contradictory=item.get("is_contradictory", False),
                    explanation=item.get("explanation", ""),
                    confidence=item.get("confidence", 0.5),
                )
            )

        # Pad if the model returned fewer results than input pairs
        while len(results) < len(claim_pairs):
            results.append(
                ContradictionResult(
                    is_contradictory=False,
                    explanation="No analysis available",
                    confidence=0.0,
                )
            )

        # Truncate if the model returned more results than input pairs
        return results[: len(claim_pairs)]

    async def assess_source_gaps(
        self,
        concept: str,
        evidence_count: int,
        claims: list[str],
    ) -> SourceGapAssessment:
        """Assess whether thin evidence represents a real knowledge gap."""
        system = (
            "You are a knowledge gap assessor. "
            "Determine if a concept has insufficient evidence and how "
            "severe the gap is."
        )

        claims_text = "\n".join(f"- {c}" for c in claims[:10])
        user = (
            f"Concept: {concept}\n"
            f"Evidence from {evidence_count} source(s)\n"
            f"Claims:\n{claims_text}\n\n"
            f'Return JSON: {{"is_gap": bool, '
            f'"severity": "critical"|"moderate"|"minor", "explanation": str}}'
        )

        parsed = await self._call_llm(system, user)

        return SourceGapAssessment(
            is_gap=parsed.get("is_gap", True),
            severity=parsed.get("severity", "moderate"),
            explanation=parsed.get("explanation", ""),
        )

    async def check_resolvable_by_search(
        self,
        claim: str,
        existing_support: list[str],
    ) -> ResolvabilityAssessment:
        """Check if a weakly-supported claim could be strengthened by search."""
        system = (
            "You are a research opportunity assessor. "
            "Determine if a claim could be better supported by searching "
            "for additional evidence."
        )

        support_text = "\n".join(f"- {s}" for s in existing_support[:5]) or "None"
        user = (
            f"Claim: {claim}\n"
            f"Existing support:\n{support_text}\n\n"
            f'Return JSON: {{"is_resolvable": bool, '
            f'"search_query": str, "confidence": float}}'
        )

        parsed = await self._call_llm(system, user)

        return ResolvabilityAssessment(
            is_resolvable=parsed.get("is_resolvable", False),
            search_query=parsed.get("search_query", ""),
            confidence=parsed.get("confidence", 0.5),
        )
