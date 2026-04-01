"""
OpenRouter unified adapter for DeepForge.

Routes both Anthropic and OpenAI models through OpenRouter's API using the
OpenAI-compatible chat completions endpoint.  This allows Hephaestus to run
its full pipeline with a single ``OPENROUTER_API_KEY`` when direct provider
keys are unavailable.

Key features:
- Automatic model name mapping (``claude-sonnet-4-6`` → ``anthropic/claude-sonnet-4-6``)
- Supports assistant prefill (OpenRouter passes it through to Anthropic)
- Same streaming/retry behaviour as the OpenAI adapter (since it extends it)
- Cost tracking uses OpenRouter pricing
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from hephaestus.deepforge.adapters.base import GenerationResult, ModelCapability, ModelConfig, StreamChunk
from hephaestus.deepforge.adapters.openai import OpenAIAdapter

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Model name mapping: internal name → OpenRouter model ID
# ---------------------------------------------------------------------------

OPENROUTER_MODEL_MAP: dict[str, str] = {
    # Anthropic
    "claude-opus-4-6": "anthropic/claude-opus-4-6",
    "claude-opus-4-5": "anthropic/claude-opus-4-5-20250514",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4-6",
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4-5-20250514",
    "claude-haiku-3-5": "anthropic/claude-3-5-haiku-20241022",
    # OpenAI
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "o3": "openai/o3",
    "o4-mini": "openai/o4-mini",
}

# ---------------------------------------------------------------------------
# Model configs with OpenRouter pricing (approximate)
# ---------------------------------------------------------------------------

OPENROUTER_MODELS: dict[str, ModelConfig] = {
    "claude-opus-4-6": ModelConfig(
        name="anthropic/claude-opus-4-6",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=15.0,
        output_cost_per_million=75.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
        },
    ),
    "claude-sonnet-4-6": ModelConfig(
        name="anthropic/claude-sonnet-4-6",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
        },
    ),
    "claude-sonnet-4-5": ModelConfig(
        name="anthropic/claude-sonnet-4-5-20250514",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
        },
    ),
    "claude-haiku-3-5": ModelConfig(
        name="anthropic/claude-3-5-haiku-20241022",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=8192,
        input_cost_per_million=0.8,
        output_cost_per_million=4.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
        },
    ),
    "gpt-4o": ModelConfig(
        name="openai/gpt-4o",
        provider="openrouter",
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
        name="openai/gpt-4o-mini",
        provider="openrouter",
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
        name="openai/o3",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=100_000,
        input_cost_per_million=10.0,
        output_cost_per_million=40.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
        },
    ),
    "o4-mini": ModelConfig(
        name="openai/o4-mini",
        provider="openrouter",
        context_window=200_000,
        max_output_tokens=100_000,
        input_cost_per_million=1.10,
        output_cost_per_million=4.40,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.VISION,
        },
    ),
}


class OpenRouterAdapter(OpenAIAdapter):
    """
    Adapter that routes any supported model through OpenRouter.

    Extends :class:`OpenAIAdapter` with OpenRouter's base URL, model name
    remapping, provider pinning for Anthropic models (so prefill works),
    and ``HTTP-Referer`` / ``X-Title`` headers for attribution.

    Parameters
    ----------
    model:
        Internal model name (e.g. ``"claude-sonnet-4-6"`` or ``"gpt-4o"``).
        Automatically mapped to the OpenRouter model ID.
    api_key:
        OpenRouter API key.  Falls back to ``OPENROUTER_API_KEY`` env var.
    timeout:
        Request timeout in seconds.
    max_retries:
        Retry attempts on transient errors.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        import os

        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")

        # If the model name is already an OpenRouter path (provider/model), use as-is
        if "/" in model:
            or_model_id = model
        else:
            or_model_id = OPENROUTER_MODEL_MAP.get(model, model)

        # Track whether this is an Anthropic model (for provider pinning)
        self._is_anthropic = or_model_id.startswith("anthropic/")

        # Use our pre-built config if available, else construct a generic one
        config = OPENROUTER_MODELS.get(model)
        if config is None:
            config = ModelConfig(
                name=or_model_id,
                provider="openrouter",
                context_window=200_000,
                max_output_tokens=16_000,
                input_cost_per_million=0.0,
                output_cost_per_million=0.0,
                capabilities={ModelCapability.STREAMING, ModelCapability.PREFILL},
            )

        super().__init__(
            model=config,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/CodePhobiia/hephaestus",
                "X-Title": "Hephaestus Invention Engine",
            },
        )

        logger.info(
            "OpenRouter adapter: %s → %s (via %s, pin_anthropic=%s)",
            model,
            or_model_id,
            OPENROUTER_BASE_URL,
            self._is_anthropic,
        )

    def _provider_routing_kwargs(self) -> dict[str, Any]:
        """
        Build extra_body kwargs to pin Anthropic models to the Anthropic
        backend on OpenRouter.  This ensures assistant prefill (the core
        DeepForge mechanism) is supported — Google/Azure backends reject it.
        """
        if not self._is_anthropic:
            return {}
        return {
            "extra_body": {
                "provider": {
                    "order": ["Anthropic"],
                    "allow_fallbacks": False,
                },
            }
        }

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
        """Override to inject Anthropic provider pinning."""
        merged = {**self._provider_routing_kwargs(), **kwargs}
        return await super().generate(
            prompt,
            system=system,
            prefill=prefill,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            **merged,
        )

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
        """Override to inject Anthropic provider pinning."""
        merged = {**self._provider_routing_kwargs(), **kwargs}
        async for chunk in super().generate_stream(
            prompt,
            system=system,
            prefill=prefill,
            max_tokens=max_tokens,
            temperature=temperature,
            **merged,
        ):
            yield chunk
