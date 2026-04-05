"""
Abstract base adapter for LLM model providers.

Every provider-specific adapter (Anthropic, OpenAI, etc.) must subclass
``BaseAdapter`` and implement all abstract methods.  The contract ensures
DeepForge can treat any model uniformly while still exploiting provider-
specific features (prefill injection, structured output, logit biasing).
"""

from __future__ import annotations

import abc
import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model capability flags
# ---------------------------------------------------------------------------


class ModelCapability(Enum):
    """Capabilities that individual models may or may not support."""

    PREFILL = auto()  # Inject arbitrary assistant prefix before generation
    STREAMING = auto()  # Real-time token streaming
    PROMPT_CACHING = auto()  # Provider-level caching of prompt segments
    EXTENDED_THINKING = auto()  # Extended chain-of-thought / reasoning mode
    STRUCTURED_OUTPUT = auto()  # JSON schema–constrained output
    FUNCTION_CALLING = auto()  # Tool / function calling
    VISION = auto()  # Multi-modal image understanding


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """
    Static configuration for a model.

    Attributes
    ----------
    name:
        The model identifier string used when calling the provider API.
    provider:
        Provider name, e.g. ``"anthropic"`` or ``"openai"``.
    context_window:
        Maximum number of tokens the model accepts as input.
    max_output_tokens:
        Hard ceiling on output token count.
    input_cost_per_million:
        Approximate input token cost in USD per 1 000 000 tokens.
    output_cost_per_million:
        Approximate output token cost in USD per 1 000 000 tokens.
    capabilities:
        Set of :class:`ModelCapability` flags the model supports.
    extra:
        Provider-specific metadata (model version strings, feature flags, etc.).
    """

    name: str
    provider: str
    context_window: int
    max_output_tokens: int
    input_cost_per_million: float
    output_cost_per_million: float
    capabilities: set[ModelCapability] = field(default_factory=set)
    extra: dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: ModelCapability) -> bool:
        """Return ``True`` if this model supports *capability*."""
        return capability in self.capabilities


@dataclass
class GenerationResult:
    """
    The result of a single (non-streaming) generation call.

    Attributes
    ----------
    text:
        The generated text.
    input_tokens:
        Number of input tokens consumed (as reported by the provider).
    output_tokens:
        Number of output tokens generated.
    cost_usd:
        Estimated cost in USD based on :attr:`ModelConfig` pricing.
    model:
        Model name used.
    stop_reason:
        Why generation stopped (``"end_turn"``, ``"max_tokens"``, etc.).
    raw:
        The raw response object from the provider SDK for debugging.
    """

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    stop_reason: str
    raw: Any = None


@dataclass
class StreamChunk:
    """
    A single chunk emitted during streaming generation.

    Attributes
    ----------
    delta:
        The incremental text token(s) in this chunk.
    accumulated:
        Full text accumulated so far (including *delta*).
    input_tokens:
        Non-zero only on the final chunk (summary from provider).
    output_tokens:
        Non-zero only on the final chunk (summary from provider).
    is_final:
        ``True`` on the last chunk.
    stop_reason:
        Populated on the final chunk only.
    """

    delta: str
    accumulated: str
    input_tokens: int = 0
    output_tokens: int = 0
    is_final: bool = False
    stop_reason: str = ""


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------


class BaseAdapter(abc.ABC):
    """
    Abstract base class for LLM provider adapters.

    Subclasses implement the provider-specific API calls while this class
    provides the shared interface, cost calculation, and stream-cancellation
    machinery.

    Parameters
    ----------
    config:
        Static :class:`ModelConfig` describing the model.
    api_key:
        Provider API key.  If ``None``, the subclass must pick it up from
        the environment.
    timeout:
        Default request timeout in seconds.
    max_retries:
        How many times to retry on transient errors (rate limits, timeouts).
    """

    def __init__(
        self,
        config: ModelConfig,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._config = config
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> ModelConfig:
        """The static :class:`ModelConfig` for this adapter."""
        return self._config

    @property
    def model_name(self) -> str:
        """Convenience accessor for ``config.name``."""
        return self._config.name

    # ------------------------------------------------------------------
    # Abstract methods — must be implemented by every subclass
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefill: str | None = None,
        stream: bool = False,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> GenerationResult:
        """
        Generate a completion for *prompt*.

        Parameters
        ----------
        prompt:
            The user-facing message or prompt text.
        system:
            Optional system-level instruction prepended to the conversation.
        prefill:
            Optional text to inject at the start of the assistant's response
            (used by the Cognitive Interference Engine on Anthropic models).
            Providers that do not support prefill should raise
            :exc:`~hephaestus.deepforge.exceptions.AdapterError`.
        stream:
            If ``True`` the call still blocks until completion but uses the
            streaming endpoint internally so that :meth:`generate_stream`
            callbacks can monitor output in real time.  Prefer calling
            :meth:`generate_stream` directly for streaming use-cases.
        max_tokens:
            Maximum number of tokens to generate.
        temperature:
            Sampling temperature (0–2 for most providers).
        **kwargs:
            Provider-specific keyword arguments forwarded verbatim to the
            underlying SDK call.

        Returns
        -------
        GenerationResult
        """

    @abc.abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefill: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream generation for *prompt*, yielding :class:`StreamChunk` objects.

        Callers should iterate over the returned async iterator and inspect
        each chunk.  Call :meth:`cancel_stream` from any coroutine to abort
        mid-generation; the iterator will raise
        :exc:`~hephaestus.deepforge.exceptions.GenerationKilled` on the next
        iteration.

        Parameters
        ----------
        prompt:
            The user-facing message or prompt text.
        system:
            Optional system-level instruction.
        prefill:
            Optional assistant prefix text.
        max_tokens:
            Maximum output tokens.
        temperature:
            Sampling temperature.
        **kwargs:
            Provider-specific forwarded arguments.

        Yields
        ------
        StreamChunk
        """
        # This stub keeps mypy happy; implementations must override fully.
        raise NotImplementedError  # pragma: no cover
        yield StreamChunk(delta="", accumulated="")

    # ------------------------------------------------------------------
    # Stream cancellation
    # ------------------------------------------------------------------

    def cancel_stream(self) -> None:
        """
        Signal the current stream to abort.

        Thread-safe; can be called from any coroutine or thread.  The
        streaming iterator will notice the event at its next iteration and
        raise :exc:`~hephaestus.deepforge.exceptions.GenerationKilled`.
        """
        self._logger.debug("cancel_stream() called on adapter %s", self.model_name)
        self._cancel_event.set()

    def _reset_cancel(self) -> None:
        """Clear the cancel event so the adapter is ready for a new stream."""
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        """``True`` if :meth:`cancel_stream` has been called."""
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------
    # Cost calculation
    # ------------------------------------------------------------------

    def compute_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate the USD cost for a generation.

        Parameters
        ----------
        input_tokens:
            Number of input (prompt) tokens consumed.
        output_tokens:
            Number of output (completion) tokens generated.

        Returns
        -------
        float
            Estimated cost in USD.
        """
        cost = (
            input_tokens * self._config.input_cost_per_million / 1_000_000
            + output_tokens * self._config.output_cost_per_million / 1_000_000
        )
        return round(cost, 8)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name!r}, provider={self._config.provider!r})"
