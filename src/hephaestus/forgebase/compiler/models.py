"""Extraction and synthesis result schemas."""
from __future__ import annotations
from dataclasses import dataclass, field
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef


@dataclass
class ExtractedClaim:
    statement: str
    segment_ref: EvidenceSegmentRef
    confidence: float
    claim_type: str  # factual, methodological, comparative, limitation


@dataclass
class ExtractedConcept:
    name: str
    aliases: list[str]
    kind: CandidateKind
    evidence_segments: list[EvidenceSegmentRef]
    salience: float


@dataclass
class SourceCardContent:
    summary: str
    key_claims: list[str]
    methods: list[str]
    limitations: list[str]
    evidence_quality: str
    concepts_mentioned: list[str]


@dataclass
class EvidenceGrade:
    strength: float
    methodology_quality: str  # strong, moderate, weak, unknown
    reasoning: str


@dataclass
class SynthesizedClaim:
    statement: str
    support_type: SupportType
    confidence: float
    derived_from_claims: list[str]


@dataclass
class SynthesizedPage:
    title: str
    content_markdown: str
    claims: list[SynthesizedClaim] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)


@dataclass
class OpenQuestion:
    question: str
    context: str
    conflicting_claims: list[str] = field(default_factory=list)
    evidence_gap: str = ""


@dataclass
class ConceptEvidence:
    source_id: EntityId
    source_title: str
    claims: list[str]
    segments: list[EvidenceSegmentRef]
