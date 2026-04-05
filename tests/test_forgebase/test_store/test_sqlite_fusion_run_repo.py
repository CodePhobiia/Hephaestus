"""Tests for SQLite FusionRunRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import FusionMode
from hephaestus.forgebase.domain.models import FusionRun
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.fusion_run_repo import SqliteFusionRunRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteFusionRunRepository(sqlite_db)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


def _make_run(id_gen, **overrides) -> FusionRun:
    defaults = dict(
        fusion_run_id=id_gen.generate("frun"),
        vault_ids=[id_gen.vault_id(), id_gen.vault_id()],
        problem=None,
        fusion_mode=FusionMode.STRICT,
        status="pending",
        bridge_count=0,
        transfer_count=0,
        manifest_id=None,
        policy_version="1.0.0",
        created_at=_now(),
        completed_at=None,
    )
    defaults.update(overrides)
    return FusionRun(**defaults)


class TestFusionRunCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo, id_gen, sqlite_db):
        run = _make_run(id_gen)
        await repo.create(run)
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.fusion_run_id == run.fusion_run_id
        assert result.status == "pending"
        assert result.fusion_mode == FusionMode.STRICT
        assert len(result.vault_ids) == 2
        assert result.problem is None
        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get(id_gen.generate("frun"))
        assert result is None

    @pytest.mark.asyncio
    async def test_create_with_problem(self, repo, id_gen, sqlite_db):
        run = _make_run(id_gen, problem="Improve battery longevity")
        await repo.create(run)
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.problem == "Improve battery longevity"

    @pytest.mark.asyncio
    async def test_create_completed_run(self, repo, id_gen, sqlite_db):
        manifest_id = id_gen.generate("mfst")
        run = _make_run(
            id_gen,
            status="completed",
            bridge_count=5,
            transfer_count=3,
            manifest_id=manifest_id,
            completed_at=_now(),
        )
        await repo.create(run)
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.status == "completed"
        assert result.bridge_count == 5
        assert result.transfer_count == 3
        assert result.manifest_id == manifest_id
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_status(self, repo, id_gen, sqlite_db):
        run = _make_run(id_gen)
        await repo.create(run)
        await sqlite_db.commit()

        manifest_id = id_gen.generate("mfst")
        await repo.update_status(
            run.fusion_run_id,
            status="completed",
            bridge_count=7,
            transfer_count=4,
            manifest_id=manifest_id,
            completed_at=_now().isoformat(),
        )
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.status == "completed"
        assert result.bridge_count == 7
        assert result.transfer_count == 4
        assert result.manifest_id == manifest_id

    @pytest.mark.asyncio
    async def test_update_status_partial(self, repo, id_gen, sqlite_db):
        run = _make_run(id_gen)
        await repo.create(run)
        await sqlite_db.commit()

        await repo.update_status(run.fusion_run_id, status="running")
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.status == "running"
        assert result.bridge_count == 0  # unchanged

    @pytest.mark.asyncio
    async def test_list_by_vaults(self, repo, id_gen, sqlite_db):
        v1 = id_gen.vault_id()
        v2 = id_gen.vault_id()
        v3 = id_gen.vault_id()

        r1 = _make_run(id_gen, vault_ids=[v1, v2])
        r2 = _make_run(id_gen, vault_ids=[v1, v2])
        r3 = _make_run(id_gen, vault_ids=[v1, v3])

        await repo.create(r1)
        await repo.create(r2)
        await repo.create(r3)
        await sqlite_db.commit()

        results = await repo.list_by_vaults([v1, v2])
        assert len(results) == 2

        results = await repo.list_by_vaults([v1, v3])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_by_problem(self, repo, id_gen, sqlite_db):
        r1 = _make_run(id_gen, problem="battery longevity")
        r2 = _make_run(id_gen, problem="battery longevity")
        r3 = _make_run(id_gen, problem="logistics optimization")
        r4 = _make_run(id_gen)  # no problem

        await repo.create(r1)
        await repo.create(r2)
        await repo.create(r3)
        await repo.create(r4)
        await sqlite_db.commit()

        results = await repo.list_by_problem("battery longevity")
        assert len(results) == 2

        results = await repo.list_by_problem("logistics optimization")
        assert len(results) == 1

        results = await repo.list_by_problem("nonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fusion_mode_exploratory(self, repo, id_gen, sqlite_db):
        run = _make_run(id_gen, fusion_mode=FusionMode.EXPLORATORY)
        await repo.create(run)
        await sqlite_db.commit()

        result = await repo.get(run.fusion_run_id)
        assert result is not None
        assert result.fusion_mode == FusionMode.EXPLORATORY
