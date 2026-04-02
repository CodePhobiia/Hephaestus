"""
Convergence Detector.

The ``ConvergenceDetector`` is the higher-level convergence detection system
that integrates the embedding model, the :class:`~hephaestus.convergence.database.ConvergenceDatabase`,
and batch-scoring logic.

Unlike the lower-level :class:`~hephaestus.deepforge.pruner.ConvergencePruner`
(which operates on live streaming output), the ``ConvergenceDetector`` is
designed for:

- **Batch evaluation** of multiple candidate outputs.
- **Database-backed** pattern library (persisted across sessions).
- **Problem-class-aware** detection (loads patterns specific to a problem type).
- **Standalone use** outside the deepforge harness (e.g., in the genesis pipeline).

Usage
-----
::

    from hephaestus.convergence.detector import ConvergenceDetector
    from hephaestus.convergence.database import ConvergenceDatabase

    db = ConvergenceDatabase("patterns.db")
    await db.connect()

    detector = ConvergenceDetector(db=db, similarity_threshold=0.85)
    await detector.load_patterns("load_balancing")

    result = await detector.detect("Use round-robin scheduling with health checks")
    if result.is_convergent:
        print(f"Banality detected! Similarity: {result.similarity:.2f}")

    # Batch scoring
    scores = await detector.score_batch(
        ["candidate A", "candidate B", "candidate C"],
        problem_class="load_balancing",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from hephaestus.convergence.database import ConvergenceDatabase, PatternRecord
from hephaestus.novelty import NoveltyVector

logger = logging.getLogger(__name__)

# Default sentence-transformer model (consistent with deepforge pruner)
_DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"

# Default threshold above which an output is considered convergent (banal)
_DEFAULT_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class DetectionResult:
    """
    Result of a single convergence detection check.

    Attributes
    ----------
    text:
        The text that was checked.
    is_convergent:
        Whether the text was flagged as banal / convergent.
    similarity:
        Highest cosine similarity found against any loaded pattern.
    matched_pattern:
        The :class:`PatternRecord` that matched (``None`` if no match).
    problem_class:
        The problem class that was active when this check was run.
    """

    text: str
    is_convergent: bool
    similarity: float
    matched_pattern: PatternRecord | None
    problem_class: str = ""
    novelty_vector: NoveltyVector = field(default_factory=NoveltyVector)


@dataclass
class BatchScore:
    """
    Convergence score for a single candidate in a batch evaluation.

    Attributes
    ----------
    text:
        The candidate text.
    novelty_score:
        ``1.0 - similarity`` — higher means more novel.
    similarity:
        Raw cosine similarity to the nearest banality pattern.
    is_convergent:
        Whether the candidate exceeds the convergence threshold.
    matched_pattern:
        The matching pattern record if convergent.
    rank:
        Rank within the batch (1 = most novel).
    """

    text: str
    novelty_score: float
    similarity: float
    is_convergent: bool
    matched_pattern: PatternRecord | None = None
    rank: int = 0
    novelty_vector: NoveltyVector = field(default_factory=NoveltyVector)


@dataclass
class BatchDetectionResult:
    """
    Result of batch-scoring multiple candidates.

    Attributes
    ----------
    candidates:
        All :class:`BatchScore` objects, sorted by novelty (best first).
    best:
        The most novel candidate.
    worst:
        The most banal candidate.
    convergent_count:
        Number of candidates flagged as convergent.
    problem_class:
        Problem class used for pattern loading.
    """

    candidates: list[BatchScore]
    best: BatchScore | None
    worst: BatchScore | None
    convergent_count: int
    problem_class: str = ""

    @property
    def novel_candidates(self) -> list[BatchScore]:
        """Return candidates that are NOT convergent, sorted by novelty."""
        return [c for c in self.candidates if not c.is_convergent]

    @property
    def convergent_candidates(self) -> list[BatchScore]:
        """Return candidates that ARE convergent."""
        return [c for c in self.candidates if c.is_convergent]


# ---------------------------------------------------------------------------
# ConvergenceDetector
# ---------------------------------------------------------------------------


class ConvergenceDetector:
    """
    Embedding-based convergence detection with database integration.

    Loads patterns from the :class:`~hephaestus.convergence.database.ConvergenceDatabase`
    and uses sentence-transformers embeddings to compute cosine similarity
    between candidate outputs and known banality patterns.

    Parameters
    ----------
    db:
        The :class:`~hephaestus.convergence.database.ConvergenceDatabase` to
        load patterns from.
    similarity_threshold:
        Cosine similarity score above which a text is considered convergent
        (default 0.85).
    embed_model_name:
        Name of the sentence-transformers model to use.
    embed_model:
        Pre-initialised :class:`SentenceTransformer` instance.  If ``None``,
        the model is loaded lazily on the first embedding call.
    """

    def __init__(
        self,
        db: ConvergenceDatabase | None = None,
        *,
        similarity_threshold: float = _DEFAULT_THRESHOLD,
        embed_model_name: str = _DEFAULT_EMBED_MODEL,
        embed_model: SentenceTransformer | None = None,
    ) -> None:
        self._db = db
        self._threshold = similarity_threshold
        self._embed_model_name = embed_model_name
        self._embed_model: SentenceTransformer | None = embed_model

        # In-memory loaded patterns (populated by load_patterns)
        self._loaded_patterns: list[PatternRecord] = []
        self._loaded_class: str = ""

        logger.debug(
            "ConvergenceDetector initialised | threshold=%.2f model=%s",
            similarity_threshold,
            embed_model_name,
        )

    # ------------------------------------------------------------------
    # Embedding model
    # ------------------------------------------------------------------

    def _get_model(self) -> SentenceTransformer:
        """Lazy-load the sentence-transformer model."""
        if self._embed_model is None:
            logger.info("Loading embedding model %s …", self._embed_model_name)
            self._embed_model = SentenceTransformer(self._embed_model_name)
        return self._embed_model

    def _embed(self, text: str) -> np.ndarray:
        """Compute a single normalised embedding."""
        model = self._get_model()
        vec: np.ndarray = model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vec.astype(np.float32)

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        """Compute normalised embeddings for a batch of texts. Returns (N, D)."""
        model = self._get_model()
        matrix: np.ndarray = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        return matrix.astype(np.float32)

    # ------------------------------------------------------------------
    # Pattern loading
    # ------------------------------------------------------------------

    async def load_patterns(
        self,
        problem_class: str | None = None,
        *,
        force_reload: bool = False,
    ) -> int:
        """
        Load patterns from the database into memory for fast detection.

        Parameters
        ----------
        problem_class:
            If provided, load patterns for this specific class only.  If
            ``None``, load all patterns (may be slow for large databases).
        force_reload:
            If ``True``, reload even if the same class is already loaded.

        Returns
        -------
        int
            Number of patterns loaded.

        Raises
        ------
        RuntimeError
            If no database is configured.
        """
        if self._db is None:
            raise RuntimeError("No database configured. Pass db= to ConvergenceDetector().")

        if not force_reload and self._loaded_class == (problem_class or "__all__"):
            return len(self._loaded_patterns)

        if problem_class is not None:
            records = await self._db.get_patterns_for_class(problem_class)
        else:
            records = await self._db.get_all_patterns()

        self._loaded_patterns = records
        self._loaded_class = problem_class or "__all__"

        logger.info(
            "Loaded %d convergence patterns (class=%r)",
            len(records),
            problem_class,
        )
        return len(records)

    def load_patterns_from_records(self, records: list[PatternRecord]) -> None:
        """
        Load patterns directly from a list of records (no database required).

        Useful for seeding the detector in tests or when patterns come from
        an in-memory source.

        Parameters
        ----------
        records:
            List of :class:`PatternRecord` objects with pre-computed embeddings.
        """
        self._loaded_patterns = records
        self._loaded_class = "in_memory"
        logger.debug("Loaded %d patterns from records directly", len(records))

    def add_in_memory_pattern(
        self,
        text: str,
        problem_class: str = "generic",
        source_model: str = "",
    ) -> PatternRecord:
        """
        Compute an embedding for *text* and add it to the in-memory patterns.

        Does NOT persist to the database.  Use the database's ``add_pattern``
        for persistence.

        Parameters
        ----------
        text:
            The banality pattern text.
        problem_class:
            Problem class label.
        source_model:
            Source model tag.

        Returns
        -------
        PatternRecord
            The newly created (in-memory) record with id=-1.
        """
        embedding = self._embed(text)
        record = PatternRecord(
            id=-1,
            problem_class=problem_class,
            pattern_text=text,
            pattern_embedding=embedding,
            source_model=source_model,
        )
        self._loaded_patterns.append(record)
        return record

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_sync(self, text: str) -> DetectionResult:
        """
        Synchronous convergence detection against loaded patterns.

        Parameters
        ----------
        text:
            The candidate text to evaluate.

        Returns
        -------
        DetectionResult
        """
        if not self._loaded_patterns:
            return DetectionResult(
                text=text,
                is_convergent=False,
                similarity=0.0,
                matched_pattern=None,
                problem_class=self._loaded_class,
                novelty_vector=NoveltyVector(),
            )

        text_emb = self._embed(text)

        pattern_matrix = np.stack(
            [p.pattern_embedding for p in self._loaded_patterns], axis=0
        )
        similarities = pattern_matrix @ text_emb

        best_idx = int(np.argmax(similarities))
        best_sim = float(similarities[best_idx])
        best_pattern = self._loaded_patterns[best_idx]
        neighborhood_density = _mean_topk_similarity(similarities)

        is_convergent = best_sim >= self._threshold

        if is_convergent:
            logger.debug(
                "Convergence detected: sim=%.3f pattern=%r",
                best_sim,
                best_pattern.pattern_text[:60],
            )

        return DetectionResult(
            text=text,
            is_convergent=is_convergent,
            similarity=best_sim,
            matched_pattern=best_pattern if is_convergent else None,
            problem_class=self._loaded_class,
            novelty_vector=NoveltyVector(
                banality_similarity=best_sim,
                prior_art_similarity=neighborhood_density,
                branch_family_distance=float(np.clip(1.0 - neighborhood_density, 0.0, 1.0)),
            ),
        )

    async def detect(
        self,
        text: str,
        *,
        problem_class: str | None = None,
        auto_load: bool = True,
    ) -> DetectionResult:
        """
        Async convergence detection with optional automatic pattern loading.

        Parameters
        ----------
        text:
            The candidate text to evaluate.
        problem_class:
            If provided and *auto_load* is ``True``, load patterns for this
            class if they aren't already loaded.
        auto_load:
            If ``True``, automatically load patterns from the database when
            needed.

        Returns
        -------
        DetectionResult
        """
        if auto_load and problem_class and self._db is not None:
            if self._loaded_class != problem_class:
                await self.load_patterns(problem_class)

        return self.detect_sync(text)

    # ------------------------------------------------------------------
    # Batch scoring
    # ------------------------------------------------------------------

    async def score_batch(
        self,
        candidates: list[str],
        *,
        problem_class: str | None = None,
        auto_load: bool = True,
    ) -> BatchDetectionResult:
        """
        Score multiple candidate outputs for convergence in one pass.

        Efficiently computes all embeddings in a single batch call, then
        computes cosine similarities against the loaded patterns.

        Parameters
        ----------
        candidates:
            List of candidate text strings to evaluate.
        problem_class:
            If provided and *auto_load* is ``True``, load patterns for this
            class automatically.
        auto_load:
            Whether to auto-load patterns from the database.

        Returns
        -------
        BatchDetectionResult
            All candidates ranked by novelty score (best first).
        """
        if not candidates:
            return BatchDetectionResult(
                candidates=[],
                best=None,
                worst=None,
                convergent_count=0,
                problem_class=problem_class or self._loaded_class,
            )

        if auto_load and problem_class and self._db is not None:
            if self._loaded_class != problem_class:
                await self.load_patterns(problem_class)

        if not self._loaded_patterns:
            # No patterns loaded — all candidates are non-convergent by default
            scores = [
                BatchScore(
                    text=c,
                    novelty_score=1.0,
                    similarity=0.0,
                    is_convergent=False,
                    rank=i + 1,
                    novelty_vector=NoveltyVector(
                        branch_family_distance=1.0,
                        mechanism_distance=1.0,
                        evaluator_gain=1.0,
                    ),
                )
                for i, c in enumerate(candidates)
            ]
            return BatchDetectionResult(
                candidates=scores,
                best=scores[0] if scores else None,
                worst=scores[-1] if scores else None,
                convergent_count=0,
                problem_class=problem_class or self._loaded_class,
            )

        # Batch embed all candidates
        candidate_matrix = self._embed_batch(candidates)  # (N_cand, D)

        # Stack pattern embeddings
        pattern_matrix = np.stack(
            [p.pattern_embedding for p in self._loaded_patterns], axis=0
        )  # (N_pat, D)

        # Similarity matrix: (N_cand, N_pat)
        sim_matrix = candidate_matrix @ pattern_matrix.T

        scores: list[BatchScore] = []
        for i, text in enumerate(candidates):
            best_idx = int(np.argmax(sim_matrix[i]))
            best_sim = float(sim_matrix[i, best_idx])
            neighborhood_density = _mean_topk_similarity(sim_matrix[i])
            is_conv = best_sim >= self._threshold
            matched = self._loaded_patterns[best_idx] if is_conv else None

            scores.append(
                BatchScore(
                    text=text,
                    novelty_score=1.0 - best_sim,
                    similarity=best_sim,
                    is_convergent=is_conv,
                    matched_pattern=matched,
                    novelty_vector=NoveltyVector(
                        banality_similarity=best_sim,
                        prior_art_similarity=neighborhood_density,
                        branch_family_distance=float(np.clip(1.0 - neighborhood_density, 0.0, 1.0)),
                    ),
                )
            )

        # Sort by novelty descending (most novel first)
        scores.sort(key=lambda s: s.novelty_score, reverse=True)
        for rank, score in enumerate(scores, start=1):
            score.rank = rank

        convergent_count = sum(1 for s in scores if s.is_convergent)

        return BatchDetectionResult(
            candidates=scores,
            best=scores[0] if scores else None,
            worst=scores[-1] if scores else None,
            convergent_count=convergent_count,
            problem_class=problem_class or self._loaded_class,
        )

    # ------------------------------------------------------------------
    # Properties and configuration
    # ------------------------------------------------------------------

    @property
    def threshold(self) -> float:
        """The current similarity threshold."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        """Update the similarity threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Threshold must be in [0.0, 1.0], got {value}")
        self._threshold = value

    @property
    def loaded_pattern_count(self) -> int:
        """Number of patterns currently loaded in memory."""
        return len(self._loaded_patterns)

    @property
    def loaded_class(self) -> str:
        """The problem class currently loaded (or ``"__all__"`` / ``"in_memory"``)."""
        return self._loaded_class

    def __repr__(self) -> str:
        return (
            f"ConvergenceDetector("
            f"threshold={self._threshold:.2f}, "
            f"patterns={self.loaded_pattern_count}, "
            f"class={self._loaded_class!r})"
        )


def _mean_topk_similarity(similarities: np.ndarray, k: int = 3) -> float:
    if similarities.size == 0:
        return 0.0
    ordered = np.sort(similarities)[::-1]
    window = ordered[: max(1, min(k, ordered.size))]
    return float(np.mean(window))
