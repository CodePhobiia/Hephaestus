"""Tests for SQLite merge proposal and merge conflict repositories."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    EntityKind,
    MergeResolution,
    MergeVerdict,
)
from hephaestus.forgebase.domain.models import MergeConflict, MergeProposal
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.store.sqlite.merge_conflict_repo import (
    SqliteMergeConflictRepository,
)
from hephaestus.forgebase.store.sqlite.merge_proposal_repo import (
    SqliteMergeProposalRepository,
)


@pytest.mark.asyncio
class TestSqliteMergeProposalRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteMergeProposalRepository(sqlite_db)
        merge_id = id_gen.merge_id()
        workbook_id = id_gen.workbook_id()
        vault_id = id_gen.vault_id()
        base_rev = id_gen.revision_id()
        target_rev = id_gen.revision_id()

        proposal = MergeProposal(
            merge_id=merge_id,
            workbook_id=workbook_id,
            vault_id=vault_id,
            base_revision_id=base_rev,
            target_revision_id=target_rev,
            verdict=MergeVerdict.CLEAN,
            resulting_revision=None,
            proposed_at=clock.now(),
            resolved_at=None,
            proposed_by=actor,
        )

        await repo.create(proposal)
        await sqlite_db.commit()

        got = await repo.get(merge_id)
        assert got is not None
        assert got.merge_id == merge_id
        assert got.workbook_id == workbook_id
        assert got.vault_id == vault_id
        assert got.base_revision_id == base_rev
        assert got.target_revision_id == target_rev
        assert got.verdict == MergeVerdict.CLEAN
        assert got.resulting_revision is None
        assert got.resolved_at is None
        assert got.proposed_by.actor_type == actor.actor_type
        assert got.proposed_by.actor_id == actor.actor_id

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteMergeProposalRepository(sqlite_db)
        assert await repo.get(id_gen.merge_id()) is None

    async def test_set_result(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteMergeProposalRepository(sqlite_db)
        merge_id = id_gen.merge_id()
        resulting_rev = id_gen.revision_id()

        proposal = MergeProposal(
            merge_id=merge_id,
            workbook_id=id_gen.workbook_id(),
            vault_id=id_gen.vault_id(),
            base_revision_id=id_gen.revision_id(),
            target_revision_id=id_gen.revision_id(),
            verdict=MergeVerdict.CLEAN,
            resulting_revision=None,
            proposed_at=clock.now(),
            resolved_at=None,
            proposed_by=actor,
        )
        await repo.create(proposal)
        await sqlite_db.commit()

        await repo.set_result(merge_id, resulting_rev)
        await sqlite_db.commit()

        got = await repo.get(merge_id)
        assert got is not None
        assert got.resulting_revision == resulting_rev

    async def test_create_with_resulting_revision(self, sqlite_db, clock, id_gen, actor):
        """Proposal can be created with a resulting revision already set."""
        repo = SqliteMergeProposalRepository(sqlite_db)
        merge_id = id_gen.merge_id()
        resulting_rev = id_gen.revision_id()

        proposal = MergeProposal(
            merge_id=merge_id,
            workbook_id=id_gen.workbook_id(),
            vault_id=id_gen.vault_id(),
            base_revision_id=id_gen.revision_id(),
            target_revision_id=id_gen.revision_id(),
            verdict=MergeVerdict.CLEAN,
            resulting_revision=resulting_rev,
            proposed_at=clock.now(),
            resolved_at=clock.now(),
            proposed_by=actor,
        )
        await repo.create(proposal)
        await sqlite_db.commit()

        got = await repo.get(merge_id)
        assert got is not None
        assert got.resulting_revision == resulting_rev
        assert got.resolved_at is not None

    async def test_create_conflicted_verdict(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteMergeProposalRepository(sqlite_db)
        merge_id = id_gen.merge_id()

        proposal = MergeProposal(
            merge_id=merge_id,
            workbook_id=id_gen.workbook_id(),
            vault_id=id_gen.vault_id(),
            base_revision_id=id_gen.revision_id(),
            target_revision_id=id_gen.revision_id(),
            verdict=MergeVerdict.CONFLICTED,
            resulting_revision=None,
            proposed_at=clock.now(),
            resolved_at=None,
            proposed_by=actor,
        )
        await repo.create(proposal)
        await sqlite_db.commit()

        got = await repo.get(merge_id)
        assert got is not None
        assert got.verdict == MergeVerdict.CONFLICTED


@pytest.mark.asyncio
class TestSqliteMergeConflictRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen):
        repo = SqliteMergeConflictRepository(sqlite_db)
        conflict_id = id_gen.conflict_id()
        merge_id = id_gen.merge_id()
        entity_id = id_gen.page_id()

        conflict = MergeConflict(
            conflict_id=conflict_id,
            merge_id=merge_id,
            entity_kind=EntityKind.PAGE,
            entity_id=entity_id,
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(3),
            resolution=None,
            resolved_at=None,
        )

        await repo.create(conflict)
        await sqlite_db.commit()

        got = await repo.get(conflict_id)
        assert got is not None
        assert got.conflict_id == conflict_id
        assert got.merge_id == merge_id
        assert got.entity_kind == EntityKind.PAGE
        assert got.entity_id == entity_id
        assert got.base_version == Version(1)
        assert got.branch_version == Version(2)
        assert got.canonical_version == Version(3)
        assert got.resolution is None
        assert got.resolved_at is None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteMergeConflictRepository(sqlite_db)
        assert await repo.get(id_gen.conflict_id()) is None

    async def test_list_by_merge(self, sqlite_db, id_gen):
        repo = SqliteMergeConflictRepository(sqlite_db)
        merge_id = id_gen.merge_id()
        other_merge = id_gen.merge_id()

        c1 = MergeConflict(
            conflict_id=id_gen.conflict_id(),
            merge_id=merge_id,
            entity_kind=EntityKind.PAGE,
            entity_id=id_gen.page_id(),
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(3),
        )
        c2 = MergeConflict(
            conflict_id=id_gen.conflict_id(),
            merge_id=merge_id,
            entity_kind=EntityKind.CLAIM,
            entity_id=id_gen.claim_id(),
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(2),
        )
        c3 = MergeConflict(
            conflict_id=id_gen.conflict_id(),
            merge_id=other_merge,
            entity_kind=EntityKind.LINK,
            entity_id=id_gen.link_id(),
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(2),
        )

        await repo.create(c1)
        await repo.create(c2)
        await repo.create(c3)
        await sqlite_db.commit()

        results = await repo.list_by_merge(merge_id)
        assert len(results) == 2
        ids = {r.conflict_id for r in results}
        assert c1.conflict_id in ids
        assert c2.conflict_id in ids

    async def test_list_by_merge_empty(self, sqlite_db, id_gen):
        repo = SqliteMergeConflictRepository(sqlite_db)
        results = await repo.list_by_merge(id_gen.merge_id())
        assert results == []

    async def test_resolve(self, sqlite_db, id_gen):
        repo = SqliteMergeConflictRepository(sqlite_db)
        conflict_id = id_gen.conflict_id()

        conflict = MergeConflict(
            conflict_id=conflict_id,
            merge_id=id_gen.merge_id(),
            entity_kind=EntityKind.PAGE,
            entity_id=id_gen.page_id(),
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(3),
        )
        await repo.create(conflict)
        await sqlite_db.commit()

        await repo.resolve(conflict_id, MergeResolution.ACCEPT_BRANCH)
        await sqlite_db.commit()

        got = await repo.get(conflict_id)
        assert got is not None
        assert got.resolution == MergeResolution.ACCEPT_BRANCH
        assert got.resolved_at is not None
