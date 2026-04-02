"""
OpenAI (GPT) model adapter for DeepForge.

Key features:
- **System prompt injection for cognitive interference** — injects lens axioms
  into the system message before generation.
- **Streaming** with real-time token interception.
- **Structured output** via ``response_format`` / JSON schema constraint.
- Automatic retry with exponential back-off on rate-limit / transient errors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import openai

from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.exceptions import (
    APIConnectionError,
    APITimeoutError,
    AdapterError,
    AuthenticationError,
    GenerationKilled,
    ModelNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-configured model catalogue
# ---------------------------------------------------------------------------

OPENAI_MODELS: dict[str, ModelConfig] = {
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        provider="openai",
        context_window=128_000,
        max_output_tokens=16_384,
        input_cost_per_million=2.5,
        output_cost_per_million=10.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
        },
    ),
    "gpt-4o-mini": ModelConfig(
        name="gpt-4o-mini",
        provider="openai",
        context_window=128_000,
        max_output_tokens=16_384,
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
        },
    ),
    "o3": ModelConfig(
        name="o3",
        provider="openai",
        context_window=200_000,
        max_output_tokens=100_000,
        input_cost_per_million=10.0,
        output_cost_per_million=40.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
    "o4-mini": ModelConfig(
        name="o4-mini",
        provider="openai",
        context_window=200_000,
        max_output_tokens=100_000,
        input_cost_per_million=1.10,
        output_cost_per_million=4.40,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
}

_RETRY_DELAYS = [1.0, 2.0, 4.0, 8.0, 16.0]


# ---------------------------------------------------------------------------
# Structured output helper
# ---------------------------------------------------------------------------


def _json_schema_response_format(schema: dict[str, Any], name: str = "output") -> dict[str, Any]:
    """
    Build the ``response_format`` dict for structured (JSON schema) output.

    Parameters
    ----------
    schema:
        A valid JSON Schema object describing the expected response shape.
    name:
        Logical name for the schema (used by the API).

    Returns
    -------
    dict
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class OpenAIAdapter(BaseAdapter):
    """
    Adapter for OpenAI GPT models.

    Uses system prompt injection as the primary mechanism for Cognitive
    Interference (since OpenAI does not support assistant prefill in the
    same way Anthropic does).

    Parameters
    ----------
    model:
        Either a model name string (key into ``OPENAI_MODELS``) or a custom
        :class:`~hephaestus.deepforge.adapters.base.ModelConfig`.
    api_key:
        OpenAI API key.  Falls back to the ``OPENAI_API_KEY`` environment
        variable.
    timeout:
        Request timeout in seconds (default 120).
    max_retries:
        Retry attempts on rate-limit / transient errors (default 3).
    base_url:
        Override the OpenAI base URL (for Azure or compatible endpoints).
    """

    def __init__(
        self,
        model: str | ModelConfig = "gpt-4o",
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(model, str):
            if model not in OPENAI_MODELS:
                raise ModelNotFoundError(
                    f"Unknown OpenAI model {model!r}. "
                    f"Available: {list(OPENAI_MODELS)}"
                )
            config = OPENAI_MODELS[model]
        else:
            config = model

        super().__init__(config, api_key=api_key, timeout=timeout, max_retries=max_retries)
        self._base_url = base_url
        self._default_headers = default_headers
        self.__client: openai.AsyncOpenAI | None = None

    # ------------------------------------------------------------------
    # Internal client
    # ------------------------------------------------------------------

    @property
    def _client(self) -> openai.AsyncOpenAI:
        """Return (and lazily create) the OpenAI async client."""
        if self.__client is None:
            kwargs: dict[str, Any] = {"timeout": self._timeout}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._default_headers:
                kwargs["default_headers"] = self._default_headers
            self.__client = openai.AsyncOpenAI(**kwargs)
        return self.__client

    # ------------------------------------------------------------------
    # Message construction helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        prompt: str,
        system: str | None,
        prefill: str | None,
    ) -> list[dict[str, Any]]:
        """
        Build the ``messages`` list.

        For OpenAI, *prefill* is injected as the beginning of an
        ``assistant`` message that immediately precedes the actual generation
        request.  Since OpenAI does not support a true "assistant prefix",
        we simulate it by adding a partial assistant message and then letting
        the model continue from there.

        When ``prefill`` is provided, the system is also augmented with a
        directive to continue from the assistant's partial response.
        """
        messages: list[dict[str, Any]] = []

        effective_system = system or ""
        if prefill:
            continuation_instruction = (
                "\n\n[IMPORTANT: The assistant has already begun responding. "
                "Continue EXACTLY from where the assistant left off, "
                "maintaining the exact conceptual frame established. "
                "Do NOT restart or restate — continue the thought seamlessly.]"
            )
            effective_system = effective_system + continuation_instruction

        if effective_system:
            messages.append({"role": "system", "content": effective_system})

        messages.append({"role": "user", "content": prompt})

        # Simulate prefill via an assistant message
        if prefill:
            messages.append({"role": "assistant", "content": prefill})

        return messages

    # ------------------------------------------------------------------
    # Error translation
    # ------------------------------------------------------------------

    @staticmethod
    def _translate_error(exc: Exception) -> AdapterError:
        """Convert OpenAI SDK exceptions into DeepForge exceptions."""
        if isinstance(exc, openai.RateLimitError):
            return RateLimitError(str(exc))
        if isinstance(exc, openai.AuthenticationError):
            return AuthenticationError(str(exc))
        if isinstance(exc, openai.NotFoundError):
            return ModelNotFoundError(str(exc))
        if isinstance(exc, openai.APIConnectionError):
            return APIConnectionError(str(exc))
        if isinstance(exc, openai.APITimeoutError):
            return APITimeoutError(str(exc))
        if isinstance(exc, openai.APIError):
            return AdapterError(f"OpenAI API error: {exc}")
        return AdapterError(f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    async def _with_retry(self, coro_factory: Any, attempt: int = 0) -> Any:
        """Execute *coro_factory()* with exponential back-off retries."""
        try:
            return await coro_factory()
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            if attempt >= self._max_retries:
                raise self._translate_error(exc) from exc
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            self._logger.warning(
                "Transient OpenAI error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                self._max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            return await self._with_retry(coro_factory, attempt + 1)
        except openai.APIError as exc:
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
        response_format: dict[str, Any] | None = None,
        json_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> GenerationResult:
        """
        Generate a completion.

        Parameters
        ----------
        prompt:
            User message text.
        system:
            Optional system instruction.  Lens axioms are injected here.
        prefill:
            Simulated assistant prefix (injected as an ``assistant`` message).
        stream:
            Internally use streaming and collect all chunks.
        max_tokens:
            Maximum output tokens.
        temperature:
            Sampling temperature.
        response_format:
            Raw ``response_format`` dict (mutually exclusive with
            *json_schema*).
        json_schema:
            JSON Schema dict for structured output.  Overrides
            *response_format*.
        **kwargs:
            Additional arguments forwarded to the OpenAI API.

        Returns
        -------
        GenerationResult
        """
        self._reset_cancel()

        if stream:
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

            output_text = accumulated
            if prefill and output_text.startswith(prefill):
                output_text = output_text[len(prefill):]

            return GenerationResult(
                text=output_text,
                input_tokens=last_chunk.input_tokens,
                output_tokens=last_chunk.output_tokens,
                cost_usd=self.compute_cost(last_chunk.input_tokens, last_chunk.output_tokens),
                model=self.model_name,
                stop_reason=last_chunk.stop_reason,
            )

        # ---- Non-streaming path ----
        messages = self._build_messages(prompt, system, prefill)

        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        # Structured output handling
        if json_schema is not None:
            call_kwargs["response_format"] = _json_schema_response_format(json_schema)
        elif response_format is not None:
            call_kwargs["response_format"] = response_format

        def _factory() -> Any:
            return self._client.chat.completions.create(**call_kwargs)

        t_start = time.monotonic()
        response = await self._with_retry(_factory)
        elapsed = time.monotonic() - t_start

        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0

        self._logger.debug(
            "OpenAI generate completed in %.2fs | in=%d out=%d",
            elapsed,
            in_tok,
            out_tok,
        )

        choice = response.choices[0]
        text = choice.message.content or ""

        # Strip simulated prefill from start of response
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]

        return GenerationResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=self.compute_cost(in_tok, out_tok),
            model=self.model_name,
            stop_reason=choice.finish_reason or "stop",
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

        Yields
        ------
        StreamChunk

        Raises
        ------
        GenerationKilled
            If :meth:`cancel_stream` is called mid-stream.
        AdapterError
            On unrecoverable API errors.
        """
        self._reset_cancel()

        messages = self._build_messages(prompt, system, prefill)

        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            **kwargs,
        }

        accumulated = prefill or ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = "stop"

        try:
            stream = await self._with_retry(
                lambda: self._client.chat.completions.create(**call_kwargs)
            )

            async for chunk in stream:
                if self.is_cancelled:
                    raise GenerationKilled(
                        "Stream cancelled by cancel_stream()",
                        partial_output=accumulated,
                    )

                # Usage summary arrives on the last chunk
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens
                    output_tokens = chunk.usage.completion_tokens

                choices = chunk.choices
                if not choices:
                    continue

                choice = choices[0]
                delta_text = ""
                if choice.delta and choice.delta.content:
                    delta_text = choice.delta.content

                if choice.finish_reason:
                    stop_reason = choice.finish_reason

                if delta_text:
                    accumulated += delta_text
                    yield StreamChunk(
                        delta=delta_text,
                        accumulated=accumulated,
                    )

        except GenerationKilled:
            raise
        except openai.APIError as exc:
            raise self._translate_error(exc) from exc

        # Final sentinel chunk
        yield StreamChunk(
            delta="",
            accumulated=accumulated,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_final=True,
            stop_reason=stop_reason,
        )

        self._logger.debug(
            "OpenAI stream completed | in=%d out=%d stop=%s",
            input_tokens,
            output_tokens,
            stop_reason,
        )

    # ------------------------------------------------------------------
    # Structured generation convenience
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        schema_name: str = "output",
        **kwargs: Any,
    ) -> tuple[dict[str, Any], GenerationResult]:
        """
        Generate a JSON-structured response validated against *schema*.

        Parameters
        ----------
        prompt:
            User message text.
        schema:
            JSON Schema describing the expected response structure.
        system:
            Optional system instruction.
        max_tokens:
            Maximum output tokens.
        temperature:
            Sampling temperature.
        schema_name:
            Logical name for the schema.
        **kwargs:
            Additional arguments forwarded to the OpenAI API.

        Returns
        -------
        tuple[dict, GenerationResult]
            Parsed JSON dict and the full :class:`GenerationResult`.

        Raises
        ------
        AdapterError
            If the response is not valid JSON.
        """
        result = await self.generate(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=schema,
            **kwargs,
        )

        try:
            parsed = json.loads(result.text)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                f"Structured output was not valid JSON: {exc}\nRaw: {result.text[:200]}"
            ) from exc

        return parsed, result
