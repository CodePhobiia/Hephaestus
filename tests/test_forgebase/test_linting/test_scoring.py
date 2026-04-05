"""Tests for knowledge debt scoring."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import FindingSeverity
from hephaestus.forgebase.linting.scoring import (
    DEFAULT_DEBT_POLICY,
    DebtScoringPolicy,
    compute_debt_score,
)


class TestDebtScoringPolicy:
    def test_default_policy_version(self):
        assert DEFAULT_DEBT_POLICY.policy_version == "1.0.0"

    def test_default_weights(self):
        w = DEFAULT_DEBT_POLICY.weights
        assert w[FindingSeverity.CRITICAL] == 10.0
        assert w[FindingSeverity.WARNING] == 3.0
        assert w[FindingSeverity.INFO] == 1.0

    def test_default_normalization_base(self):
        assert DEFAULT_DEBT_POLICY.normalization_base == "pages_plus_claims"

    def test_custom_policy(self):
        policy = DebtScoringPolicy(
            policy_version="2.0.0",
            weights={FindingSeverity.CRITICAL: 20.0},
            normalization_base="pages_only",
        )
        assert policy.policy_version == "2.0.0"
        assert policy.weights[FindingSeverity.CRITICAL] == 20.0
        assert policy.normalization_base == "pages_only"


class TestComputeDebtScore:
    def test_empty_vault_returns_zero(self):
        """An empty vault (vault_size=0) should always return 0."""
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 5},
            vault_size=0,
        )
        assert score == 0.0

    def test_zero_findings_returns_zero(self):
        """No findings at all should yield 0."""
        score = compute_debt_score(
            findings_by_severity={},
            vault_size=100,
        )
        assert score == 0.0

    def test_zero_findings_explicit_zeros_returns_zero(self):
        """Explicit zero counts should also yield 0."""
        score = compute_debt_score(
            findings_by_severity={
                FindingSeverity.CRITICAL: 0,
                FindingSeverity.WARNING: 0,
                FindingSeverity.INFO: 0,
            },
            vault_size=50,
        )
        assert score == 0.0

    def test_critical_findings_increase_score(self):
        """Critical findings should produce a higher score than info findings."""
        score_critical = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 1},
            vault_size=100,
        )
        score_info = compute_debt_score(
            findings_by_severity={FindingSeverity.INFO: 1},
            vault_size=100,
        )
        assert score_critical > score_info

    def test_normalization_by_vault_size(self):
        """Same findings, larger vault -> lower score."""
        findings = {FindingSeverity.WARNING: 5}
        score_small = compute_debt_score(findings, vault_size=10)
        score_large = compute_debt_score(findings, vault_size=100)
        assert score_small > score_large

    def test_score_capped_at_100(self):
        """Even extreme findings should not exceed 100."""
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 1000},
            vault_size=1,
        )
        assert score == 100.0

    def test_custom_weights(self):
        """A custom policy with higher weights should produce a higher score."""
        normal_policy = DebtScoringPolicy(
            weights={FindingSeverity.CRITICAL: 10.0},
        )
        heavy_policy = DebtScoringPolicy(
            weights={FindingSeverity.CRITICAL: 50.0},
        )
        findings = {FindingSeverity.CRITICAL: 1}
        score_normal = compute_debt_score(findings, vault_size=100, policy=normal_policy)
        score_heavy = compute_debt_score(findings, vault_size=100, policy=heavy_policy)
        assert score_heavy > score_normal

    def test_known_score_calculation(self):
        """Verify a specific computation: 2 criticals + 3 warnings + 5 info, vault=100.

        raw = 2*10 + 3*3 + 5*1 = 20 + 9 + 5 = 34
        score = (34 / 100) * 100 = 34.0
        """
        score = compute_debt_score(
            findings_by_severity={
                FindingSeverity.CRITICAL: 2,
                FindingSeverity.WARNING: 3,
                FindingSeverity.INFO: 5,
            },
            vault_size=100,
        )
        assert score == 34.0

    def test_score_rounded_to_one_decimal(self):
        """Score should be rounded to 1 decimal place.

        1 warning, vault_size=7: raw = 3.0, score = (3/7)*100 = 42.857... -> 42.9
        """
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.WARNING: 1},
            vault_size=7,
        )
        assert score == 42.9

    def test_unknown_severity_uses_fallback_weight(self):
        """A severity not in the policy weights should use 1.0 as default."""
        # Create a policy with only CRITICAL weight
        policy = DebtScoringPolicy(
            weights={FindingSeverity.CRITICAL: 10.0},
        )
        # INFO is not in the custom weights, should fallback to 1.0
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.INFO: 10},
            vault_size=100,
            policy=policy,
        )
        # raw = 10 * 1.0 = 10, score = (10/100)*100 = 10.0
        assert score == 10.0

    def test_uses_default_policy_when_none(self):
        """When policy is None, DEFAULT_DEBT_POLICY should be used."""
        score_explicit = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 1},
            vault_size=100,
            policy=DEFAULT_DEBT_POLICY,
        )
        score_default = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 1},
            vault_size=100,
            policy=None,
        )
        assert score_explicit == score_default

    def test_vault_size_one(self):
        """Single-item vault with one critical finding.

        raw = 10.0, score = (10/1)*100 = 1000.0 -> capped at 100.0
        """
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.CRITICAL: 1},
            vault_size=1,
        )
        assert score == 100.0

    def test_all_severities_combined(self):
        """All severity levels contribute to the score.

        1 of each, vault_size=10: raw = 10+3+1 = 14, score = (14/10)*100 = 140.0 -> 100.0
        """
        score = compute_debt_score(
            findings_by_severity={
                FindingSeverity.CRITICAL: 1,
                FindingSeverity.WARNING: 1,
                FindingSeverity.INFO: 1,
            },
            vault_size=10,
        )
        assert score == 100.0

    def test_large_vault_low_score(self):
        """Large vault with few findings should produce a low score.

        1 info, vault_size=10000: raw = 1.0, score = (1/10000)*100 = 0.01 -> 0.0
        """
        score = compute_debt_score(
            findings_by_severity={FindingSeverity.INFO: 1},
            vault_size=10000,
        )
        assert score == 0.0
