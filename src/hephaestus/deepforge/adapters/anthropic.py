"""
Anthropic (Claude) model adapter for DeepForge.

Key features:
- **Assistant prefill injection** — the primary mechanism DeepForge uses for
  Cognitive Interference.  The entire assistant prefix is injected before
  the model starts generating, forcing it to continue from an alien frame.
- **Streaming** with real-time token interception via ``MessageStreamEvent``.
- **Prompt caching** — marks long system prompts and context documents as
  cacheable, reducing repeat costs by ~35 %.
- **Extended thinking** — passes ``thinking`` budget tokens for Opus models
  that support it, exposing internal CoT for deeper interference.
- Automatic retry with exponential back-off on rate-limit / transient errors.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.exceptions import (
    AdapterError,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    GenerationKilled,
    ModelNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-configured model catalogue
# ---------------------------------------------------------------------------

ANTHROPIC_MODELS: dict[str, ModelConfig] = {
    "claude-opus-4-5": ModelConfig(
        name="claude-opus-4-5",
        provider="anthropic",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=15.0,
        output_cost_per_million=75.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.PROMPT_CACHING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.VISION,
        },
    ),
    "claude-sonnet-4-5": ModelConfig(
        name="claude-sonnet-4-5",
        provider="anthropic",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.PROMPT_CACHING,
            ModelCapability.VISION,
        },
    ),
    "claude-haiku-3-5": ModelConfig(
        name="claude-haiku-3-5",
        provider="anthropic",
        context_window=200_000,
        max_output_tokens=8192,
        input_cost_per_million=0.8,
        output_cost_per_million=4.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.PROMPT_CACHING,
            ModelCapability.VISION,
        },
    ),
}

# Default retry delays (seconds) for exponential back-off
_RETRY_DELAYS = [1.0, 2.0, 4.0, 8.0, 16.0]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class AnthropicAdapter(BaseAdapter):
    """
    Adapter for Anthropic Claude models.

    Supports assistant prefill injection, prompt caching, extended thinking,
    streaming, and automatic retry on transient errors.

    Parameters
    ----------
    model:
        Either a model name string (key into ``ANTHROPIC_MODELS``) or a
        fully custom :class:`~hephaestus.deepforge.adapters.base.ModelConfig`.
    api_key:
        Anthropic API key.  Falls back to the ``ANTHROPIC_API_KEY`` environment
        variable when ``None``.
    timeout:
        Request timeout in seconds (default 120).
    max_retries:
        Retry attempts on rate-limit / transient errors (default 3).
    enable_prompt_caching:
        Whether to attach ``cache_control`` breakpoints to eligible prompts
        (default ``True``).
    thinking_budget_tokens:
        Token budget for extended thinking on supported models.  ``None``
        disables extended thinking.
    """

    def __init__(
        self,
        model: str | ModelConfig = "claude-sonnet-4-5",
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        enable_prompt_caching: bool = True,
        thinking_budget_tokens: int | None = None,
    ) -> None:
        if isinstance(model, str):
            if model not in ANTHROPIC_MODELS:
                raise ModelNotFoundError(
                    f"Unknown Anthropic model {model!r}. Available: {list(ANTHROPIC_MODELS)}"
                )
            config = ANTHROPIC_MODELS[model]
        else:
            config = model

        super().__init__(config, api_key=api_key, timeout=timeout, max_retries=max_retries)

        self._enable_prompt_caching = enable_prompt_caching
        self._thinking_budget = thinking_budget_tokens

        # Lazy-initialised client (allows instantiation without a key for tests)
        self.__client: anthropic.AsyncAnthropic | None = None

    # ------------------------------------------------------------------
    # Internal client
    # ------------------------------------------------------------------

    @property
    def _client(self) -> anthropic.AsyncAnthropic:
        """Return (and lazily create) the Anthropic async client."""
        if self.__client is None:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self.__client = anthropic.AsyncAnthropic(**kwargs)
        return self.__client

    # ------------------------------------------------------------------
    # Message construction helpers
    # ------------------------------------------------------------------

    def _build_system_block(self, system: str) -> list[dict[str, Any]]:
        """
        Build the ``system`` parameter value.

        When prompt caching is enabled the system text gets a
        ``cache_control`` breakpoint so Anthropic caches it across calls
        with the same prefix.
        """
        block: dict[str, Any] = {"type": "text", "text": system}
        if self._enable_prompt_caching:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]

    def _build_messages(self, prompt: str, prefill: str | None) -> list[dict[str, Any]]:
        """
        Assemble the ``messages`` list.

        If *prefill* is provided an ``assistant`` message is appended
        **before** generation begins.  The model is forced to continue from
        that assistant text — the cornerstone of Cognitive Interference.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        if prefill:
            messages.append({"role": "assistant", "content": prefill})
        return messages

    def _build_thinking_param(self) -> dict[str, Any] | None:
        """Return the ``thinking`` parameter dict if applicable."""
        if self._thinking_budget is not None and self._config.supports(
            ModelCapability.EXTENDED_THINKING
        ):
            return {"type": "enabled", "budget_tokens": self._thinking_budget}
        return None

    # ------------------------------------------------------------------
    # Error translation
    # ------------------------------------------------------------------

    @staticmethod
    def _translate_error(exc: Exception) -> AdapterError:
        """Convert Anthropic SDK exceptions into DeepForge exceptions."""
        if isinstance(exc, anthropic.RateLimitError):
            return RateLimitError(str(exc))
        if isinstance(exc, anthropic.AuthenticationError):
            return AuthenticationError(str(exc))
        if isinstance(exc, anthropic.NotFoundError):
            return ModelNotFoundError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return APIConnectionError(str(exc))
        if isinstance(exc, anthropic.APITimeoutError):
            return APITimeoutError(str(exc))
        if isinstance(exc, anthropic.APIError):
            return AdapterError(f"Anthropic API error: {exc}")
        return AdapterError(f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    async def _with_retry(self, coro_factory: Any, attempt: int = 0) -> Any:
        """
        Execute *coro_factory()* with exponential back-off retries.

        Parameters
        ----------
        coro_factory:
            Zero-argument callable that returns a coroutine.
        attempt:
            Current attempt index (starts at 0).
        """
        try:
            return await coro_factory()
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        ) as exc:
            if attempt >= self._max_retries:
                raise self._translate_error(exc) from exc
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            self._logger.warning(
                "Transient Anthropic error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                self._max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            return await self._with_retry(coro_factory, attempt + 1)
        except anthropic.APIError as exc:
            raise self._translate_error(exc) from exc

    # ------------------------------------------------------------------
    # generate()
    # ------------------------------------------------------------------

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
        Generate a completion with optional assistant prefill.

        Parameters
        ----------
        prompt:
            User message text.
        system:
            Optional system instruction.
        prefill:
            Text injected at the start of the assistant response (Cognitive
            Interference injection point).
        stream:
            Use the streaming endpoint internally and collect all chunks.
        max_tokens:
            Maximum output tokens.
        temperature:
            Sampling temperature (0–1 recommended for most DeepForge use).
        **kwargs:
            Additional arguments forwarded to the Anthropic API.

        Returns
        -------
        GenerationResult
        """
        self._reset_cancel()

        if stream:
            # Collect stream into a single result
            accumulated = ""
            last_chunk: StreamChunk | None = None
            async for chunk in self.generate_stream(
                prompt,
                system=system,
                prefill=prefill,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            ):
                accumulated = chunk.accumulated
                last_chunk = chunk

            if last_chunk is None:
                raise AdapterError("Stream produced no output")

            # If prefill was provided, strip it from the final text so the
            # caller sees only the freshly generated content.
            output_text = accumulated
            if prefill and output_text.startswith(prefill):
                output_text = output_text[len(prefill) :]

            return GenerationResult(
                text=output_text,
                input_tokens=last_chunk.input_tokens,
                output_tokens=last_chunk.output_tokens,
                cost_usd=self.compute_cost(last_chunk.input_tokens, last_chunk.output_tokens),
                model=self.model_name,
                stop_reason=last_chunk.stop_reason,
            )

        # ---- Non-streaming path ----
        messages = self._build_messages(prompt, prefill)
        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        if system:
            call_kwargs["system"] = self._build_system_block(system)

        thinking = self._build_thinking_param()
        if thinking:
            call_kwargs["thinking"] = thinking
            # Extended thinking requires temperature=1
            call_kwargs["temperature"] = 1.0

        def _factory() -> Any:
            return self._client.messages.create(**call_kwargs)

        t_start = time.monotonic()
        response = await self._with_retry(_factory)
        elapsed = time.monotonic() - t_start

        self._logger.debug(
            "Anthropic generate completed in %.2fs | in=%d out=%d",
            elapsed,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        # Extract text content (skip thinking blocks)
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)

        full_text = "".join(text_parts)

        # Strip prefill from the front of the generated text
        if prefill and full_text.startswith(prefill):
            full_text = full_text[len(prefill) :]

        return GenerationResult(
            text=full_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=self.compute_cost(response.usage.input_tokens, response.usage.output_tokens),
            model=self.model_name,
            stop_reason=response.stop_reason or "end_turn",
            raw=response,
        )

    # ------------------------------------------------------------------
    # generate_stream()
    # ------------------------------------------------------------------

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
        Stream generation, yielding :class:`StreamChunk` objects.

        Streaming is the primary mode used by the Convergence Pruner — it
        inspects each chunk and calls :meth:`cancel_stream` when a banality
        pattern is detected.

        Yields
        ------
        StreamChunk
            Each chunk carries the incremental delta and the full accumulated
            text.  The final chunk has ``is_final=True`` and populated
            ``input_tokens`` / ``output_tokens`` / ``stop_reason``.

        Raises
        ------
        GenerationKilled
            If :meth:`cancel_stream` is called mid-stream.
        AdapterError
            On unrecoverable API errors.
        """
        self._reset_cancel()

        messages = self._build_messages(prompt, prefill)
        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        if system:
            call_kwargs["system"] = self._build_system_block(system)

        thinking = self._build_thinking_param()
        if thinking:
            call_kwargs["thinking"] = thinking
            call_kwargs["temperature"] = 1.0

        accumulated = prefill or ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = "end_turn"

        try:
            # messages.stream() returns a synchronous async-context-manager —
            # it must NOT be awaited; use it directly as an async context manager.
            async with self._client.messages.stream(**call_kwargs) as stream:
                async for text in stream.text_stream:
                    if self.is_cancelled:
                        raise GenerationKilled(
                            "Stream cancelled by cancel_stream()",
                            partial_output=accumulated,
                        )
                    accumulated += text
                    yield StreamChunk(
                        delta=text,
                        accumulated=accumulated,
                    )

                # Retrieve usage from the final message
                final_msg = await stream.get_final_message()
                input_tokens = final_msg.usage.input_tokens
                output_tokens = final_msg.usage.output_tokens
                stop_reason = final_msg.stop_reason or "end_turn"

        except GenerationKilled:
            raise
        except anthropic.APIError as exc:
            raise self._translate_error(exc) from exc

        # Emit the final sentinel chunk with usage info
        yield StreamChunk(
            delta="",
            accumulated=accumulated,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_final=True,
            stop_reason=stop_reason,
        )

        self._logger.debug(
            "Anthropic stream completed | in=%d out=%d stop=%s",
            input_tokens,
            output_tokens,
            stop_reason,
        )
