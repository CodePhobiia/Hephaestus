"""Consumer registry for durable event delivery."""
from __future__ import annotations

from abc import ABC, abstractmethod

from hephaestus.forgebase.domain.models import DomainEvent


class EventConsumer(ABC):
    """Base class for all event consumers.

    Each consumer has a unique name used to track delivery state in
    ``fb_event_deliveries``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable, unique consumer identifier (used as PK in delivery table)."""
        ...

    @abstractmethod
    async def handle(self, event: DomainEvent) -> None:
        """Process a single domain event.

        Raise on failure — the dispatcher will record the error and schedule
        a retry with exponential backoff.
        """
        ...


class ConsumerRegistry:
    """Thread-safe registry of named event consumers."""

    def __init__(self) -> None:
        self._consumers: dict[str, EventConsumer] = {}

    def register(self, consumer: EventConsumer) -> None:
        """Register a consumer. Raises ``ValueError`` on duplicate name."""
        if consumer.name in self._consumers:
            raise ValueError(
                f"Consumer already registered: {consumer.name!r}"
            )
        self._consumers[consumer.name] = consumer

    def get(self, name: str) -> EventConsumer | None:
        """Look up a consumer by name. Returns ``None`` if not found."""
        return self._consumers.get(name)

    def all_names(self) -> list[str]:
        """Return sorted list of all registered consumer names."""
        return sorted(self._consumers.keys())
