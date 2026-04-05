"""
Tests for the Solution Shape Detector.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hephaestus.novelty.solution_shapes import (
    aggregate_shape_scores,
    classify_architecture_text,
    classify_banned_baseline,
    classify_banned_baselines,
    classify_generated_invention,
    extract_invention_text,
    get_shape_library,
    shape_overlap_score,
)


class TestShapeLibrary:
    def test_contains_expected_common_shapes(self) -> None:
        keys = {shape.key for shape in get_shape_library()}
        assert {
            "classifier_threshold",
            "recommender_ranker",
            "marketplace_reputation",
            "centralized_registry",
            "feedback_controller",
            "graph_ranker",
            "monitoring_intervention_loop",
            "pipeline",
        }.issubset(keys)


class TestBaselineClassification:
    def test_classifier_threshold_baseline(self) -> None:
        result = classify_banned_baseline(
            "Simple spam classifier with a fixed confidence threshold and binary decision gate."
        )

        assert result.source_kind == "baseline"
        assert result.shape_keys[0] == "classifier_threshold"
        assert "classifier" in result.matches[0].evidence
        assert "threshold" in result.matches[0].evidence

    def test_marketplace_reputation_baseline(self) -> None:
        result = classify_banned_baseline(
            "A buyer-seller marketplace that routes jobs using reputation scores and reviews."
        )

        assert "marketplace_reputation" in result.shape_keys

    def test_multiple_baselines_can_be_aggregated_without_double_counting(self) -> None:
        classifications = classify_banned_baselines(
            [
                "Fraud classifier with a threshold.",
                "A detector that applies a confidence threshold before blocking.",
            ]
        )

        profile = aggregate_shape_scores(classifications)
        assert set(profile) == {"classifier_threshold"}
        assert profile["classifier_threshold"] >= 0.9


class TestArchitectureClassification:
    def test_architecture_text_can_match_multiple_shapes(self) -> None:
        result = classify_architecture_text(
            """
            Stage 1 ingest events into a graph of accounts and edges.
            Stage 2 compute a PageRank-style ranking over the network.
            Stage 3 monitor telemetry and quarantine suspicious nodes.
            """
        )

        assert "graph_ranker" in result.shape_keys
        assert "monitoring_intervention_loop" in result.shape_keys
        assert "pipeline" in result.shape_keys

    def test_generated_invention_supports_nested_translation_like_objects(self) -> None:
        translation = SimpleNamespace(
            invention_name="Adaptive Trust Loop",
            architecture=(
                "A closed loop feedback controller watches the error signal from the system "
                "and adjusts the actuator toward a target setpoint."
            ),
            key_insight="Treat trust drift as a control problem.",
            implementation_notes="Use a PID-like regulator for the actuator gain.",
            mapping=[
                SimpleNamespace(
                    source_element="Sensor",
                    target_element="Trust monitor",
                    mechanism="Observes the system state",
                )
            ],
            limitations=["Controller tuning matters."],
        )
        verified = SimpleNamespace(
            translation=translation,
            novelty_notes="Novel because it reframes adaptation as regulation.",
        )

        extracted = extract_invention_text(verified)
        result = classify_generated_invention(verified)

        assert "Adaptive Trust Loop" in extracted
        assert "feedback_controller" in result.shape_keys

    def test_generated_invention_supports_dict_payloads(self) -> None:
        invention = {
            "invention_name": "Registry Sentinel",
            "architecture": (
                "A central control plane maintains a service registry and directory. "
                "Workers heartbeat into the registry and clients perform service discovery "
                "through that single source of truth."
            ),
            "mapping": [
                {
                    "source_element": "Directory entry",
                    "target_element": "Worker record",
                    "mechanism": "Both allow discovery through lookup",
                }
            ],
        }

        result = classify_generated_invention(invention)
        assert "centralized_registry" in result.shape_keys


class TestOverlapScoring:
    def test_overlap_is_high_for_matching_shape_profiles(self) -> None:
        score = shape_overlap_score(
            ["Classifier with confidence threshold."],
            [
                "The architecture uses a detector that emits a risk score and a fixed threshold "
                "gates whether the request is blocked."
            ],
        )

        assert score >= 0.8

    def test_overlap_is_zero_for_disjoint_profiles(self) -> None:
        score = shape_overlap_score(
            ["Central service registry with service discovery."],
            ["A closed loop feedback controller adjusts actuators from an error signal."],
        )

        assert score == pytest.approx(0.0)

    def test_overlap_supports_partial_multi_label_matches(self) -> None:
        score = shape_overlap_score(
            ["Three-stage pipeline that ingests data and computes a graph ranking over nodes."],
            ["A PageRank-style graph ranker scores nodes by link structure."],
        )

        assert 0.2 < score < 0.8
