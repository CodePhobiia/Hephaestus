"""ForgeBase domain models — all core entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hephaestus.forgebase.domain.enums import (
    ActorType,
    BranchPurpose,
    CandidateKind,
    CandidateStatus,
    ClaimStatus,
    DirtyTargetKind,
    EntityKind,
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    JobKind,
    JobStatus,
    LinkKind,
    MergeResolution,
    MergeVerdict,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
    WorkbookStatus,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    BlobRef,
    ContentHash,
    EntityId,
    EvidenceSegmentRef,
    VaultRevisionId,
    Version,
)


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------

@dataclass
class Vault:
    vault_id: EntityId
    name: str
    description: str
    head_revision_id: VaultRevisionId
    created_at: datetime
    updated_at: datetime
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class VaultRevision:
    revision_id: VaultRevisionId
    vault_id: EntityId
    parent_revision_id: VaultRevisionId | None
    created_at: datetime
    created_by: ActorRef
    causation_event_id: EntityId | None
    summary: str


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

@dataclass
class Source:
    source_id: EntityId
    vault_id: EntityId
    format: SourceFormat
    origin_locator: str | None
    created_at: datetime


@dataclass
class SourceVersion:
    source_id: EntityId
    version: Version
    title: str
    authors: list[str]
    url: str | None
    raw_artifact_ref: BlobRef
    normalized_ref: BlobRef | None
    content_hash: ContentHash
    metadata: dict[str, Any]
    trust_tier: SourceTrustTier
    status: SourceStatus
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@dataclass
class Page:
    page_id: EntityId
    vault_id: EntityId
    page_type: PageType
    page_key: str
    created_at: datetime
    created_by_run: EntityId | None = None


@dataclass
class PageVersion:
    page_id: EntityId
    version: Version
    title: str
    content_ref: BlobRef
    content_hash: ContentHash
    summary: str
    compiled_from: list[EntityId]
    created_at: datetime
    created_by: ActorRef
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    claim_id: EntityId
    vault_id: EntityId
    page_id: EntityId
    created_at: datetime


@dataclass
class ClaimVersion:
    claim_id: EntityId
    version: Version
    statement: str
    status: ClaimStatus
    support_type: SupportType
    confidence: float
    validated_at: datetime
    fresh_until: datetime | None
    created_at: datetime
    created_by: ActorRef


@dataclass
class ClaimSupport:
    support_id: EntityId
    claim_id: EntityId
    source_id: EntityId
    source_segment: str | None
    strength: float
    created_at: datetime
    created_by: ActorRef


@dataclass
class ClaimDerivation:
    derivation_id: EntityId
    claim_id: EntityId
    parent_claim_id: EntityId
    relationship: str
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------

@dataclass
class Link:
    link_id: EntityId
    vault_id: EntityId
    kind: LinkKind
    created_at: datetime


@dataclass
class LinkVersion:
    link_id: EntityId
    version: Version
    source_entity: EntityId
    target_entity: EntityId
    label: str | None
    weight: float
    created_at: datetime
    created_by: ActorRef


# ---------------------------------------------------------------------------
# Workbook (= Branch)
# ---------------------------------------------------------------------------

@dataclass
class Workbook:
    workbook_id: EntityId
    vault_id: EntityId
    name: str
    purpose: BranchPurpose
    status: WorkbookStatus
    base_revision_id: VaultRevisionId
    created_at: datetime
    created_by: ActorRef
    created_by_run: EntityId | None = None


# ---------------------------------------------------------------------------
# Branch heads and tombstones
# ---------------------------------------------------------------------------

@dataclass
class BranchPageHead:
    workbook_id: EntityId
    page_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchClaimHead:
    workbook_id: EntityId
    claim_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchLinkHead:
    workbook_id: EntityId
    link_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchSourceHead:
    workbook_id: EntityId
    source_id: EntityId
    head_version: Version
    base_version: Version


@dataclass
class BranchClaimSupportHead:
    workbook_id: EntityId
    support_id: EntityId
    created_on_branch: bool


@dataclass
class BranchClaimDerivationHead:
    workbook_id: EntityId
    derivation_id: EntityId
    created_on_branch: bool


@dataclass
class BranchTombstone:
    workbook_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    tombstoned_at: datetime


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

@dataclass
class MergeProposal:
    merge_id: EntityId
    workbook_id: EntityId
    vault_id: EntityId
    base_revision_id: VaultRevisionId
    target_revision_id: VaultRevisionId
    verdict: MergeVerdict
    resulting_revision: VaultRevisionId | None
    proposed_at: datetime
    resolved_at: datetime | None
    proposed_by: ActorRef


@dataclass
class MergeConflict:
    conflict_id: EntityId
    merge_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    base_version: Version
    branch_version: Version
    canonical_version: Version
    resolution: MergeResolution | None = None
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@dataclass
class Job:
    job_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    kind: JobKind
    status: JobStatus
    config: dict[str, Any]
    idempotency_key: str
    priority: int
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    leased_until: datetime | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_by: ActorRef
    created_by_run: EntityId | None = None


@dataclass
class LintFinding:
    finding_id: EntityId
    job_id: EntityId
    vault_id: EntityId
    category: FindingCategory
    severity: FindingSeverity
    page_id: EntityId | None
    claim_id: EntityId | None
    description: str
    suggested_action: str | None
    status: FindingStatus
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Run integration
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeRunRef:
    ref_id: EntityId
    vault_id: EntityId
    run_id: str
    run_type: str
    upstream_system: str
    upstream_ref: str | None
    source_hash: str | None
    sync_status: str
    sync_error: str | None
    synced_at: datetime | None
    created_at: datetime


@dataclass
class KnowledgeRunArtifact:
    ref_id: EntityId
    entity_kind: EntityKind
    entity_id: EntityId
    role: str


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@dataclass
class DomainEvent:
    event_id: EntityId
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: EntityId
    aggregate_version: Version | None
    vault_id: EntityId
    workbook_id: EntityId | None
    run_id: str | None
    causation_id: EntityId | None
    correlation_id: str | None
    actor_type: ActorType
    actor_id: str
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass
class EventDelivery:
    event_id: EntityId
    consumer_name: str
    status: str
    attempt_count: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    delivered_at: datetime | None


# ---------------------------------------------------------------------------
# Backend call metadata
# ---------------------------------------------------------------------------

@dataclass
class BackendCallRecord:
    model_name: str
    backend_kind: str
    prompt_id: str
    prompt_version: str
    schema_version: int
    repair_invoked: bool
    input_tokens: int
    output_tokens: int
    duration_ms: int
    raw_output_ref: BlobRef | None = None


# ---------------------------------------------------------------------------
# Concept candidates
# ---------------------------------------------------------------------------

@dataclass
class ConceptCandidate:
    candidate_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    source_id: EntityId
    source_version: Version
    source_compile_job_id: EntityId
    name: str
    normalized_name: str
    aliases: list[str]
    candidate_kind: CandidateKind
    confidence: float
    salience: float
    status: CandidateStatus
    resolved_page_id: EntityId | None
    compiler_policy_version: str
    created_at: datetime


@dataclass
class ConceptCandidateEvidence:
    evidence_id: EntityId
    candidate_id: EntityId
    segment_ref: EvidenceSegmentRef
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Dirty tracking
# ---------------------------------------------------------------------------

@dataclass
class SynthesisDirtyMarker:
    marker_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    target_kind: DirtyTargetKind
    target_key: str
    first_dirtied_at: datetime
    last_dirtied_at: datetime
    times_dirtied: int
    last_dirtied_by_source: EntityId
    last_dirtied_by_job: EntityId
    consumed_by_job: EntityId | None
    consumed_at: datetime | None


# ---------------------------------------------------------------------------
# Compile manifests
# ---------------------------------------------------------------------------

@dataclass
class SourceCompileManifest:
    manifest_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    source_id: EntityId
    source_version: Version
    job_id: EntityId
    compiler_policy_version: str
    prompt_versions: dict[str, str]
    backend_calls: list[BackendCallRecord]
    claim_count: int
    concept_count: int
    relationship_count: int
    source_content_hash: ContentHash
    created_at: datetime


@dataclass
class VaultSynthesisManifest:
    manifest_id: EntityId
    vault_id: EntityId
    workbook_id: EntityId | None
    job_id: EntityId
    base_revision: VaultRevisionId
    synthesis_policy_version: str
    prompt_versions: dict[str, str]
    backend_calls: list[BackendCallRecord]
    candidates_resolved: int
    augmentor_calls: int
    created_at: datetime
