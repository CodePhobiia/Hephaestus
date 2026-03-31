"""
Tests for the Novelty Proof Generator.
"""

from __future__ import annotations

import pytest

from hephaestus.output.proof import (
    DomainDistanceAnalysis,
    MechanismOriginalityAnalysis,
    NoveltyProof,
    NoveltyProofGenerator,
    PriorArtAnalysis,
    StructuralMappingAnalysis,
)
from hephaestus.output.prior_art import PriorArtReport, PatentResult, PaperResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator() -> NoveltyProofGenerator:
    return NoveltyProofGenerator(alpha=1.5)


def _make_proof(**overrides: object) -> NoveltyProof:
    generator = _make_generator()
    defaults = dict(
        problem="Distributed load balancing under traffic spikes",
        invention_name="Pheromone-Gradient Load Balancer",
        source_domain="Ant Colony Optimization",
        target_domain="Distributed Systems",
        domain_distance=0.94,
        structural_fidelity=0.87,
        mechanism="Ants deposit pheromone on faster paths",
        structural_mapping={"ant": "request", "pheromone": "routing weight"},
    )
    defaults.update(overrides)
    return generator.generate(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# NoveltyProofGenerator
# ---------------------------------------------------------------------------


class TestNoveltyProofGeneratorBasic:
    def test_generates_proof_object(self) -> None:
        proof = _make_proof()
        assert isinstance(proof, NoveltyProof)

    def test_invention_name_in_proof(self) -> None:
        proof = _make_proof()
        assert proof.invention_name == "Pheromone-Gradient Load Balancer"

    def test_problem_in_proof(self) -> None:
        proof = _make_proof()
        assert "load balancing" in proof.problem

    def test_novelty_score_range(self) -> None:
        proof = _make_proof()
        assert 0.0 <= proof.novelty_score <= 1.0

    def test_novelty_score_computed_from_distance_fidelity(self) -> None:
        # score = fidelity * (distance^alpha) = 0.87 * (0.94^1.5)
        expected = 0.87 * (0.94 ** 1.5)
        proof = _make_proof(novelty_score=None)
        assert proof.novelty_score == pytest.approx(expected, abs=1e-3)

    def test_precomputed_score_respected(self) -> None:
        proof = _make_proof(novelty_score=0.75)
        assert proof.novelty_score == pytest.approx(0.75, abs=1e-3)

    def test_score_capped_at_1(self) -> None:
        proof = _make_proof(domain_distance=1.0, structural_fidelity=1.0)
        assert proof.novelty_score <= 1.0

    def test_has_formal_statement(self) -> None:
        proof = _make_proof()
        assert isinstance(proof.formal_statement, str)
        assert len(proof.formal_statement) > 100

    def test_has_caveats(self) -> None:
        proof = _make_proof()
        assert isinstance(proof.caveats, list)
        assert len(proof.caveats) >= 1

    def test_generated_at_nonempty(self) -> None:
        proof = _make_proof()
        assert proof.generated_at

    def test_confidence_is_string(self) -> None:
        proof = _make_proof()
        assert proof.confidence in ("HIGH", "MEDIUM", "LOW")


class TestConfidenceLevels:
    def test_high_confidence_high_distance_fidelity_no_prior_art(self) -> None:
        prior_art_report = PriorArtReport(
            query="test",
            invention_name="test",
            patents=[],
            papers=[],
            search_available=True,
        )
        proof = _make_proof(
            domain_distance=0.92,
            structural_fidelity=0.85,
            prior_art_report=prior_art_report,
        )
        assert proof.confidence == "HIGH"

    def test_medium_confidence_moderate_distance(self) -> None:
        proof = _make_proof(domain_distance=0.65, structural_fidelity=0.60)
        assert proof.confidence in ("MEDIUM", "HIGH")

    def test_low_confidence_low_distance(self) -> None:
        proof = _make_proof(domain_distance=0.30, structural_fidelity=0.40)
        assert proof.confidence == "LOW"

    def test_no_prior_art_report_reduces_confidence(self) -> None:
        proof = _make_proof(
            domain_distance=0.90,
            structural_fidelity=0.90,
            prior_art_report=None,
        )
        # Without prior art search, max confidence is MEDIUM
        assert proof.confidence in ("MEDIUM", "LOW")


# ---------------------------------------------------------------------------
# Sub-analyses
# ---------------------------------------------------------------------------


class TestStructuralMappingAnalysis:
    def test_mapping_preserved(self) -> None:
        mapping = {"ant": "request", "pheromone": "weight", "colony": "cluster"}
        proof = _make_proof(structural_mapping=mapping)
        assert proof.structural_mapping.mapping == mapping
        assert proof.structural_mapping.element_count == 3

    def test_empty_mapping(self) -> None:
        proof = _make_proof(structural_mapping={})
        assert proof.structural_mapping.element_count == 0

    def test_high_fidelity_strong_isomorphism(self) -> None:
        proof = _make_proof(structural_fidelity=0.9)
        assert "Strong structural isomorphism" in proof.structural_mapping.isomorphism_statement

    def test_medium_fidelity_partial_isomorphism(self) -> None:
        proof = _make_proof(structural_fidelity=0.6)
        assert "Partial" in proof.structural_mapping.isomorphism_statement

    def test_low_fidelity_loose_analogy(self) -> None:
        proof = _make_proof(structural_fidelity=0.3)
        assert "Loose" in proof.structural_mapping.isomorphism_statement


class TestDomainDistanceAnalysis:
    def test_score_preserved(self) -> None:
        proof = _make_proof(domain_distance=0.94)
        assert proof.domain_distance.score == pytest.approx(0.94, abs=1e-4)

    def test_source_target_preserved(self) -> None:
        proof = _make_proof(
            source_domain="Biology", target_domain="Finance"
        )
        assert proof.domain_distance.source_domain == "Biology"
        assert proof.domain_distance.target_domain == "Finance"

    def test_high_distance_interpretation(self) -> None:
        proof = _make_proof(domain_distance=0.95)
        assert "Exceptional" in proof.domain_distance.interpretation

    def test_high_interpretation(self) -> None:
        proof = _make_proof(domain_distance=0.82)
        assert "High" in proof.domain_distance.interpretation

    def test_moderate_interpretation(self) -> None:
        proof = _make_proof(domain_distance=0.70)
        assert "Moderate" in proof.domain_distance.interpretation

    def test_lower_interpretation(self) -> None:
        proof = _make_proof(domain_distance=0.40)
        assert "Lower" in proof.domain_distance.interpretation

    def test_distance_basis_nonempty(self) -> None:
        proof = _make_proof()
        assert proof.domain_distance.distance_basis


class TestPriorArtAnalysis:
    def test_no_prior_art_report(self) -> None:
        proof = _make_proof(prior_art_report=None)
        assert not proof.prior_art.search_available

    def test_empty_prior_art_report(self) -> None:
        pa = PriorArtReport(query="q", invention_name="I", search_available=True)
        proof = _make_proof(prior_art_report=pa)
        assert proof.prior_art.search_available
        assert proof.prior_art.patents_found == 0
        assert proof.prior_art.papers_found == 0
        assert "No direct prior art" in proof.prior_art.absence_statement

    def test_prior_art_found(self) -> None:
        patent = PatentResult(patent_id="US1", title="Related Patent")
        pa = PriorArtReport(query="q", invention_name="I", patents=[patent])
        proof = _make_proof(prior_art_report=pa)
        assert proof.prior_art.patents_found == 1
        assert "Related Patent" in proof.prior_art.closest_prior_art

    def test_unavailable_search(self) -> None:
        pa = PriorArtReport(
            query="q",
            invention_name="I",
            search_available=False,
        )
        proof = _make_proof(prior_art_report=pa)
        assert not proof.prior_art.search_available
        assert "unavailable" in proof.prior_art.absence_statement.lower()


class TestMechanismOriginality:
    def test_mechanism_preserved(self) -> None:
        proof = _make_proof(mechanism="pheromone positive feedback loop")
        assert "pheromone positive feedback loop" in proof.mechanism_originality.mechanism

    def test_origin_domain_is_source_domain(self) -> None:
        proof = _make_proof(source_domain="Neuroscience")
        assert proof.mechanism_originality.origin_domain == "Neuroscience"

    def test_originality_statement_nonempty(self) -> None:
        proof = _make_proof()
        assert proof.mechanism_originality.originality_statement


# ---------------------------------------------------------------------------
# Formal statement
# ---------------------------------------------------------------------------


class TestFormalStatement:
    def test_contains_invention_name(self) -> None:
        proof = _make_proof(invention_name="Test Invention")
        assert "Test Invention" in proof.formal_statement

    def test_contains_ground_labels(self) -> None:
        proof = _make_proof()
        assert "GROUND 1" in proof.formal_statement
        assert "GROUND 2" in proof.formal_statement
        assert "GROUND 3" in proof.formal_statement
        assert "GROUND 4" in proof.formal_statement

    def test_contains_mapping_elements(self) -> None:
        proof = _make_proof(structural_mapping={"ant": "request"})
        assert "ant" in proof.formal_statement
        assert "request" in proof.formal_statement

    def test_contains_novelty_score_in_statement(self) -> None:
        proof = _make_proof()
        assert str(proof.novelty_score)[:4] in proof.formal_statement

    def test_contains_caveats_section(self) -> None:
        proof = _make_proof()
        assert "CAVEATS" in proof.formal_statement

    def test_contains_disclaimer(self) -> None:
        proof = _make_proof()
        assert "legal advice" in proof.formal_statement


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_returns_dict(self) -> None:
        proof = _make_proof()
        d = proof.to_dict()
        assert isinstance(d, dict)

    def test_required_keys(self) -> None:
        proof = _make_proof()
        d = proof.to_dict()
        required = [
            "invention_name",
            "problem",
            "novelty_score",
            "confidence",
            "structural_mapping",
            "domain_distance",
            "prior_art",
            "mechanism_originality",
            "formal_statement",
            "caveats",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_structural_mapping_in_dict(self) -> None:
        mapping = {"a": "b"}
        proof = _make_proof(structural_mapping=mapping)
        d = proof.to_dict()
        assert d["structural_mapping"]["mapping"] == mapping

    def test_json_serialisable(self) -> None:
        import json
        proof = _make_proof()
        json.dumps(proof.to_dict())  # should not raise


# ---------------------------------------------------------------------------
# Caveats
# ---------------------------------------------------------------------------


class TestCaveats:
    def test_analogy_break_added_as_caveat(self) -> None:
        proof = _make_proof(
            where_analogy_breaks="Pheromone evaporation too slow for ms-scale routing"
        )
        assert any(
            "Pheromone evaporation" in c for c in proof.caveats
        )

    def test_low_fidelity_caveat(self) -> None:
        proof = _make_proof(structural_fidelity=0.4)
        assert any("fidelity" in c.lower() for c in proof.caveats)

    def test_prior_art_found_caveat(self) -> None:
        pa = PriorArtReport(
            query="q",
            invention_name="I",
            patents=[PatentResult(patent_id="X", title="Test")],
        )
        proof = _make_proof(prior_art_report=pa)
        assert any("prior art" in c.lower() for c in proof.caveats)

    def test_additional_caveats(self) -> None:
        proof = _make_proof(additional_caveats=["Custom caveat"])
        assert any("Custom caveat" in c for c in proof.caveats)
