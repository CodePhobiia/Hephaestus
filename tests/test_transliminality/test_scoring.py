"""Tests for transliminality integration scoring."""

import pytest

from hephaestus.transliminality.domain.models import IntegrationScoreBreakdown
from hephaestus.transliminality.domain.scoring import (
    FinalScoreBreakdown,
    _geometric_mean,
    compute_final_score,
    compute_integration_score,
)


class TestGeometricMean:
    def test_empty_returns_zero(self) -> None:
        assert _geometric_mean([]) == 0.0

    def test_single_value(self) -> None:
        assert _geometric_mean([0.5]) == pytest.approx(0.5)

    def test_equal_values(self) -> None:
        assert _geometric_mean([0.7, 0.7, 0.7]) == pytest.approx(0.7)

    def test_zero_collapses_to_zero(self) -> None:
        assert _geometric_mean([0.9, 0.8, 0.0, 0.7]) == 0.0

    def test_negative_collapses_to_zero(self) -> None:
        assert _geometric_mean([0.9, -0.1, 0.7]) == 0.0

    def test_known_values(self) -> None:
        # GM(2, 8) = sqrt(16) = 4
        assert _geometric_mean([2.0, 8.0]) == pytest.approx(4.0)

    def test_near_one(self) -> None:
        result = _geometric_mean([1.0, 1.0, 1.0])
        assert result == pytest.approx(1.0)


class TestIntegrationScore:
    def test_all_zeros_returns_zero(self) -> None:
        breakdown = IntegrationScoreBreakdown()
        assert compute_integration_score(breakdown) == 0.0

    def test_all_ones(self) -> None:
        breakdown = IntegrationScoreBreakdown(
            structural_alignment=1.0,
            constraint_fidelity=1.0,
            source_grounding=1.0,
            counterfactual_dependence=1.0,
            bidirectional_explainability=1.0,
            non_ornamental_use=1.0,
        )
        assert compute_integration_score(breakdown) == pytest.approx(1.0)

    def test_one_weak_dimension_drags_down(self) -> None:
        strong = IntegrationScoreBreakdown(
            structural_alignment=0.9,
            constraint_fidelity=0.9,
            source_grounding=0.9,
            counterfactual_dependence=0.9,
            bidirectional_explainability=0.9,
            non_ornamental_use=0.9,
        )
        mixed = IntegrationScoreBreakdown(
            structural_alignment=0.9,
            constraint_fidelity=0.9,
            source_grounding=0.9,
            counterfactual_dependence=0.1,  # one weak dimension
            bidirectional_explainability=0.9,
            non_ornamental_use=0.9,
        )
        assert compute_integration_score(mixed) < compute_integration_score(strong)

    def test_zero_dimension_kills_score(self) -> None:
        breakdown = IntegrationScoreBreakdown(
            structural_alignment=0.95,
            constraint_fidelity=0.95,
            source_grounding=0.0,  # zero
            counterfactual_dependence=0.95,
            bidirectional_explainability=0.95,
            non_ornamental_use=0.95,
        )
        assert compute_integration_score(breakdown) == 0.0


class TestFinalScore:
    def test_balanced_scores(self) -> None:
        breakdown = FinalScoreBreakdown(
            novelty=0.8,
            integration=0.8,
            feasibility=0.8,
            verifiability=0.8,
        )
        assert compute_final_score(breakdown) == pytest.approx(0.8)

    def test_novel_nonsense_fails(self) -> None:
        """Highly novel but zero integration → zero final score."""
        breakdown = FinalScoreBreakdown(
            novelty=0.99,
            integration=0.0,
            feasibility=0.8,
            verifiability=0.8,
        )
        assert compute_final_score(breakdown) == 0.0

    def test_grounded_conventionality_fails(self) -> None:
        """Strong integration but zero novelty → zero final score."""
        breakdown = FinalScoreBreakdown(
            novelty=0.0,
            integration=0.95,
            feasibility=0.9,
            verifiability=0.9,
        )
        assert compute_final_score(breakdown) == 0.0
