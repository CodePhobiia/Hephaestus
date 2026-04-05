"""Fusion domain models — all fusion-specific dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hephaestus.forgebase.domain.enums import (
    AnalogyVerdict,
    BridgeCandidateKind,
    FusionMode,
)
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId

# ---------------------------------------------------------------------------
# Value objects for structural mappings
# ---------------------------------------------------------------------------


@dataclass
class ComponentMapping:
    """Maps a component in the left domain to its analog in the right domain."""

    left_component: str
    right_component: str
    left_ref: EntityId | None = None
    right_ref: EntityId | None = None
    mapping_confidence: float = 0.0


@dataclass
class ConstraintMapping:
    """Maps constraints across domains, noting whether they are preserved."""

    left_constraint: str
    right_constraint: str
    preserved: bool = True


@dataclass
class AnalogyBreak:
    """A detected break or limitation in a cross-domain analogy."""

    description: str
    severity: str
    category: str  # structural_mismatch, scale_difference, domain_assumption, temporal_mismatch


# ---------------------------------------------------------------------------
# Stage 1 output
# ---------------------------------------------------------------------------


@dataclass
class BridgeCandidate:
    """A candidate bridge between two vault entities for structural analogy."""

    candidate_id: EntityId
    left_vault_id: EntityId
    right_vault_id: EntityId
    left_entity_ref: EntityId
    right_entity_ref: EntityId
    left_kind: BridgeCandidateKind
    right_kind: BridgeCandidateKind
    similarity_score: float
    retrieval_reason: str
    left_text: str
    right_text: str
    left_claim_refs: list[EntityId] = field(default_factory=list)
    right_claim_refs: list[EntityId] = field(default_factory=list)
    left_source_refs: list[EntityId] = field(default_factory=list)
    right_source_refs: list[EntityId] = field(default_factory=list)
    left_revision_ref: VaultRevisionId | None = None
    right_revision_ref: VaultRevisionId | None = None
    epistemic_filter_passed: bool = True
    problem_relevance: float | None = None


# ---------------------------------------------------------------------------
# Stage 2 output
# ---------------------------------------------------------------------------


@dataclass
class AnalogicalMap:
    """A validated structural analogy between two domains."""

    map_id: EntityId
    bridge_concept: str
    left_structure: str
    right_structure: str
    mapped_components: list[ComponentMapping] = field(default_factory=list)
    mapped_constraints: list[ConstraintMapping] = field(default_factory=list)
    analogy_breaks: list[AnalogyBreak] = field(default_factory=list)
    confidence: float = 0.0
    verdict: AnalogyVerdict = AnalogyVerdict.NO_ANALOGY
    problem_relevance: float | None = None
    source_candidates: list[EntityId] = field(default_factory=list)
    left_page_refs: list[EntityId] = field(default_factory=list)
    right_page_refs: list[EntityId] = field(default_factory=list)
    left_claim_refs: list[EntityId] = field(default_factory=list)
    right_claim_refs: list[EntityId] = field(default_factory=list)


@dataclass
class TransferOpportunity:
    """An identified opportunity to transfer knowledge between domains."""

    opportunity_id: EntityId
    from_vault_id: EntityId
    to_vault_id: EntityId
    mechanism: str
    rationale: str
    caveats: list[str] = field(default_factory=list)
    caveat_categories: list[str] = field(default_factory=list)
    analogical_map_id: EntityId | None = None
    confidence: float = 0.0
    problem_relevance: float | None = None
    from_page_refs: list[EntityId] = field(default_factory=list)
    to_page_refs: list[EntityId] = field(default_factory=list)
    from_claim_refs: list[EntityId] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


@dataclass
class PairFusionManifest:
    """Manifest for a single vault-pair fusion analysis."""

    left_vault_id: EntityId
    right_vault_id: EntityId
    left_revision: VaultRevisionId
    right_revision: VaultRevisionId
    candidate_count: int
    map_count: int
    transfer_count: int
    analyzer_calls: list[BackendCallRecord] = field(default_factory=list)


@dataclass
class FusionManifest:
    """Top-level manifest for a complete fusion run."""

    manifest_id: EntityId
    vault_ids: list[EntityId]
    problem: str | None
    fusion_mode: FusionMode
    candidate_count: int
    analyzed_count: int
    bridge_count: int
    transfer_count: int
    policy_version: str
    analyzer_version: str
    analyzer_calls: list[BackendCallRecord] = field(default_factory=list)
    pair_manifests: list[PairFusionManifest] = field(default_factory=list)
    created_at: datetime | None = None
