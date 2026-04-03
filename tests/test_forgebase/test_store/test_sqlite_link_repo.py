"""Tests for SQLite link repository."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import LinkKind
from hephaestus.forgebase.domain.models import Link, LinkVersion
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.store.sqlite.link_repo import SqliteLinkRepository


@pytest.mark.asyncio
class TestSqliteLinkRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        link_id = id_gen.link_id()
        vault_id = id_gen.vault_id()
        source_entity = id_gen.page_id()
        target_entity = id_gen.page_id()

        link = Link(
            link_id=link_id,
            vault_id=vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            created_at=clock.now(),
        )
        version = LinkVersion(
            link_id=link_id,
            version=Version(1),
            source_entity=source_entity,
            target_entity=target_entity,
            label="related to",
            weight=0.8,
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(link, version)
        await sqlite_db.commit()

        got = await repo.get(link_id)
        assert got is not None
        assert got.link_id == link_id
        assert got.vault_id == vault_id
        assert got.kind == LinkKind.RELATED_CONCEPT

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteLinkRepository(sqlite_db)
        assert await repo.get(id_gen.link_id()) is None

    async def test_get_version(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        link_id = id_gen.link_id()
        vault_id = id_gen.vault_id()

        link = Link(
            link_id=link_id, vault_id=vault_id, kind=LinkKind.BACKLINK,
            created_at=clock.now(),
        )
        v1 = LinkVersion(
            link_id=link_id, version=Version(1),
            source_entity=id_gen.page_id(), target_entity=id_gen.page_id(),
            label=None, weight=1.0,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create(link, v1)
        await sqlite_db.commit()

        got = await repo.get_version(link_id, Version(1))
        assert got is not None
        assert got.version == Version(1)
        assert got.weight == 1.0
        assert got.label is None

    async def test_get_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqliteLinkRepository(sqlite_db)
        assert await repo.get_version(id_gen.link_id(), Version(1)) is None

    async def test_version_chain(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        link_id = id_gen.link_id()
        vault_id = id_gen.vault_id()
        src = id_gen.page_id()
        tgt = id_gen.page_id()

        link = Link(
            link_id=link_id, vault_id=vault_id, kind=LinkKind.PAGE_TO_PAGE,
            created_at=clock.now(),
        )
        v1 = LinkVersion(
            link_id=link_id, version=Version(1),
            source_entity=src, target_entity=tgt,
            label="original", weight=0.5,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create(link, v1)

        clock.tick(10)
        v2 = LinkVersion(
            link_id=link_id, version=Version(2),
            source_entity=src, target_entity=tgt,
            label="updated", weight=0.9,
            created_at=clock.now(), created_by=actor,
        )
        await repo.create_version(v2)
        await sqlite_db.commit()

        # Head should be v2
        head = await repo.get_head_version(link_id)
        assert head is not None
        assert head.version == Version(2)
        assert head.label == "updated"
        assert head.weight == 0.9

        # v1 still accessible
        old = await repo.get_version(link_id, Version(1))
        assert old is not None
        assert old.label == "original"

    async def test_get_head_version_nonexistent(self, sqlite_db, id_gen):
        repo = SqliteLinkRepository(sqlite_db)
        assert await repo.get_head_version(id_gen.link_id()) is None

    async def test_list_by_entity_outgoing(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        entity_a = id_gen.page_id()
        entity_b = id_gen.page_id()
        entity_c = id_gen.page_id()

        # Link A -> B
        lid1 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid1, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid1, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        # Link C -> A
        lid2 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid2, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid2, version=Version(1), source_entity=entity_c, target_entity=entity_a, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        await sqlite_db.commit()

        # Outgoing from A should only return the A->B link
        outgoing = await repo.list_by_entity(entity_a, direction="outgoing")
        assert len(outgoing) == 1
        assert outgoing[0].link_id == lid1

    async def test_list_by_entity_incoming(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        entity_a = id_gen.page_id()
        entity_b = id_gen.page_id()
        entity_c = id_gen.page_id()

        # Link A -> B
        lid1 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid1, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid1, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        # Link C -> B
        lid2 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid2, vault_id=vault_id, kind=LinkKind.RELATED_CONCEPT, created_at=clock.now()),
            LinkVersion(link_id=lid2, version=Version(1), source_entity=entity_c, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        await sqlite_db.commit()

        # Incoming to B should return both links
        incoming = await repo.list_by_entity(entity_b, direction="incoming")
        assert len(incoming) == 2

    async def test_list_by_entity_both(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        entity_a = id_gen.page_id()
        entity_b = id_gen.page_id()
        entity_c = id_gen.page_id()

        # Link A -> B
        lid1 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid1, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid1, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        # Link C -> A
        lid2 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid2, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid2, version=Version(1), source_entity=entity_c, target_entity=entity_a, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        await sqlite_db.commit()

        # "both" for A should return both links (outgoing A->B and incoming C->A)
        both = await repo.list_by_entity(entity_a, direction="both")
        assert len(both) == 2

    async def test_list_by_entity_with_kind_filter(self, sqlite_db, clock, id_gen, actor):
        repo = SqliteLinkRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        entity_a = id_gen.page_id()
        entity_b = id_gen.page_id()

        # Backlink A -> B
        lid1 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid1, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid1, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        # Related concept A -> B
        lid2 = id_gen.link_id()
        await repo.create(
            Link(link_id=lid2, vault_id=vault_id, kind=LinkKind.RELATED_CONCEPT, created_at=clock.now()),
            LinkVersion(link_id=lid2, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        await sqlite_db.commit()

        # Filter by kind=backlink
        filtered = await repo.list_by_entity(entity_a, kind="backlink")
        assert len(filtered) == 1
        assert filtered[0].link_id == lid1

    async def test_list_by_entity_uses_head_version(self, sqlite_db, clock, id_gen, actor):
        """list_by_entity should use the head (latest) version for direction matching."""
        repo = SqliteLinkRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        entity_a = id_gen.page_id()
        entity_b = id_gen.page_id()
        entity_c = id_gen.page_id()

        # Link v1: A -> B, then v2: A -> C
        lid = id_gen.link_id()
        await repo.create(
            Link(link_id=lid, vault_id=vault_id, kind=LinkKind.BACKLINK, created_at=clock.now()),
            LinkVersion(link_id=lid, version=Version(1), source_entity=entity_a, target_entity=entity_b, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        clock.tick(5)
        await repo.create_version(
            LinkVersion(link_id=lid, version=Version(2), source_entity=entity_a, target_entity=entity_c, label=None, weight=1.0, created_at=clock.now(), created_by=actor),
        )
        await sqlite_db.commit()

        # Searching for entity_b should NOT find the link (head now points to C)
        by_b = await repo.list_by_entity(entity_b, direction="incoming")
        assert len(by_b) == 0

        # Searching for entity_c should find it
        by_c = await repo.list_by_entity(entity_c, direction="incoming")
        assert len(by_c) == 1
