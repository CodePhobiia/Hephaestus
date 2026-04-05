"""Anthropic provider with lazy SDK loading and health tracking."""

from __future__ import annotations

import logging
import os
from typing import Any

from hephaestus.providers.base import ProviderCapability, ProviderStatus

logger = logging.getLogger(__name__)

_sdk_module: Any = None
_sdk_import_error: str | None = None


def _lazy_import() -> Any:
    """Lazily import the anthropic SDK."""
    global _sdk_module, _sdk_import_error
    if _sdk_module is not None:
        return _sdk_module
    if _sdk_import_error is not None:
        return None
    try:
        import anthropic

        _sdk_module = anthropic
        return _sdk_module
    except ImportError as exc:
        _sdk_import_error = str(exc)
        logger.debug("Anthropic SDK not available: %s", exc)
        return None


class AnthropicProvider:
    """Anthropic Claude provider with lazy SDK loading."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._status = ProviderStatus.UNAVAILABLE
        self._client: Any = None
        self._check_availability()

    def _check_availability(self) -> None:
        sdk = _lazy_import()
        if sdk is None:
            self._status = ProviderStatus.UNAVAILABLE
            return
        if not self._api_key:
            self._status = ProviderStatus.UNAVAILABLE
            return
        self._status = ProviderStatus.AVAILABLE

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def capabilities(self) -> list[ProviderCapability]:
        return [ProviderCapability.CHAT, ProviderCapability.CODE]

    @property
    def status(self) -> ProviderStatus:
        return self._status

    def is_available(self) -> bool:
        return self._status == ProviderStatus.AVAILABLE

    def unavailability_reason(self) -> str:
        if _sdk_import_error:
            return f"Anthropic SDK not installed: {_sdk_import_error}"
        if not self._api_key:
            return "ANTHROPIC_API_KEY not configured"
        return ""

    def get_client(self) -> Any:
        """Return a configured Anthropic client, or raise if unavailable."""
        if not self.is_available():
            raise RuntimeError(f"Anthropic provider unavailable: {self.unavailability_reason()}")
        sdk = _lazy_import()
        if self._client is None:
            self._client = sdk.Anthropic(api_key=self._api_key)
        return self._client

    def get_async_client(self) -> Any:
        """Return a configured async Anthropic client."""
        if not self.is_available():
            raise RuntimeError(f"Anthropic provider unavailable: {self.unavailability_reason()}")
        sdk = _lazy_import()
        return sdk.AsyncAnthropic(api_key=self._api_key)

    async def health_check(self) -> ProviderStatus:
        if not self.is_available():
            return ProviderStatus.UNAVAILABLE
        try:
            client = self.get_async_client()
            # Minimal API call to verify connectivity
            await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            self._status = ProviderStatus.AVAILABLE
        except Exception as exc:
            logger.warning("Anthropic health check failed: %s", exc)
            self._status = ProviderStatus.DEGRADED
        return self._status


__all__ = ["AnthropicProvider"]
