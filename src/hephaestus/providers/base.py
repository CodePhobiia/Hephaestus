"""Base provider protocol and shared types."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ProviderStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ProviderCapability(str, Enum):
    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    RESEARCH = "research"
    CODE = "code"


@runtime_checkable
class BaseProvider(Protocol):
    """Protocol that all provider implementations must satisfy."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> list[ProviderCapability]: ...

    @property
    def status(self) -> ProviderStatus: ...

    def is_available(self) -> bool: ...

    def unavailability_reason(self) -> str: ...

    async def health_check(self) -> ProviderStatus: ...


__all__ = [
    "BaseProvider",
    "ProviderCapability",
    "ProviderStatus",
]
