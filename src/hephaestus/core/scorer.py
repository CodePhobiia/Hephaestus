"""
Stage 3: Candidate Scoring.

Scores each ``SearchCandidate`` on two axes:

- **Structural fidelity** (0–1): How precisely does the foreign solution map
  onto the original problem structure?  Assessed via LLM (few-shot prompt).
- **Domain distance** (0–1): How far is the source domain from the target?
  Computed via cosine distance on sentence embeddings.

Combined score: ``fidelity × distance^1.5``

The superlinear exponent on distance (α = 1.5) rewards candidates from
maximally distant domains — the further the source, the more genuinely
novel the invention will be.

Candidates from adjacent domains (distance < 0.3) are filtered out.

Usage::

    scorer = CandidateScorer(harness)
    scored = await scorer.score(candidates, structure)
    for s in scored:
        print(f"{s.source_domain}: fidelity={s.structural_fidelity:.2f} "
              f"dist={s.domain_distance:.2f} score={s.combined_score:.3f}")
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hephaestus.core.decomposer import ProblemStructure
from hephaestus.core.json_utils import loads_lenient
from hephaestus.core.searcher import SearchCandidate
from hephaestus.deepforge.harness import DeepForgeHarness, ForgeTrace
from hephaestus.lenses.selector import EmbeddingModel, _cosine_distance
from hephaestus.novelty import NoveltyVector

if TYPE_CHECKING:
    pass

def _lazy_np():
    import numpy as np
    return np

logger = logging.getLogger(__name__)

# Superlinear distance exponent — same as the lens selector
_DISTANCE_EXPONENT = 1.5

# Minimum domain distance; candidates below this are filtered out
_MIN_DOMAIN_DISTANCE = 0.3

# ---------------------------------------------------------------------------
# System prompt for fidelity scoring
# ---------------------------------------------------------------------------

_FIDELITY_SYSTEM = """\
You are a structural isomorphism evaluator. You will be given:
1. An abstract structural problem description
2. A candidate solution from a foreign domain

Your task: assess how precisely the foreign solution's STRUCTURE maps onto the
target problem's STRUCTURE. Score structural fidelity from 0.0 to 1.0.

Fidelity criteria:
- 0.9-1.0: Near-perfect structural isomorphism — every element of the target
           maps to a corresponding element in the source mechanism
- 0.7-0.9: Strong structural match — most elements map, minor gaps
- 0.5-0.7: Partial match — core mechanism maps but peripheral elements differ
- 0.3-0.5: Weak match — some structural resonance but significant mismatches
- 0.0-0.3: Poor match — superficial metaphor, structural incompatibility

Output ONLY valid JSON:
{
  "structural_fidelity": <float 0.0-1.0>,
  "fidelity_reasoning": "<1-2 sentences explaining the score>",
  "strong_mappings": ["<element A maps to element B>", ...],
  "weak_mappings": ["<where the analogy struggles>", ...]
}
"""

_FIDELITY_PROMPT_TEMPLATE = """\
TARGET PROBLEM STRUCTURE:
{structure}

MATHEMATICAL SHAPE:
{mathematical_shape}

CANDIDATE FROM DOMAIN: {source_domain}
Solution: {source_solution}
Mechanism: {mechanism}
Claimed structural mapping: {structural_mapping}

Evaluate structural fidelity. Return JSON only.
"""

_MECHANISM_NOVELTY_SYSTEM = """\
You are a mechanism novelty evaluator. Given a candidate solution from a foreign domain
and the target domain it would be applied to, assess whether the MECHANISM itself
is novel in the target domain.

The question is NOT whether the source domain is far away. The question is:
"Would a competent engineer in the target domain independently come up with this
specific mechanism to solve this problem?"

Scoring:
- 0.9-1.0: The mechanism is genuinely alien to the target domain — no engineer would think of this
- 0.7-0.9: The mechanism is unusual and non-obvious in the target domain
- 0.4-0.7: The mechanism has analogues in the target domain but this framing adds insight
- 0.1-0.4: The mechanism is a known pattern with foreign vocabulary (e.g., "T-cell memory" = caching)
- 0.0-0.1: The mechanism is completely obvious in the target domain

