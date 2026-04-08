"""
Anti-Training Pressure Engine.

The Anti-Training Pressure engine applies counter-pressure against the model's
RLHF-trained preferences.  It pushes the model into the long tail of its
output distribution — the region where genuinely novel solutions live.

Two mechanisms are combined:

**Adversarial Mirror**
    Ask the model for its default answer first.  Feed that answer back as an
    explicit structural prohibition.  The model's own consensus response
    becomes the wall it must climb over.

**Multi-round stacking**
    Round 1: Block the default answer.
    Round 2: Block the first alternative (which is often just the second
             obvious answer).
    Round N: After N rounds the model is past its top-N convergence points
             and forced into genuinely unexplored territory.

**Structural incompatibility verification**
    Between rounds, verify that the new output is *structurally different*
    from all previously blocked paths (not just surface rephrasing).  Uses
    embedding-distance to detect shallow rephrasings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def _get_numpy() -> Any:
    """Lazy import for numpy."""
    import numpy as np

    return np


def _get_sentence_transformer(model_name: str) -> Any:
    """Lazy import and instantiation for SentenceTransformer."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


from hephaestus.deepforge.adapters.base import BaseAdapter, GenerationResult  # noqa: E402
from hephaestus.deepforge.exceptions import (  # noqa: E402
    ConfigurationError,
)

logger = logging.getLogger(__name__)

_DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"

# Cosine similarity below which two outputs are considered structurally
# different.  Outputs above this threshold are treated as rephrasings.
_STRUCTURAL_DISTANCE_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BlockedPath:
    """
    A generation that was blocked as a convergence point.

    Attributes
    ----------
    round_index:
        The pressure round during which this path was blocked (0 = default).
    text:
        The full text of the blocked generation.
    embedding:
        Pre-computed embedding vector.
    reason:
        Human-readable reason for blocking.
    """

    round_index: int
    text: str
    embedding: Any  # np.ndarray — lazy-loaded
    reason: str


@dataclass
class PressureTrace:
    """
    Full trace of an anti-training pressure run.

    Attributes
    ----------
    blocked_paths:
        All :class:`BlockedPath` objects accumulated across rounds.
    final_output:
        The text of the generation that passed all structural checks.
    rounds_completed:
        How many pressure rounds were executed.
    total_cost_usd:
        Total API cost across all rounds.
    total_input_tokens:
        Sum of input tokens across all rounds.
    total_output_tokens:
        Sum of output tokens across all rounds.
    structural_distances:
        Per-round minimum structural distance from blocked paths.
    success:
        Whether a structurally novel output was found within the round limit.
    """

    blocked_paths: list[BlockedPath] = field(default_factory=list)
    final_output: str = ""
    rounds_completed: int = 0
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    structural_distances: list[float] = field(default_factory=list)
    success: bool = False

    def add_result(self, result: GenerationResult, cost: float | None = None) -> None:
        """Accumulate token usage from a :class:`GenerationResult`."""
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_cost_usd += cost if cost is not None else result.cost_usd
        self.rounds_completed += 1


# ---------------------------------------------------------------------------
# AntiTrainingPressure
# ---------------------------------------------------------------------------


