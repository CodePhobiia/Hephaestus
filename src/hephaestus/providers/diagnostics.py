"""Provider diagnostics — startup report and availability summary."""

from __future__ import annotations

import logging
from typing import Any

from hephaestus.providers.base import ProviderStatus

logger = logging.getLogger(__name__)


def startup_report(registry: Any) -> str:
    """Generate a human-readable startup report of provider availability.

    Args:
        registry: A ProviderRegistry instance.

    Returns:
        Formatted report string.
    """
    lines = ["", "═══ Hephaestus Provider Diagnostics ═══", ""]
    providers = registry.list_providers()

    if not providers:
        lines.append("  No providers registered.")
        lines.append("")
        return "\n".join(lines)

    available_count = 0
    for provider in providers:
        status_icon = {
            ProviderStatus.AVAILABLE: "✓",
            ProviderStatus.DEGRADED: "⚠",
            ProviderStatus.UNAVAILABLE: "✗",
        }.get(provider.status, "?")

        caps = ", ".join(c.value for c in provider.capabilities)
        line = (
            f"  {status_icon} {provider.name:<20} [{provider.status.value}]  capabilities: {caps}"
        )
        lines.append(line)

        if provider.status == ProviderStatus.AVAILABLE:
            available_count += 1
        elif not provider.is_available():
            reason = provider.unavailability_reason()
            if reason:
                lines.append(f"    └─ {reason}")

    lines.append("")
    lines.append(f"  {available_count}/{len(providers)} providers available")
    lines.append("═" * 42)
    lines.append("")
    return "\n".join(lines)


def provider_health_summary(registry: Any) -> dict[str, Any]:
    """Return a JSON-serializable health summary for API endpoints."""
    providers = registry.list_providers()
    return {
        "providers": [
            {
                "name": p.name,
                "status": p.status.value,
                "capabilities": [c.value for c in p.capabilities],
                "available": p.is_available(),
                "reason": p.unavailability_reason() if not p.is_available() else None,
            }
            for p in providers
        ],
        "available_count": sum(1 for p in providers if p.is_available()),
        "total_count": len(providers),
    }


__all__ = ["provider_health_summary", "startup_report"]
