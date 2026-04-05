"""
Convergence Pruner.

The Convergence Pruner monitors the model's output stream in real time.
When it detects the model heading toward a known convergence point (a
predictable, RLHF-grooved answer pattern), it kills the generation and
records the blocked path.

Convergence detection uses local sentence-transformer embeddings — no
additional API calls, no round-trip latency, runs in < 1 ms per chunk on
modern hardware.

The pruner maintains per-session state:

- A set of **blocked paths** (partial outputs that triggered kills)
- The **kill count** (how many generations were killed)
- The accumulated **cost wasted** on killed generations

These are used by :class:`~hephaestus.deepforge.pressure.AntiTrainingPressure`
to construct the structural prohibitions passed to subsequent rounds.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

from hephaestus.deepforge.adapters.base import BaseAdapter, StreamChunk
from hephaestus.deepforge.exceptions import (
    ConvergenceDetected,
    GenerationKilled,
    PrunerError,
)


def _lazy_np() -> Any:
    import numpy as np  # noqa: F811
    return np


def _lazy_st(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)

logger = logging.getLogger(__name__)

# Default model for embedding computation
_DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"

# Minimum characters accumulated before we start checking for convergence
_MIN_CHARS_BEFORE_CHECK = 80

# How often (in tokens/chunks) to run the embedding check
_CHECK_INTERVAL_CHUNKS = 10


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ConvergencePattern:
    """
    A known convergence (banality) pattern stored in the pruner.

    Attributes
    ----------
    text:
        The representative text of the convergence pattern.
    embedding:
        Pre-computed embedding vector (shape: ``(embed_dim,)``).
    label:
        Human-readable label describing what kind of banality this is.
    source:
        Where this pattern came from (e.g. ``"seed"``, ``"organic"``).
    block_count:
        How many times this pattern has been blocked in this session.
    """

    text: str
    embedding: np.ndarray
    label: str = "generic"
    source: str = "seed"
    block_count: int = 0


@dataclass
class PrunerSession:
    """
    Per-session state accumulated by the :class:`ConvergencePruner`.

    Attributes
    ----------
    blocked_paths:
        List of partial outputs that triggered convergence kills.
    kill_count:
        Total number of kills in this session.
    tokens_wasted:
        Tokens consumed by killed generations (output side only).
    cost_wasted_usd:
        Estimated USD cost consumed by killed generations.
    pattern_hits:
        Mapping from pattern label to hit count.
    """

    blocked_paths: list[str] = field(default_factory=list)
    kill_count: int = 0
    tokens_wasted: int = 0
    cost_wasted_usd: float = 0.0
    pattern_hits: dict[str, int] = field(default_factory=dict)

    def record_kill(
        self,
        partial_output: str,
        pattern_label: str,
        tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record a convergence kill into the session state."""
        self.blocked_paths.append(partial_output)
        self.kill_count += 1
        self.tokens_wasted += tokens
        self.cost_wasted_usd += cost
        self.pattern_hits[pattern_label] = self.pattern_hits.get(pattern_label, 0) + 1


@dataclass
class PruneResult:
    """
    Result returned when pruned generation completes (without being killed).

    Attributes
    ----------
    text:
        The full generated text.
    was_pruned:
        Always ``False`` for successful completions (killed generations raise
        :exc:`~hephaestus.deepforge.exceptions.ConvergenceDetected`).
    input_tokens:
        Input tokens consumed.
    output_tokens:
        Output tokens generated.
    cost_usd:
        Estimated cost.
    stop_reason:
        Why generation stopped.
    """

    text: str
    was_pruned: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str = "end_turn"


# ---------------------------------------------------------------------------
# ConvergencePruner
# ---------------------------------------------------------------------------