class AntiTrainingPressure:
    """
    Apply multi-round adversarial mirror pressure to force novel generation.

    The engine drives the adapter through multiple rounds:

    1. **Round 0 (Mirror):** Generate the default answer and immediately mark
       it as a blocked path.
    2. **Round 1…N (Pressure):** Generate with an explicit prohibition against
       all blocked paths, verify structural incompatibility, and repeat until
       a genuinely novel output is found or ``max_rounds`` is exhausted.

    Parameters
    ----------
    adapter:
        The model adapter to use for generation.
    max_rounds:
        Maximum number of pressure rounds, including the initial mirror
        (default 3).  Increasing this explores deeper into the long tail but
        costs more.
    structural_distance_threshold:
        Minimum cosine distance from blocked paths for a new output to be
        considered structurally novel (default 0.75).
    embed_model:
        Pre-initialised sentence-transformers model.  Loaded lazily if
        ``None``.
    embed_model_name:
        Model name to use when loading lazily.
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        *,
        max_rounds: int = 3,
        structural_distance_threshold: float = _STRUCTURAL_DISTANCE_THRESHOLD,
        embed_model: Any | None = None,
        embed_model_name: str = _DEFAULT_EMBED_MODEL,
    ) -> None:
        if max_rounds < 1:
            raise ConfigurationError("max_rounds must be at least 1")

        self._adapter = adapter
        self._max_rounds = max_rounds
        self._threshold = structural_distance_threshold
        self._embed_model: Any | None = embed_model
        self._embed_model_name = embed_model_name

        logger.debug(
            "AntiTrainingPressure initialised | max_rounds=%d threshold=%.2f",
            max_rounds,
            structural_distance_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def apply(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.9,
        extra_blocked_paths: list[str] | None = None,
        **kwargs: Any,
    ) -> PressureTrace:
        """
        Execute the full adversarial mirror + multi-round pressure pipeline.

        Parameters
        ----------
        prompt:
            The user's original problem statement.
        system:
            Base system instruction (lens injection happens on top of this).
        max_tokens:
            Maximum output tokens per round.
        temperature:
            Sampling temperature.  Slightly elevated (0.9) to help escape
            probability modes between rounds.
        extra_blocked_paths:
            Additional text paths to pre-block (e.g. from the convergence
            pruner's session state).
        **kwargs:
            Extra arguments forwarded to the adapter.

        Returns
        -------
        PressureTrace
            Full trace including all blocked paths and the final output.

        Raises
        ------
        PressureError
            If no novel output was found within ``max_rounds``.
        """
        trace = PressureTrace()
        blocked: list[BlockedPath] = []

        # Pre-seed blocked paths from external sources (e.g. pruner session)
        if extra_blocked_paths:
            for text in extra_blocked_paths:
                if text.strip():
                    emb = self._embed(text)
                    blocked.append(
                        BlockedPath(
                            round_index=-1,
                            text=text,
                            embedding=emb,
                            reason="pre-seeded from pruner session",
                        )
                    )
            logger.debug("Pre-seeded %d blocked paths", len(blocked))

        # ---- Round 0: Mirror — generate the default answer ----
        logger.info("Pressure round 0: generating default (mirror) answer …")
        default_result = await self._adapter.generate(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        trace.add_result(default_result)

        default_emb = self._embed(default_result.text)
        mirror_path = BlockedPath(
            round_index=0,
            text=default_result.text,
            embedding=default_emb,
            reason="default answer (adversarial mirror)",
        )
        blocked.append(mirror_path)
        trace.blocked_paths.append(mirror_path)

        logger.info(
            "Pressure round 0 complete | tokens_out=%d blocked default answer",
            default_result.output_tokens,
        )

        # ---- Rounds 1…max_rounds: pressure rounds ----
        for round_idx in range(1, self._max_rounds):
            prohibition_system = self._build_prohibition_system(
                base_system=system,
                blocked=blocked,
            )

            logger.info(
                "Pressure round %d: generating with %d blocked paths …", round_idx, len(blocked)
            )

            result = await self._adapter.generate(
                prompt,
                system=prohibition_system,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            trace.add_result(result)

            new_emb = self._embed(result.text)
            min_dist = self._min_structural_distance(new_emb, blocked)
            trace.structural_distances.append(min_dist)

            logger.info(
                "Pressure round %d | structural_distance=%.3f threshold=%.3f",
                round_idx,
                min_dist,
                self._threshold,
            )

            if min_dist >= self._threshold:
                # Output is structurally distinct from all blocked paths
                trace.final_output = result.text
                trace.success = True
                trace.blocked_paths = blocked  # Export all blocked paths
                logger.info(
                    "Novel output found at round %d | dist=%.3f",
                    round_idx,
                    min_dist,
                )
                return trace

            # Not structurally novel enough — block it and go again
            new_path = BlockedPath(
                round_index=round_idx,
                text=result.text,
                embedding=new_emb,
                reason=f"round {round_idx} rephrasing (dist={min_dist:.3f})",
            )
            blocked.append(new_path)
            trace.blocked_paths.append(new_path)

        # Exhausted rounds — return the last output with a warning
        logger.warning(
            "Exhausted %d pressure rounds without finding fully novel output. "
            "Returning last generated output.",
            self._max_rounds,
        )

        # Return best-effort output: last blocked path's text, or the mirror default.
        trace.success = False
        trace.final_output = blocked[-1].text if blocked else default_result.text
        trace.blocked_paths = list(blocked)
        return trace

    # ------------------------------------------------------------------
    # Structural distance
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> Any:
        """Compute a normalised embedding vector for *text*."""
        if self._embed_model is None:
            logger.info("Loading embedding model %s …", self._embed_model_name)
            self._embed_model = _get_sentence_transformer(self._embed_model_name)
        vec = self._embed_model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec

    def _min_structural_distance(self, embedding: Any, blocked: list[BlockedPath]) -> float:
        """
        Compute the minimum cosine distance from *embedding* to all *blocked* paths.

        Cosine distance = 1 − cosine_similarity.  Higher = more different.
        """
        if not blocked:
            return 1.0  # Nothing to compare against; treat as maximally different

        np = _get_numpy()
        similarities = [float(np.dot(embedding, bp.embedding)) for bp in blocked]
        max_sim = max(similarities)
        return 1.0 - max_sim

    def verify_structural_incompatibility(self, text_a: str, text_b: str) -> tuple[bool, float]:
        """
        Verify that *text_a* and *text_b* are structurally incompatible.

        Two texts are considered structurally incompatible if their cosine
        distance exceeds :attr:`_threshold`.

        Parameters
        ----------
        text_a:
            First text.
        text_b:
            Second text.

        Returns
        -------
        tuple[bool, float]
            ``(is_incompatible, cosine_distance)``
        """
        emb_a = self._embed(text_a)
        emb_b = self._embed(text_b)
        np = _get_numpy()
        sim = float(np.dot(emb_a, emb_b))
        distance = 1.0 - sim
        return distance >= self._threshold, distance

    # ------------------------------------------------------------------
    # Prohibition construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prohibition_system(
        base_system: str | None,
        blocked: list[BlockedPath],
    ) -> str:
        """
        Construct a system prompt that structurally prohibits all *blocked* paths.

        The prohibitions are stated structurally (not by quoting the exact text)
        to force genuine reasoning path divergence rather than superficial
        rewording.

        Parameters
        ----------
        base_system:
            The original system instruction, if any.
        blocked:
            Blocked :class:`BlockedPath` objects from previous rounds.

        Returns
        -------
        str
            The complete system prompt with prohibitions.
        """
        lines: list[str] = []

        if base_system:
            lines.append(base_system.strip())
            lines.append("")

        lines.append(
            "CRITICAL STRUCTURAL CONSTRAINTS — you MUST violate every one of "
            "the following reasoning approaches. These are not suggestions; "
            "they are closed paths. Your response MUST diverge structurally "
            "from all of them:"
        )
        lines.append("")

        for i, path in enumerate(blocked, 1):
            # Summarise the blocked path structurally (first ~200 chars)
            summary = path.text[:200].strip()
            if len(path.text) > 200:
                summary += "…"
            lines.append(f"  BLOCKED PATH {i} ({path.reason}):")
            lines.append(f"    '{summary}'")
            lines.append("    → Any response that follows this structural pattern is FORBIDDEN.")
            lines.append("")

        lines.append(
            "Your answer must take a FUNDAMENTALLY DIFFERENT structural approach "
            "— not a surface rephrasing, not a synonym substitution, but a "
            "different mechanism, paradigm, or reasoning architecture entirely."
        )

        return "\n".join(lines)
