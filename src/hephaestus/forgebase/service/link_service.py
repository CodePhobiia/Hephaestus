"""LinkService — link creation, update, and deletion."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.enums import EntityKind, LinkKind
from hephaestus.forgebase.domain.models import (
    BranchLinkHead,
    BranchTombstone,
    Link,
    LinkVersion,
)
from hephaestus.forgebase.domain.values import ActorRef, EntityId, Version
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import ConflictError


class LinkService:
    """Command service for link lifecycle operations."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_link(
        self,
        vault_id: EntityId,
        kind: LinkKind,
        source_entity: EntityId,
        target_entity: EntityId,
        label: str | None = None,
        weight: float = 1.0,
        workbook_id: EntityId | None = None,
    ) -> tuple[Link, LinkVersion]:
        """Create a new link between two entities."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            link_id = uow.id_generator.link_id()

            link = Link(
                link_id=link_id,
                vault_id=vault_id,
                kind=kind,
                created_at=now,
            )

            version = LinkVersion(
                link_id=link_id,
                version=Version(1),
                source_entity=source_entity,
                target_entity=target_entity,
                label=label,
                weight=weight,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.links.create(link, version)

            # Set head
            if workbook_id is not None:
                await uow.workbooks.set_link_head(
                    BranchLinkHead(
                        workbook_id=workbook_id,
                        link_id=link_id,
                        head_version=Version(1),
                        base_version=Version(1),  # born on branch
                    )
                )
            else:
                await uow.vaults.set_canonical_link_head(
                    vault_id,
                    link_id,
                    1,
                )

            uow.record_event(
                uow.event_factory.create(
                    event_type="link.version_created",
                    aggregate_type="link",
                    aggregate_id=link_id,
                    aggregate_version=Version(1),
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "kind": kind.value,
                        "source_entity": str(source_entity),
                        "target_entity": str(target_entity),
                        "label": label,
                        "weight": weight,
                        "version": 1,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return link, version

    async def update_link(
        self,
        link_id: EntityId,
        expected_version: Version,
        label: str | None = None,
        weight: float | None = None,
        workbook_id: EntityId | None = None,
    ) -> LinkVersion:
        """Update a link, creating a new version with optimistic concurrency."""
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            link = await uow.links.get(link_id)
            if link is None:
                raise ValueError(f"Link not found: {link_id}")

            current_head = await uow.links.get_head_version(link_id)
            if current_head is None:
                raise ValueError(f"No versions found for link: {link_id}")

            if current_head.version != expected_version:
                raise ConflictError(
                    entity_id=str(link_id),
                    expected=expected_version.number,
                    actual=current_head.version.number,
                )

            new_version_num = expected_version.next()

            # Label update: use _SENTINEL to distinguish "not provided" from "set to None"
            resolved_label = label if label is not None else current_head.label
            resolved_weight = weight if weight is not None else current_head.weight

            new_version = LinkVersion(
                link_id=link_id,
                version=new_version_num,
                source_entity=current_head.source_entity,
                target_entity=current_head.target_entity,
                label=resolved_label,
                weight=resolved_weight,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.links.create_version(new_version)

            # Update head
            if workbook_id is not None:
                await uow.workbooks.set_link_head(
                    BranchLinkHead(
                        workbook_id=workbook_id,
                        link_id=link_id,
                        head_version=new_version_num,
                        base_version=expected_version,
                    )
                )
            else:
                await uow.vaults.set_canonical_link_head(
                    link.vault_id,
                    link_id,
                    new_version_num.number,
                )

            uow.record_event(
                uow.event_factory.create(
                    event_type="link.version_created",
                    aggregate_type="link",
                    aggregate_id=link_id,
                    aggregate_version=new_version_num,
                    vault_id=link.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "label": resolved_label,
                        "weight": resolved_weight,
                        "version": new_version_num.number,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return new_version

    async def delete_link(
        self,
        link_id: EntityId,
        workbook_id: EntityId,
    ) -> None:
        """Delete a link on a branch by adding a tombstone.

        Requires a workbook_id -- canonical deletes are not supported.
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            link = await uow.links.get(link_id)
            if link is None:
                raise ValueError(f"Link not found: {link_id}")

            await uow.workbooks.add_tombstone(
                BranchTombstone(
                    workbook_id=workbook_id,
                    entity_kind=EntityKind.LINK,
                    entity_id=link_id,
                    tombstoned_at=now,
                )
            )

            uow.record_event(
                uow.event_factory.create(
                    event_type="link.deleted",
                    aggregate_type="link",
                    aggregate_id=link_id,
                    vault_id=link.vault_id,
                    workbook_id=workbook_id,
                    payload={"link_id": str(link_id)},
                    actor=self._default_actor,
                )
            )

            await uow.commit()
