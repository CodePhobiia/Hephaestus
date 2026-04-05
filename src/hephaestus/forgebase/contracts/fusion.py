"""Fusion contracts — canonical public API types for cross-vault fusion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FusionMode
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)

if TYPE_CHECKING:
    from hephaestus.forgebase.fusion.models import (
        AnalogicalMap,
        FusionManifest,
        PairFusionManifest,
        TransferOpportunity,
    )
    from hephaestus.forgebase.fusion.policy import FusionPolicy


@dataclass
class FusionRequest:
    """Request to perform cross-vault fusion."""

    vault_ids: list[EntityId]
    problem: str | None = None
    fusion_mode: FusionMode = FusionMode.STRICT
    policy: FusionPolicy | None = None
    max_candidates: int = 50
    max_bridges: int = 20
    max_transfers: int = 10


@dataclass
class FusionResult:
    """Complete fusion result with fused packs and manifests."""

    fusion_id: EntityId
    request: FusionRequest
    bridge_concepts: list[AnalogicalMap]
    transfer_opportunities: list[TransferOpportunity]
    fused_baseline: PriorArtBaselinePack
    fused_context: DomainContextPack
    fused_dossier: ConstraintDossierPack
    pair_results: list[PairFusionResult]
    fusion_manifest: FusionManifest
    created_at: datetime


@dataclass
class PairFusionResult:
    """Per-pair sub-result within a multi-vault fusion."""

    left_vault_id: EntityId
    right_vault_id: EntityId
    candidates_generated: int
    maps_produced: list[AnalogicalMap]
    transfers_produced: list[TransferOpportunity]
    pair_manifest: PairFusionManifest
