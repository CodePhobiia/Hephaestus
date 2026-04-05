"""Tests for SQLite RepairBatchRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.models import RepairBatch
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.repair_batch_repo import SqliteRepairBatchRepository


@pytest.fixture
def repo(sqlite_db):
    return SqliteRepairBatchRepository(sqlite_db)


@pytest.fixture
def id_gen():
    return DeterministicIdGenerator()


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


class TestRepairBatchCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo, id_gen, sqlite_db):
        batch = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=id_gen.vault_id(),
            batch_fingerprint="batch_fp_001",
            batch_strategy="BY_PAGE",
            batch_reason="Same page findings",
            finding_ids=[id_gen.finding_id(), id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        await repo.create(batch)
        await sqlite_db.commit()

        result = await repo.get(batch.batch_id)
        assert result is not None
        assert result.batch_strategy == "BY_PAGE"
        assert len(result.finding_ids) == 2
        assert result.workbook_id is None

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo, id_gen):
        result = await repo.get(id_gen.batch_id())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_vault(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        other_vault = id_gen.vault_id()

        b1 = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=vault_id,
            batch_fingerprint="fp_1",
            batch_strategy="BY_PAGE",
            batch_reason="Batch 1",
            finding_ids=[id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        b2 = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=vault_id,
            batch_fingerprint="fp_2",
            batch_strategy="BY_CATEGORY",
            batch_reason="Batch 2",
            finding_ids=[id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        b3 = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=other_vault,
            batch_fingerprint="fp_3",
            batch_strategy="BY_PAGE",
            batch_reason="Other vault",
            finding_ids=[id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        await repo.create(b1)
        await repo.create(b2)
        await repo.create(b3)
        await sqlite_db.commit()

        results = await repo.list_by_vault(vault_id)
        assert len(results) == 2


class TestFindByFingerprint:
    @pytest.mark.asyncio
    async def test_find_existing(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        batch = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=vault_id,
            batch_fingerprint="unique_fp",
            batch_strategy="BY_PAGE",
            batch_reason="Test",
            finding_ids=[id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        await repo.create(batch)
        await sqlite_db.commit()

        result = await repo.find_by_fingerprint(vault_id, "unique_fp")
        assert result is not None
        assert result.batch_id == batch.batch_id

    @pytest.mark.asyncio
    async def test_find_nonexistent(self, repo, id_gen):
        vault_id = id_gen.vault_id()
        result = await repo.find_by_fingerprint(vault_id, "nope")
        assert result is None


class TestUpdateWorkbook:
    @pytest.mark.asyncio
    async def test_update_workbook_id(self, repo, id_gen, sqlite_db):
        vault_id = id_gen.vault_id()
        batch = RepairBatch(
            batch_id=id_gen.batch_id(),
            vault_id=vault_id,
            batch_fingerprint="fp_wb",
            batch_strategy="BY_PAGE",
            batch_reason="Needs workbook",
            finding_ids=[id_gen.finding_id()],
            policy_version="1.0.0",
            workbook_id=None,
            created_by_job_id=id_gen.job_id(),
            created_at=_now(),
        )
        await repo.create(batch)
        await sqlite_db.commit()

        wb_id = id_gen.workbook_id()
        await repo.update_workbook(batch.batch_id, wb_id)
        await sqlite_db.commit()

        result = await repo.get(batch.batch_id)
        assert result is not None
        assert result.workbook_id == wb_id
