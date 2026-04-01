"""
Stage 2: Cross-Domain Search.

Takes the abstract structural form produced by Stage 1 (``ProblemStructure``)
and searches 200+ knowledge domains for solved problems that share the same
mathematical shape.

The searcher:
1. Uses ``LensSelector`` to find the most distant lenses whose structural
   patterns map onto the problem.
2. For each selected lens, invokes the LLM (via DeepForge) to find solved
   problems in that domain matching the mathematical shape.
3. Returns 8-10 ``SearchCandidate`` objects from maximally distant fields.

Usage::

    from hephaestus.core.searcher import CrossDomainSearcher
    from hephaestus.core.decomposer import ProblemStructure

    searcher = CrossDomainSearcher(harness, loader)
    candidates = await searcher.search(structure)
    for c in candidates:
        print(c.source_domain, c.source_solution[:80])
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace
from hephaestus.lenses.loader import Lens, LensLoader
from hephaestus.lenses.selector import LensScore, LensSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt templates
# ---------------------------------------------------------------------------

_SEARCH_SYSTEM = """\
You are an expert in structural cross-domain pattern recognition. You will be
given an abstract structural description of a problem, and a specific knowledge
domain to search within.

Your task: identify ONE real, well-understood solved problem from the given
domain that shares the SAME MATHEMATICAL STRUCTURE as the abstract problem.

You must output ONLY valid JSON matching this schema:
{
  "source_domain": "<specific subdomain, e.g., 'Immune System — T-Cell Memory'>",
  "source_solution": "<description of how this domain solves the problem, 2-4 sentences>",
  "mechanism": "<the core mechanism/principle that makes it work, 1-2 sentences>",
  "structural_mapping": "<brief explanation of why the mathematical shapes match, 1-2 sentences>",
  "confidence": <float 0.0-1.0>
}

IMPORTANT:
- Be specific. Name real phenomena, organisms, systems, or mechanisms.
- The structural match must be genuine — not superficial metaphor.
- If no genuine structural match exists in this domain, set confidence < 0.3.
- Do NOT invent mechanisms. Use real, documented phenomena from the domain.
"""

_SEARCH_PROMPT_TEMPLATE = """\
ABSTRACT STRUCTURAL PROBLEM:
{structure}

MATHEMATICAL SHAPE:
{mathematical_shape}

CONSTRAINTS TO SATISFY:
{constraints}

DOMAIN TO SEARCH:
{domain_name}: {domain_description}

Domain axioms (from the lens):
{axioms}

Find a real solved problem in this domain that matches the mathematical structure above.
Return JSON only.
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SearchCandidate:
    """
    A candidate solution found by cross-domain search.

    Represents a solved problem from a foreign domain whose mathematical
    structure matches the target problem.

    Attributes
    ----------
    source_domain:
        Specific subdomain where the solution was found (e.g., "Immune System — T-Cell Memory").
    source_solution:
        Description of how the foreign domain solves its version of the problem.
    mechanism:
        The core mechanism/principle at work.
    structural_mapping:
        Brief explanation of why the mathematical shapes match.
    lens_used:
        The lens object that led to this candidate.
    lens_score:
        The LensScore from the selector (contains domain_distance etc.).
    confidence:
        Model's confidence in the structural match (0.0–1.0).
    raw_response:
        Raw model response text for debugging.
    cost_usd:
        API cost for generating this candidate.
    trace:
        DeepForge trace for this candidate.
    """

    source_domain: str
    source_solution: str
    mechanism: str
    structural_mapping: str
    lens_used: Lens
    lens_score: LensScore | None = None
    confidence: float = 0.8
    raw_response: str = ""
    cost_usd: float = 0.0
    trace: ForgeTrace | None = None

    @property
    def domain_distance(self) -> float:
        """Domain distance from the lens score, or 0.0 if unavailable."""
        return self.lens_score.domain_distance if self.lens_score else 0.0

    @property
    def lens_id(self) -> str:
        """Lens identifier."""
        return self.lens_used.lens_id

    def summary(self) -> str:
        """One-line summary for logging/display."""
        dist = f"dist={self.domain_distance:.2f}" if self.lens_score else "dist=?"
        return (
            f"[{self.source_domain}] {dist} conf={self.confidence:.2f} | "
            f"{self.source_solution[:80]}…"
        )


# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------


class SearchError(Exception):
    """Raised when the cross-domain search fails unrecoverably."""


