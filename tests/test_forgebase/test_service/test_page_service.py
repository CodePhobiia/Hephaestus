"""Tests for PageService."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import PageType
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.service.exceptions import ConflictError
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestPageService:
    async def _create_vault(self, uow_factory, actor):
        """Helper to create a vault for page operations."""
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="TestVault")

    async def test_create_page_basic(self, uow_factory, actor, sqlite_db, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, version = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="quantum-computing",
            page_type=PageType.CONCEPT,
            title="Quantum Computing",
            content=b"# Quantum Computing\nOverview...",
            summary="Initial creation",
        )

        assert page.vault_id == vault.vault_id
        assert page.page_type == PageType.CONCEPT
        assert page.page_key == "quantum-computing"
        assert version.version == Version(1)
        assert version.title == "Quantum Computing"
        assert version.summary == "Initial creation"

    async def test_create_page_content_stored(self, uow_factory, actor, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        _, version = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="test-page",
            page_type=PageType.CONCEPT,
            title="Test",
            content=b"page content bytes",
        )

        data = await content_store.read(version.content_ref)
        assert data == b"page content bytes"

    async def test_create_page_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="evented-page",
            page_type=PageType.MECHANISM,
            title="Evented",
            content=b"content",
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id FROM fb_domain_events WHERE event_type = ?",
            ("page.version_created",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["aggregate_id"] == str(page.page_id)

    async def test_create_page_sets_canonical_head(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="canonical-page",
            page_type=PageType.CONCEPT,
            title="Canonical",
            content=b"data",
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(page.page_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1

    async def test_create_page_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        wb_id = id_gen.workbook_id()

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="branch-page",
            page_type=PageType.CONCEPT,
            title="Branch Page",
            content=b"branch content",
            workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version, base_version FROM fb_branch_page_heads WHERE page_id = ?",
            (str(page.page_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1
        assert row["base_version"] == 1  # born on branch

        # No canonical head
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_canonical_heads WHERE entity_id = ?",
            (str(page.page_id),),
        )
        assert await cursor.fetchone() is None

    async def test_update_page_basic(self, uow_factory, actor, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, v1 = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="updatable",
            page_type=PageType.CONCEPT,
            title="Original Title",
            content=b"original content",
        )

        v2 = await svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="Updated Title",
            content=b"updated content",
            summary="Revised section 2",
        )

        assert v2.version == Version(2)
        assert v2.title == "Updated Title"
        assert v2.summary == "Revised section 2"

        # Content readable
        data = await content_store.read(v2.content_ref)
        assert data == b"updated content"

    async def test_update_page_title_only(self, uow_factory, actor, content_store):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, v1 = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="title-update",
            page_type=PageType.CONCEPT,
            title="Before",
            content=b"unchanged content",
        )

        v2 = await svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="After",
        )

        assert v2.title == "After"
        # Content ref should be the same (not re-staged)
        assert v2.content_hash == v1.content_hash

    async def test_update_page_optimistic_concurrency(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="conflict-page",
            page_type=PageType.CONCEPT,
            title="V1",
            content=b"v1",
        )

        # Update to v2
        await svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="V2",
        )

        # Stale update (expected v1 but head is v2)
        with pytest.raises(ConflictError) as exc_info:
            await svc.update_page(
                page_id=page.page_id,
                expected_version=Version(1),
                title="Stale",
            )
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

    async def test_update_page_canonical_head_advances(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="advancing",
            page_type=PageType.CONCEPT,
            title="V1",
            content=b"v1",
        )

        await svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="V2",
            content=b"v2",
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(page.page_id),),
        )
        row = await cursor.fetchone()
        assert row["head_version"] == 2

    async def test_update_page_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="ev-page",
            page_type=PageType.CONCEPT,
            title="V1",
            content=b"v1",
        )

        await svc.update_page(
            page_id=page.page_id,
            expected_version=Version(1),
            title="V2",
        )

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as c FROM fb_domain_events WHERE event_type = ?",
            ("page.version_created",),
        )
        row = await cursor.fetchone()
        assert row["c"] == 2  # create + update

    async def test_delete_page_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="deletable",
            page_type=PageType.CONCEPT,
            title="To Delete",
            content=b"content",
        )

        wb_id = id_gen.workbook_id()

        await svc.delete_page(page_id=page.page_id, workbook_id=wb_id)

        # Tombstone should exist
        cursor = await sqlite_db.execute(
            "SELECT entity_kind, entity_id FROM fb_branch_tombstones WHERE workbook_id = ?",
            (str(wb_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["entity_kind"] == "page"
        assert row["entity_id"] == str(page.page_id)

    async def test_delete_page_emits_event(self, uow_factory, actor, sqlite_db, id_gen):
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, _ = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="del-ev",
            page_type=PageType.CONCEPT,
            title="Del",
            content=b"x",
        )

        wb_id = id_gen.workbook_id()
        await svc.delete_page(page_id=page.page_id, workbook_id=wb_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("page.deleted",),
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_delete_page_not_found(self, uow_factory, actor, id_gen):
        svc = PageService(uow_factory=uow_factory, default_actor=actor)
        fake_id = id_gen.page_id()
        wb_id = id_gen.workbook_id()

        with pytest.raises(ValueError, match="Page not found"):
            await svc.delete_page(page_id=fake_id, workbook_id=wb_id)

    async def test_update_page_not_found(self, uow_factory, actor, id_gen):
        svc = PageService(uow_factory=uow_factory, default_actor=actor)
        fake_id = id_gen.page_id()

        with pytest.raises(ValueError, match="Page not found"):
            await svc.update_page(
                page_id=fake_id,
                expected_version=Version(1),
                title="X",
            )

    async def test_version_chain(self, uow_factory, actor):
        """Verify multiple sequential updates produce correct version numbers."""
        vault = await self._create_vault(uow_factory, actor)
        svc = PageService(uow_factory=uow_factory, default_actor=actor)

        page, v1 = await svc.create_page(
            vault_id=vault.vault_id,
            page_key="chain",
            page_type=PageType.CONCEPT,
            title="V1",
            content=b"v1",
        )
        assert v1.version == Version(1)

        v2 = await svc.update_page(page.page_id, Version(1), title="V2")
        assert v2.version == Version(2)

        v3 = await svc.update_page(page.page_id, Version(2), title="V3")
        assert v3.version == Version(3)

        v4 = await svc.update_page(page.page_id, Version(3), title="V4", content=b"v4")
        assert v4.version == Version(4)
