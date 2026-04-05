"""Tests for FusionPolicy and DEFAULT_FUSION_POLICY."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import ClaimStatus
from hephaestus.forgebase.fusion.policy import DEFAULT_FUSION_POLICY, FusionPolicy


class TestFusionPolicy:
    def test_default_construction(self):
        policy = FusionPolicy()

        assert policy.policy_version == "1.0.0"
        assert policy.max_candidates_per_pair == 50
        assert policy.min_similarity_threshold == 0.3
        assert policy.max_analogical_maps == 20
        assert policy.max_transfer_opportunities == 10
        assert policy.baseline_min_claim_status == ClaimStatus.SUPPORTED
        assert policy.context_include_hypothesis is True
        assert policy.dossier_include_unresolved is True
        assert policy.problem_relevance_weight == 0.3

    def test_candidate_type_allocation(self):
        policy = FusionPolicy()

        alloc = policy.candidate_type_allocation
        assert alloc["concept"] == 0.4
        assert alloc["mechanism"] == 0.3
        assert alloc["claim_cluster"] == 0.2
        assert alloc["exploratory"] == 0.1
        # Allocations should sum to 1.0
        assert abs(sum(alloc.values()) - 1.0) < 1e-9

    def test_similarity_bands(self):
        policy = FusionPolicy()

        bands = policy.similarity_bands
        assert len(bands) == 3
        assert bands[0] == (0.7, 1.0)
        assert bands[1] == (0.5, 0.7)
        assert bands[2] == (0.3, 0.5)

    def test_custom_construction(self):
        policy = FusionPolicy(
            policy_version="2.0.0-beta",
            max_candidates_per_pair=100,
            min_similarity_threshold=0.5,
            max_analogical_maps=30,
            problem_relevance_weight=0.5,
        )

        assert policy.policy_version == "2.0.0-beta"
        assert policy.max_candidates_per_pair == 100
        assert policy.min_similarity_threshold == 0.5
        assert policy.problem_relevance_weight == 0.5

    def test_default_fusion_policy_singleton(self):
        assert DEFAULT_FUSION_POLICY is not None
        assert isinstance(DEFAULT_FUSION_POLICY, FusionPolicy)
        assert DEFAULT_FUSION_POLICY.policy_version == "1.0.0"

    def test_default_policy_matches_manual_default(self):
        """DEFAULT_FUSION_POLICY should be identical to FusionPolicy()."""
        fresh = FusionPolicy()
        assert DEFAULT_FUSION_POLICY.policy_version == fresh.policy_version
        assert DEFAULT_FUSION_POLICY.max_candidates_per_pair == fresh.max_candidates_per_pair
        assert DEFAULT_FUSION_POLICY.min_similarity_threshold == fresh.min_similarity_threshold
        assert DEFAULT_FUSION_POLICY.max_analogical_maps == fresh.max_analogical_maps
        assert DEFAULT_FUSION_POLICY.problem_relevance_weight == fresh.problem_relevance_weight

    def test_independent_mutable_fields(self):
        """Mutable default fields should not be shared between instances."""
        p1 = FusionPolicy()
        p2 = FusionPolicy()

        p1.candidate_type_allocation["concept"] = 0.9
        assert p2.candidate_type_allocation["concept"] == 0.4

        p1.similarity_bands.append((0.1, 0.3))
        assert len(p2.similarity_bands) == 3
