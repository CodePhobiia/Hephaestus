"""BranchService — create and abandon workbooks (branches)."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.enums import BranchPurpose, WorkbookStatus
from hephaestus.forgebase.domain.models import Workbook
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import EntityNotFoundError


class BranchService:
    """Command service for workbook (branch) lifecycle."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_workbook(
        self,
        vault_id: EntityId,
        name: str,
        purpose: BranchPurpose,
        *,
        actor: ActorRef | None = None,
        run_id: EntityId | None = None,
    ) -> Workbook:
        """Create a new workbook pinned to the vault's current head revision.

        Returns the created Workbook.
        """
        actor = actor or self._default_actor
        uow = self._uow_factory()
        async with uow:
            vault = await uow.vaults.get(vault_id)
            if vault is None:
                raise EntityNotFoundError("Vault", str(vault_id))

            now = uow.clock.now()
            workbook_id = uow.id_generator.workbook_id()

            workbook = Workbook(
                workbook_id=workbook_id,
                vault_id=vault_id,
                name=name,
                purpose=purpose,
                status=WorkbookStatus.OPEN,
                base_revision_id=vault.head_revision_id,
                created_at=now,
                created_by=actor,
                created_by_run=run_id,
            )

            await uow.workbooks.create(workbook)

            uow.record_event(
                uow.event_factory.create(
                    event_type="workbook.created",
                    aggregate_type="workbook",
                    aggregate_id=workbook_id,
                    vault_id=vault_id,
                    payload={
                        "name": name,
                        "purpose": purpose.value,
                        "base_revision_id": str(vault.head_revision_id),
                    },
                    actor=actor,
                    workbook_id=workbook_id,
                    run_id=str(run_id) if run_id else None,
                )
            )

            await uow.commit()

        return workbook

    async def abandon_workbook(
        self,
        workbook_id: EntityId,
        *,
        actor: ActorRef | None = None,
    ) -> Workbook:
        """Abandon a workbook, setting its status to ABANDONED.

        Returns the updated Workbook.
        """
        actor = actor or self._default_actor
        uow = self._uow_factory()
        async with uow:
            workbook = await uow.workbooks.get(workbook_id)
            if workbook is None:
                raise EntityNotFoundError("Workbook", str(workbook_id))

            await uow.workbooks.update_status(workbook_id, WorkbookStatus.ABANDONED)

            uow.record_event(
                uow.event_factory.create(
                    event_type="workbook.abandoned",
                    aggregate_type="workbook",
                    aggregate_id=workbook_id,
                    vault_id=workbook.vault_id,
                    payload={},
                    actor=actor,
                    workbook_id=workbook_id,
                )
            )

            await uow.commit()

        workbook.status = WorkbookStatus.ABANDONED
        return workbook
