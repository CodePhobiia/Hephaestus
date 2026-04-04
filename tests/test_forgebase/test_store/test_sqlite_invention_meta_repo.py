"""Tests for SQLite InventionPageMeta repository."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import InventionEpistemicState
from hephaestus.forgebase.domain.models import InventionPageMeta
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.store.sqlite.invention_meta_repo import (
    SqliteInventionPageMetaRepository,
)


def _make_meta(
    id_gen,
    clock,
    *,
    vault_id: EntityId | None = None,
    state: InventionEpistemicState = InventionEpistemicState.PROPOSED,
    **overrides,
) -> InventionPageMeta:
    now = clock.now()
    defaults = dict(
        page_id=id_gen.page_id(),
        vault_id=vault_id or id_gen.vault_id(),
        invention_state=state,
        run_id="genesis-001",
        run_type="genesis",
        models_used=["claude-sonnet-4-5"],
        novelty_score=None,
        fidelity_score=None,
        domain_distance=None,
        source_domain=None,
        target_domain=None,
        pantheon_verdict=None,
        pantheon_outcome_tier=None,
        pantheon_consensus=None,
        objection_count_open=0,
        objection_count_resolved=0,
        total_cost_usd=0.0,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return InventionPageMeta(**defaults)


@pytest.mark.asyncio
class TestSqliteInventionPageMetaRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)

        await repo.create(meta)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.page_id == meta.page_id
        assert got.vault_id == meta.vault_id
        assert got.invention_state == InventionEpistemicState.PROPOSED
        assert got.run_id == "genesis-001"
        assert got.run_type == "genesis"
        assert got.models_used == ["claude-sonnet-4-5"]
        assert got.novelty_score is None
        assert got.fidelity_score is None
        assert got.domain_distance is None
        assert got.source_domain is None
        assert got.target_domain is None
        assert got.pantheon_verdict is None
        assert got.pantheon_outcome_tier is None
        assert got.pantheon_consensus is None
        assert got.objection_count_open == 0
        assert got.objection_count_resolved == 0
        assert got.total_cost_usd == 0.0
        assert got.created_at == meta.created_at
        assert got.updated_at == meta.updated_at

    async def test_create_with_all_fields(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(
            id_gen,
            clock,
            novelty_score=0.87,
            fidelity_score=0.91,
            domain_distance=0.65,
            source_domain="biology",
            target_domain="networking",
            pantheon_verdict="unanimous_consensus",
            pantheon_outcome_tier="high",
            pantheon_consensus=True,
            objection_count_open=2,
            objection_count_resolved=5,
            total_cost_usd=1.42,
            models_used=["claude-sonnet-4-5", "claude-haiku-3-5"],
        )

        await repo.create(meta)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.novelty_score == 0.87
        assert got.fidelity_score == 0.91
        assert got.domain_distance == 0.65
        assert got.source_domain == "biology"
        assert got.target_domain == "networking"
        assert got.pantheon_verdict == "unanimous_consensus"
        assert got.pantheon_outcome_tier == "high"
        assert got.pantheon_consensus is True
        assert got.objection_count_open == 2
        assert got.objection_count_resolved == 5
        assert got.total_cost_usd == 1.42
        assert got.models_used == ["claude-sonnet-4-5", "claude-haiku-3-5"]

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        assert await repo.get(id_gen.page_id()) is None

    async def test_update_state(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        await repo.update_state(meta.page_id, InventionEpistemicState.REVIEWED)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.invention_state == InventionEpistemicState.REVIEWED

    async def test_update_state_to_verified(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        await repo.update_state(meta.page_id, InventionEpistemicState.VERIFIED)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.invention_state == InventionEpistemicState.VERIFIED

    async def test_update_state_to_rejected(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        await repo.update_state(meta.page_id, InventionEpistemicState.REJECTED)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.invention_state == InventionEpistemicState.REJECTED

    async def test_update_pantheon(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        await repo.update_pantheon(
            meta.page_id,
            verdict="unanimous_consensus",
            outcome_tier="high",
            consensus=True,
            objection_count_open=1,
            objection_count_resolved=3,
        )
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.pantheon_verdict == "unanimous_consensus"
        assert got.pantheon_outcome_tier == "high"
        assert got.pantheon_consensus is True
        assert got.objection_count_open == 1
        assert got.objection_count_resolved == 3

    async def test_update_pantheon_with_no_consensus(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        await repo.update_pantheon(
            meta.page_id,
            verdict="fail_closed",
            outcome_tier="rejected",
            consensus=False,
            objection_count_open=5,
            objection_count_resolved=0,
        )
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.pantheon_verdict == "fail_closed"
        assert got.pantheon_consensus is False

    async def test_list_by_vault(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        meta1 = _make_meta(id_gen, clock, vault_id=vault_id)
        meta2 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.REVIEWED,
        )
        meta3 = _make_meta(id_gen, clock)  # different vault

        await repo.create(meta1)
        await repo.create(meta2)
        await repo.create(meta3)
        await sqlite_db.commit()

        results = await repo.list_by_vault(vault_id)
        assert len(results) == 2
        page_ids = {m.page_id for m in results}
        assert meta1.page_id in page_ids
        assert meta2.page_id in page_ids

    async def test_list_by_vault_with_state_filter(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        meta1 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.PROPOSED,
        )
        meta2 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.REVIEWED,
        )

        await repo.create(meta1)
        await repo.create(meta2)
        await sqlite_db.commit()

        results = await repo.list_by_vault(
            vault_id, state=InventionEpistemicState.PROPOSED
        )
        assert len(results) == 1
        assert results[0].page_id == meta1.page_id

    async def test_list_by_vault_empty(self, sqlite_db, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        results = await repo.list_by_vault(id_gen.vault_id())
        assert results == []

    async def test_list_by_state(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        meta1 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.VERIFIED,
        )
        meta2 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.VERIFIED,
        )
        meta3 = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.PROPOSED,
        )

        await repo.create(meta1)
        await repo.create(meta2)
        await repo.create(meta3)
        await sqlite_db.commit()

        results = await repo.list_by_state(
            vault_id, InventionEpistemicState.VERIFIED
        )
        assert len(results) == 2
        page_ids = {m.page_id for m in results}
        assert meta1.page_id in page_ids
        assert meta2.page_id in page_ids

    async def test_list_by_state_empty(self, sqlite_db, clock, id_gen):
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        meta = _make_meta(
            id_gen,
            clock,
            vault_id=vault_id,
            state=InventionEpistemicState.PROPOSED,
        )
        await repo.create(meta)
        await sqlite_db.commit()

        results = await repo.list_by_state(
            vault_id, InventionEpistemicState.VERIFIED
        )
        assert results == []

    async def test_consensus_none_roundtrip(self, sqlite_db, clock, id_gen):
        """Verify that pantheon_consensus=None survives the roundtrip."""
        repo = SqliteInventionPageMetaRepository(sqlite_db)
        meta = _make_meta(id_gen, clock)
        await repo.create(meta)
        await sqlite_db.commit()

        got = await repo.get(meta.page_id)
        assert got is not None
        assert got.pantheon_consensus is None
