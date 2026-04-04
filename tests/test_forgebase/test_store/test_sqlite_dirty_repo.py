"""Tests for SQLite dirty marker repository."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.domain.models import SynthesisDirtyMarker
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.store.sqlite.dirty_marker_repo import SqliteDirtyMarkerRepository


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


def _later() -> datetime:
    return datetime(2026, 4, 3, 13, 0, 0, tzinfo=UTC)


def _marker(
    id_gen,
    vault_id: EntityId,
    *,
    target_kind: DirtyTargetKind = DirtyTargetKind.CONCEPT,
    target_key: str = "solid electrolyte interphase",
    workbook_id: EntityId | None = None,
    times_dirtied: int = 1,
    created_at: datetime | None = None,
) -> SynthesisDirtyMarker:
    t = created_at or _now()
    return SynthesisDirtyMarker(
        marker_id=id_gen.generate("dirty"),
        vault_id=vault_id,
        workbook_id=workbook_id,
        target_kind=target_kind,
        target_key=target_key,
        first_dirtied_at=t,
        last_dirtied_at=t,
        times_dirtied=times_dirtied,
        last_dirtied_by_source=id_gen.generate("source"),
        last_dirtied_by_job=id_gen.generate("job"),
        consumed_by_job=None,
        consumed_at=None,
    )


@pytest.mark.asyncio
class TestSqliteDirtyMarkerRepository:
    async def test_upsert_new(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        m = _marker(id_gen, vault_id)

        await repo.upsert(m)
        await sqlite_db.commit()

        got = await repo.get(m.marker_id)
        assert got is not None
        assert got.target_kind == DirtyTargetKind.CONCEPT
        assert got.target_key == "solid electrolyte interphase"
        assert got.times_dirtied == 1
        assert got.consumed_by_job is None

    async def test_upsert_existing_preserves_first_dirtied_at(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m1 = _marker(id_gen, vault_id, target_key="sei", created_at=_now())
        await repo.upsert(m1)
        await sqlite_db.commit()

        # Upsert again with same target — should increment times_dirtied and preserve first_dirtied_at
        m2 = _marker(id_gen, vault_id, target_key="sei", created_at=_later())
        await repo.upsert(m2)
        await sqlite_db.commit()

        # The original marker should have been updated
        got = await repo.find_by_target(vault_id, DirtyTargetKind.CONCEPT, "sei")
        assert got is not None
        assert got.times_dirtied == 2
        assert got.first_dirtied_at == _now()  # preserved
        assert got.last_dirtied_at == _later()  # updated
        assert got.marker_id == m1.marker_id  # original marker_id preserved

    async def test_list_unconsumed(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m1 = _marker(id_gen, vault_id, target_key="a")
        m2 = _marker(id_gen, vault_id, target_key="b")
        m3 = _marker(id_gen, vault_id, target_key="c")

        for m in [m1, m2, m3]:
            await repo.upsert(m)
        await sqlite_db.commit()

        # Consume one
        job_id = id_gen.generate("job")
        await repo.consume(m2.marker_id, job_id)
        await sqlite_db.commit()

        unconsumed = await repo.list_unconsumed(vault_id)
        assert len(unconsumed) == 2
        ids = {m.marker_id for m in unconsumed}
        assert m1.marker_id in ids
        assert m3.marker_id in ids

    async def test_count_unconsumed(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m1 = _marker(id_gen, vault_id, target_key="a")
        m2 = _marker(id_gen, vault_id, target_key="b")

        await repo.upsert(m1)
        await repo.upsert(m2)
        await sqlite_db.commit()

        assert await repo.count_unconsumed(vault_id) == 2

        await repo.consume(m1.marker_id, id_gen.generate("job"))
        await sqlite_db.commit()

        assert await repo.count_unconsumed(vault_id) == 1

    async def test_find_by_target(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m = _marker(id_gen, vault_id, target_kind=DirtyTargetKind.MECHANISM, target_key="photosynthesis")
        await repo.upsert(m)
        await sqlite_db.commit()

        got = await repo.find_by_target(vault_id, DirtyTargetKind.MECHANISM, "photosynthesis")
        assert got is not None
        assert got.marker_id == m.marker_id

        # Wrong kind
        assert await repo.find_by_target(vault_id, DirtyTargetKind.CONCEPT, "photosynthesis") is None

    async def test_consume(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        m = _marker(id_gen, vault_id)

        await repo.upsert(m)
        await sqlite_db.commit()

        job_id = id_gen.generate("job")
        await repo.consume(m.marker_id, job_id)
        await sqlite_db.commit()

        got = await repo.get(m.marker_id)
        assert got is not None
        assert got.consumed_by_job == job_id
        assert got.consumed_at is not None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        assert await repo.get(id_gen.generate("dirty")) is None

    async def test_upsert_resets_consumed_state(self, sqlite_db, id_gen):
        """When a marker is re-dirtied after consumption, it should become unconsumed again."""
        repo = SqliteDirtyMarkerRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        m1 = _marker(id_gen, vault_id, target_key="re-dirty")
        await repo.upsert(m1)
        await sqlite_db.commit()

        # Consume it
        job_id = id_gen.generate("job")
        await repo.consume(m1.marker_id, job_id)
        await sqlite_db.commit()

        got = await repo.get(m1.marker_id)
        assert got is not None
        assert got.consumed_by_job is not None

        # Re-dirty
        m2 = _marker(id_gen, vault_id, target_key="re-dirty", created_at=_later())
        await repo.upsert(m2)
        await sqlite_db.commit()

        got = await repo.find_by_target(vault_id, DirtyTargetKind.CONCEPT, "re-dirty")
        assert got is not None
        assert got.consumed_by_job is None
        assert got.consumed_at is None
        assert got.times_dirtied == 2
