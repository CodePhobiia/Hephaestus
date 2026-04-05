"""Transliminality domain models — frozen dataclasses, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    BridgeEntityKind,
    ConstraintTag,
    ControlPatternTag,
    EpistemicState,
    FailureModeTag,
    PackOriginKind,
    RetrievalReason,
    RoleTag,
    SignatureSubjectKind,
    TimeScaleTag,
    TopologyTag,
    TransliminalityMode,
    TrustTier,
)

# ---------------------------------------------------------------------------
# Cross-aggregate reference
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EntityRef:
    """Cross-aggregate reference to an entity, optionally scoped to a vault."""

    entity_id: EntityId
    entity_kind: str
    vault_id: EntityId | None = None

    def __str__(self) -> str:
        base = f"{self.entity_kind}:{self.entity_id}"
        if self.vault_id:
            return f"{self.vault_id}/{base}"
        return base


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransliminalityConfig:
    """Configuration for a transliminality engine run."""

    enabled: bool = True
    mode: TransliminalityMode = TransliminalityMode.BALANCED

    # Vault routing
    home_vault_ids: list[EntityId] = field(default_factory=list)
    remote_vault_ids: list[EntityId] | None = None
    auto_select_remote_vaults: bool = True
    max_remote_vaults: int = 3

    # Problem conditioning
    require_problem_conditioning: bool = True

    # Retrieval and analysis limits
    prefilter_top_k: int = 40
    analyzed_candidate_limit: int = 12
    maps_to_keep: int = 6
    transfer_opportunities_to_keep: int = 4

    # Channel confidence thresholds
    strict_channel_min_confidence: float = 0.80
    soft_channel_min_confidence: float = 0.50

    # Content policy
    allow_hypothesis_in_soft_channel: bool = True
    allow_candidates_in_soft_channel: bool = False

    # Validation
    enforce_counterfactual_check: bool = True
    write_back_artifacts: bool = True


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransliminalityRequest:
    """Input to a transliminality engine run."""

    run_id: EntityId
    problem: str
    home_vault_ids: list[EntityId]
    config: TransliminalityConfig
    remote_vault_ids: list[EntityId] | None = None
    branch_id: EntityId | None = None
    vault_revision_ids: list[EntityId] | None = None


# ---------------------------------------------------------------------------
# Role signatures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalTag:
    """A named input or output signal of a mechanism."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class ResourceTag:
    """A resource consumed or produced by a mechanism."""

    name: str
    direction: str = "consumed"  # consumed | produced | both
    description: str = ""


@dataclass(frozen=True)
class RoleSignature:
    """Functional identity of a problem, mechanism, concept, or artifact.

    Role signatures enable structural (not lexical) cross-domain matching.
    """

    signature_id: EntityId
    subject_ref: EntityRef
    subject_kind: SignatureSubjectKind

    vault_id: EntityId | None = None
    branch_id: EntityId | None = None
    vault_revision_id: EntityId | None = None

    functional_roles: list[RoleTag] = field(default_factory=list)
    inputs: list[SignalTag] = field(default_factory=list)
    outputs: list[SignalTag] = field(default_factory=list)
    constraints: list[ConstraintTag] = field(default_factory=list)
    failure_modes: list[FailureModeTag] = field(default_factory=list)
    control_patterns: list[ControlPatternTag] = field(default_factory=list)
    timescale: TimeScaleTag | None = None
    resource_profile: list[ResourceTag] = field(default_factory=list)
    topology: list[TopologyTag] = field(default_factory=list)

    confidence: float = 0.0
    provenance_refs: list[EntityRef] = field(default_factory=list)

    policy_version: str = "1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Bridge candidates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BridgeCandidate:
    """Candidate bridge prior to deep analogy validation."""

    candidate_id: EntityId

    left_ref: EntityRef
    right_ref: EntityRef
    left_signature_ref: EntityRef
    right_signature_ref: EntityRef

    left_kind: BridgeEntityKind
    right_kind: BridgeEntityKind

    retrieval_reason: RetrievalReason
    similarity_score: float

    left_claim_refs: list[EntityRef] = field(default_factory=list)
    right_claim_refs: list[EntityRef] = field(default_factory=list)
    left_source_refs: list[EntityRef] = field(default_factory=list)
    right_source_refs: list[EntityRef] = field(default_factory=list)

    left_revision_ref: EntityId | None = None
    right_revision_ref: EntityId | None = None

    epistemic_filter_passed: bool = True


# ---------------------------------------------------------------------------
# Analogy analysis
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComponentMapping:
    """A single component-to-component mapping within an analogy."""

    left_component_ref: EntityRef | None
    right_component_ref: EntityRef | None
    shared_role: str
    mapping_rationale: str


@dataclass(frozen=True)
class AnalogyBreak:
    """A point where an analogy between two domains breaks down."""

    category: AnalogyBreakCategory
    description: str
    affected_constraint: str | None = None
    severity: float = 0.0