Output ONLY valid JSON:
{
  "mechanism_novelty": <float 0.0-1.0>,
  "target_domain_equivalent": "<what's the closest known pattern in the target domain? Be specific>",
  "novelty_reasoning": "<why this mechanism is or isn't novel in the target domain>",
  "would_engineer_reach_for_this": <bool — would a target domain expert independently build this?>
}
"""

_MECHANISM_NOVELTY_PROMPT = """\
TARGET DOMAIN: {native_domain}
TARGET PROBLEM: {structure}

CANDIDATE MECHANISM FROM {source_domain}:
{mechanism}
Solution: {source_solution}

Would a {native_domain} engineer independently come up with this mechanism?
What is the closest known pattern in {native_domain}?
Rate mechanism novelty. Return JSON only.
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ScoredCandidate:
    """
    A ``SearchCandidate`` enriched with scoring information.

    Attributes
    ----------
    candidate:
        The original ``SearchCandidate`` from Stage 2.
    structural_fidelity:
        LLM-assessed structural fidelity score (0.0–1.0).
    domain_distance:
        Embedding-based cosine distance from source domain to target (0.0–1.0).
    combined_score:
        ``structural_fidelity × domain_distance^1.5`` — the primary ranking key.
    fidelity_reasoning:
        Model's brief explanation of the fidelity score.
    strong_mappings:
        Element-by-element mappings that hold well.
    weak_mappings:
        Where the structural analogy breaks.
    scoring_cost_usd:
        API cost for the fidelity scoring LLM call.
    scoring_trace:
        DeepForge trace for the scoring call.
    """

    candidate: SearchCandidate
    structural_fidelity: float
    domain_distance: float
    combined_score: float
    fidelity_reasoning: str = ""
    strong_mappings: list[str] = field(default_factory=list)
    weak_mappings: list[str] = field(default_factory=list)
    mechanism_novelty: float = 0.5  # 0=obvious, 1=alien to target domain
    target_domain_equivalent: str = ""  # closest known pattern
    novelty_reasoning: str = ""
    would_engineer_reach_for_this: bool = True  # if True, mechanism is conventional
    scoring_cost_usd: float = 0.0
    scoring_trace: ForgeTrace | None = None
    novelty_vector: NoveltyVector = field(default_factory=NoveltyVector)
    creativity_score: float = 0.0
    retrieval_expansion_headroom: float = 0.0

    # Delegate key properties to the underlying candidate
    @property
    def source_domain(self) -> str:
        return self.candidate.source_domain

    @property
    def source_solution(self) -> str:
        return self.candidate.source_solution

    @property
    def mechanism(self) -> str:
        return self.candidate.mechanism

    @property
    def lens_id(self) -> str:
        return self.candidate.lens_id

    @property
    def lens_used(self):
        return self.candidate.lens_used

    @property
    def bundle_proof(self) -> Any | None:
        return getattr(self.candidate, "bundle_proof", None)

    @property
    def bundle_lineage(self) -> Any | None:
        return getattr(self.candidate, "bundle_lineage", None)

    @property
    def selection_mode(self) -> str:
        return str(getattr(self.candidate, "selection_mode", "singleton"))

    @property
    def bundle_role(self) -> str:
        return str(getattr(self.candidate, "bundle_role", ""))

    @property
    def total_cost_usd(self) -> float:
        """Combined cost of search + scoring."""
        return self.candidate.cost_usd + self.scoring_cost_usd

    def summary(self) -> str:
        """One-line summary for logging."""
        return (
            f"[{self.source_domain}] "
            f"fidelity={self.structural_fidelity:.2f} "
            f"dist={self.domain_distance:.2f} "
            f"creativity={self.creativity_score:.2f} "
            f"score={self.combined_score:.3f}"
        )


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class ScoringError(Exception):
    """Raised when candidate scoring fails critically."""


