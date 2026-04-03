"""Tests for SQLite claim repository."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ClaimStatus, SupportType
from hephaestus.forgebase.domain.models import Claim, ClaimVersion
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.store.sqlite.claim_repo import SqliteClaimRepository


@pytest.mark.asyncio
class TestSqliteClaimRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimRepository(sqlite_db)
        claim_id = id_gen.claim_id()
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()

        claim = Claim(
            claim_id=claim_id,
            vault_id=vault_id,
            page_id=page_id,
            created_at=clock.now(),
        )
        version = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement="Water boils at 100C",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.95,
            validated_at=clock.now(),
            fresh_until=None,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(claim, version)
        await sqlite_db.commit()

        got = await repo.get(claim_id)
        assert got is not None
        assert got.claim_id == claim_id
        assert got.vault_id == vault_id
        assert got.page_id == page_id

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteClaimRepository(sqlite_db)
        assert await repo.get(id_gen.claim_id()) is None

    async def test_get_version(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimRepository(sqlite_db)
        claim_id = id_gen.claim_id()
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()

        claim = Claim(
            claim_id=claim_id, vault_id=vault_id, page_id=page_id,
            created_at=clock.now(),
        )
        v1 = ClaimVersion(
            claim_id=claim_id, version=Version(1),
            statement="v1 statement", status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED, confidence=0.5,
            validated_at=clock.now(), fresh_until=None,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create(claim, v1)
        await sqlite_db.commit()

        got = await repo.get_version(claim_id, Version(1))
        assert got is not None
        assert got.statement == "v1 statement"
        assert got.status == ClaimStatus.HYPOTHESIS
        assert got.support_type == SupportType.GENERATED
        assert got.confidence == 0.5

    async def test_get_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteClaimRepository(sqlite_db)
        assert await repo.get_version(id_gen.claim_id(), Version(1)) is None

    async def test_version_chain(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimRepository(sqlite_db)
        claim_id = id_gen.claim_id()
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()

        claim = Claim(
            claim_id=claim_id, vault_id=vault_id, page_id=page_id,
            created_at=clock.now(),
        )
        v1 = ClaimVersion(
            claim_id=claim_id, version=Version(1),
            statement="original", status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED, confidence=0.5,
            validated_at=clock.now(), fresh_until=None,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create(claim, v1)

        clock.tick(10)
        v2 = ClaimVersion(
            claim_id=claim_id, version=Version(2),
            statement="updated", status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT, confidence=0.9,
            validated_at=clock.now(), fresh_until=clock.now(),
            created_at=clock.now(), created_by=actor,
        )
        await repo.create_version(v2)
        await sqlite_db.commit()

        # Head should be v2
        head = await repo.get_head_version(claim_id)
        assert head is not None
        assert head.version == Version(2)
        assert head.statement == "updated"
        assert head.fresh_until is not None

        # v1 should still be accessible
        old = await repo.get_version(claim_id, Version(1))
        assert old is not None
        assert old.statement == "original"

    async def test_get_head_version_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteClaimRepository(sqlite_db)
        assert await repo.get_head_version(id_gen.claim_id()) is None

    async def test_list_by_page(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteClaimRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()
        other_page = id_gen.page_id()

        # Create 2 claims for page_id
        for _ in range(2):
            cid = id_gen.claim_id()
            c = Claim(claim_id=cid, vault_id=vault_id, page_id=page_id, created_at=clock.now())
            v = ClaimVersion(
                claim_id=cid, version=Version(1), statement="s",
                status=ClaimStatus.SUPPORTED, support_type=SupportType.DIRECT,
                confidence=0.9, validated_at=clock.now(), fresh_until=None,
                created_at=clock.now(), created_by=actor,
            )
            await repo.create(c, v)

        # Create 1 claim for other_page
        cid = id_gen.claim_id()
        c = Claim(claim_id=cid, vault_id=vault_id, page_id=other_page, created_at=clock.now())
        v = ClaimVersion(
            claim_id=cid, version=Version(1), statement="other",
            status=ClaimStatus.SUPPORTED, support_type=SupportType.DIRECT,
            confidence=0.8, validated_at=clock.now(), fresh_until=None,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create(c, v)
        await sqlite_db.commit()

        results = await repo.list_by_page(page_id)
        assert len(results) == 2

        other_results = await repo.list_by_page(other_page)
        assert len(other_results) == 1
