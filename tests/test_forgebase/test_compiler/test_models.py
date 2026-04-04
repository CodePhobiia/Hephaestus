from __future__ import annotations
import pytest
from hephaestus.forgebase.compiler.models import (
    ExtractedClaim, ExtractedConcept, SourceCardContent,
    EvidenceGrade, SynthesizedPage, SynthesizedClaim,
    OpenQuestion, ConceptEvidence,
)
from hephaestus.forgebase.domain.enums import CandidateKind, SupportType
from hephaestus.forgebase.domain.values import EntityId, EvidenceSegmentRef, Version


def _seg() -> EvidenceSegmentRef:
    return EvidenceSegmentRef(
        source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
        source_version=Version(1),
        segment_start=0, segment_end=100,
        section_key=None, preview_text="Test...",
    )


class TestExtractedClaim:
    def test_create(self):
        c = ExtractedClaim(
            statement="SEI degrades during cycling",
            segment_ref=_seg(),
            confidence=0.9,
            claim_type="factual",
        )
        assert c.statement == "SEI degrades during cycling"

    def test_confidence_stored(self):
        c = ExtractedClaim(
            statement="X", segment_ref=_seg(), confidence=0.5, claim_type="methodological",
        )
        assert c.confidence == 0.5
        assert c.claim_type == "methodological"


class TestExtractedConcept:
    def test_create(self):
        c = ExtractedConcept(
            name="Solid Electrolyte Interphase",
            aliases=["SEI"],
            kind=CandidateKind.MECHANISM,
            evidence_segments=[_seg()],
            salience=0.85,
        )
        assert c.salience == 0.85

    def test_aliases_list(self):
        c = ExtractedConcept(
            name="Lithium", aliases=["Li", "Li+"], kind=CandidateKind.ENTITY,
            evidence_segments=[], salience=0.7,
        )
        assert len(c.aliases) == 2
        assert c.kind == CandidateKind.ENTITY


class TestSourceCardContent:
    def test_create(self):
        sc = SourceCardContent(
            summary="Paper on SEI degradation",
            key_claims=["SEI degrades during cycling"],
            methods=["Electrochemical impedance spectroscopy"],
            limitations=["Only tested at room temperature"],
            evidence_quality="strong",
            concepts_mentioned=["SEI", "anode"],
        )
        assert len(sc.key_claims) == 1

    def test_empty_lists(self):
        sc = SourceCardContent(
            summary="Minimal paper",
            key_claims=[], methods=[], limitations=[],
            evidence_quality="unknown",
            concepts_mentioned=[],
        )
        assert sc.summary == "Minimal paper"


class TestEvidenceGrade:
    def test_create(self):
        g = EvidenceGrade(
            strength=0.85,
            methodology_quality="strong",
            reasoning="Well-designed RCT with appropriate controls.",
        )
        assert g.strength == 0.85
        assert g.methodology_quality == "strong"


class TestSynthesizedClaim:
    def test_create(self):
        sc = SynthesizedClaim(
            statement="SEI is primary degradation mechanism",
            support_type=SupportType.SYNTHESIZED,
            confidence=0.8,
            derived_from_claims=["SEI degrades during cycling"],
        )
        assert sc.support_type == SupportType.SYNTHESIZED


class TestSynthesizedPage:
    def test_create(self):
        sp = SynthesizedPage(
            title="Solid Electrolyte Interphase",
            content_markdown="# SEI\n\nThe SEI layer...",
            claims=[SynthesizedClaim(
                statement="SEI is primary degradation mechanism",
                support_type=SupportType.SYNTHESIZED,
                confidence=0.8,
                derived_from_claims=["SEI degrades during cycling"],
            )],
            related_concepts=["anode", "electrolyte"],
        )
        assert len(sp.claims) == 1

    def test_default_empty_lists(self):
        sp = SynthesizedPage(
            title="Empty Page",
            content_markdown="# Empty",
        )
        assert sp.claims == []
        assert sp.related_concepts == []


class TestOpenQuestion:
    def test_create(self):
        oq = OpenQuestion(
            question="What causes SEI instability at high temperatures?",
            context="Multiple sources disagree on the mechanism",
            conflicting_claims=["claim A", "claim B"],
            evidence_gap="No high-temperature cycling data",
        )
        assert oq.question.startswith("What causes")

    def test_defaults(self):
        oq = OpenQuestion(
            question="Why?",
            context="Unknown",
        )
        assert oq.conflicting_claims == []
        assert oq.evidence_gap == ""


class TestConceptEvidence:
    def test_create(self):
        ce = ConceptEvidence(
            source_id=EntityId("source_01HXYZ12345678901234ABCDEF"),
            source_title="SEI Formation in Li-ion Batteries",
            claims=["SEI forms during first charge"],
            segments=[_seg()],
        )
        assert ce.source_title == "SEI Formation in Li-ion Batteries"
        assert len(ce.segments) == 1
