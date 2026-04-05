"""SQLite store test fixtures."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.store.sqlite.schema import initialize_schema


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    """File-backed SQLite database with WAL mode for realistic testing."""
    db_path = tmp_path / "forgebase_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()
