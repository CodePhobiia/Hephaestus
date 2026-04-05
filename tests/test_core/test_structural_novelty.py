"""Tests for model-free structural novelty scoring."""

from __future__ import annotations

from hephaestus.core.structural_novelty import StructuralNoveltyScore, compute_structural_novelty


class TestStructuralNovelty:
    def test_novel_invention(self):
        result = compute_structural_novelty(
            problem="I need a distributed rate limiter across microservices",
            architecture=(
                "Each service maintains a cyclic phase variable theta_i in [0, 2pi]. "
                "Services broadcast theta via UDP every 100ms. Each service computes "
                "rate_i = base_rate + K * sum(sin(theta_j - theta_i)) for neighbors j. "
                "The coupling constant K = 0.3 controls convergence speed. "
                "When theta_i wraps past 2pi, the service has consumed one token. "
                "The aggregate rate converges to N * base_rate via Kuramoto synchronization. "
                "Partition tolerance: isolated partitions maintain local rate at "
                "partition_size * base_rate, automatically correct on rejoin."
            ),
            key_insight="Phase coupling via sinusoidal adjustment creates emergent global rate without consensus.",
            source_domain_words=["oscillator", "entrainment", "rhythm", "musical", "acoustic"],
        )
        assert result.specificity > 0.5  # concrete architecture
        assert result.self_containment > 0.5  # no source domain leakage
        assert result.composite > 0.3

    def test_decorative_invention(self):
        result = compute_structural_novelty(
            problem="I need a cache for database queries",
            architecture=(
                "Inspired by the immune system, we could potentially build something "
                "similar to how T-cells remember threats. Various approaches might work. "
                "The system would generally cache results, possibly using some form of "
                "memory, analogous to biological memory systems."
            ),
            key_insight="Just as immune cells remember, we cache queries.",
            source_domain_words=["immune", "T-cell", "pathogen", "antibody"],
        )
        assert result.specificity < 0.3  # very vague
        # composite may be moderate due to vocabulary divergence, but specificity is low

    def test_empty_architecture(self):
        result = compute_structural_novelty(problem="test", architecture="", key_insight="test")
        assert result.concept_density == 0.0

    def test_label_novel(self):
        score = StructuralNoveltyScore(
            vocabulary_divergence=0.8,
            concept_density=0.7,
            specificity=0.8,
            self_containment=0.9,
            composite=0.8,
        )
        assert score.label == "STRUCTURALLY_NOVEL"

    def test_label_conventional(self):
        score = StructuralNoveltyScore(
            vocabulary_divergence=0.2,
            concept_density=0.1,
            specificity=0.2,
            self_containment=0.3,
            composite=0.2,
        )
        assert score.label == "STRUCTURALLY_CONVENTIONAL"

    def test_source_domain_leakage_penalized(self):
        result = compute_structural_novelty(
            problem="rate limiting",
            architecture="The oscillator rhythm creates musical entrainment patterns that synchronize the acoustic oscillator network.",
            key_insight="Musical rhythmic entrainment",
            source_domain_words=["oscillator", "rhythm", "musical", "entrainment", "acoustic"],
        )
        assert result.self_containment < 0.5

    def test_vocabulary_divergence(self):
        result = compute_structural_novelty(
            problem="I need load balancing",
            architecture="Implement eigenvalue decomposition of the adjacency matrix to find spectral communities, then route requests along Fiedler vector gradients.",
            key_insight="Spectral graph partitioning for routing",
        )
        assert result.vocabulary_divergence > 0.5  # lots of new words
