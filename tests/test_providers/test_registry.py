"""Tests for the ProviderRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.providers.base import ProviderCapability, ProviderStatus


def _make_provider(
    name: str = "test",
    status: ProviderStatus = ProviderStatus.AVAILABLE,
    capabilities: set[ProviderCapability] | None = None,
    available: bool = True,
) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.status = status
    p.capabilities = capabilities or {ProviderCapability.CHAT}
    p.is_available.return_value = available
    p.health_check = AsyncMock(return_value=status)
    return p


class TestProviderRegistry:
    def test_register_and_get(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        provider = _make_provider(name="anthropic")
        reg.register(provider)
        assert reg.get("anthropic") is provider

    def test_get_missing_returns_none(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        assert reg.get("missing") is None

    def test_list_providers(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(name="a"))
        reg.register(_make_provider(name="b"))
        assert len(reg.list_providers()) == 2

    def test_available_providers_filters(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(name="up", available=True))
        reg.register(_make_provider(name="down", available=False))
        available = reg.available_providers()
        assert len(available) == 1
        assert available[0].name == "up"

    def test_providers_with_capability(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(name="gen", capabilities={ProviderCapability.CHAT}))
        reg.register(_make_provider(name="emb", capabilities={ProviderCapability.EMBEDDINGS}))

        gen_providers = reg.providers_with_capability(ProviderCapability.CHAT)
        assert len(gen_providers) == 1
        assert gen_providers[0].name == "gen"

    def test_is_capability_available(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(capabilities={ProviderCapability.CHAT}))
        assert reg.is_capability_available(ProviderCapability.CHAT)
        assert not reg.is_capability_available(ProviderCapability.EMBEDDINGS)

    def test_summary(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(name="a", status=ProviderStatus.AVAILABLE))
        reg.register(_make_provider(name="b", status=ProviderStatus.UNAVAILABLE))
        summary = reg.summary()
        assert summary == {"a": "available", "b": "unavailable"}


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health_check_all(self) -> None:
        from hephaestus.providers import ProviderRegistry

        reg = ProviderRegistry()
        reg.register(_make_provider(name="healthy", status=ProviderStatus.AVAILABLE))
        sick = _make_provider(name="sick")
        sick.health_check = AsyncMock(side_effect=RuntimeError("down"))
        reg.register(sick)

        results = await reg.health_check_all()
        assert results["healthy"] == ProviderStatus.AVAILABLE
        assert results["sick"] == ProviderStatus.UNAVAILABLE
