"""Diversity scoring for candidate selection.

Prevents the pipeline from selecting too-similar candidates by penalizing
overlap and rewarding structural diversity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class DiversityScore:
    """Diversity assessment for a set of candidates."""

    pairwise_similarities: list[tuple[int, int, float]]
    mean_similarity: float
    diversity_bonus: float  # 0.0 (all same) to 1.0 (all different)
    penalty_applied: list[int]  # indices of penalized candidates


def compute_text_similarity(a: str, b: str) -> float:
    """Jaccard similarity over word tokens."""
    tokens_a = set(_tokenize(a))
    tokens_b = set(_tokenize(b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def compute_diversity(candidates: list[Any], text_fn: Any = None) -> DiversityScore:
    """Compute pairwise diversity for a list of candidates.

    Parameters
    ----------
    candidates:
        List of candidate objects.
    text_fn:
        Function to extract text from a candidate for comparison.
        Default: str(candidate).
    """
    if text_fn is None:
        text_fn = str

    n = len(candidates)
    pairs: list[tuple[int, int, float]] = []
    total_sim = 0.0

    for i in range(n):
        for j in range(i + 1, n):
            sim = compute_text_similarity(text_fn(candidates[i]), text_fn(candidates[j]))
            pairs.append((i, j, sim))
            total_sim += sim

    num_pairs = len(pairs)
    mean_sim = total_sim / num_pairs if num_pairs > 0 else 0.0
    diversity_bonus = 1.0 - mean_sim

    # Penalize candidates that are too similar to an earlier, higher-ranked one
    penalty_threshold = 0.6
    penalized: list[int] = []
    for _i, j, sim in pairs:
        if sim > penalty_threshold and j not in penalized:
            penalized.append(j)

    return DiversityScore(
        pairwise_similarities=pairs,
        mean_similarity=mean_sim,
        diversity_bonus=diversity_bonus,
        penalty_applied=sorted(set(penalized)),
    )


def apply_diversity_rerank(
    candidates: list[Any],
    scores: list[float],
    text_fn: Any = None,
    penalty_factor: float = 0.3,
) -> list[tuple[Any, float]]:
    """Re-rank candidates by applying a diversity penalty to similar ones.

    Returns list of (candidate, adjusted_score) sorted by adjusted score descending.
    """
    if not candidates:
        return []

    diversity = compute_diversity(candidates, text_fn)
    adjusted = list(scores)

    for idx in diversity.penalty_applied:
        if idx < len(adjusted):
            adjusted[idx] *= 1.0 - penalty_factor

    paired = list(zip(candidates, adjusted, strict=True))
    paired.sort(key=lambda x: x[1], reverse=True)
    return paired


def _tokenize(text: str) -> list[str]:
    """Extract lowercase word tokens from text."""
    return [t.lower() for t in re.findall(r"[a-zA-Z]{3,}", text)]


__all__ = [
    "DiversityScore",
    "compute_diversity",
    "compute_text_similarity",
    "apply_diversity_rerank",
]
