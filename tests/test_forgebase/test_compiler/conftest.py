"""Shared fixtures for compiler tests."""
from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from hephaestus.forgebase.compiler.backend import CompilerBackend
from hephaestus.forgebase.compiler.models import (
    ConceptEvidence,
    EvidenceGrade,
    ExtractedClaim,
    ExtractedConcept,
    OpenQuestion,
    SourceCardContent,
    SynthesizedClaim,
    SynthesizedPage,
)
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version
from hephaestus.forgebase.store.sqlite.schema import initialize_schema


@pytest.fixture
async def sqlite_db(tmp_path: Path):
    """File-backed SQLite database with WAL mode for realistic testing."""
    db_path = tmp_path / "forgebase_compiler_test.db"
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    await initialize_schema(db)
    yield db
    await db.close()


# -------------------------------------------------------------------
# MockCompilerBackend
# -------------------------------------------------------------------


class MockCompilerBackend(CompilerBackend):
    """Returns deterministic results for testing."""

    def _call_record(self, prompt_id: str) -> BackendCallRecord:
        return BackendCallRecord(
            model_name="mock",
            backend_kind="mock",
            prompt_id=prompt_id,
            prompt_version="1.0.0",
            schema_version=1,
            repair_invoked=False,
            input_tokens=100,
            output_tokens=50,
            duration_ms=10,
            raw_output_ref=None,
        )

    async def extract_claims(self, source_text, source_metadata):
        claims = [
            ExtractedClaim(
                statement=f"Claim from: {source_text[:30]}",
                segment_ref=EvidenceSegmentRef(
                    source_id=EntityId(
                        source_metadata.get(
                            "source_id", "source_00000000000000000000000001"
                        )
                    ),
                    source_version=Version(
                        source_metadata.get("source_version", 1)
                    ),
                    segment_start=0,
                    segment_end=min(100, len(source_text)),
                    section_key=None,
                    preview_text=source_text[:100],
                ),
                confidence=0.9,
                claim_type="factual",
            )
        ]
        return claims, self._call_record("claim_extraction")

    async def extract_concepts(self, source_text, source_metadata):
        concepts = [
            ExtractedConcept(
                name="Test Concept",
                aliases=["TC"],
                kind=CandidateKind.CONCEPT,
                evidence_segments=[
                    EvidenceSegmentRef(
                        source_id=EntityId(
                            source_metadata.get(
                                "source_id", "source_00000000000000000000000001"
                            )
                        ),
                        source_version=Version(
                            source_metadata.get("source_version", 1)
                        ),
                        segment_start=0,
                        segment_end=50,
                        section_key=None,
                        preview_text=source_text[:50],
                    )
                ],
                salience=0.85,
            )
        ]
        return concepts, self._call_record("concept_extraction")

    async def generate_source_card(
        self, source_text, source_metadata, extracted_claims, extracted_concepts
    ):
        card = SourceCardContent(
            summary=f"Summary of source with {len(extracted_claims)} claims",
            key_claims=[c.statement for c in extracted_claims],
            methods=["Test method"],
            limitations=["Test limitation"],
            evidence_quality="moderate",
            concepts_mentioned=[c.name for c in extracted_concepts],
        )
        return card, self._call_record("source_card")

    async def grade_evidence(self, claim, segment_ref, source_text):
        return (
            EvidenceGrade(
                strength=0.8,
                methodology_quality="moderate",
                reasoning="Mock",
            ),
            self._call_record("evidence_grading"),
        )

    async def synthesize_concept_page(
        self, concept_name, evidence, existing_claims, related_concepts, policy
    ):
        page = SynthesizedPage(
            title=concept_name,
            content_markdown=f"# {concept_name}\n\nSynthesized from {len(evidence)} sources.",
            claims=[
                SynthesizedClaim(
                    statement=f"{concept_name} is well-established",
                    support_type=SupportType.SYNTHESIZED,
                    confidence=0.85,
                    derived_from_claims=[
                        c for e in evidence for c in e.claims[:1]
                    ],
                )
            ],
            related_concepts=related_concepts[:3],
        )
        return page, self._call_record("synthesis")

    async def synthesize_mechanism_page(
        self, mechanism_name, causal_claims, source_evidence, policy
    ):
        page = SynthesizedPage(
            title=mechanism_name,
            content_markdown=f"# {mechanism_name}\n\nMechanism.",
        )
        return page, self._call_record("synthesis")

    async def synthesize_comparison_page(self, entities, comparison_data, policy):
        page = SynthesizedPage(
            title=f"Comparison: {', '.join(entities)}",
            content_markdown="# Comparison",
        )
        return page, self._call_record("synthesis")

    async def synthesize_timeline_page(self, topic, temporal_claims, policy):
        page = SynthesizedPage(
            title=f"Timeline: {topic}",
            content_markdown="# Timeline",
        )
        return page, self._call_record("synthesis")

    async def identify_open_questions(
        self, contested_claims, evidence_gaps, policy
    ):
        questions = [
            OpenQuestion(
                question="What are the long-term effects?",
                context="Insufficient longitudinal data",
                evidence_gap="No studies > 5 years",
            )
        ]
        return questions, self._call_record("synthesis")


@pytest.fixture
def mock_backend() -> MockCompilerBackend:
    return MockCompilerBackend()
