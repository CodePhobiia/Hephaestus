"""In-memory post-commit fanout for low-latency event notifications.

This is a best-effort, non-authoritative delivery mechanism.  The durable
``EventDispatcher`` is the source of truth — the fanout is an optimization
for subscribers that benefit from immediate notification.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from hephaestus.forgebase.domain.models import DomainEvent

logger = logging.getLogger(__name__)


class PostCommitFanout:
    """Best-effort in-memory event broadcaster.

    Subscribers are invoked concurrently after a UoW commit.  A failing
    subscriber is logged but never prevents other subscribers from being
    notified, and never raises to the caller.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[DomainEvent], Awaitable[None]]] = []

    def subscribe(
        self, callback: Callable[[DomainEvent], Awaitable[None]]
    ) -> None:
        """Add a subscriber callback."""
        self._subscribers.append(callback)

    async def notify(self, events: list[DomainEvent]) -> None:
        """Deliver events to all subscribers, swallowing individual failures."""
        for event in events:
            for subscriber in self._subscribers:
                try:
                    await subscriber(event)
                except Exception:
                    logger.exception(
                        "Fanout subscriber %r failed for event %s",
                        subscriber,
                        event.event_id,
                    )
