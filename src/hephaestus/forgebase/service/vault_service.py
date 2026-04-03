"""VaultService — create and configure vaults."""
from __future__ import annotations

from typing import Any, Callable

from hephaestus.forgebase.domain.models import Vault, VaultRevision
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork


class VaultService:
    """Command service for vault lifecycle operations."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def create_vault(
        self,
        name: str,
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> Vault:
        """Create a new vault with an initial revision.

        Returns the created Vault.
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            vault_id = uow.id_generator.vault_id()
            rev_id = uow.id_generator.revision_id()

            vault = Vault(
                vault_id=vault_id,
                name=name,
                description=description,
                head_revision_id=rev_id,
                created_at=now,
                updated_at=now,
                config=config or {},
            )

            revision = VaultRevision(
                revision_id=rev_id,
                vault_id=vault_id,
                parent_revision_id=None,
                created_at=now,
                created_by=self._default_actor,
                causation_event_id=None,
                summary="Initial vault creation",
            )

            await uow.vaults.create(vault, revision)

            uow.record_event(
                uow.event_factory.create(
                    event_type="vault.created",
                    aggregate_type="vault",
                    aggregate_id=vault_id,
                    vault_id=vault_id,
                    payload={"name": name, "description": description},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return vault

    async def update_vault_config(
        self,
        vault_id: EntityId,
        config: dict[str, Any],
    ) -> Vault:
        """Update the configuration of an existing vault.

        Returns the updated Vault.
        """
        uow = self._uow_factory()
        async with uow:
            vault = await uow.vaults.get(vault_id)
            if vault is None:
                raise ValueError(f"Vault not found: {vault_id}")

            await uow.vaults.update_config(vault_id, config)

            uow.record_event(
                uow.event_factory.create(
                    event_type="vault.config_updated",
                    aggregate_type="vault",
                    aggregate_id=vault_id,
                    vault_id=vault_id,
                    payload={"config": config},
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        # Re-read after commit to return the fresh state
        vault.config = config
        return vault
