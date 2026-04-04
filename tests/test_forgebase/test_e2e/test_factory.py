"""Test ForgeBase factory bootstrap."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import ForgeBase, create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.mark.asyncio
async def test_create_forgebase_default():
    """Factory produces a ForgeBase with all services wired."""
    fb = await create_forgebase()
    assert fb.vaults is not None
    assert fb.ingest is not None
    assert fb.pages is not None
    assert fb.claims is not None
    assert fb.links is not None
    assert fb.branches is not None
    assert fb.merge is not None
    assert fb.compile is not None
    assert fb.lint is not None
    assert fb.run_integration is not None
    assert fb.bridge is not None
    assert fb.source_compiler is not None
    assert fb.vault_synthesizer is not None
    assert fb.normalization is not None
    assert fb.dispatcher is not None
    assert fb.fanout is not None
    assert fb.uow_factory is not None
    # Linting components
    assert fb.lint_engine is not None
    assert fb.research_job is not None
    assert fb.repair_job is not None
    assert fb.verification_job is not None
    await fb.close()


@pytest.mark.asyncio
async def test_create_forgebase_with_test_fixtures():
    """Factory works with deterministic clock and ID generator."""
    fb = await create_forgebase(
        clock=FixedClock(datetime(2026, 4, 3, tzinfo=UTC)),
        id_generator=DeterministicIdGenerator(),
    )
    vault = await fb.vaults.create_vault(name="test-vault", description="A test")
    assert vault.vault_id.prefix == "vault"
    assert vault.name == "test-vault"
    await fb.close()


@pytest.mark.asyncio
async def test_forgebase_is_instance():
    """create_forgebase returns a ForgeBase instance."""
    fb = await create_forgebase()
    assert isinstance(fb, ForgeBase)
    await fb.close()
