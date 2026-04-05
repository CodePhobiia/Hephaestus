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

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.core.json_utils import loads_lenient
from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace
from hephaestus.lenses.cards import compile_lens_card
from hephaestus.lenses.cells import build_reference_state
from hephaestus.lenses.exclusion_ledger import AdaptiveExclusionLedger
from hephaestus.lenses.lineage import lineage_from_bundle_proof, lineage_from_singleton
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

CRITICAL: Go deep into the domain. Do not pick the first obvious example.
The best cross-domain transfers come from SPECIFIC, DETAILED mechanisms —
not broad principles. Instead of "immune systems remember threats" (too broad),
find "CD8+ T-cells maintain a clonal archive indexed by MHC-peptide complex
affinity, with recall latency inversely proportional to clone frequency"
(specific enough to engineer from).

The more SPECIFIC the mechanism, the more useful the structural transfer.
Name exact phenomena, exact processes, exact mathematical relationships
from the domain. Vague mechanisms produce vague inventions.

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
- CRITICAL NOVELTY TEST: The mechanism you find must be one that a domain expert in the TARGET domain would NOT independently reach for. If the mechanism is "cache results", "retry with backoff", "use a queue", or any other obvious engineering pattern — set confidence < 0.2 regardless of how good the structural match is. The value of cross-domain transfer is finding mechanisms that are UNKNOWN in the target domain, not validating known ones with foreign vocabulary.
"""

_SEARCH_PROMPT_TEMPLATE = """\
ABSTRACT STRUCTURAL PROBLEM:
{structure}

MATHEMATICAL SHAPE:
{mathematical_shape}

CONSTRAINTS TO SATISFY:
{constraints}

CURRENT TARGET-DOMAIN BASELINES:
{baseline_summary}

KNOWN FAILURE MODES / BOTTLENECKS IN THE TARGET DOMAIN:
{baseline_failures}

CONVENTIONAL TARGET-DOMAIN MECHANISMS TO AVOID REINVENTING:
{baseline_keywords}

DOMAIN TO SEARCH:
{domain_name}: {domain_description}

RETRIEVAL FRONTIER EXPANSION:
{retrieval_frontier}

LENS DISCLOSURE CARD (typed comparison surface):
{lens_card}
{bundle_context}

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
    bundle_proof: Any | None = None
    bundle_lineage: Any | None = None
    cohesion_cell: Any | None = None
    selection_mode: str = "singleton"
    bundle_role: str = ""
    bundle_position: int | None = None
    runtime_context: dict[str, Any] = field(default_factory=dict)

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


@dataclass
class SearchRuntimeResult:
    """Runtime selection metadata carried across search, translation, and verification."""

    retrieval_mode: str
    selected_lens_ids: tuple[str, ...]
    fallback_lens_ids: tuple[str, ...]
    bundle_proof: Any | None = None
    selection: Any | None = None
    exclusion_snapshot: dict[str, Any] = field(default_factory=dict)
    candidates: list[SearchCandidate] = field(default_factory=list)
    fallback_used: bool = False
    retrieval_frontier: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "selected_lens_ids": list(self.selected_lens_ids),
            "fallback_lens_ids": list(self.fallback_lens_ids),
            "bundle_proof": self.bundle_proof.to_dict() if self.bundle_proof is not None else None,
            "selection": self.selection.to_dict() if hasattr(self.selection, "to_dict") else None,
            "exclusion_snapshot": dict(self.exclusion_snapshot),
            "fallback_used": self.fallback_used,
            "retrieval_frontier": dict(self.retrieval_frontier),
            "candidate_count": len(self.candidates),
        }


