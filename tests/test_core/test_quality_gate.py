"""Tests for the invention quality gate."""

from __future__ import annotations

import pytest

from hephaestus.core.quality_gate import QualityAssessment, assess_invention_quality


class TestAssessInventionQuality:
    def test_clean_invention_passes(self):
        result = assess_invention_quality(
            architecture="Use a Jacobian coupling matrix to track state dependencies across subsystems. When eigenvalue crosses threshold, trigger cascade.",
            key_insight="Non-Hermitian eigenvalue dynamics create transient amplification that conventional stability analysis misses.",
        )
        assert result.passed
        assert result.decorative_signal_count == 0

    def test_decorative_invention_flagged(self):
        result = assess_invention_quality(
            architecture="Inspired by how immune systems work, similar to how T-cells remember threats, analogous to vaccination.",
            key_insight="Just as the immune system remembers threats, so too does our cache remember queries.",
        )
        assert result.decorative_signal_count >= 3
        assert any("DECORATIVE" in f for f in result.flags)

    def test_known_pattern_detected(self):
        result = assess_invention_quality(
            architecture="Implement a circuit breaker that opens after 5 failures and uses exponential backoff for retry.",
            key_insight="Circuit breaker prevents cascade failures.",
        )
        assert len(result.known_pattern_matches) >= 1
        assert any("KNOWN_PATTERN" in f for f in result.flags)

    def test_vague_architecture_flagged(self):
        result = assess_invention_quality(
            architecture="One possible approach could be implemented that would potentially improve things. Further research needed.",
            key_insight="Theoretically this could work.",
        )
        assert result.vague_architecture_count >= 2
        assert any("VAGUE" in f for f in result.flags)

    def test_honest_subtraction_collapse(self):
        result = assess_invention_quality(
            architecture="Redis-based caching layer with TTL.",
            key_insight="Cache results for reuse.",
            subtraction_test="Without the biological framing, this essentially collapses to a standard caching pattern.",
        )
        assert any("HONEST_COLLAPSE" in f for f in result.flags)

    def test_baseline_match_detected(self):
        result = assess_invention_quality(
            architecture="Queue-based load balancing.",
            key_insight="Distribute load across workers.",
            baseline_comparison="A senior engineer would build essentially the same mechanism using a message queue.",
        )
        assert any("BASELINE_MATCH" in f for f in result.flags)

    def test_gate_fails_on_heavy_penalties(self):
        result = assess_invention_quality(
            architecture="Inspired by ants, similar to how colonies work, analogous to swarm intelligence. Implement a load balancer with round robin.",
            key_insight="Just as ants find food, we find servers.",
            subtraction_test="This essentially collapses to standard load balancing.",
            baseline_comparison="A senior engineer would build essentially the same thing.",
        )
        assert not result.passed
        assert result.recommendation

    def test_score_adjustment_negative(self):
        result = assess_invention_quality(
            architecture="Inspired by the immune system. Use a cache.",
            key_insight="Similar to how T-cells remember.",
        )
        assert result.score_adjustment < 0

    def test_no_false_positives_on_technical_text(self):
        result = assess_invention_quality(
            architecture=(
                "Implement a non-equilibrium thermodynamic controller that maintains "
                "the system at the edge of chaos via a distributed PID feedback loop. "
                "Each node computes its local Lyapunov exponent and broadcasts it. "
                "The controller adjusts coupling strength to keep lambda_i near zero."
            ),
            key_insight="Criticality maintenance via distributed spectral monitoring.",
        )
        assert result.passed
        assert result.decorative_signal_count == 0
        assert len(result.known_pattern_matches) == 0
