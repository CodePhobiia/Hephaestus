"""RunIntegrationService — attach runs and record artifacts."""

from __future__ import annotations

from collections.abc import Callable

from hephaestus.forgebase.domain.enums import EntityKind
from hephaestus.forgebase.domain.models import KnowledgeRunArtifact, KnowledgeRunRef
from hephaestus.forgebase.domain.values import ActorRef, EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import EntityNotFoundError


class RunIntegrationService:
    """Command service for run integration: attach runs and record artifacts."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def attach_run(
        self,
        vault_id: EntityId,
        run_id: str,
        run_type: str,
        upstream_system: str,
        *,
        upstream_ref: str | None = None,
    ) -> KnowledgeRunRef:
        """Attach a run reference to a vault.

        Returns the created KnowledgeRunRef.
        """
        uow = self._uow_factory()
        async with uow:
            vault = await uow.vaults.get(vault_id)
            if vault is None:
                raise EntityNotFoundError("Vault", str(vault_id))

            now = uow.clock.now()
            ref_id = uow.id_generator.ref_id()

            ref = KnowledgeRunRef(
                ref_id=ref_id,
                vault_id=vault_id,
                run_id=run_id,
                run_type=run_type,
                upstream_system=upstream_system,
                upstream_ref=upstream_ref,
                source_hash=None,
                sync_status="attached",
                sync_error=None,
                synced_at=None,
                created_at=now,
            )

            await uow.run_refs.create(ref)

            uow.record_event(
                uow.event_factory.create(
                    event_type="artifact.attached",
                    aggregate_type="run_ref",
                    aggregate_id=ref_id,
                    vault_id=vault_id,
                    payload={
                        "run_id": run_id,
                        "run_type": run_type,
                        "upstream_system": upstream_system,
                    },
                    actor=self._default_actor,
                    run_id=run_id,
                )
            )

            await uow.commit()

        return ref

    async def record_artifact(
        self,
        ref_id: EntityId,
        entity_kind: EntityKind,
        entity_id: EntityId,
        role: str,
        *,
        idempotency_key: str,
    ) -> KnowledgeRunArtifact:
        """Record an artifact produced by a run.

        Returns the created KnowledgeRunArtifact.
        The idempotency_key is used as a guard — if an artifact with
        the same ref_id + entity_id + role already exists, this is a no-op.
        """
        uow = self._uow_factory()
        async with uow:
            ref = await uow.run_refs.get(ref_id)
            if ref is None:
                raise EntityNotFoundError("KnowledgeRunRef", str(ref_id))

            # Idempotency check: if artifact already exists, return it
            existing_artifacts = await uow.run_artifacts.list_by_ref(ref_id)
            for art in existing_artifacts:
                if art.entity_id == entity_id and art.role == role:
                    await uow.rollback()
                    return art

            artifact = KnowledgeRunArtifact(
                ref_id=ref_id,
                entity_kind=entity_kind,
                entity_id=entity_id,
                role=role,
            )

            await uow.run_artifacts.create(artifact)
            await uow.commit()

        return artifact