@dataclass(frozen=True)
class RetrievalExpansionRequest:
    """Optional branch-conditioned retrieval steering for frontier expansion."""

    branch_id: str = ""
    failure_mode: str = ""
    novelty_target: str = ""
    excluded_families: tuple[str, ...] = ()
    analogy_axes: tuple[str, ...] = ()
    frontier_bias: str = "balanced"
    branch_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "failure_mode": self.failure_mode,
            "novelty_target": self.novelty_target,
            "excluded_families": list(self.excluded_families),
            "analogy_axes": list(self.analogy_axes),
            "frontier_bias": self.frontier_bias,
            "branch_hints": list(self.branch_hints),
        }


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
        max_bundle_size: int = 3,
        use_adaptive_lens_engine: bool = True,
        allow_lens_bundle_fallback: bool = True,
    ) -> None:
        self._harness = harness
        self._loader = loader or LensLoader()
        self._selector = selector or LensSelector(self._loader)
        self._num_candidates = num_candidates
        self._num_lenses = num_lenses
        self._min_confidence = min_confidence
        self._max_bundle_size = max(2, max_bundle_size)
        self._use_adaptive_lens_engine = use_adaptive_lens_engine
        self._allow_lens_bundle_fallback = allow_lens_bundle_fallback
        self._bundle_exclusion_ledger = AdaptiveExclusionLedger()
        self._last_runtime: SearchRuntimeResult | None = None

    @property
    def last_runtime(self) -> SearchRuntimeResult | None:
        return self._last_runtime

    async def search(
        self,
        structure: ProblemStructure,  # noqa: F821 — imported below
        *,
        expansion_request: RetrievalExpansionRequest | None = None,
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

        selection = self._select_runtime(structure)
        if not selection.selected_lenses:
            raise SearchError(
                f"No suitable lenses found for problem in domain '{structure.native_domain}'"
            )
        self._last_runtime = SearchRuntimeResult(
            retrieval_mode=selection.retrieval_mode,
            selected_lens_ids=tuple(score.lens.lens_id for score in selection.selected_lenses),
            fallback_lens_ids=tuple(score.lens.lens_id for score in selection.fallback_lenses),
            bundle_proof=selection.active_bundle,
            selection=selection,
            exclusion_snapshot=dict(selection.exclusion_snapshot),
            retrieval_frontier=expansion_request.to_dict() if expansion_request is not None else {},
        )

        logger.info(
            "Selected %d lenses for search | mode=%s bundle=%s",
            len(selection.selected_lenses),
            selection.retrieval_mode,
            getattr(selection.active_bundle, "bundle_id", None),
        )

        # Step 1: query the primary bundle or singleton set.
        import asyncio

        tasks = [
            self._query_lens(
                structure,
                lens_score,
                bundle_proof=selection.active_bundle,
                bundle_peer_ids=tuple(score.lens.lens_id for score in selection.selected_lenses),
                selection_mode=selection.retrieval_mode,
                bundle_position=index,
                expansion_request=expansion_request,
            )
            for index, lens_score in enumerate(selection.selected_lenses)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 2: collect successful candidates from the primary plan.
        candidates: list[SearchCandidate] = []
        for ls, result in zip(selection.selected_lenses, results, strict=True):
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

        # Step 3: if the bundle weakened during retrieval, query singleton fallbacks.
        fallback_used = False
        if (
            selection.retrieval_mode == "bundle"
            and len(candidates) < min(len(selection.selected_lenses), 2)
            and selection.fallback_lenses
        ):
            needed = min(self._num_candidates, max(1, self._num_lenses // 2))
            fallback_tasks = [
                self._query_lens(
                    structure,
                    lens_score,
                    bundle_proof=None,
                    bundle_peer_ids=(),
                    selection_mode="singleton_fallback",
                    expansion_request=expansion_request,
                )
                for lens_score in selection.fallback_lenses[:needed]
            ]
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            fallback_used = True
            for _ls, result in zip(
                selection.fallback_lenses[:needed], fallback_results, strict=True
            ):
                if isinstance(result, Exception) or result is None:
                    continue
                if result.confidence >= self._min_confidence:
                    candidates.append(result)

        # Sort bundle-backed candidates ahead of singleton fallbacks.
        candidates.sort(
            key=lambda c: (
                float(c.bundle_proof is not None),
                float(
                    getattr(c.bundle_proof, "proof_confidence", 0.0)
                    if c.bundle_proof is not None
                    else 0.0
                ),
                c.domain_distance,
            ),
            reverse=True,
        )

        duration = time.monotonic() - t_start
        total_cost = sum(c.cost_usd for c in candidates)
        if self._last_runtime is not None:
            self._last_runtime.candidates = list(candidates)
            self._last_runtime.fallback_used = fallback_used
        logger.info(
            "Search complete | candidates=%d duration=%.1fs total_cost=$%.4f fallback_used=%s",
            len(candidates),
            duration,
            total_cost,
            fallback_used,
        )

        return candidates[: self._num_candidates]

    def _select_runtime(self, structure: ProblemStructure) -> Any:
        """Select either a bundle proof or a singleton fallback plan."""
        if self._use_adaptive_lens_engine and hasattr(self._selector, "select_bundle_first"):
            return self._selector.select_bundle_first(
                problem_description=structure.to_search_description(),
                problem_maps_to=structure.problem_maps_to,
                exclude_domains={structure.native_domain},
                target_domain=structure.native_domain,
                top_n=self._num_lenses,
                require_relevance=False,
                structure=structure,
                max_bundle_size=self._max_bundle_size,
                exclusion_ledger=self._bundle_exclusion_ledger,
                allow_singleton_fallback=self._allow_lens_bundle_fallback,
            )

        lens_scores = self._select_lenses(structure)
        from hephaestus.lenses.bundles import BundleSelectionResult

        return BundleSelectionResult(
            retrieval_mode="singleton",
            selected_lenses=tuple(lens_scores),
            fallback_lenses=(),
        )

    def _select_lenses(
        self,
        structure: ProblemStructure,
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
        structure: ProblemStructure,
        lens_score: LensScore,
        *,
        bundle_proof: Any | None = None,
        bundle_peer_ids: tuple[str, ...] = (),
        selection_mode: str = "singleton",
        bundle_position: int | None = None,
        expansion_request: RetrievalExpansionRequest | None = None,
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
        lens_card = compile_lens_card(lens)
        bundle_context = self._bundle_context_for_prompt(
            lens_score,
            bundle_proof=bundle_proof,
            bundle_peer_ids=bundle_peer_ids,
        )
        frontier_context = self._expansion_context_for_prompt(expansion_request)

        dossier = getattr(structure, "baseline_dossier", None)
        baseline_summary = (
            getattr(dossier, "summary", "") or "(no external baseline reconnaissance attached)"
        )
        failure_modes = getattr(dossier, "common_failure_modes", []) or getattr(
            dossier, "known_bottlenecks", []
        )
        keywords_to_avoid = getattr(dossier, "keywords_to_avoid", [])

        prompt = _SEARCH_PROMPT_TEMPLATE.format(
            structure=structure.structure,
            mathematical_shape=structure.mathematical_shape,
            constraints=constraints_text or "• (none specified)",
            baseline_summary=baseline_summary,
            baseline_failures="\n".join(f"• {item}" for item in failure_modes[:6])
            or "• (none recorded)",
            baseline_keywords="\n".join(f"• {item}" for item in keywords_to_avoid[:8])
            or "• (none recorded)",
            domain_name=domain_desc,
            domain_description=" | ".join(p.abstract for p in lens.structural_patterns[:3]),
            retrieval_frontier=frontier_context,
            lens_card=lens_card.summary_text(),
            bundle_context=bundle_context,
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
            reference_state = build_reference_state(
                structure,
                branch_genome=getattr(lens_score, "branch_genome", None),
            )
            if bundle_proof is not None:
                lineage = lineage_from_bundle_proof(bundle_proof)
                cohesion_cell = next(
                    (
                        cell
                        for cell in getattr(bundle_proof, "cells", ())
                        if cell.lens_id == lens.lens_id
                    ),
                    None,
                )
                bundle_role = (
                    "critical"
                    if lens.lens_id in set(getattr(bundle_proof, "critical_lens_ids", ()))
                    else (
                        "conditional"
                        if getattr(bundle_proof, "conditional_requirements", {}).get(lens.lens_id)
                        else "support"
                    )
                )
            else:
                lineage = lineage_from_singleton(
                    lens.lens_id,
                    reference_state,
                    card_fingerprint64=lens_card.fingerprint64,
                )
                cohesion_cell = None
                bundle_role = "singleton"

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
                bundle_proof=bundle_proof,
                bundle_lineage=lineage,
                cohesion_cell=cohesion_cell,
                selection_mode=selection_mode,
                bundle_role=bundle_role,
                bundle_position=bundle_position,
                runtime_context={
                    "reference_state": reference_state.to_dict(),
                    "bundle_peer_ids": list(bundle_peer_ids),
                    "conditional_requirements": list(
                        getattr(bundle_proof, "conditional_requirements", {}).get(lens.lens_id, ())
                    )
                    if bundle_proof is not None
                    else [],
                    "retrieval_frontier": expansion_request.to_dict()
                    if expansion_request is not None
                    else {},
                },
            )

            logger.debug(
                "Candidate from %s | conf=%.2f dist=%.2f mode=%s | %s",
                lens.lens_id,
                candidate.confidence,
                candidate.domain_distance,
                selection_mode,
                candidate.source_domain,
            )
            return candidate

        except Exception as exc:
            logger.warning("Lens %s query failed: %s", lens.lens_id, exc)
            return None

    def _bundle_context_for_prompt(
        self,
        lens_score: LensScore,
        *,
        bundle_proof: Any | None,
        bundle_peer_ids: tuple[str, ...],
    ) -> str:
        if bundle_proof is None:
            return ""
        conditions = getattr(bundle_proof, "conditional_requirements", {}).get(
            lens_score.lens.lens_id, ()
        )
        return (
            "\nACTIVE BUNDLE PROOF:\n"
            f"- bundle_id: {getattr(bundle_proof, 'bundle_id', '')}\n"
            f"- bundle_confidence: {getattr(bundle_proof, 'proof_confidence', 0.0):.2f}\n"
            f"- active_peers: {', '.join(bundle_peer_ids)}\n"
            f"- translation_order: {', '.join(getattr(bundle_proof, 'translation_order', ()))}\n"
            f"- higher_order_score: {getattr(bundle_proof, 'higher_order_score', 0.0):.2f}\n"
            f"- conditional_requirements_for_this_lens: {', '.join(conditions) or 'none'}\n"
            "- search for a mechanism that complements the other active bundle members rather than duplicating them.\n"
        )

    @staticmethod
    def _expansion_context_for_prompt(expansion_request: RetrievalExpansionRequest | None) -> str:
        if expansion_request is None:
            return "• default frontier search (no branch-conditioned expansion request)"
        lines = [
            f"• branch_id: {expansion_request.branch_id or 'unbound'}",
            f"• failure_mode: {expansion_request.failure_mode or 'unspecified'}",
            f"• novelty_target: {expansion_request.novelty_target or 'maximize mechanism distance while staying executable'}",
            f"• frontier_bias: {expansion_request.frontier_bias}",
            "• excluded_families: " + (", ".join(expansion_request.excluded_families) or "none"),
            "• analogy_axes: " + (", ".join(expansion_request.analogy_axes) or "none"),
        ]
        lines.extend(f"• branch_hint: {hint}" for hint in expansion_request.branch_hints[:4])
        lines.append(
            "• search for a mechanism that expands the frontier rather than refining the nearest neighbor baseline."
        )
        return "\n".join(lines)

    def _parse_candidate(self, raw: str) -> dict[str, Any]:
        """Parse model JSON output into a candidate dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON found in model output: {raw[:200]}")

        data = loads_lenient(json_match.group(), default=None, label="searcher")
        if data is None:
            raise ValueError(f"JSON parse failure in candidate: {raw[:200]}")

        required = {"source_solution", "mechanism"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Candidate missing required fields: {missing}")

        return data


# Import here to avoid circular imports at module load time
from hephaestus.core.decomposer import ProblemStructure  # noqa: E402
