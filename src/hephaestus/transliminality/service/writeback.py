"""ForgeBase writeback service — persists transliminality artifacts.

Stores role signatures, accepted/rejected analogical maps, transfer
opportunities, and run manifests into ForgeBase via UoW.

Writeback is durable and idempotent — re-running with the same pack
should not create duplicates.

Uses a deferred approach: opens its own isolated database connection
to avoid nested-transaction issues with the shared SQLite connection
used by the bridge retriever during build_pack().
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.domain.enums import AnalogicalVerdict
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    EntityRef,
    TransferOpportunity,
    TransliminalityPack,
    TransliminalityRunManifest,
)

if TYPE_CHECKING:
    from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class ForgeBaseWritebackService:
    """Persists transliminality artifacts into ForgeBase.

    Opens its own database connection to avoid nested-transaction
    conflicts with the shared connection used during build_pack().
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._id_gen = id_generator

    async def write_back(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        downstream_outcome_refs: list[EntityRef],
    ) -> TransliminalityRunManifest:
        """Persist all transliminality artifacts and return a run manifest."""
        valid_maps = [m for m in maps if m.verdict != AnalogicalVerdict.INVALID]
        rejected_maps = [m for m in maps if m.verdict == AnalogicalVerdict.INVALID]

        manifest_id = self._id_gen.generate("tman")

        try:
            uow = await self._create_isolated_uow()
            async with uow:
                # Persist role signature
                await self._persist_artifact(
                    uow,
                    ref_id=pack.run_id,
                    entity_id=pack.problem_signature_ref.entity_id,
                    entity_kind="transliminality_role_signature",
                    role="problem_role_signature",
                )

                for amap in valid_maps:
                    await self._persist_artifact(
                        uow,
                        ref_id=pack.run_id,
                        entity_id=amap.map_id,
                        entity_kind="transliminality_map_valid",
                        role="accepted_analogical_map",
                    )

                for amap in rejected_maps:
                    await self._persist_artifact(
                        uow,
                        ref_id=pack.run_id,
                        entity_id=amap.map_id,
                        entity_kind="transliminality_map_rejected",
                        role="rejected_analogical_map",
                    )

                for opp in opportunities:
                    await self._persist_artifact(
                        uow,
                        ref_id=pack.run_id,
                        entity_id=opp.opportunity_id,
                        entity_kind="transliminality_transfer",
                        role="transfer_opportunity",
                    )

                await self._persist_artifact(
                    uow,
                    ref_id=pack.run_id,
                    entity_id=pack.pack_id,
                    entity_kind="transliminality_pack",
                    role="assembled_pack",
                )

                await self._persist_artifact(
                    uow,
                    ref_id=pack.run_id,
                    entity_id=manifest_id,
                    entity_kind="transliminality_manifest",
                    role="run_manifest",
                )

                await uow.commit()

            logger.info(
                "writeback_completed  run_id=%s  valid=%d  rejected=%d  transfers=%d",
                pack.run_id, len(valid_maps), len(rejected_maps), len(opportunities),
            )

        except Exception:
            logger.exception("writeback_failed  run_id=%s", pack.run_id)
            # Writeback failure should not crash the invention pipeline.

        return TransliminalityRunManifest(
            manifest_id=manifest_id,
            run_id=pack.run_id,
            policy_version=pack.policy_version,
            assembler_version=pack.assembler_version,
            selected_vaults=list(pack.remote_vault_ids),
            candidate_count=len(pack.bridge_candidates),
            analyzed_count=len(maps),
            valid_map_count=len(valid_maps),
            rejected_map_count=len(rejected_maps),
            transfer_opportunity_count=len(opportunities),
            injected_pack_ref=EntityRef(
                entity_id=pack.pack_id,
                entity_kind="transliminality_pack",
            ),
            downstream_outcome_refs=list(downstream_outcome_refs),
        )

    async def _create_isolated_uow(self) -> AbstractUnitOfWork:
        """Create a UoW with its own database connection.

        Avoids the 'cannot start a transaction within a transaction' error
        that occurs when the shared connection already has an active txn.
        """
        import aiosqlite

        from hephaestus.forgebase.domain.event_types import WallClock
        from hephaestus.forgebase.store.blobs.memory import InMemoryContentStore
        from hephaestus.forgebase.store.sqlite.schema import initialize_schema
        from hephaestus.forgebase.store.sqlite.uow import SqliteUnitOfWork

        db_path = str(Path.home() / ".hephaestus" / "forgebase.db")
        db = await aiosqlite.connect(db_path, isolation_level=None)
        db.row_factory = aiosqlite.Row
        await initialize_schema(db)

        return SqliteUnitOfWork(
            db=db,
            content=InMemoryContentStore(),
            clock=WallClock(),
            id_generator=self._id_gen,
            consumer_names=[],
        )

    async def _persist_artifact(
        self,
        uow: AbstractUnitOfWork,
        *,
        ref_id: EntityId,
        entity_id: EntityId,
        entity_kind: str,
        role: str,
    ) -> None:
        """Create a KnowledgeRunArtifact record."""
        from hephaestus.forgebase.domain.enums import EntityKind
        from hephaestus.forgebase.domain.models import KnowledgeRunArtifact

        artifact = KnowledgeRunArtifact(
            ref_id=ref_id,
            entity_kind=EntityKind.SOURCE,  # closest fit for run artifacts
            entity_id=entity_id,
            role=role,  # role field distinguishes transliminality artifact type
        )
        await uow.run_artifacts.create(artifact)