@dataclass(frozen=True)
class AnalogicalMap:
    """A validated structural analogy between two domain entities."""

    map_id: EntityId
    candidate_ref: EntityRef

    shared_role: str
    mapped_components: list[ComponentMapping] = field(default_factory=list)

    preserved_constraints: list[str] = field(default_factory=list)
    broken_constraints: list[str] = field(default_factory=list)
    analogy_breaks: list[AnalogyBreak] = field(default_factory=list)

    structural_alignment_score: float = 0.0
    constraint_carryover_score: float = 0.0
    grounding_score: float = 0.0
    confidence: float = 0.0

    verdict: AnalogicalVerdict = AnalogicalVerdict.INVALID
    rationale: str = ""

    provenance_refs: list[EntityRef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transfer opportunities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransferCaveat:
    """A caveat or warning about a transfer opportunity."""

    category: str
    description: str
    severity: float = 0.0


@dataclass(frozen=True)
class TransferOpportunity:
    """An identified opportunity to transfer a mechanism across domains."""

    opportunity_id: EntityId
    map_ref: EntityRef

    title: str
    transferred_mechanism: str
    target_problem_fit: str

    expected_benefit: str
    required_transformations: list[str] = field(default_factory=list)
    caveats: list[TransferCaveat] = field(default_factory=list)

    confidence: float = 0.0
    epistemic_state: EpistemicState = EpistemicState.HYPOTHESIS

    supporting_refs: list[EntityRef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Knowledge pack entries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnowledgePackEntry:
    """A single entry in a transliminality knowledge pack."""

    entry_id: EntityId
    text: str

    origin_kind: PackOriginKind
    claim_ids: list[EntityId] = field(default_factory=list)
    page_ids: list[EntityId] = field(default_factory=list)
    source_refs: list[EntityRef] = field(default_factory=list)

    epistemic_state: EpistemicState = EpistemicState.VALIDATED
    trust_tier: TrustTier = TrustTier.INTERNAL_VERIFIED
    salience: float = 0.0


# ---------------------------------------------------------------------------
# Integration scoring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegrationScoreBreakdown:
    """Six-dimension integration score for cross-domain synthesis quality."""

    structural_alignment: float = 0.0
    constraint_fidelity: float = 0.0
    source_grounding: float = 0.0
    counterfactual_dependence: float = 0.0
    bidirectional_explainability: float = 0.0
    non_ornamental_use: float = 0.0


# ---------------------------------------------------------------------------
# Transliminality pack (the main output)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransliminalityPack:
    """Assembled invention-time context from the transliminality engine.

    This is the primary output of the engine — injected into DeepForge,
    lens selection, Genesis, and Pantheon.
    """

    pack_id: EntityId
    run_id: EntityId

    problem_signature_ref: EntityRef

    home_vault_ids: list[EntityId] = field(default_factory=list)
    remote_vault_ids: list[EntityId] = field(default_factory=list)

    bridge_candidates: list[EntityRef] = field(default_factory=list)
    validated_maps: list[EntityRef] = field(default_factory=list)
    transfer_opportunities: list[EntityRef] = field(default_factory=list)

    # Three-channel output
    strict_baseline_entries: list[KnowledgePackEntry] = field(default_factory=list)
    soft_context_entries: list[KnowledgePackEntry] = field(default_factory=list)
    strict_constraint_entries: list[KnowledgePackEntry] = field(default_factory=list)

    integration_score_preview: IntegrationScoreBreakdown = field(
        default_factory=IntegrationScoreBreakdown,
    )
    policy_version: str = "1.0"
    assembler_version: str = "1.0"

    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransliminalityRunManifest:
    """Audit record for a transliminality engine run."""

    manifest_id: EntityId
    run_id: EntityId

    policy_version: str = "1.0"
    assembler_version: str = "1.0"
    scorer_version: str = "1.0"

    selected_vaults: list[EntityId] = field(default_factory=list)
    candidate_count: int = 0
    analyzed_count: int = 0
    valid_map_count: int = 0
    rejected_map_count: int = 0
    transfer_opportunity_count: int = 0

    injected_pack_ref: EntityRef | None = None
    downstream_outcome_refs: list[EntityRef] = field(default_factory=list)

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Vault metadata (used by vault router — domain value, no I/O)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VaultMetadata:
    """Lightweight vault metadata for routing decisions."""

    vault_id: EntityId
    name: str
    description: str
    domain: str = ""
    tags: tuple[str, ...] = ()

    @property
    def text_summary(self) -> str:
        """Concatenated text for scoring against problem signatures."""
        parts = [self.name, self.description]
        if self.domain:
            parts.append(self.domain)
        if self.tags:
            parts.append(" ".join(self.tags))
        return " ".join(parts).lower()
