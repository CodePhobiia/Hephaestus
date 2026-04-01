"""Structural novelty scoring — model-free novelty assessment.

Instead of asking a model "is this novel?" (which is self-referential when the
same model generated it), this module uses structural signals to assess novelty:

1. Vocabulary divergence: How different is the invention's vocabulary from the
   problem's vocabulary? High divergence = new concepts introduced.
2. Concept density: How many distinct technical concepts per paragraph?
   Genuine inventions introduce dense new concepts.
3. Specificity: Does the architecture use specific data structures, algorithms,
   and parameters? Or is it vague hand-waving?
4. Self-containment: Can the architecture section be understood without
   the source domain context? If yes, it's a real mechanism.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass
class StructuralNoveltyScore:
    """Model-free novelty assessment based on structural text signals."""
    vocabulary_divergence: float  # 0-1: how different are invention words from problem words
    concept_density: float  # 0-1: technical concepts per unit text
    specificity: float  # 0-1: concrete vs vague language ratio
    self_containment: float  # 0-1: how well architecture stands without source context
    composite: float  # weighted combination

    @property
    def label(self) -> str:
        if self.composite >= 0.7:
            return "STRUCTURALLY_NOVEL"
        if self.composite >= 0.4:
            return "MODERATELY_NOVEL"
        return "STRUCTURALLY_CONVENTIONAL"


def compute_structural_novelty(
    problem: str,
    architecture: str,
    key_insight: str,
    phase1_abstract: str = "",
    source_domain_words: list[str] | None = None,
) -> StructuralNoveltyScore:
    """Compute structural novelty without asking a model.

    Uses text-level signals to assess whether the invention introduces
    genuinely new concepts vs repackaging known ones.
    """
    invention_text = f"{architecture} {key_insight} {phase1_abstract}"

    vocab_div = _vocabulary_divergence(problem, invention_text)
    concept_den = _concept_density(architecture)
    specificity = _specificity_score(architecture)
    self_contain = _self_containment(architecture, source_domain_words or [])

    # Weighted composite
    composite = (
        0.25 * vocab_div +
        0.25 * concept_den +
        0.30 * specificity +
        0.20 * self_contain
    )

    return StructuralNoveltyScore(
        vocabulary_divergence=vocab_div,
        concept_density=concept_den,
        specificity=specificity,
        self_containment=self_contain,
        composite=composite,
    )


def _vocabulary_divergence(problem: str, invention: str) -> float:
    """Measure how much new vocabulary the invention introduces."""
    problem_words = set(_extract_technical_words(problem))
    invention_words = set(_extract_technical_words(invention))

    if not invention_words:
        return 0.0

    new_words = invention_words - problem_words
    return len(new_words) / len(invention_words)


def _concept_density(architecture: str) -> float:
    """Count distinct technical concepts per 100 words."""
    words = architecture.split()
    if len(words) < 20:
        return 0.0

    technical = _extract_technical_words(architecture)
    unique_technical = set(technical)

    # Concepts per 100 words, capped at 1.0
    density = len(unique_technical) / (len(words) / 100)
    return min(density / 30, 1.0)  # 30 unique technical terms per 100 words = 1.0


def _specificity_score(architecture: str) -> float:
    """Score how specific vs vague the architecture is."""
    if not architecture:
        return 0.0

    # Specific signals: data structures, algorithms, parameters, equations
    specific_patterns = [
        r'\b(?:array|list|dict|map|queue|stack|tree|graph|matrix|vector|tensor)\b',
        r'\b(?:O\([^)]+\)|log\s*n|n\^2|linear|polynomial|exponential)\b',
        r'\b\d+(?:\.\d+)?\b',  # numbers/parameters
        r'[=<>≤≥]+',  # equations/comparisons
        r'\b(?:if|then|else|while|for|return|def|class|struct)\b',  # code-like
        r'\b(?:threshold|coefficient|weight|parameter|constant|variable)\b',
        r'\b(?:UDP|TCP|HTTP|RPC|gRPC|REST|API)\b',  # protocols
        r'\b(?:Redis|PostgreSQL|Kafka|NATS|ZeroMQ)\b',  # technologies
    ]

    # Vague signals
    vague_patterns = [
        r'\b(?:could|would|might|perhaps|possibly|potentially)\b',
        r'\b(?:similar|analogous|inspired|reminiscent|akin)\b',
        r'\b(?:somehow|generally|typically|usually|often)\b',
        r'\b(?:various|several|multiple|many|some)\b',
    ]

    specific_count = sum(
        len(re.findall(p, architecture, re.IGNORECASE))
        for p in specific_patterns
    )
    vague_count = sum(
        len(re.findall(p, architecture, re.IGNORECASE))
        for p in vague_patterns
    )

    total = specific_count + vague_count
    if total == 0:
        return 0.5

    return min(specific_count / (total + 1), 1.0)


def _self_containment(architecture: str, source_domain_words: list[str]) -> float:
    """Measure how well the architecture stands without source domain references."""
    if not architecture or not source_domain_words:
        return 0.8  # Benefit of doubt when no source words to check

    arch_lower = architecture.lower()
    total_words = len(architecture.split())
    source_hits = sum(
        arch_lower.count(word.lower())
        for word in source_domain_words
        if len(word) > 3
    )

    # Source domain word density — lower is better
    if total_words == 0:
        return 0.5
    density = source_hits / total_words
    return max(0.0, 1.0 - density * 10)  # 10% source words = 0.0


def _extract_technical_words(text: str) -> list[str]:
    """Extract words that are likely technical terms."""
    # Words that are capitalized, contain underscores, or are longer than 6 chars
    words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text)
    technical = [
        w for w in words
        if len(w) > 5
        or '_' in w
        or (w[0].isupper() and len(w) > 3)
        or w.lower() in _TECHNICAL_VOCAB
    ]
    return technical


_TECHNICAL_VOCAB = {
    "algorithm", "buffer", "cache", "cluster", "codec", "config",
    "counter", "daemon", "delta", "epoch", "fetch", "graph",
    "hash", "index", "kafka", "layer", "merge", "mutex",
    "node", "queue", "redis", "shard", "state", "token",
    "vector", "worker", "yield", "batch", "bloom", "chunk",
    "codec", "fiber", "float", "frame", "guard", "heapq",
    "infer", "latch", "model", "parse", "probe", "proto",
    "qubit", "relay", "route", "scope", "stack", "table",
    "timer", "tuple", "union", "valve", "async", "await",
}


__all__ = ["StructuralNoveltyScore", "compute_structural_novelty"]
