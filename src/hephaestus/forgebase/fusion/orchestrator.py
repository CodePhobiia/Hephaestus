"""FusionOrchestrator -- full three-stage cross-vault fusion pipeline.

Ties together:
  Stage 1: Bridge candidate generation  (candidates.py)
  Stage 2: FusionAnalyzer validation     (analyzer.py)
  Stage 3: Fusion synthesis              (synthesis.py)

Plus: vault validation, context assembly, FusionRun persistence, event emission.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from itertools import combinations

from hephaestus.forgebase.contracts.fusion import (
    FusionRequest,
    FusionResult,
    PairFusionResult,
)
from hephaestus.forgebase.domain.models import FusionRun
from hephaestus.forgebase.domain.values import ActorRef, EntityId, VaultRevisionId
from hephaestus.forgebase.extraction.assembler import VaultContextAssembler
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.candidates import generate_bridge_candidates
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
from hephaestus.forgebase.fusion.models import PairFusionManifest
from hephaestus.forgebase.fusion.policy import DEFAULT_FUSION_POLICY, FusionPolicy
from hephaestus.forgebase.fusion.synthesis import synthesize_fusion_result
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class FusionOrchestrator:
    """Orchestrates the three-stage fusion pipeline.

    1. Validate request (vault_ids exist, >= 2 vaults)
    2. Assemble context packs from each vault via context_assembler
    3. For each vault pair (N*(N-1)/2 pairs):
       a. Stage 1: generate_bridge_candidates()
       b. Stage 2: fusion_analyzer.analyze_candidates()
       c. Build PairFusionResult with pair manifest
    4. Stage 3: synthesize_fusion_result() to aggregate
    5. Persist FusionRun as durable artifact
    6. Emit events (fusion.completed or fusion.failed)
    7. Return FusionResult
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        context_assembler: VaultContextAssembler,
        fusion_analyzer: FusionAnalyzer,
        embedding_index: EmbeddingIndex,
        policy: FusionPolicy | None = None,
        default_actor: ActorRef | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._context_assembler = context_assembler
        self._analyzer = fusion_analyzer
        self._embedding_index = embedding_index
        self._default_actor = default_actor or ActorRef.system()
        self._policy = policy or DEFAULT_FUSION_POLICY

    async def fuse(self, request: FusionRequest) -> FusionResult:
        """Execute full fusion pipeline."""
        policy = request.policy or self._policy

        # ------------------------------------------------------------------
        # 1. Validate request
        # ------------------------------------------------------------------
        if len(request.vault_ids) < 2:
            raise ValueError(f"Fusion requires at least 2 vaults, got {len(request.vault_ids)}")

        # Validate that all vaults exist
        uow = self._uow_factory()
        vault_revisions: dict[EntityId, VaultRevisionId] = {}
        async with uow:
            for vid in request.vault_ids:
                vault = await uow.vaults.get(vid)
                if vault is None:
                    raise ValueError(f"Vault {vid} not found")
                vault_revisions[vid] = vault.head_revision_id
            await uow.rollback()  # read-only

        try:
            # ------------------------------------------------------------------
            # 2. Assemble context packs from each vault
            # ------------------------------------------------------------------
            vault_packs: dict[
                EntityId,
                tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack],
            ] = {}
            for vid in request.vault_ids:
                baseline, context, dossier = await self._context_assembler.assemble_all(vid)
                vault_packs[vid] = (baseline, context, dossier)

            # ------------------------------------------------------------------
            # 3. Pairwise candidate generation + analysis
            # ------------------------------------------------------------------
            pairs = list(combinations(request.vault_ids, 2))
            pair_results: list[PairFusionResult] = []
            all_analyzer_calls = []

            for left_id, right_id in pairs:
                # Stage 1: generate bridge candidates
                # NOTE: we do NOT use ``async with uow`` here because
                # generate_bridge_candidates internally calls the
                # EmbeddingIndex which opens its own UoW.  With a
                # single-connection SQLite backend the nested BEGIN
                # would fail.  Reads work without an explicit
                # transaction (SQLite auto-transaction for reads).
                uow1 = self._uow_factory()
                candidates = await generate_bridge_candidates(
                    uow=uow1,
                    left_vault_id=left_id,
                    right_vault_id=right_id,
                    embedding_index=self._embedding_index,
                    policy=policy,
                    id_generator=uow1.id_generator,
                    problem=request.problem,
                    fusion_mode=request.fusion_mode,
                )

                # Stage 2: analyzer validates candidates
                left_context = vault_packs[left_id][1]  # DomainContextPack
                right_context = vault_packs[right_id][1]
                maps, transfers, call_record = await self._analyzer.analyze_candidates(
                    candidates,
                    left_context,
                    right_context,
                    request.problem,
                )
                all_analyzer_calls.append(call_record)

                # Build pair result
                pair_manifest = PairFusionManifest(
                    left_vault_id=left_id,
                    right_vault_id=right_id,
                    left_revision=vault_revisions[left_id],
                    right_revision=vault_revisions[right_id],
                    candidate_count=len(candidates),
                    map_count=len(maps),
                    transfer_count=len(transfers),
                    analyzer_calls=[call_record],
                )
                pair_results.append(
                    PairFusionResult(
                        left_vault_id=left_id,
                        right_vault_id=right_id,
                        candidates_generated=len(candidates),
                        maps_produced=maps,
                        transfers_produced=transfers,
                        pair_manifest=pair_manifest,
                    )
                )

            # ------------------------------------------------------------------
            # 4. Stage 3: synthesize fusion result
            # ------------------------------------------------------------------
            uow_synth = self._uow_factory()
            async with uow_synth:
                manifest_metadata = {
                    "analyzer_version": "mock_v1",
                    "analyzer_calls": all_analyzer_calls,
                    "created_at": uow_synth.clock.now(),
                }
                id_gen_for_synth = uow_synth.id_generator
                await uow_synth.rollback()

            result = await synthesize_fusion_result(
                pair_results=pair_results,
                vault_packs=vault_packs,
                policy=policy,
                request=request,
                manifest_metadata=manifest_metadata,
                id_generator=id_gen_for_synth,
            )

            # ------------------------------------------------------------------
            # 5. Persist FusionRun
            # ------------------------------------------------------------------
            uow2 = self._uow_factory()
            async with uow2:
                fusion_run = FusionRun(
                    fusion_run_id=uow2.id_generator.generate("frun"),
                    vault_ids=request.vault_ids,
                    problem=request.problem,
                    fusion_mode=request.fusion_mode,
                    status="completed",
                    bridge_count=len(result.bridge_concepts),
                    transfer_count=len(result.transfer_opportunities),
                    manifest_id=result.fusion_manifest.manifest_id,
                    policy_version=policy.policy_version,
                    created_at=uow2.clock.now(),
                    completed_at=uow2.clock.now(),
                )
                await uow2.fusion_runs.create(fusion_run)

                # ------------------------------------------------------------------
                # 6. Emit fusion.completed event
                # ------------------------------------------------------------------
                uow2.record_event(
                    uow2.event_factory.create(
                        event_type="fusion.completed",
                        aggregate_type="fusion_run",
                        aggregate_id=fusion_run.fusion_run_id,
                        vault_id=request.vault_ids[0],  # primary vault
                        payload={
                            "vault_ids": [str(v) for v in request.vault_ids],
                            "bridge_count": fusion_run.bridge_count,
                            "transfer_count": fusion_run.transfer_count,
                            "manifest_id": str(result.fusion_manifest.manifest_id),
                            "fusion_mode": request.fusion_mode.value,
                            "problem": request.problem,
                        },
                        actor=self._default_actor,
                    )
                )
                await uow2.commit()

            logger.info(
                "Fusion completed: %s vaults, %d bridges, %d transfers",
                len(request.vault_ids),
                len(result.bridge_concepts),
                len(result.transfer_opportunities),
            )
            return result

        except Exception:
            # ------------------------------------------------------------------
            # Error handling: persist failed FusionRun + emit fusion.failed
            # ------------------------------------------------------------------
            try:
                uow_err = self._uow_factory()
                async with uow_err:
                    fusion_run = FusionRun(
                        fusion_run_id=uow_err.id_generator.generate("frun"),
                        vault_ids=request.vault_ids,
                        problem=request.problem,
                        fusion_mode=request.fusion_mode,
                        status="failed",
                        bridge_count=0,
                        transfer_count=0,
                        manifest_id=None,
                        policy_version=policy.policy_version,
                        created_at=uow_err.clock.now(),
                        completed_at=uow_err.clock.now(),
                    )
                    await uow_err.fusion_runs.create(fusion_run)

                    uow_err.record_event(
                        uow_err.event_factory.create(
                            event_type="fusion.failed",
                            aggregate_type="fusion_run",
                            aggregate_id=fusion_run.fusion_run_id,
                            vault_id=request.vault_ids[0],
                            payload={
                                "vault_ids": [str(v) for v in request.vault_ids],
                                "fusion_mode": request.fusion_mode.value,
                                "problem": request.problem,
                            },
                            actor=self._default_actor,
                        )
                    )
                    await uow_err.commit()
            except Exception:
                logger.exception("Failed to persist failed FusionRun")
            raise
