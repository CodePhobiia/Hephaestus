"""Shared test fixtures for ForgeBase."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import ActorType
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def id_gen() -> DeterministicIdGenerator:
    return DeterministicIdGenerator()


@pytest.fixture
def actor() -> ActorRef:
    return ActorRef(actor_type=ActorType.SYSTEM, actor_id="test")
