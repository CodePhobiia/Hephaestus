"""Shared fixtures for integration bridge tests.

Uses a real SQLite backend — no mocks — so the full service stack is exercised.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService
from hephaestus.forgebase.service.vault_service import VaultService
from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
from hephaestus.forgebase.store.sqlite.schema import initialize_schema
from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    """File-backed SQLite database with schema initialised."""
    db_path = tmp_path / "forgebase_integration_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()


@pytest.fixture
def content_store() -> InMemoryContentStore:
    return InMemoryContentStore()


@pytest.fixture
def uow_factory(sqlite_db, content_store, clock, id_gen):
    """Factory that returns a fresh SqliteUnitOfWork each time."""

    def _factory() -> SqliteUnitOfWork:
        return SqliteUnitOfWork(
            db=sqlite_db,
            content=content_store,
            clock=clock,
            id_generator=id_gen,
        )

    return _factory


@pytest.fixture
def run_integration_service(uow_factory, actor) -> RunIntegrationService:
    return RunIntegrationService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
def ingest_service(uow_factory, actor) -> IngestService:
    return IngestService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
def vault_service(uow_factory, actor) -> VaultService:
    return VaultService(uow_factory=uow_factory, default_actor=actor)


@pytest.fixture
async def vault(vault_service):
    """Pre-created vault for tests that need one."""
    return await vault_service.create_vault(name="IntegrationTestVault")
