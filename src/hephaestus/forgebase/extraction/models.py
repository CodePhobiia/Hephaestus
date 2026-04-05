"""Extraction pack models — typed internal structures for vault knowledge extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hephaestus.forgebase.domain.enums import ProvenanceKind
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId


@dataclass
class PackEntry:
    """Typed internal entry for extraction packs.

    Each entry represents a piece of vault knowledge with full provenance
    metadata. Rendering to strings happens at the injection boundary,
    not here in the domain model.
    """

    text: str
    origin_kind: str
    claim_ids: list[EntityId]
    page_ids: list[EntityId]
    source_refs: list[EntityId]
    epistemic_state: str
    trust_tier: str
    salience: float
    provenance_kind: ProvenanceKind


@dataclass
class PriorArtBaselinePack:
    """Strictest extraction channel — prior-art baselines for DeepForge.

    Only SUPPORTED claims from VERIFIED inventions and AUTHORITATIVE
    external sources. No hypotheses, no contested, no rejected.
    """

    entries: list[PackEntry]
    vault_id: EntityId
    vault_revision_id: VaultRevisionId
    branch_id: EntityId | None
    extraction_policy_version: str
    assembler_version: str
    extracted_at: datetime


@dataclass
class DomainContextPack:
    """Broadest extraction channel — domain context for LensSelector.

    Includes hypotheses, open questions, explored directions.
    Rejected inventions enter explored_directions as summaries only.
    All categories have policy-driven max counts with salience ranking.
    """

    concepts: list[PackEntry]
    mechanisms: list[PackEntry]
    open_questions: list[PackEntry]
    explored_directions: list[PackEntry]
    vault_id: EntityId
    vault_revision_id: VaultRevisionId
    branch_id: EntityId | None
    extraction_policy_version: str
    assembler_version: str
    extracted_at: datetime


@dataclass
class ConstraintDossierPack:
    """Governance-grade extraction channel — constraints for Pantheon dossier.

    Evidence-backed constraints, known failures, validated objections,
    unresolved controversies (explicitly labeled), competitive landscape.
    """

    hard_constraints: list[PackEntry]
    known_failure_modes: list[PackEntry]
    validated_objections: list[PackEntry]
    unresolved_controversies: list[PackEntry]
    competitive_landscape: list[PackEntry]
    vault_id: EntityId
    vault_revision_id: VaultRevisionId
    branch_id: EntityId | None
    extraction_policy_version: str
    assembler_version: str
    extracted_at: datetime