class CandidateScorer:
    """
    Stage 3 of the Genesis pipeline: Candidate Scoring.

    Scores each candidate on structural fidelity (LLM) and domain distance
    (embeddings), then computes combined score and filters adjacent domains.

    Parameters
    ----------
    harness:
        DeepForge harness for LLM fidelity scoring.
    embedding_model:
        EmbeddingModel for domain distance computation.
    distance_exponent:
        Superlinear exponent for distance reward (default 1.5).
    min_domain_distance:
        Minimum distance to include a candidate (default 0.3).
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        embedding_model: EmbeddingModel | None = None,
        distance_exponent: float = _DISTANCE_EXPONENT,
        min_domain_distance: float = _MIN_DOMAIN_DISTANCE,
    ) -> None:
        self._harness = harness
        self._embed = embedding_model or EmbeddingModel()
        self._alpha = distance_exponent
        self._min_distance = min_domain_distance

    async def score(
        self,
        candidates: list[SearchCandidate],
        structure: ProblemStructure,
    ) -> list[ScoredCandidate]:
        """
        Score all candidates and return them sorted by combined_score descending.

        Parameters
        ----------
        candidates:
            SearchCandidates from Stage 2.
        structure:
            The ProblemStructure from Stage 1.

        Returns
        -------
        list[ScoredCandidate]
            Filtered and sorted candidates. Adjacent domains (distance < 0.3)
            are removed.
        """
        if not candidates:
            return []

        logger.info("Scoring %d candidates", len(candidates))
        t_start = time.monotonic()

        # Step 1: Compute embedding-based domain distances (batch for efficiency)
        distances = self._compute_domain_distances(candidates, structure)

        # Step 2: Filter out adjacent domains first (saves LLM calls)
        pre_filtered = [c for c in candidates if distances.get(id(c), 0.0) >= self._min_distance]
        filtered_out = len(candidates) - len(pre_filtered)
        if filtered_out > 0:
            logger.info(
                "Filtered out %d adjacent-domain candidates (distance < %.2f)",
                filtered_out,
                self._min_distance,
            )

        if not pre_filtered:
            logger.warning("All candidates filtered out as adjacent domains")
            return []

        # Step 3: Score fidelity via LLM (concurrent)
        import asyncio

        scored = await asyncio.gather(
            *[self._score_candidate(c, structure, distances.get(id(c), 0.5)) for c in pre_filtered],
            return_exceptions=True,
        )

        # Step 4: Collect results
        results: list[ScoredCandidate] = []
        for candidate, result in zip(pre_filtered, scored, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Scoring failed for %s: %s",
                    candidate.source_domain,
                    result,
                )
                # Fallback: use search confidence as fidelity
                dist = distances.get(id(candidate), 0.5)
                novelty_vector = NoveltyVector(
                    banality_similarity=1.0 - candidate.confidence,
                    prior_art_similarity=1.0 - candidate.confidence,
                    source_domain_distance=dist,
                    mechanism_distance=0.5,
                    evaluator_gain=candidate.confidence,
                )
                creativity_score = novelty_vector.creativity_score()
                combined = (
                    candidate.confidence
                    * (dist**self._alpha)
                    * self._novelty_multiplier(creativity_score, True)
                    * self._bundle_score_multiplier(candidate)
                )
                results.append(
                    ScoredCandidate(
                        candidate=candidate,
                        structural_fidelity=candidate.confidence,
                        domain_distance=dist,
                        combined_score=combined,
                        fidelity_reasoning="Scoring failed; using search confidence",
                        mechanism_novelty=0.5,
                        novelty_vector=novelty_vector,
                        creativity_score=creativity_score,
                        retrieval_expansion_headroom=max(0.0, candidate.confidence - 0.5),
                    )
                )
            else:
                if result is not None:
                    results.append(result)

        # Sort by combined score descending
        results.sort(key=lambda s: s.combined_score, reverse=True)

        duration = time.monotonic() - t_start
        total_cost = sum(s.scoring_cost_usd for s in results)
        logger.info(
            "Scoring complete | kept=%d duration=%.1fs cost=$%.4f",
            len(results),
            duration,
            total_cost,
        )

        return results

    def _compute_domain_distances(
        self,
        candidates: list[SearchCandidate],
        structure: ProblemStructure,
    ) -> dict[int, float]:
        """
        Batch-compute embedding distance from target problem to each candidate's domain.

        Uses the candidate's source_domain text and the problem's search description.

        Returns a dict mapping id(candidate) → distance.
        """
        problem_text = structure.to_search_description()
        domain_texts = [c.source_domain + " " + c.mechanism for c in candidates]

        # Batch encode for efficiency
        all_texts = [problem_text] + domain_texts
        embeddings = self._embed.encode(all_texts)

        problem_emb = embeddings[0]
        domain_embs = embeddings[1:]

        distances: dict[int, float] = {}
        for candidate, domain_emb in zip(candidates, domain_embs, strict=True):
            dist = _cosine_distance(problem_emb, domain_emb)

            # Blend with lens distance if available for better signal
            if candidate.lens_score is not None:
                lens_dist = candidate.lens_score.domain_distance
                # Weighted average: 70% embedding distance, 30% lens distance
                blended = 0.7 * dist + 0.3 * lens_dist
            else:
                blended = dist

            distances[id(candidate)] = float(_lazy_np().clip(blended, 0.0, 1.0))

        return distances

    async def _score_candidate(
        self,
        candidate: SearchCandidate,
        structure: ProblemStructure,
        domain_distance: float,
    ) -> ScoredCandidate:
        """Score a single candidate via LLM fidelity assessment."""
        fidelity_prompt = _FIDELITY_PROMPT_TEMPLATE.format(
            structure=structure.structure,
            mathematical_shape=structure.mathematical_shape,
            source_domain=candidate.source_domain,
            source_solution=candidate.source_solution,
            mechanism=candidate.mechanism,
            structural_mapping=candidate.structural_mapping,
        )
        novelty_prompt = _MECHANISM_NOVELTY_PROMPT.format(
            native_domain=structure.native_domain.replace("_", " "),
            structure=structure.structure,
            source_domain=candidate.source_domain,
            mechanism=candidate.mechanism,
            source_solution=candidate.source_solution,
        )
        import asyncio

        fidelity_result, novelty_result = await asyncio.gather(
            self._harness.forge(
                fidelity_prompt,
                system=_FIDELITY_SYSTEM,
                max_tokens=16000,
                temperature=0.2,
            ),
            self._harness.forge(
                novelty_prompt,
                system=_MECHANISM_NOVELTY_SYSTEM,
                max_tokens=16000,
                temperature=0.2,
            ),
        )

        parsed = self._parse_fidelity(fidelity_result.output)
        fidelity = float(parsed.get("structural_fidelity", 0.5))
        fidelity = float(_lazy_np().clip(fidelity, 0.0, 1.0))
        novelty_parsed = self._parse_mechanism_novelty(novelty_result.output)
        mechanism_novelty = float(
            _lazy_np().clip(float(novelty_parsed.get("mechanism_novelty", 0.5)), 0.0, 1.0)
        )
        would_engineer_reach_for_this = bool(
            novelty_parsed.get("would_engineer_reach_for_this", True)
        )
        novelty_vector = self._build_novelty_vector(
            fidelity=fidelity,
            domain_distance=domain_distance,
            mechanism_novelty=mechanism_novelty,
            would_engineer_reach_for_this=would_engineer_reach_for_this,
            strong_mappings=parsed.get("strong_mappings", []),
            weak_mappings=parsed.get("weak_mappings", []),
        )
        creativity_score = novelty_vector.creativity_score()
        combined = (
            fidelity
            * (domain_distance**self._alpha)
            * self._novelty_multiplier(creativity_score, would_engineer_reach_for_this)
            * self._bundle_score_multiplier(candidate)
        )
        total_scoring_cost = (
            fidelity_result.trace.total_cost_usd + novelty_result.trace.total_cost_usd
        )

        return ScoredCandidate(
            candidate=candidate,
            structural_fidelity=fidelity,
            domain_distance=domain_distance,
            combined_score=combined,
            fidelity_reasoning=parsed.get("fidelity_reasoning", ""),
            strong_mappings=parsed.get("strong_mappings", []),
            weak_mappings=parsed.get("weak_mappings", []),
            mechanism_novelty=mechanism_novelty,
            target_domain_equivalent=str(novelty_parsed.get("target_domain_equivalent", "")),
            novelty_reasoning=str(novelty_parsed.get("novelty_reasoning", "")),
            would_engineer_reach_for_this=would_engineer_reach_for_this,
            scoring_cost_usd=total_scoring_cost,
            scoring_trace=fidelity_result.trace,
            novelty_vector=novelty_vector,
            creativity_score=creativity_score,
            retrieval_expansion_headroom=float(
                _lazy_np().clip(
                    max(0.0, fidelity - mechanism_novelty)
                    + 0.25 * float(would_engineer_reach_for_this),
                    0.0,
                    1.0,
                )
            ),
        )

    @staticmethod
    def _bundle_score_multiplier(candidate: SearchCandidate) -> float:
        proof = getattr(candidate, "bundle_proof", None)
        if proof is None:
            return 1.0
        confidence = float(getattr(proof, "proof_confidence", 0.5))
        role_bonus = 0.03 if getattr(candidate, "bundle_role", "") == "critical" else 0.0
        return float(_lazy_np().clip(0.94 + 0.18 * confidence + role_bonus, 0.9, 1.12))

    @staticmethod
    def _novelty_multiplier(creativity_score: float, would_engineer_reach_for_this: bool) -> float:
        penalty = 0.10 if would_engineer_reach_for_this else 0.0
        return float(_lazy_np().clip(0.84 + 0.34 * creativity_score - penalty, 0.72, 1.16))

    @staticmethod
    def _build_novelty_vector(
        *,
        fidelity: float,
        domain_distance: float,
        mechanism_novelty: float,
        would_engineer_reach_for_this: bool,
        strong_mappings: list[str],
        weak_mappings: list[str],
    ) -> NoveltyVector:
        disagreement = 0.0
        if strong_mappings or weak_mappings:
            disagreement = len(weak_mappings) / max(1, len(strong_mappings) + len(weak_mappings))
        disagreement = float(
            _lazy_np().clip(0.55 * disagreement + 0.45 * abs(fidelity - mechanism_novelty), 0.0, 1.0)
        )
        banality_similarity = float(_lazy_np().clip(1.0 - mechanism_novelty, 0.0, 1.0))
        prior_art_similarity = float(
            _lazy_np().clip(0.65 if would_engineer_reach_for_this else 0.25, 0.0, 1.0)
        )
        subtraction_delta = float(_lazy_np().clip(0.45 * fidelity + 0.55 * mechanism_novelty, 0.0, 1.0))
        return NoveltyVector(
            banality_similarity=banality_similarity,
            prior_art_similarity=prior_art_similarity,
            source_domain_distance=domain_distance,
            mechanism_distance=mechanism_novelty,
            evaluator_gain=fidelity,
            subtraction_delta=subtraction_delta,
            critic_disagreement=disagreement,
        )

    def _parse_fidelity(self, raw: str) -> dict[str, Any]:
        """Parse the fidelity scoring JSON."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            logger.warning("No JSON in fidelity response, using defaults")
            return {"structural_fidelity": 0.5}

        try:
            data = loads_lenient(
                json_match.group(), default={"structural_fidelity": 0.5}, label="scorer.fidelity"
            )
        except json.JSONDecodeError:
            return {"structural_fidelity": 0.5}

        return data

    def _parse_mechanism_novelty(self, raw: str) -> dict[str, Any]:
        """Parse the mechanism-novelty JSON."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            logger.warning("No JSON in mechanism novelty response, using defaults")
            return {"mechanism_novelty": 0.5, "would_engineer_reach_for_this": True}

        try:
            data = loads_lenient(
                json_match.group(),
                default={"mechanism_novelty": 0.5, "would_engineer_reach_for_this": True},
                label="scorer.novelty",
            )
        except json.JSONDecodeError:
            return {"mechanism_novelty": 0.5, "would_engineer_reach_for_this": True}

        return data
