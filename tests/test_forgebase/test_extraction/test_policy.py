"""Tests for ExtractionPolicy — per-channel trust filters.

Verifies that the default policy encodes the correct strictness hierarchy:
  baseline (strictest) < dossier (governance) < context (broadest)
and that custom overrides work correctly.
"""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    SourceTrustTier,
)
from hephaestus.forgebase.extraction.policy import (
    DEFAULT_EXTRACTION_POLICY,
    ExtractionPolicy,
)


class TestDefaultPolicyValues:
    """Verify every default matches the design spec."""

    def test_policy_version(self):
        p = ExtractionPolicy()
        assert p.policy_version == "1.0.0"

    def test_assembler_version(self):
        p = ExtractionPolicy()
        assert p.assembler_version == "1.0.0"

    def test_baseline_defaults(self):
        p = ExtractionPolicy()
        assert p.baseline_min_external_source_trust == SourceTrustTier.AUTHORITATIVE
        assert p.baseline_min_internal_invention_state == InventionEpistemicState.VERIFIED
        assert p.baseline_min_claim_status == ClaimStatus.SUPPORTED
        assert p.baseline_include_hypothesis is False
        assert p.baseline_include_contested is False

    def test_context_defaults(self):
        p = ExtractionPolicy()
        assert p.context_include_hypothesis is True
        assert p.context_include_contested is True
        assert p.context_include_open_questions is True
        assert p.context_include_prior_directions is True
        assert p.context_max_concepts == 50
        assert p.context_max_mechanisms == 30
        assert p.context_max_open_questions == 20
        assert p.context_max_explored_directions == 20

    def test_dossier_defaults(self):
        p = ExtractionPolicy()
        assert p.dossier_min_claim_status == ClaimStatus.SUPPORTED
        assert p.dossier_include_resolved_objections is True
        assert p.dossier_include_unresolved_controversies is True
        assert p.dossier_include_failure_modes is True
        assert p.dossier_max_claim_age_days is None

    def test_default_constant_matches_fresh_instance(self):
        assert ExtractionPolicy() == DEFAULT_EXTRACTION_POLICY


class TestBaselineStrictest:
    """Baseline channel must be the most restrictive."""

    def test_requires_authoritative_trust(self):
        p = ExtractionPolicy()
        assert p.baseline_min_external_source_trust == SourceTrustTier.AUTHORITATIVE

    def test_requires_verified_invention(self):
        p = ExtractionPolicy()
        assert p.baseline_min_internal_invention_state == InventionEpistemicState.VERIFIED

    def test_requires_supported_claims(self):
        p = ExtractionPolicy()
        assert p.baseline_min_claim_status == ClaimStatus.SUPPORTED

    def test_excludes_hypothesis(self):
        p = ExtractionPolicy()
        assert p.baseline_include_hypothesis is False

    def test_excludes_contested(self):
        p = ExtractionPolicy()
        assert p.baseline_include_contested is False


class TestContextBroadest:
    """Context channel is the most permissive — includes hypotheses and open questions."""

    def test_includes_hypothesis(self):
        p = ExtractionPolicy()
        assert p.context_include_hypothesis is True

    def test_includes_contested(self):
        p = ExtractionPolicy()
        assert p.context_include_contested is True

    def test_includes_open_questions(self):
        p = ExtractionPolicy()
        assert p.context_include_open_questions is True

    def test_includes_prior_directions(self):
        p = ExtractionPolicy()
        assert p.context_include_prior_directions is True

    def test_has_category_caps(self):
        p = ExtractionPolicy()
        assert p.context_max_concepts > 0
        assert p.context_max_mechanisms > 0
        assert p.context_max_open_questions > 0
        assert p.context_max_explored_directions > 0


class TestDossierGovernance:
    """Dossier channel is governance-grade: requires SUPPORTED claims, includes objections."""

    def test_requires_supported_claims(self):
        p = ExtractionPolicy()
        assert p.dossier_min_claim_status == ClaimStatus.SUPPORTED

    def test_includes_resolved_objections(self):
        p = ExtractionPolicy()
        assert p.dossier_include_resolved_objections is True

    def test_includes_unresolved_controversies(self):
        p = ExtractionPolicy()
        assert p.dossier_include_unresolved_controversies is True

    def test_includes_failure_modes(self):
        p = ExtractionPolicy()
        assert p.dossier_include_failure_modes is True

    def test_no_age_limit_by_default(self):
        p = ExtractionPolicy()
        assert p.dossier_max_claim_age_days is None


class TestCustomPolicy:
    """Overriding specific fields produces correct custom policies."""

    def test_override_baseline_trust(self):
        p = ExtractionPolicy(baseline_min_external_source_trust=SourceTrustTier.STANDARD)
        assert p.baseline_min_external_source_trust == SourceTrustTier.STANDARD
        # Other baseline fields remain default
        assert p.baseline_min_claim_status == ClaimStatus.SUPPORTED

    def test_override_context_caps(self):
        p = ExtractionPolicy(
            context_max_concepts=100,
            context_max_mechanisms=60,
        )
        assert p.context_max_concepts == 100
        assert p.context_max_mechanisms == 60
        # Other context fields remain default
        assert p.context_max_open_questions == 20

    def test_override_dossier_age_limit(self):
        p = ExtractionPolicy(dossier_max_claim_age_days=90)
        assert p.dossier_max_claim_age_days == 90

    def test_override_baseline_include_hypothesis(self):
        p = ExtractionPolicy(baseline_include_hypothesis=True)
        assert p.baseline_include_hypothesis is True

    def test_override_policy_version(self):
        p = ExtractionPolicy(policy_version="2.0.0", assembler_version="1.1.0")
        assert p.policy_version == "2.0.0"
        assert p.assembler_version == "1.1.0"

    def test_override_invention_state(self):
        p = ExtractionPolicy(baseline_min_internal_invention_state=InventionEpistemicState.REVIEWED)
        assert p.baseline_min_internal_invention_state == InventionEpistemicState.REVIEWED

    def test_fully_custom_policy(self):
        """Build a completely custom policy with all fields overridden."""
        p = ExtractionPolicy(
            policy_version="3.0.0",
            assembler_version="2.0.0",
            baseline_min_external_source_trust=SourceTrustTier.LOW,
            baseline_min_internal_invention_state=InventionEpistemicState.PROPOSED,
            baseline_min_claim_status=ClaimStatus.HYPOTHESIS,
            baseline_include_hypothesis=True,
            baseline_include_contested=True,
            context_include_hypothesis=False,
            context_include_contested=False,
            context_include_open_questions=False,
            context_include_prior_directions=False,
            context_max_concepts=5,
            context_max_mechanisms=3,
            context_max_open_questions=2,
            context_max_explored_directions=2,
            dossier_min_claim_status=ClaimStatus.HYPOTHESIS,
            dossier_include_resolved_objections=False,
            dossier_include_unresolved_controversies=False,
            dossier_include_failure_modes=False,
            dossier_max_claim_age_days=30,
        )
        assert p.policy_version == "3.0.0"
        assert p.baseline_min_external_source_trust == SourceTrustTier.LOW
        assert p.baseline_include_hypothesis is True
        assert p.context_include_hypothesis is False
        assert p.context_max_concepts == 5
        assert p.dossier_min_claim_status == ClaimStatus.HYPOTHESIS
        assert p.dossier_max_claim_age_days == 30
