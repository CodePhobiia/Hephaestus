"""
Custom exception hierarchy for the DeepForge LLM harness.

All DeepForge exceptions inherit from ``DeepForgeError``, allowing callers
to catch the entire family with a single ``except DeepForgeError`` clause
while still being able to distinguish sub-types.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class DeepForgeError(Exception):
    """Base class for all DeepForge errors."""


# ---------------------------------------------------------------------------
# Adapter layer
# ---------------------------------------------------------------------------


class AdapterError(DeepForgeError):
    """An error originating inside a model adapter."""


class RateLimitError(AdapterError):
    """The upstream API returned a rate-limit response (429)."""


class AuthenticationError(AdapterError):
    """API authentication failed (invalid key, expired token, etc.)."""


class ModelNotFoundError(AdapterError):
    """The requested model is not available or does not exist."""


class APIConnectionError(AdapterError):
    """Network-level failure communicating with the upstream API."""


class APITimeoutError(AdapterError):
    """Request to the upstream API timed out."""


# ---------------------------------------------------------------------------
# Generation control
# ---------------------------------------------------------------------------


class GenerationKilled(DeepForgeError): # noqa: N818
    """
    Generation was forcibly killed before completion.

    Attributes
    ----------
    partial_output:
        Text that had been accumulated before the kill.
    reason:
        Human-readable explanation of why generation was killed.
    """

    def __init__(self, reason: str, partial_output: str = "") -> None:
        super().__init__(reason)
        self.reason: str = reason
        self.partial_output: str = partial_output

    def __str__(self) -> str:
        snippet = (
            self.partial_output[:120] + "…"
            if len(self.partial_output) > 120
            else self.partial_output
        )
        return f"{self.reason} | partial: {snippet!r}"


class ConvergenceDetected(GenerationKilled):
    """
    The convergence pruner identified a predictable / banality pattern
    in the stream and killed generation.

    Attributes
    ----------
    pattern_similarity:
        Cosine similarity (0–1) between the output and the matched pattern.
    matched_pattern:
        The convergence pattern text that triggered the kill.
    """

    def __init__(
        self,
        partial_output: str,
        pattern_similarity: float,
        matched_pattern: str,
    ) -> None:
        reason = (
            f"Convergence detected — similarity {pattern_similarity:.3f} to known banality pattern"
        )
        super().__init__(reason=reason, partial_output=partial_output)
        self.pattern_similarity: float = pattern_similarity
        self.matched_pattern: str = matched_pattern


# ---------------------------------------------------------------------------
# Engine errors
# ---------------------------------------------------------------------------


class InterferenceError(DeepForgeError):
    """An error inside the Cognitive Interference Engine."""


class PrunerError(DeepForgeError):
    """An error inside the Convergence Pruner."""


class PressureError(DeepForgeError):
    """An error inside the Anti-Training Pressure engine."""


class HarnessError(DeepForgeError):
    """An error inside the DeepForge harness orchestrator."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigurationError(DeepForgeError):
    """Invalid or missing configuration for a DeepForge component."""
