"""TransliminalityEngine — top-level orchestrator for the Layer 2 pipeline.

Stages:
  0. Problem conditioning  → RoleSignature
  1. Vault routing         → selected remote vault set
  2. Bridge retrieval      → BridgeCandidate[]
  3. Structural analysis   → AnalogicalMap[], TransferOpportunity[]
  4. Pack assembly         → TransliminalityPack
  5. Injection             → (caller wires into Genesis/DeepForge/Pantheon)
  6. Writeback             → TransliminalityRunManifest
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    BridgeCandidate,
    EntityRef,
    IntegrationScoreBreakdown,
    RoleSignature,
    TransferOpportunity,
    TransliminalityConfig,
    TransliminalityPack,
    TransliminalityRequest,
    TransliminalityRunManifest,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal service protocols
# ---------------------------------------------------------------------------

class ProblemRoleSignatureBuilder(Protocol):
    async def build(
        self,
        problem: str,
        home_vault_ids: list[EntityId],
        branch_id: EntityId | None,
        config: TransliminalityConfig,
    ) -> RoleSignature: ...


class VaultRouter(Protocol):
    async def select_vaults(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        explicit_remote_vault_ids: list[EntityId] | None,
        config: TransliminalityConfig,
    ) -> list[EntityId]: ...


class BridgeRetrieverProtocol(Protocol):
    async def retrieve(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        config: TransliminalityConfig,
    ) -> list[BridgeCandidate]: ...


class FusionAnalyzerAdapter(Protocol):
    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        problem_signature: RoleSignature,
        config: TransliminalityConfig,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity]]: ...


class PackAssemblerProtocol(Protocol):
    async def assemble(
        self,
        run_id: EntityId,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        config: TransliminalityConfig,
    ) -> TransliminalityPack: ...


class IntegrationScorerProtocol(Protocol):
    async def score_pack(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
    ) -> IntegrationScoreBreakdown: ...


class WritebackServiceProtocol(Protocol):
    async def write_back(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        downstream_outcome_refs: list[EntityRef],
    ) -> TransliminalityRunManifest: ...


# ---------------------------------------------------------------------------
# Build result (eliminates mutable engine state — audit fix C-2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuildPackResult:
    """Complete result of stages 0-4, carrying the pack and intermediate artifacts.

    Callers pass this to ``write_back()`` so the engine never stashes
    mutable state between calls.
    """

    pack: TransliminalityPack
    maps: list[AnalogicalMap] = field(default_factory=list)
    opportunities: list[TransferOpportunity] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TransliminalityEngine:
    """Top-level orchestrator for the transliminality pipeline."""

    def __init__(
        self,
        *,
        signature_builder: ProblemRoleSignatureBuilder,
        vault_router: VaultRouter,
        bridge_retriever: BridgeRetrieverProtocol,
        fusion_analyzer: FusionAnalyzerAdapter,
        pack_assembler: PackAssemblerProtocol,
        integration_scorer: IntegrationScorerProtocol,
        writeback_service: WritebackServiceProtocol,
        id_generator: _IdGeneratorProtocol | None = None,
    ) -> None:
        self._signature_builder = signature_builder
        self._vault_router = vault_router
        self._bridge_retriever = bridge_retriever
        self._fusion_analyzer = fusion_analyzer
        self._pack_assembler = pack_assembler
        self._integration_scorer = integration_scorer
        self._writeback_service = writeback_service
        self._id_gen = id_generator

    async def build_pack(
        self,
        request: TransliminalityRequest,
    ) -> BuildPackResult:
        """Execute stages 0-4 and return the pack with intermediate artifacts."""
        config = request.config
        logger.info(
            "transliminality.requested  run_id=%s  mode=%s",
            request.run_id, config.mode,
        )

        # Stage 0 — Problem conditioning
        logger.info("transliminality.stage0  building problem role signature")
        signature = await self._signature_builder.build(
            problem=request.problem,
            home_vault_ids=request.home_vault_ids,
            branch_id=request.branch_id,
            config=config,
        )
        logger.info(
            "transliminality.problem_signature_built  roles=%s",
            [r.value for r in signature.functional_roles],
        )

        # Stage 1 — Vault routing
        logger.info("transliminality.stage1  routing vaults")
        remote_vault_ids = await self._vault_router.select_vaults(
            problem_signature=signature,
            home_vault_ids=request.home_vault_ids,
            explicit_remote_vault_ids=request.remote_vault_ids,
            config=config,
        )
        logger.info(
            "transliminality.vaults_selected  count=%d", len(remote_vault_ids),
        )

        # Stage 2 — Bridge retrieval
        logger.info("transliminality.stage2  retrieving bridge candidates")
        candidates = await self._bridge_retriever.retrieve(
            problem_signature=signature,
            home_vault_ids=request.home_vault_ids,
            remote_vault_ids=remote_vault_ids,
            config=config,
        )
        logger.info(
            "transliminality.bridge_retrieval_completed  candidates=%d",
            len(candidates),
        )

        # Stage 3 — Structural analogy analysis
        logger.info("transliminality.stage3  analyzing candidates")
        shortlist = candidates[: config.analyzed_candidate_limit]
        maps, opportunities = await self._fusion_analyzer.analyze_candidates(
            candidates=shortlist,
            problem_signature=signature,
            config=config,
        )
        logger.info(
            "transliminality.analysis_completed  maps=%d  opportunities=%d",
            len(maps), len(opportunities),
        )

        kept_maps = maps[: config.maps_to_keep]
        kept_opps = opportunities[: config.transfer_opportunities_to_keep]

        # Stage 4 — Pack assembly
        logger.info("transliminality.stage4  assembling pack")
        pack = await self._pack_assembler.assemble(
            run_id=request.run_id,
            problem_signature=signature,
            home_vault_ids=request.home_vault_ids,
            remote_vault_ids=remote_vault_ids,
            maps=kept_maps,
            opportunities=kept_opps,
            config=config,
        )

        # Stage 4b — Integration scoring (audit fix H-2)
        score = await self._integration_scorer.score_pack(pack, kept_maps, kept_opps)
        # Replace the preview score with the real score
        pack = TransliminalityPack(
            pack_id=pack.pack_id,
            run_id=pack.run_id,
            problem_signature_ref=pack.problem_signature_ref,
            home_vault_ids=pack.home_vault_ids,
            remote_vault_ids=pack.remote_vault_ids,
            bridge_candidates=pack.bridge_candidates,
            validated_maps=pack.validated_maps,
            transfer_opportunities=pack.transfer_opportunities,
            strict_baseline_entries=pack.strict_baseline_entries,
            soft_context_entries=pack.soft_context_entries,
            strict_constraint_entries=pack.strict_constraint_entries,
            integration_score_preview=score,
            policy_version=pack.policy_version,
            assembler_version=pack.assembler_version,
            extracted_at=pack.extracted_at,
        )

        logger.info(
            "transliminality.pack_assembled  "
            "strict_baseline=%d  soft_context=%d  strict_constraint=%d",
            len(pack.strict_baseline_entries),
            len(pack.soft_context_entries),
            len(pack.strict_constraint_entries),
        )

        return BuildPackResult(pack=pack, maps=kept_maps, opportunities=kept_opps)

    async def write_back(
        self,
        result: BuildPackResult,
        downstream_outcome_refs: list[EntityRef] | None = None,
    ) -> TransliminalityRunManifest:
        """Execute stage 6 — persist artifacts into ForgeBase."""
        logger.info("transliminality.stage6  writing back artifacts")
        manifest = await self._writeback_service.write_back(
            pack=result.pack,
            maps=result.maps,
            opportunities=result.opportunities,
            downstream_outcome_refs=downstream_outcome_refs or [],
        )
        logger.info(
            "transliminality.writeback_completed  manifest_id=%s",
            manifest.manifest_id,
        )
        return manifest


# Protocol for ID generation (matches existing IdGenerator ABC)
class _IdGeneratorProtocol(Protocol):
    def generate(self, prefix: str) -> EntityId: ...