class CrossDomainSearcher:
    """
    Stage 2 of the Genesis pipeline: Cross-Domain Search.

    Selects maximally distant lenses and queries each for solved problems
    that share the target problem's mathematical structure.

    Parameters
    ----------
    harness:
        DeepForge harness for LLM generation.
    loader:
        LensLoader providing access to the lens library.
    selector:
        LensSelector for domain distance scoring (created from loader if None).
    num_candidates:
        Target number of candidates to return (default 8).
    num_lenses:
        Number of lenses to query (should be >= num_candidates, default 10).
    min_confidence:
        Minimum confidence threshold to include a candidate (default 0.4).
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        loader: LensLoader | None = None,
        selector: LensSelector | None = None,
        num_candidates: int = 8,
        num_lenses: int = 10,
        min_confidence: float = 0.4,
    ) -> None:
        self._harness = harness
        self._loader = loader or LensLoader()
        self._selector = selector or LensSelector(self._loader)
        self._num_candidates = num_candidates
        self._num_lenses = num_lenses
        self._min_confidence = min_confidence

    async def search(
        self,
        structure: "ProblemStructure",  # noqa: F821 — imported below
    ) -> list[SearchCandidate]:
        """
        Search for cross-domain candidates matching the problem structure.

        Parameters
        ----------
        structure:
            The ``ProblemStructure`` from Stage 1.

        Returns
        -------
        list[SearchCandidate]
            Candidates sorted by domain distance (most distant first).
            Length is between 0 and ``num_candidates``.

        Raises
        ------
        SearchError
            If no lenses are available or a critical error occurs.
        """
        logger.info(
            "Cross-domain search | domain=%s maps_to=%s",
            structure.native_domain,
            structure.problem_maps_to,
        )
        t_start = time.monotonic()

        # Step 1: Select lenses
        lens_scores = self._select_lenses(structure)
        if not lens_scores:
            raise SearchError(
                f"No suitable lenses found for problem in domain '{structure.native_domain}'"
            )

        logger.info("Selected %d lenses for search", len(lens_scores))

        # Step 2: Query each lens concurrently
        import asyncio

        tasks = [
            self._query_lens(structure, ls)
            for ls in lens_scores
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Collect successful candidates
        candidates: list[SearchCandidate] = []
        for ls, result in zip(lens_scores, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Lens %s search failed: %s",
                    ls.lens.lens_id,
                    result,
                )
                continue
            if result is None:
                continue
            if result.confidence >= self._min_confidence:
                candidates.append(result)
            else:
                logger.debug(
                    "Candidate from %s below confidence threshold (%.2f < %.2f)",
                    ls.lens.lens_id,
                    result.confidence,
                    self._min_confidence,
                )

        # Sort by domain distance descending (most distant first)
        candidates.sort(key=lambda c: c.domain_distance, reverse=True)

        duration = time.monotonic() - t_start
        total_cost = sum(c.cost_usd for c in candidates)
        logger.info(
            "Search complete | candidates=%d duration=%.1fs total_cost=$%.4f",
            len(candidates),
            duration,
            total_cost,
        )

        return candidates[: self._num_candidates]

    def _select_lenses(
        self,
        structure: "ProblemStructure",
    ) -> list[LensScore]:
        """Select the most distant relevant lenses for the problem."""
        return self._selector.select(
            problem_description=structure.to_search_description(),
            problem_maps_to=structure.problem_maps_to,
            exclude_domains={structure.native_domain},
            target_domain=structure.native_domain,
            top_n=self._num_lenses,
            require_relevance=False,
        )

    async def _query_lens(
        self,
        structure: "ProblemStructure",
        lens_score: LensScore,
    ) -> SearchCandidate | None:
        """
        Query the LLM for a solved problem in the lens's domain.

        Returns None if the query fails or produces a low-confidence result.
        """
        lens = lens_score.lens

        # Build domain description from lens metadata
        domain_desc = f"{lens.domain.capitalize()} — {lens.name}"
        axioms_text = "\n".join(f"• {a}" for a in lens.axioms[:5])
        constraints_text = "\n".join(f"• {c}" for c in structure.constraints[:5])

        prompt = _SEARCH_PROMPT_TEMPLATE.format(
            structure=structure.structure,
            mathematical_shape=structure.mathematical_shape,
            constraints=constraints_text or "• (none specified)",
            domain_name=domain_desc,
            domain_description=" | ".join(
                p.abstract for p in lens.structural_patterns[:3]
            ),
            axioms=axioms_text,
        )

        try:
            result = await self._harness.forge(
                prompt,
                system=_SEARCH_SYSTEM,
                max_tokens=16000,
                temperature=0.5,
            )
            raw = result.output

            parsed = self._parse_candidate(raw)

            candidate = SearchCandidate(
                source_domain=parsed.get("source_domain", lens.name),
                source_solution=parsed.get("source_solution", ""),
                mechanism=parsed.get("mechanism", ""),
                structural_mapping=parsed.get("structural_mapping", ""),
                lens_used=lens,
                lens_score=lens_score,
                confidence=float(parsed.get("confidence", 0.5)),
                raw_response=raw,
                cost_usd=result.trace.total_cost_usd,
                trace=result.trace,
            )

            logger.debug(
                "Candidate from %s | conf=%.2f dist=%.2f | %s",
                lens.lens_id,
                candidate.confidence,
                candidate.domain_distance,
                candidate.source_domain,
            )
            return candidate

        except Exception as exc:
            logger.warning("Lens %s query failed: %s", lens.lens_id, exc)
            return None

    def _parse_candidate(self, raw: str) -> dict[str, Any]:
        """Parse model JSON output into a candidate dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON found in model output: {raw[:200]}")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parse error: {exc}") from exc

        required = {"source_solution", "mechanism"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Candidate missing required fields: {missing}")

        return data


# Import here to avoid circular imports at module load time
from hephaestus.core.decomposer import ProblemStructure  # noqa: E402
