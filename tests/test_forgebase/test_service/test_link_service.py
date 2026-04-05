"""Tests for LinkService."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import LinkKind, PageType
from hephaestus.forgebase.domain.values import Version
from hephaestus.forgebase.service.exceptions import ConflictError
from hephaestus.forgebase.service.link_service import LinkService
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestLinkService:
    async def _setup(self, uow_factory, actor):
        """Create a vault and two pages to link together."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        vault = await vault_svc.create_vault(name="TestVault")
        page_a, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-a",
            page_type=PageType.CONCEPT,
            title="Page A",
            content=b"A",
        )
        page_b, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="page-b",
            page_type=PageType.CONCEPT,
            title="Page B",
            content=b"B",
        )
        return vault, page_a, page_b

    # ---- create_link ----

    async def test_create_link_basic(self, uow_factory, actor):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, version = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
            label="is related to",
            weight=0.8,
        )

        assert link.vault_id == vault.vault_id
        assert link.kind == LinkKind.RELATED_CONCEPT
        assert version.version == Version(1)
        assert version.source_entity == page_a.page_id
        assert version.target_entity == page_b.page_id
        assert version.label == "is related to"
        assert version.weight == 0.8

    async def test_create_link_emits_event(self, uow_factory, actor, sqlite_db):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.BACKLINK,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id FROM fb_domain_events WHERE event_type = ?",
            ("link.version_created",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["aggregate_id"] == str(link.link_id)

    async def test_create_link_sets_canonical_head(self, uow_factory, actor, sqlite_db):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.PAGE_TO_PAGE,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(link.link_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1

    async def test_create_link_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        wb_id = id_gen.workbook_id()

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.SUPERSEDES,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
            workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version, base_version FROM fb_branch_link_heads WHERE link_id = ?",
            (str(link.link_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1
        assert row["base_version"] == 1

        # No canonical head
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_canonical_heads WHERE entity_id = ?",
            (str(link.link_id),),
        )
        assert await cursor.fetchone() is None

    # ---- update_link ----

    async def test_update_link_basic(self, uow_factory, actor):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, v1 = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
            label="original",
            weight=0.5,
        )

        v2 = await svc.update_link(
            link_id=link.link_id,
            expected_version=Version(1),
            label="updated label",
            weight=0.9,
        )

        assert v2.version == Version(2)
        assert v2.label == "updated label"
        assert v2.weight == 0.9
        # source/target preserved
        assert v2.source_entity == page_a.page_id
        assert v2.target_entity == page_b.page_id

    async def test_update_link_partial(self, uow_factory, actor):
        """Only update provided fields."""
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.BACKLINK,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
            label="keep me",
            weight=0.7,
        )

        v2 = await svc.update_link(
            link_id=link.link_id,
            expected_version=Version(1),
            weight=0.3,  # only change weight
        )

        assert v2.label == "keep me"  # carried over
        assert v2.weight == 0.3

    async def test_update_link_optimistic_concurrency(self, uow_factory, actor):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        # Update to v2
        await svc.update_link(link.link_id, Version(1), label="v2")

        # Stale update
        with pytest.raises(ConflictError) as exc_info:
            await svc.update_link(link.link_id, Version(1), label="stale")
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

    async def test_update_link_canonical_head_advances(self, uow_factory, actor, sqlite_db):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        await svc.update_link(link.link_id, Version(1), weight=0.5)

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(link.link_id),),
        )
        row = await cursor.fetchone()
        assert row["head_version"] == 2

    async def test_update_link_emits_event(self, uow_factory, actor, sqlite_db):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.BACKLINK,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        await svc.update_link(link.link_id, Version(1), label="new")

        cursor = await sqlite_db.execute(
            "SELECT COUNT(*) as c FROM fb_domain_events WHERE event_type = ?",
            ("link.version_created",),
        )
        row = await cursor.fetchone()
        assert row["c"] == 2  # create + update

    async def test_update_link_not_found(self, uow_factory, actor, id_gen):
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        fake = id_gen.link_id()
        with pytest.raises(ValueError, match="Link not found"):
            await svc.update_link(fake, Version(1), label="X")

    # ---- delete_link ----

    async def test_delete_link_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        wb_id = id_gen.workbook_id()
        await svc.delete_link(link_id=link.link_id, workbook_id=wb_id)

        cursor = await sqlite_db.execute(
            "SELECT entity_kind, entity_id FROM fb_branch_tombstones WHERE workbook_id = ?",
            (str(wb_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["entity_kind"] == "link"
        assert row["entity_id"] == str(link.link_id)

    async def test_delete_link_emits_event(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, _ = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.PAGE_TO_PAGE,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
        )

        wb_id = id_gen.workbook_id()
        await svc.delete_link(link.link_id, wb_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("link.deleted",),
        )
        assert await cursor.fetchone() is not None

    async def test_delete_link_not_found(self, uow_factory, actor, id_gen):
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)
        fake = id_gen.link_id()
        wb_id = id_gen.workbook_id()
        with pytest.raises(ValueError, match="Link not found"):
            await svc.delete_link(fake, wb_id)

    async def test_version_chain(self, uow_factory, actor):
        """Verify multiple sequential updates produce correct version numbers."""
        vault, page_a, page_b = await self._setup(uow_factory, actor)
        svc = LinkService(uow_factory=uow_factory, default_actor=actor)

        link, v1 = await svc.create_link(
            vault_id=vault.vault_id,
            kind=LinkKind.RELATED_CONCEPT,
            source_entity=page_a.page_id,
            target_entity=page_b.page_id,
            weight=0.1,
        )
        assert v1.version == Version(1)

        v2 = await svc.update_link(link.link_id, Version(1), weight=0.2)
        assert v2.version == Version(2)

        v3 = await svc.update_link(link.link_id, Version(2), weight=0.3)
        assert v3.version == Version(3)

        v4 = await svc.update_link(link.link_id, Version(3), label="final", weight=0.4)
        assert v4.version == Version(4)
        assert v4.label == "final"
        assert v4.weight == 0.4
