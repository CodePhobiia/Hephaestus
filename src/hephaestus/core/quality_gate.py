"""Invention quality gate — filters and flags low-quality inventions before output.

This module runs after verification to catch inventions that passed the pipeline
but are likely decorative rather than genuinely novel.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Phrases that signal decorative transfer (metaphor, not mechanism)
_DECORATIVE_SIGNALS = [
    "inspired by",
    "analogous to",
    "similar to how",
    "just as.*so too",
    "borrowing from",
    "taking a page from",
    "in the same way that",
    "mirrors the",
    "echoes the",
    "akin to",
    "much like",
    "reminiscent of",
    "draws from",
    "modeled after",
    "based on the analogy",
    "metaphorically",
    "in a manner similar",
]

# Architecture phrases that signal no concrete mechanism
_VAGUE_ARCHITECTURE_SIGNALS = [
    "could be implemented",
    "would potentially",
    "in principle",
    "theoretically",
    "one possible approach",
    "a system could",
    "further research needed",
    "remains to be seen",
    "future work",
]

# Known pattern names that get redressed as inventions
_KNOWN_PATTERNS = [
    "circuit breaker",
    "retry with backoff",
    "exponential backoff",
    "load balancer",
    "round robin",
    "consistent hashing",
    "pub.?sub",
    "event.?driven",
    "message queue",
    "cache invalidation",
    "ttl.?based",
    "rate limit",
    "connection pool",
    "thread pool",
    "observer pattern",
    "factory pattern",
    "strategy pattern",
    "state machine",
    "finite automata",
]


@dataclass
class QualityAssessment:
    """Result of the quality gate assessment."""
    passed: bool
    score_adjustment: float = 0.0  # negative = penalty
    decorative_signal_count: int = 0
    vague_architecture_count: int = 0
    known_pattern_matches: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    recommendation: str = ""


def assess_invention_quality(
    architecture: str,
    key_insight: str,
    mechanism_differs_from_baseline: str = "",
    subtraction_test: str = "",
    baseline_comparison: str = "",
) -> QualityAssessment:
    """Run quality checks on an invention's output text.

    Returns a QualityAssessment with flags and score adjustment.
    """
    combined = f"{architecture} {key_insight} {mechanism_differs_from_baseline}"
    combined_lower = combined.lower()

    flags: list[str] = []

    # Check for decorative transfer signals
    decorative_count = 0
    for pattern in _DECORATIVE_SIGNALS:
        if re.search(pattern, combined_lower):
            decorative_count += 1

    if decorative_count >= 3:
        flags.append(f"HIGH_DECORATIVE: {decorative_count} metaphor-signaling phrases found")
    elif decorative_count >= 1:
        flags.append(f"MILD_DECORATIVE: {decorative_count} metaphor-signaling phrase(s)")

    # Check for vague architecture
    vague_count = 0
    arch_lower = architecture.lower()
    for pattern in _VAGUE_ARCHITECTURE_SIGNALS:
        if re.search(pattern, arch_lower):
            vague_count += 1

    if vague_count >= 2:
        flags.append(f"VAGUE_ARCHITECTURE: {vague_count} non-concrete phrases")

    # Check for known pattern redressing
    known_matches: list[str] = []
    for pattern in _KNOWN_PATTERNS:
        if re.search(pattern, combined_lower):
            known_matches.append(pattern)

    if known_matches:
        flags.append(f"KNOWN_PATTERN: matches {', '.join(known_matches)}")

    # Check subtraction test honesty
    if subtraction_test:
        sub_lower = subtraction_test.lower()
        honesty_markers = ["collapses to", "essentially", "well-known", "standard", "conventional"]
        honest_collapse = any(m in sub_lower for m in honesty_markers)
        if honest_collapse:
            flags.append("HONEST_COLLAPSE: subtraction test admits mechanism is known")

    # Check if baseline comparison reveals no difference
    if baseline_comparison:
        base_lower = baseline_comparison.lower()
        no_diff_markers = ["essentially the same", "no significant", "similar approach", "same mechanism"]
        if any(m in base_lower for m in no_diff_markers):
            flags.append("BASELINE_MATCH: invention matches conventional baseline")

    # Compute score adjustment
    adjustment = 0.0
    if decorative_count >= 3:
        adjustment -= 0.2
    elif decorative_count >= 1:
        adjustment -= 0.05
    if vague_count >= 2:
        adjustment -= 0.15
    if known_matches:
        adjustment -= 0.1 * len(known_matches)
    if "HONEST_COLLAPSE" in str(flags):
        adjustment -= 0.2
    if "BASELINE_MATCH" in str(flags):
        adjustment -= 0.3

    passed = adjustment > -0.4  # Fail gate if too many penalties

    recommendation = ""
    if not passed:
        recommendation = (
            "This invention appears to be a conventional pattern dressed in "
            "cross-domain vocabulary. Consider: (a) increasing divergence intensity, "
            "(b) excluding the detected known patterns from search, "
            "(c) adding the mechanism to anti-memory."
        )

    return QualityAssessment(
        passed=passed,
        score_adjustment=adjustment,
        decorative_signal_count=decorative_count,
        vague_architecture_count=vague_count,
        known_pattern_matches=known_matches,
        flags=flags,
        recommendation=recommendation,
    )


__all__ = ["QualityAssessment", "assess_invention_quality"]
