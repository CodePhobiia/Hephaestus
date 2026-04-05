"""Shared fixtures for ForgeBase web API tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.fixture
async def forgebase():
    """Create a fresh in-memory ForgeBase instance for testing."""
    fb = await create_forgebase(
        clock=FixedClock(datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)),
        id_generator=DeterministicIdGenerator(),
    )
    yield fb
    await fb.close()


@pytest.fixture
async def client(forgebase):
    """Create a test client with ForgeBase dependency overridden."""
    from web.app import app
    from web.forgebase_deps import get_forgebase

    async def _override():
        return forgebase

    app.dependency_overrides[get_forgebase] = _override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
