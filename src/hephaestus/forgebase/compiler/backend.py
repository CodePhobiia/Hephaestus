"""CompilerBackend ABC — structured extraction interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from hephaestus.forgebase.compiler.models import (
    ConceptEvidence, EvidenceGrade, ExtractedClaim, ExtractedConcept,
    OpenQuestion, SourceCardContent, SynthesizedPage,
)
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EvidenceSegmentRef


class CompilerBackend(ABC):
    """Structured extraction backend for the ForgeBase compiler."""

    # ------------------------------------------------------------------
    # Tier 1: per-source extraction
    # ------------------------------------------------------------------

    @abstractmethod
    async def extract_claims(
        self, source_text: str, source_metadata: dict,
    ) -> tuple[list[ExtractedClaim], BackendCallRecord]: ...

    @abstractmethod
    async def extract_concepts(
        self, source_text: str, source_metadata: dict,
    ) -> tuple[list[ExtractedConcept], BackendCallRecord]: ...

    @abstractmethod
    async def generate_source_card(
        self, source_text: str, source_metadata: dict,
        extracted_claims: list[ExtractedClaim],
        extracted_concepts: list[ExtractedConcept],
    ) -> tuple[SourceCardContent, BackendCallRecord]: ...

    @abstractmethod
    async def grade_evidence(
        self, claim: str, segment_ref: EvidenceSegmentRef, source_text: str,
    ) -> tuple[EvidenceGrade, BackendCallRecord]: ...

    # ------------------------------------------------------------------
    # Tier 2: vault-wide synthesis
    # ------------------------------------------------------------------

    @abstractmethod
    async def synthesize_concept_page(
        self, concept_name: str, evidence: list[ConceptEvidence],
        existing_claims: list[str], related_concepts: list[str],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_mechanism_page(
        self, mechanism_name: str, causal_claims: list[str],
        source_evidence: list[ConceptEvidence], policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_comparison_page(
        self, entities: list[str], comparison_data: list[dict],
        policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def synthesize_timeline_page(
        self, topic: str, temporal_claims: list[str], policy: object,
    ) -> tuple[SynthesizedPage, BackendCallRecord]: ...

    @abstractmethod
    async def identify_open_questions(
        self, contested_claims: list[str], evidence_gaps: list[str],
        policy: object,
    ) -> tuple[list[OpenQuestion], BackendCallRecord]: ...
