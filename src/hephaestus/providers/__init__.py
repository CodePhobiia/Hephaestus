"""Provider registry — discover, register, and query provider integrations."""

from __future__ import annotations

import logging
from typing import Any

from hephaestus.providers.base import BaseProvider, ProviderCapability, ProviderStatus

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Central registry for all provider integrations."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}  # name → provider instance

    def register(self, provider: Any) -> None:
        """Register a provider instance."""
        self._providers[provider.name] = provider
        logger.debug("Registered provider: %s (%s)", provider.name, provider.status.value)

    def get(self, name: str) -> Any | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[Any]:
        """Return all registered providers."""
        return list(self._providers.values())

    def available_providers(self) -> list[Any]:
        """Return only available providers."""
        return [p for p in self._providers.values() if p.is_available()]

    def providers_with_capability(self, capability: ProviderCapability) -> list[Any]:
        """Return providers that support a given capability."""
        return [
            p for p in self._providers.values()
            if capability in p.capabilities and p.is_available()
        ]

    def is_capability_available(self, capability: ProviderCapability) -> bool:
        """Check if any provider supports a capability."""
        return len(self.providers_with_capability(capability)) > 0

    async def health_check_all(self) -> dict[str, ProviderStatus]:
        """Run health checks on all providers and return status map."""
        results: dict[str, ProviderStatus] = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception as exc:
                logger.warning("Health check failed for %s: %s", name, exc)
                results[name] = ProviderStatus.UNAVAILABLE
        return results

    def summary(self) -> dict[str, str]:
        """Return a name→status summary dict."""
        return {name: p.status.value for name, p in self._providers.items()}


def build_default_registry(
    *,
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> ProviderRegistry:
    """Create a registry pre-populated with the standard providers."""
    from hephaestus.providers.anthropic import AnthropicProvider
    from hephaestus.providers.openai_provider import OpenAIProvider
    from hephaestus.providers.embeddings import EmbeddingsProvider

    registry = ProviderRegistry()
    registry.register(AnthropicProvider(api_key=anthropic_api_key))
    registry.register(OpenAIProvider(api_key=openai_api_key))
    registry.register(EmbeddingsProvider(model_name=embedding_model))
    return registry


__all__ = [
    "ProviderRegistry",
    "build_default_registry",
]
