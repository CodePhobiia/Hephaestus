"""Tests for SQLite page repository."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ActorType, PageType
from hephaestus.forgebase.domain.models import Page, PageVersion
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.store.sqlite.page_repo import SqlitePageRepository


@pytest.mark.asyncio
class TestSqlitePageRepository:
    async def test_create_and_get(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        page_id = id_gen.page_id()
        vault_id = id_gen.vault_id()

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.CONCEPT,
            page_key="quantum-entanglement",
            created_at=clock.now(),
            created_by_run=None,
        )
        version = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Quantum Entanglement",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=2048,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="b" * 64),
            summary="Overview of quantum entanglement",
            compiled_from=[id_gen.source_id(), id_gen.source_id()],
            created_at=clock.now(),
            created_by=actor,
            schema_version=1,
        )

        await repo.create(page, version)
        await sqlite_db.commit()

        got = await repo.get(page_id)
        assert got is not None
        assert got.page_id == page_id
        assert got.vault_id == vault_id
        assert got.page_type == PageType.CONCEPT
        assert got.page_key == "quantum-entanglement"
        assert got.created_by_run is None

    async def test_get_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqlitePageRepository(sqlite_db)
        assert await repo.get(id_gen.page_id()) is None

    async def test_find_by_key(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        vault_id = id_gen.vault_id()
        page_id = id_gen.page_id()

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.PROBLEM,
            page_key="traveling-salesman",
            created_at=clock.now(),
        )
        ver = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Traveling Salesman",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="b" * 64),
            summary="",
            compiled_from=[],
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(page, ver)
        await sqlite_db.commit()

        found = await repo.find_by_key(vault_id, "traveling-salesman")
        assert found is not None
        assert found.page_id == page_id

        not_found = await repo.find_by_key(vault_id, "nonexistent-key")
        assert not_found is None

    async def test_list_by_vault_with_filter(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        vault_id = id_gen.vault_id()

        # Create 2 CONCEPT pages and 1 PROBLEM page
        for ptype, count in [(PageType.CONCEPT, 2), (PageType.PROBLEM, 1)]:
            for i in range(count):
                pid = id_gen.page_id()
                page = Page(
                    page_id=pid,
                    vault_id=vault_id,
                    page_type=ptype,
                    page_key=f"{ptype.value}-{i}",
                    created_at=clock.now(),
                )
                ver = PageVersion(
                    page_id=pid,
                    version=Version(1),
                    title=f"Page {ptype.value} {i}",
                    content_ref=BlobRef(
                        content_hash=ContentHash(sha256="a" * 64),
                        size_bytes=100,
                        mime_type="text/markdown",
                    ),
                    content_hash=ContentHash(sha256="b" * 64),
                    summary="",
                    compiled_from=[],
                    created_at=clock.now(),
                    created_by=actor,
                )
                await repo.create(page, ver)

        await sqlite_db.commit()

        # All pages in vault
        all_pages = await repo.list_by_vault(vault_id)
        assert len(all_pages) == 3

        # Filter by type
        concepts = await repo.list_by_vault(vault_id, page_type="concept")
        assert len(concepts) == 2

        problems = await repo.list_by_vault(vault_id, page_type="problem")
        assert len(problems) == 1

    async def test_version_chain(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        page_id = id_gen.page_id()
        vault_id = id_gen.vault_id()
        src_id = id_gen.source_id()

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.MECHANISM,
            page_key="crispr-cas9",
            created_at=clock.now(),
        )
        v1 = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="CRISPR v1",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="b" * 64),
            summary="Initial",
            compiled_from=[src_id],
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(page, v1)

        v2 = PageVersion(
            page_id=page_id,
            version=Version(2),
            title="CRISPR v2",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="c" * 64),
                size_bytes=200,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="d" * 64),
            summary="Expanded",
            compiled_from=[src_id, id_gen.source_id()],
            created_at=clock.now(),
            created_by=actor,
            schema_version=2,
        )
        await repo.create_version(v2)
        await sqlite_db.commit()

        # Both versions accessible
        got_v1 = await repo.get_version(page_id, Version(1))
        assert got_v1 is not None
        assert got_v1.title == "CRISPR v1"
        assert len(got_v1.compiled_from) == 1

        got_v2 = await repo.get_version(page_id, Version(2))
        assert got_v2 is not None
        assert got_v2.title == "CRISPR v2"
        assert got_v2.schema_version == 2
        assert len(got_v2.compiled_from) == 2

    async def test_get_head_version(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        page_id = id_gen.page_id()
        vault_id = id_gen.vault_id()

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.CONCEPT,
            page_key="relativity",
            created_at=clock.now(),
        )
        v1 = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Relativity v1",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="b" * 64),
            summary="First draft",
            compiled_from=[],
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(page, v1)

        v2 = PageVersion(
            page_id=page_id,
            version=Version(2),
            title="Relativity v2",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="c" * 64),
                size_bytes=200,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="d" * 64),
            summary="Second draft",
            compiled_from=[],
            created_at=clock.now(),
            created_by=actor,
        )
        await repo.create_version(v2)
        await sqlite_db.commit()

        head = await repo.get_head_version(page_id)
        assert head is not None
        assert head.version == Version(2)
        assert head.title == "Relativity v2"

    async def test_get_head_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqlitePageRepository(sqlite_db)
        assert await repo.get_head_version(id_gen.page_id()) is None

    async def test_get_version_nonexistent_returns_none(self, sqlite_db, id_gen):
        repo = SqlitePageRepository(sqlite_db)
        assert await repo.get_version(id_gen.page_id(), Version(1)) is None

    async def test_page_with_created_by_run(self, sqlite_db, clock, id_gen, actor):
        repo = SqlitePageRepository(sqlite_db)
        page_id = id_gen.page_id()
        vault_id = id_gen.vault_id()
        run_id = id_gen.generate("run")

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.CONCEPT,
            page_key="with-run",
            created_at=clock.now(),
            created_by_run=run_id,
        )
        ver = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="With Run",
            content_ref=BlobRef(
                content_hash=ContentHash(sha256="a" * 64),
                size_bytes=100,
                mime_type="text/markdown",
            ),
            content_hash=ContentHash(sha256="b" * 64),
            summary="",
            compiled_from=[],
            created_at=clock.now(),
            created_by=actor,
        )

        await repo.create(page, ver)
        await sqlite_db.commit()

        got = await repo.get(page_id)
        assert got is not None
        assert got.created_by_run == run_id
