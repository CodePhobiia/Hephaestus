"""Tests for SQLite claim support and claim derivation repositories."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.models import ClaimDerivation, ClaimSupport
from hephaestus.forgebase.store.sqlite.claim_derivation_repo import SqliteClaimDerivationRepository
from hephaestus.forgebase.store.sqlite.claim_support_repo import SqliteClaimSupportRepository


@pytest.mark.asyncio
class TestSqliteClaimSupportRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimSupportRepository(sqlite_db)
        support_id = id_gen.support_id()
        claim_id = id_gen.claim_id()
        source_id = id_gen.source_id()

        support = ClaimSupport(
            support_id=support_id,
            claim_id=claim_id,
            source_id=source_id,
            source_segment="paragraph 3",
            strength=0.85,
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(support)
        await sqlite_db.commit()

        got = await repo.get(support_id)
        assert got is not None
        assert got.support_id == support_id
        assert got.claim_id == claim_id
        assert got.source_id == source_id
        assert got.source_segment == "paragraph 3"
        assert got.strength == 0.85

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteClaimSupportRepository(sqlite_db)
        assert await repo.get(id_gen.support_id()) is None

    async def test_delete(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimSupportRepository(sqlite_db)
        support_id = id_gen.support_id()

        support = ClaimSupport(
            support_id=support_id,
            claim_id=id_gen.claim_id(),
            source_id=id_gen.source_id(),
            source_segment=None,
            strength=0.7,
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(support)
        await sqlite_db.commit()

        await repo.delete(support_id)
        await sqlite_db.commit()

        assert await repo.get(support_id) is None

    async def test_list_by_claim(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimSupportRepository(sqlite_db)
        claim_a = id_gen.claim_id()
        claim_b = id_gen.claim_id()

        # 2 supports for claim_a
        for _ in range(2):
            s = ClaimSupport(
                support_id=id_gen.support_id(),
                claim_id=claim_a,
                source_id=id_gen.source_id(),
                source_segment=None,
                strength=0.8,
                created_at=clock.now(),
                created_by=actor,
            )
            await repo.create(s)

        # 1 support for claim_b
        s = ClaimSupport(
            support_id=id_gen.support_id(),
            claim_id=claim_b,
            source_id=id_gen.source_id(),
            source_segment=None,
            strength=0.6,
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(s)
        await sqlite_db.commit()

        assert len(await repo.list_by_claim(claim_a)) == 2
        assert len(await repo.list_by_claim(claim_b)) == 1

    async def test_null_source_segment(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimSupportRepository(sqlite_db)
        support_id = id_gen.support_id()

        support = ClaimSupport(
            support_id=support_id,
            claim_id=id_gen.claim_id(),
            source_id=id_gen.source_id(),
            source_segment=None,
            strength=0.5,
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(support)
        await sqlite_db.commit()

        got = await repo.get(support_id)
        assert got is not None
        assert got.source_segment is None


@pytest.mark.asyncio
class TestSqliteClaimDerivationRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimDerivationRepository(sqlite_db)
        derivation_id = id_gen.derivation_id()
        claim_id = id_gen.claim_id()
        parent_claim_id = id_gen.claim_id()

        derivation = ClaimDerivation(
            derivation_id=derivation_id,
            claim_id=claim_id,
            parent_claim_id=parent_claim_id,
            relationship="implies",
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(derivation)
        await sqlite_db.commit()

        got = await repo.get(derivation_id)
        assert got is not None
        assert got.derivation_id == derivation_id
        assert got.claim_id == claim_id
        assert got.parent_claim_id == parent_claim_id
        assert got.relationship == "implies"

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteClaimDerivationRepository(sqlite_db)
        assert await repo.get(id_gen.derivation_id()) is None

    async def test_delete(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimDerivationRepository(sqlite_db)
        derivation_id = id_gen.derivation_id()

        derivation = ClaimDerivation(
            derivation_id=derivation_id,
            claim_id=id_gen.claim_id(),
            parent_claim_id=id_gen.claim_id(),
            relationship="supports",
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(derivation)
        await sqlite_db.commit()

        await repo.delete(derivation_id)
        await sqlite_db.commit()

        assert await repo.get(derivation_id) is None

    async def test_list_by_claim(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimDerivationRepository(sqlite_db)
        claim_a = id_gen.claim_id()
        claim_b = id_gen.claim_id()

        # 2 derivations for claim_a
        for _ in range(2):
            d = ClaimDerivation(
                derivation_id=id_gen.derivation_id(),
                claim_id=claim_a,
                parent_claim_id=id_gen.claim_id(),
                relationship="implies",
                created_at=clock.now(),
                created_by=actor,
            )
            await repo.create(d)

        # 1 derivation for claim_b
        d = ClaimDerivation(
            derivation_id=id_gen.derivation_id(),
            claim_id=claim_b,
            parent_claim_id=id_gen.claim_id(),
            relationship="contradicts",
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create(d)
        await sqlite_db.commit()

        assert len(await repo.list_by_claim(claim_a)) == 2
        assert len(await repo.list_by_claim(claim_b)) == 1
