from __future__ import annotations
import pytest
from hephaestus.forgebase.compiler.policy import SynthesisPolicy, DEFAULT_POLICY


class TestSynthesisPolicy:
    def test_default_values(self):
        p = SynthesisPolicy()
        assert p.policy_version == "1.0.0"
        assert p.name_similarity_threshold == 0.85
        assert p.min_sources_for_promotion == 2
        assert p.min_salience_single_source == 0.8
        assert p.max_claims_per_page == 50
        assert p.max_related_concepts == 20
        assert p.dirty_threshold_for_auto_synthesis == 5
        assert p.debounce_minutes == 10.0
        assert p.min_evidence_strength_for_supported == 0.3

    def test_custom_values(self):
        p = SynthesisPolicy(
            policy_version="2.0.0",
            name_similarity_threshold=0.90,
            min_sources_for_promotion=3,
        )
        assert p.policy_version == "2.0.0"
        assert p.name_similarity_threshold == 0.90
        assert p.min_sources_for_promotion == 3
        # Other fields should keep defaults
        assert p.max_claims_per_page == 50

    def test_default_policy_constant(self):
        assert isinstance(DEFAULT_POLICY, SynthesisPolicy)
        assert DEFAULT_POLICY.policy_version == "1.0.0"
        assert DEFAULT_POLICY.name_similarity_threshold == 0.85
