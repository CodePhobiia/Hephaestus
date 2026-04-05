"""Transliminality factory — the only composition root for the subsystem.

All service implementations are wired here.  Phase 1 provides stub
implementations; Phase 2 adds real LLM-backed and fusion-backed services.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator, UlidIdGenerator
from hephaestus.transliminality.domain.enums import SignatureSubjectKind
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    BridgeCandidate,
    EntityRef,
    IntegrationScoreBreakdown,
    RoleSignature,
    TransferOpportunity,
    TransliminalityConfig,
    TransliminalityPack,
    TransliminalityRunManifest,
)
from hephaestus.transliminality.service.engine import TransliminalityEngine

if TYPE_CHECKING:
    from hephaestus.deepforge.harness import DeepForgeHarness
    from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
    from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stub implementations (used when real deps not available)
# ---------------------------------------------------------------------------

class _StubSignatureBuilder:
    """Returns a minimal role signature. Replaced by LLMProblemRoleSignatureBuilder."""

    def __init__(self, id_gen: IdGenerator) -> None:
        self._id_gen = id_gen

    async def build(
        self,
        problem: str,
        home_vault_ids: list[EntityId],
        branch_id: EntityId | None,
        config: TransliminalityConfig,
    ) -> RoleSignature:
        sig_id = self._id_gen.generate("sig")
        subject_ref = EntityRef(entity_id=sig_id, entity_kind="problem")
        return RoleSignature(
            signature_id=sig_id,
            subject_ref=subject_ref,
            subject_kind=SignatureSubjectKind.PROBLEM,
            confidence=0.0,
            policy_version=config.mode.value,
        )


class _StubVaultRouter:
    """Returns explicitly requested vaults or empty list."""

    async def select_vaults(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        explicit_remote_vault_ids: list[EntityId] | None,
        config: TransliminalityConfig,
    ) -> list[EntityId]:
        if explicit_remote_vault_ids:
            return explicit_remote_vault_ids[: config.max_remote_vaults]
        return []


class _StubBridgeRetriever:
    """Returns no candidates. Replaced by FusionBridgeRetriever."""

    async def retrieve(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        config: TransliminalityConfig,
    ) -> list[BridgeCandidate]:
        return []


class _StubFusionAnalyzer:
    """Returns no maps. Phase 3 replaces with real analyzer adapter."""

    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        problem_signature: RoleSignature,
        config: TransliminalityConfig,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity]]:
        return [], []


class _StubPackAssembler:
    """Assembles an empty pack. Phase 3 replaces with real assembler."""

    def __init__(self, id_gen: IdGenerator) -> None:
        self._id_gen = id_gen

    async def assemble(
        self,
        run_id: EntityId,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        config: TransliminalityConfig,
    ) -> TransliminalityPack:
        pack_id = self._id_gen.generate("tpack")
        sig_ref = EntityRef(
            entity_id=problem_signature.signature_id,
            entity_kind="role_signature",
        )
        return TransliminalityPack(
            pack_id=pack_id,
            run_id=run_id,
            problem_signature_ref=sig_ref,
            home_vault_ids=list(home_vault_ids),
            remote_vault_ids=list(remote_vault_ids),
        )


class _StubIntegrationScorer:
    """Returns zeroed scores. Phase 4 replaces with real scorer."""

    async def score_pack(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
    ) -> IntegrationScoreBreakdown:
        return IntegrationScoreBreakdown()


class _StubWritebackService:
    """Logs but does not persist. Phase 5 replaces with ForgeBase writeback."""

    def __init__(self, id_gen: IdGenerator) -> None:
        self._id_gen = id_gen

    async def write_back(
        self,
        pack: TransliminalityPack,
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        downstream_outcome_refs: list[EntityRef],
    ) -> TransliminalityRunManifest:
        manifest_id = self._id_gen.generate("tman")
        logger.info(
            "stub writeback: pack_id=%s (no-op, Phase 5 will persist)",
            pack.pack_id,
        )
        return TransliminalityRunManifest(
            manifest_id=manifest_id,
            run_id=pack.run_id,
            policy_version=pack.policy_version,
            assembler_version=pack.assembler_version,
            selected_vaults=list(pack.remote_vault_ids),
            candidate_count=len(pack.bridge_candidates),
            valid_map_count=0,
            rejected_map_count=0,
            transfer_opportunity_count=len(pack.transfer_opportunities),
            injected_pack_ref=EntityRef(
                entity_id=pack.pack_id,
                entity_kind="transliminality_pack",
            ),
            downstream_outcome_refs=list(downstream_outcome_refs),
        )


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def create_engine(
    *,
    config: TransliminalityConfig | None = None,
    id_generator: IdGenerator | None = None,
) -> TransliminalityEngine:
    """Create a TransliminalityEngine with stub service wiring.

    Use this for testing or when ForgeBase/DeepForge are not available.
    For production, use ``create_engine_with_deps()``.
    """
    id_gen = id_generator or UlidIdGenerator()

    return TransliminalityEngine(
        signature_builder=_StubSignatureBuilder(id_gen),
        vault_router=_StubVaultRouter(),
        bridge_retriever=_StubBridgeRetriever(),
        fusion_analyzer=_StubFusionAnalyzer(),
        pack_assembler=_StubPackAssembler(id_gen),
        integration_scorer=_StubIntegrationScorer(),
        writeback_service=_StubWritebackService(id_gen),
        id_generator=id_gen,
    )


def create_engine_with_harness(
    *,
    harness: DeepForgeHarness,
    id_generator: IdGenerator | None = None,
) -> TransliminalityEngine:
    """Create a TransliminalityEngine with LLM-backed services but no ForgeBase.

    Uses the harness for:
    - Role signature extraction (LLM-backed)
    - Analogy validation (LLM-backed)
    - Transfer synthesis (LLM-backed)
    - Counterfactual + non-ornamental evaluation (LLM-backed)
    - Real pack assembler + integration scorer

    Stubs only for ForgeBase-dependent services:
    - Vault router (no vaults → returns empty)
    - Bridge retriever (no embeddings → returns empty)
    - Writeback (no persistence → logs only)

    This is the correct factory for CLI usage where ForgeBase is not running.
    """
    from hephaestus.transliminality.adapters.fusion_analyzer import LLMFusionAnalyzerAdapter
    from hephaestus.transliminality.service.integration_scorer import HeuristicIntegrationScorer
    from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator
    from hephaestus.transliminality.service.pack_assembler import ChannelPackAssembler
    from hephaestus.transliminality.service.problem_signature_builder import (
        LLMProblemRoleSignatureBuilder,
    )

    id_gen = id_generator or UlidIdGenerator()

    return TransliminalityEngine(
        signature_builder=LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=id_gen,
        ),
        vault_router=_StubVaultRouter(),
        bridge_retriever=_StubBridgeRetriever(),
        fusion_analyzer=LLMFusionAnalyzerAdapter(
            harness=harness,
            id_generator=id_gen,
        ),
        pack_assembler=ChannelPackAssembler(id_generator=id_gen),
        integration_scorer=HeuristicIntegrationScorer(
            llm_evaluator=LLMIntegrationEvaluator(harness=harness),
        ),
        writeback_service=_StubWritebackService(id_gen),
        id_generator=id_gen,
    )


def create_engine_with_deps(
    *,
    harness: DeepForgeHarness,
    uow_factory: Callable[[], AbstractUnitOfWork],
    embedding_index: EmbeddingIndex,
    id_generator: IdGenerator | None = None,
) -> TransliminalityEngine:
    """Create a TransliminalityEngine with real Phase 2 services.

    Requires:
    - harness: DeepForgeHarness for LLM-backed role signature extraction
    - uow_factory: ForgeBase UoW factory for vault access
    - embedding_index: For fusion-based bridge retrieval

    All stages use real implementations. The only stub remaining is the
    fusion analyzer (future: LLM-backed structural analogy validation).
    """
    from hephaestus.transliminality.adapters.forgebase import ForgeBaseVaultAdapter
    from hephaestus.transliminality.adapters.fusion_analyzer import LLMFusionAnalyzerAdapter
    from hephaestus.transliminality.service.bridge_retriever import FusionBridgeRetriever
    from hephaestus.transliminality.service.integration_scorer import HeuristicIntegrationScorer
    from hephaestus.transliminality.service.llm_evaluator import LLMIntegrationEvaluator
    from hephaestus.transliminality.service.pack_assembler import ChannelPackAssembler
    from hephaestus.transliminality.service.problem_signature_builder import (
        LLMProblemRoleSignatureBuilder,
    )
    from hephaestus.transliminality.service.vault_router import MetadataVaultRouter
    from hephaestus.transliminality.service.writeback import ForgeBaseWritebackService

    id_gen = id_generator or UlidIdGenerator()
    vault_adapter = ForgeBaseVaultAdapter(uow_factory)

    return TransliminalityEngine(
        signature_builder=LLMProblemRoleSignatureBuilder(
            harness=harness,
            id_generator=id_gen,
        ),
        vault_router=MetadataVaultRouter(vault_adapter=vault_adapter),
        bridge_retriever=FusionBridgeRetriever(
            uow_factory=uow_factory,
            embedding_index=embedding_index,
            id_generator=id_gen,
        ),
        fusion_analyzer=LLMFusionAnalyzerAdapter(
            harness=harness,
            id_generator=id_gen,
        ),
        pack_assembler=ChannelPackAssembler(id_generator=id_gen),
        integration_scorer=HeuristicIntegrationScorer(
            llm_evaluator=LLMIntegrationEvaluator(harness=harness),
        ),
        writeback_service=ForgeBaseWritebackService(
            uow_factory=uow_factory,
            id_generator=id_gen,
        ),
        id_generator=id_gen,
    )