class ConvergencePruner:
    """
    Real-time stream monitor that kills generation on convergence detection.

    Parameters
    ----------
    patterns:
        Seed convergence patterns.  These are the "obvious answers" the pruner
        blocks.  Can be added dynamically via :meth:`add_pattern`.
    similarity_threshold:
        Cosine similarity score above which a chunk is considered converged
        (default 0.82 — high precision to avoid false positives).
    embed_model_name:
        Name of the sentence-transformers model to use for embeddings.
    check_interval:
        Number of streaming chunks between embedding similarity checks.  Lower
        values = more sensitive but more CPU-intensive.
    min_chars_before_check:
        Minimum accumulated characters before running any convergence check.
        Prevents triggering on short, ambiguous prefixes.
    embed_model:
        Pre-initialised :class:`SentenceTransformer` instance.  If ``None``,
        the model is loaded lazily on the first call.
    """

    def __init__(
        self,
        patterns: list[ConvergencePattern] | None = None,
        *,
        similarity_threshold: float = 0.82,
        embed_model_name: str = _DEFAULT_EMBED_MODEL,
        check_interval: int = _CHECK_INTERVAL_CHUNKS,
        min_chars_before_check: int = _MIN_CHARS_BEFORE_CHECK,
        embed_model: Any | None = None,
    ) -> None:
        self._patterns: list[ConvergencePattern] = patterns or []
        self._threshold = similarity_threshold
        self._embed_model_name = embed_model_name
        self._check_interval = check_interval
        self._min_chars = min_chars_before_check
        self._embed_model: Any | None = embed_model
        self._session = PrunerSession()

        logger.debug(
            "ConvergencePruner initialised | patterns=%d threshold=%.2f",
            len(self._patterns),
            similarity_threshold,
        )

    # ------------------------------------------------------------------
    # Embedding model (lazy-loaded)
    # ------------------------------------------------------------------

    def _get_embed_model(self) -> Any:
        """Lazy-load the sentence-transformer model."""
        if self._embed_model is None:
            logger.info("Loading embedding model %s …", self._embed_model_name)
            self._embed_model = _lazy_st(self._embed_model_name)
        return self._embed_model

    def _embed(self, text: str) -> np.ndarray:
        """Compute a normalised embedding vector for *text*."""
        model = self._get_embed_model()
        vec: np.ndarray = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec

    # ------------------------------------------------------------------
    # Pattern management
    # ------------------------------------------------------------------

    def add_pattern(
        self,
        text: str,
        label: str = "generic",
        source: str = "organic",
    ) -> ConvergencePattern:
        """
        Add a new convergence pattern (computes its embedding immediately).

        Parameters
        ----------
        text:
            The pattern text.
        label:
            Human-readable category label.
        source:
            Origin of the pattern (``"seed"``, ``"organic"``, ``"user"``).

        Returns
        -------
        ConvergencePattern
        """
        embedding = self._embed(text)
        pattern = ConvergencePattern(
            text=text,
            embedding=embedding,
            label=label,
            source=source,
        )
        self._patterns.append(pattern)
        logger.debug("Added convergence pattern: %r (label=%s)", text[:60], label)
        return pattern

    def add_patterns_from_texts(
        self,
        texts: list[str],
        label: str = "seed",
        source: str = "seed",
    ) -> list[ConvergencePattern]:
        """
        Batch-add multiple patterns, computing embeddings in one pass.

        Parameters
        ----------
        texts:
            Pattern texts.
        label:
            Common label for all patterns.
        source:
            Common source tag.

        Returns
        -------
        list[ConvergencePattern]
        """
        if not texts:
            return []

        model = self._get_embed_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        new_patterns = []
        for text, embedding in zip(texts, embeddings, strict=True):
            pattern = ConvergencePattern(
                text=text,
                embedding=embedding,
                label=label,
                source=source,
            )
            self._patterns.append(pattern)
            new_patterns.append(pattern)

        logger.debug("Batch-added %d convergence patterns (label=%s)", len(texts), label)
        return new_patterns

    # ------------------------------------------------------------------
    # Convergence detection
    # ------------------------------------------------------------------

    def check_convergence(self, text: str) -> tuple[bool, float, ConvergencePattern | None]:
        """
        Check whether *text* matches any known convergence pattern.

        Parameters
        ----------
        text:
            The accumulated output text to check.

        Returns
        -------
        tuple[bool, float, ConvergencePattern | None]
            ``(is_converged, max_similarity, matched_pattern)``
        """
        if not self._patterns:
            return False, 0.0, None

        if len(text) < self._min_chars:
            return False, 0.0, None

        text_emb = self._embed(text)

        best_sim = 0.0
        best_pattern: ConvergencePattern | None = None

        for pattern in self._patterns:
            sim = float(_lazy_np().dot(text_emb, pattern.embedding))
            if sim > best_sim:
                best_sim = sim
                best_pattern = pattern

        is_converged = best_sim >= self._threshold
        return is_converged, best_sim, best_pattern

    # ------------------------------------------------------------------
    # Monitored streaming
    # ------------------------------------------------------------------

    async def monitor_stream(
        self,
        stream: AsyncIterator[StreamChunk],
        *,
        adapter: BaseAdapter | None = None,
    ) -> PruneResult:
        """
        Consume *stream*, killing generation if convergence is detected.

        This coroutine iterates over the given async stream (from an adapter's
        :meth:`~hephaestus.deepforge.adapters.base.BaseAdapter.generate_stream`)
        and periodically runs the convergence check against the accumulated
        text.

        When convergence is detected:
        1. The adapter's :meth:`~BaseAdapter.cancel_stream` is called.
        2. The partial output is recorded in the session.
        3. :exc:`~hephaestus.deepforge.exceptions.ConvergenceDetected` is raised.

        Parameters
        ----------
        stream:
            Async iterator of :class:`StreamChunk` objects.
        adapter:
            The adapter that produced *stream*.  Used to call
            :meth:`~BaseAdapter.cancel_stream` on detection.

        Returns
        -------
        PruneResult
            On non-converged completion.

        Raises
        ------
        ConvergenceDetected
            When a convergence pattern is detected in the stream.
        PrunerError
            On unexpected failures inside the pruner.
        """
        chunk_count = 0
        last_check_text = ""
        final_chunk: StreamChunk | None = None

        try:
            async for chunk in stream:
                chunk_count += 1

                if chunk.is_final:
                    final_chunk = chunk
                    break

                # Run convergence check every N chunks
                if (
                    chunk_count % self._check_interval == 0
                    and len(chunk.accumulated) >= self._min_chars
                    and chunk.accumulated != last_check_text
                ):
                    last_check_text = chunk.accumulated
                    is_converged, similarity, pattern = self.check_convergence(chunk.accumulated)

                    if is_converged and pattern is not None:
                        # Signal adapter to stop generating
                        if adapter is not None:
                            adapter.cancel_stream()

                        pattern.block_count += 1
                        self._session.record_kill(
                            partial_output=chunk.accumulated,
                            pattern_label=pattern.label,
                        )

                        logger.info(
                            "Convergence detected | sim=%.3f pattern=%r chunks=%d",
                            similarity,
                            pattern.label,
                            chunk_count,
                        )
                        raise ConvergenceDetected(
                            partial_output=chunk.accumulated,
                            pattern_similarity=similarity,
                            matched_pattern=pattern.text,
                        )

        except (ConvergenceDetected, GenerationKilled):
            raise
        except Exception as exc:
            raise PrunerError(f"Unexpected error in monitor_stream: {exc}") from exc

        if final_chunk is None:
            raise PrunerError("Stream ended without a final chunk")

        accumulated = final_chunk.accumulated
        in_tok = final_chunk.input_tokens
        out_tok = final_chunk.output_tokens

        return PruneResult(
            text=accumulated,
            was_pruned=False,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=adapter.compute_cost(in_tok, out_tok) if adapter else 0.0,
            stop_reason=final_chunk.stop_reason,
        )

    # ------------------------------------------------------------------
    # Session access
    # ------------------------------------------------------------------

    @property
    def session(self) -> PrunerSession:
        """The current :class:`PrunerSession` state."""
        return self._session

    def reset_session(self) -> None:
        """Reset per-session state (blocked paths, kill count, etc.)."""
        self._session = PrunerSession()

    @property
    def pattern_count(self) -> int:
        """Number of convergence patterns currently loaded."""
        return len(self._patterns)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def export_patterns(self) -> list[dict[str, Any]]:
        """
        Export all patterns as a list of dicts (without embeddings).

        Suitable for persisting to a JSON file or database.
        """
        return [
            {
                "text": p.text,
                "label": p.label,
                "source": p.source,
                "block_count": p.block_count,
            }
            for p in self._patterns
        ]
