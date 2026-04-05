"""PageService — page creation, update, and deletion."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.enums import EntityKind, PageType
from hephaestus.forgebase.domain.models import (
    BranchPageHead,
    BranchTombstone,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import ConflictError


class PageService:
    """Command service for page lifecycle operations."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_page(
        self,
        vault_id: EntityId,
        page_key: str,
        page_type: PageType,
        title: str,
        content: bytes,
        compiled_from: list[EntityId] | None = None,
        workbook_id: EntityId | None = None,
        summary: str = "",
    ) -> tuple[Page, PageVersion]:
        """Create a new page with initial version.

        Steps:
          1. Stage content -> PendingContentRef
          2. Create Page + PageVersion(version=1)
          3. If workbook_id: set BranchPageHead; else: set canonical page head
          4. Emit page.version_created
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            page_id = uow.id_generator.page_id()

            # 1. Stage content
            pending_ref = await uow.content.stage(content, "text/markdown")
            blob_ref = pending_ref.to_blob_ref()
            content_hash = ContentHash.from_bytes(content)

            # 2. Create Page + PageVersion
            page = Page(
                page_id=page_id,
                vault_id=vault_id,
                page_type=page_type,
                page_key=page_key,
                created_at=now,
            )

            version = PageVersion(
                page_id=page_id,
                version=Version(1),
                title=title,
                content_ref=blob_ref,
                content_hash=content_hash,
                summary=summary,
                compiled_from=compiled_from or [],
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.pages.create(page, version)

            # 3. Set head
            if workbook_id is not None:
                await uow.workbooks.set_page_head(
                    BranchPageHead(
                        workbook_id=workbook_id,
                        page_id=page_id,
                        head_version=Version(1),
                        base_version=Version(1),  # born on branch
                    )
                )
            else:
                await uow.vaults.set_canonical_page_head(
                    vault_id,
                    page_id,
                    1,
                )

            # 4. Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="page.version_created",
                    aggregate_type="page",
                    aggregate_id=page_id,
                    aggregate_version=Version(1),
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "page_key": page_key,
                        "page_type": page_type.value,
                        "title": title,
                        "version": 1,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return page, version

    async def update_page(
        self,
        page_id: EntityId,
        expected_version: Version,
        title: str | None = None,
        content: bytes | None = None,
        summary: str = "",
        workbook_id: EntityId | None = None,
    ) -> PageVersion:
        """Update an existing page, creating a new version.

        Steps:
          1. Get current head version, verify == expected_version
          2. Stage new content if provided -> PendingContentRef
          3. Create new PageVersion(version=N+1)
          4. Update branch or canonical head
          5. Emit page.version_created
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            page = await uow.pages.get(page_id)
            if page is None:
                raise ValueError(f"Page not found: {page_id}")

            # 1. Get current head and verify
            current_head = await uow.pages.get_head_version(page_id)
            if current_head is None:
                raise ValueError(f"No versions found for page: {page_id}")

            if current_head.version != expected_version:
                raise ConflictError(
                    entity_id=str(page_id),
                    expected=expected_version.number,
                    actual=current_head.version.number,
                )

            new_version_num = expected_version.next()

            # 2. Stage content if provided
            if content is not None:
                pending_ref = await uow.content.stage(content, "text/markdown")
                new_blob_ref = pending_ref.to_blob_ref()
                new_content_hash = ContentHash.from_bytes(content)
            else:
                new_blob_ref = current_head.content_ref
                new_content_hash = current_head.content_hash

            # Resolve title
            resolved_title = title if title is not None else current_head.title

            # 3. Create new PageVersion
            new_version = PageVersion(
                page_id=page_id,
                version=new_version_num,
                title=resolved_title,
                content_ref=new_blob_ref,
                content_hash=new_content_hash,
                summary=summary,
                compiled_from=current_head.compiled_from,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.pages.create_version(new_version)

            # 4. Update head
            if workbook_id is not None:
                await uow.workbooks.set_page_head(
                    BranchPageHead(
                        workbook_id=workbook_id,
                        page_id=page_id,
                        head_version=new_version_num,
                        base_version=expected_version,
                    )
                )
            else:
                await uow.vaults.set_canonical_page_head(
                    page.vault_id,
                    page_id,
                    new_version_num.number,
                )

            # 5. Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="page.version_created",
                    aggregate_type="page",
                    aggregate_id=page_id,
                    aggregate_version=new_version_num,
                    vault_id=page.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "title": resolved_title,
                        "version": new_version_num.number,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return new_version

    async def delete_page(
        self,
        page_id: EntityId,
        workbook_id: EntityId,
    ) -> None:
        """Delete a page on a branch by adding a tombstone.

        Requires a workbook_id -- canonical deletes are not supported.
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            page = await uow.pages.get(page_id)
            if page is None:
                raise ValueError(f"Page not found: {page_id}")

            await uow.workbooks.add_tombstone(
                BranchTombstone(
                    workbook_id=workbook_id,
                    entity_kind=EntityKind.PAGE,
                    entity_id=page_id,
                    tombstoned_at=now,
                )
            )

            uow.record_event(
                uow.event_factory.create(
                    event_type="page.deleted",
                    aggregate_type="page",
                    aggregate_id=page_id,
                    vault_id=page.vault_id,
                    workbook_id=workbook_id,
                    payload={"page_id": str(page_id)},
                    actor=self._default_actor,
                )
            )

            await uow.commit()
