"""Tests for remediation policy engine — route resolution and precedence."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    RemediationRoute,
)
from hephaestus.forgebase.linting.remediation.policy import (
    DEFAULT_REMEDIATION_POLICY,
    RemediationPolicy,
    RemediationRule,
    resolve_route,
)

# ---------------------------------------------------------------------------
# Custom policy for precedence tests
# ---------------------------------------------------------------------------


def _make_policy(
    *rules: RemediationRule, default: RemediationRoute = RemediationRoute.REPORT_ONLY
) -> RemediationPolicy:
    return RemediationPolicy(rules=list(rules), default_route=default)


class TestResolveRoute:
    """Tests for resolve_route precedence logic."""

    def test_exact_match_wins_over_partial(self) -> None:
        """An exact (category + severity) match beats a category-only match."""
        policy = _make_policy(
            # Category-only rule: any severity for UNSUPPORTED_CLAIM -> RESEARCH_ONLY
            RemediationRule(
                FindingCategory.UNSUPPORTED_CLAIM, None, RemediationRoute.RESEARCH_ONLY, priority=10
            ),
            # Exact rule: UNSUPPORTED_CLAIM + CRITICAL -> RESEARCH_THEN_REPAIR
            RemediationRule(
                FindingCategory.UNSUPPORTED_CLAIM,
                FindingSeverity.CRITICAL,
                RemediationRoute.RESEARCH_THEN_REPAIR,
                priority=5,
            ),
        )
        route = resolve_route(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.CRITICAL,
            policy,
        )
        # Exact match (specificity=2) wins even though the partial rule has higher priority
        assert route == RemediationRoute.RESEARCH_THEN_REPAIR

    def test_category_only_match(self) -> None:
        """A category-only rule matches when no exact rule exists."""
        policy = _make_policy(
            RemediationRule(
                FindingCategory.SOURCE_GAP, None, RemediationRoute.RESEARCH_ONLY, priority=5
            ),
        )
        route = resolve_route(
            FindingCategory.SOURCE_GAP,
            FindingSeverity.WARNING,
            policy,
        )
        assert route == RemediationRoute.RESEARCH_ONLY

    def test_severity_only_match(self) -> None:
        """A severity-only rule (category=None) matches when no category rule exists."""
        policy = _make_policy(
            RemediationRule(
                None, FindingSeverity.CRITICAL, RemediationRoute.RESEARCH_THEN_REPAIR, priority=5
            ),
        )
        route = resolve_route(
            FindingCategory.ORPHANED_PAGE,
            FindingSeverity.CRITICAL,
            policy,
        )
        assert route == RemediationRoute.RESEARCH_THEN_REPAIR

    def test_default_route_when_no_match(self) -> None:
        """Falls back to default_route when no rules match."""
        policy = _make_policy(
            RemediationRule(
                FindingCategory.STALE_EVIDENCE,
                FindingSeverity.CRITICAL,
                RemediationRoute.RESEARCH_THEN_REPAIR,
                priority=10,
            ),
            default=RemediationRoute.REPORT_ONLY,
        )
        route = resolve_route(
            FindingCategory.ORPHANED_PAGE,
            FindingSeverity.INFO,
            policy,
        )
        assert route == RemediationRoute.REPORT_ONLY

    def test_higher_priority_wins(self) -> None:
        """Among rules with the same specificity, higher priority wins."""
        policy = _make_policy(
            RemediationRule(
                FindingCategory.DUPLICATE_PAGE, None, RemediationRoute.REPORT_ONLY, priority=3
            ),
            RemediationRule(
                FindingCategory.DUPLICATE_PAGE, None, RemediationRoute.REPAIR_ONLY, priority=8
            ),
        )
        route = resolve_route(
            FindingCategory.DUPLICATE_PAGE,
            FindingSeverity.WARNING,
            policy,
        )
        assert route == RemediationRoute.REPAIR_ONLY

    def test_severity_only_loses_to_category_only(self) -> None:
        """Category-only (specificity=1, cat) and severity-only (specificity=1, sev) are
        both specificity 1. The one with higher priority should win."""
        policy = _make_policy(
            RemediationRule(
                None, FindingSeverity.WARNING, RemediationRoute.RESEARCH_ONLY, priority=3
            ),
            RemediationRule(
                FindingCategory.STALE_EVIDENCE, None, RemediationRoute.REPAIR_ONLY, priority=5
            ),
        )
        route = resolve_route(
            FindingCategory.STALE_EVIDENCE,
            FindingSeverity.WARNING,
            policy,
        )
        # Both are specificity 1, but category-only has higher priority (5 > 3)
        assert route == RemediationRoute.REPAIR_ONLY

    def test_exact_match_beats_severity_only_even_with_lower_priority(self) -> None:
        """Exact match (specificity=2) beats severity-only (specificity=1)
        even when severity-only has a higher priority number."""
        policy = _make_policy(
            RemediationRule(
                None, FindingSeverity.CRITICAL, RemediationRoute.REPORT_ONLY, priority=100
            ),
            RemediationRule(
                FindingCategory.STALE_EVIDENCE,
                FindingSeverity.CRITICAL,
                RemediationRoute.RESEARCH_THEN_REPAIR,
                priority=1,
            ),
        )
        route = resolve_route(
            FindingCategory.STALE_EVIDENCE,
            FindingSeverity.CRITICAL,
            policy,
        )
        assert route == RemediationRoute.RESEARCH_THEN_REPAIR

    def test_empty_rules_returns_default(self) -> None:
        """Policy with no rules always returns default_route."""
        policy = RemediationPolicy(
            default_route=RemediationRoute.REPAIR_ONLY,
            rules=[],
        )
        route = resolve_route(
            FindingCategory.ORPHANED_PAGE,
            FindingSeverity.INFO,
            policy,
        )
        assert route == RemediationRoute.REPAIR_ONLY


class TestDefaultRemediationPolicy:
    """Tests verifying the DEFAULT_REMEDIATION_POLICY routes specific categories correctly."""

    def test_default_policy_contradictions_get_research_then_repair(self) -> None:
        """All contradictory claims get RESEARCH_THEN_REPAIR regardless of severity."""
        for sev in FindingSeverity:
            route = resolve_route(
                FindingCategory.CONTRADICTORY_CLAIM,
                sev,
                DEFAULT_REMEDIATION_POLICY,
            )
            assert route == RemediationRoute.RESEARCH_THEN_REPAIR, (
                f"Expected RESEARCH_THEN_REPAIR for CONTRADICTORY_CLAIM/{sev}, got {route}"
            )

    def test_default_policy_structural_get_repair_only(self) -> None:
        """Structural findings (DUPLICATE_PAGE, ORPHANED_PAGE, BROKEN_REFERENCE)
        get REPAIR_ONLY regardless of severity."""
        structural = [
            FindingCategory.DUPLICATE_PAGE,
            FindingCategory.ORPHANED_PAGE,
            FindingCategory.BROKEN_REFERENCE,
        ]
        for cat in structural:
            for sev in FindingSeverity:
                route = resolve_route(cat, sev, DEFAULT_REMEDIATION_POLICY)
                assert route == RemediationRoute.REPAIR_ONLY, (
                    f"Expected REPAIR_ONLY for {cat}/{sev}, got {route}"
                )

    def test_default_policy_low_priority_get_report_only(self) -> None:
        """Low-priority categories (MISSING_CANONICAL, UNRESOLVED_TODO, MISSING_FIGURE_EXPLANATION)
        get REPORT_ONLY regardless of severity."""
        low_pri = [
            FindingCategory.MISSING_CANONICAL,
            FindingCategory.UNRESOLVED_TODO,
            FindingCategory.MISSING_FIGURE_EXPLANATION,
        ]
        for cat in low_pri:
            for sev in FindingSeverity:
                route = resolve_route(cat, sev, DEFAULT_REMEDIATION_POLICY)
                assert route == RemediationRoute.REPORT_ONLY, (
                    f"Expected REPORT_ONLY for {cat}/{sev}, got {route}"
                )

    def test_default_policy_unsupported_claim_critical_gets_research_then_repair(self) -> None:
        """UNSUPPORTED_CLAIM + CRITICAL -> RESEARCH_THEN_REPAIR."""
        route = resolve_route(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.CRITICAL,
            DEFAULT_REMEDIATION_POLICY,
        )
        assert route == RemediationRoute.RESEARCH_THEN_REPAIR

    def test_default_policy_unsupported_claim_warning_gets_research_only(self) -> None:
        """UNSUPPORTED_CLAIM + WARNING -> RESEARCH_ONLY."""
        route = resolve_route(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.WARNING,
            DEFAULT_REMEDIATION_POLICY,
        )
        assert route == RemediationRoute.RESEARCH_ONLY

    def test_default_policy_unsupported_claim_info_gets_report_only(self) -> None:
        """UNSUPPORTED_CLAIM + INFO -> REPORT_ONLY."""
        route = resolve_route(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.INFO,
            DEFAULT_REMEDIATION_POLICY,
        )
        assert route == RemediationRoute.REPORT_ONLY

    def test_default_policy_source_gap_gets_research_only(self) -> None:
        """SOURCE_GAP -> RESEARCH_ONLY regardless of severity."""
        for sev in FindingSeverity:
            route = resolve_route(
                FindingCategory.SOURCE_GAP,
                sev,
                DEFAULT_REMEDIATION_POLICY,
            )
            assert route == RemediationRoute.RESEARCH_ONLY, (
                f"Expected RESEARCH_ONLY for SOURCE_GAP/{sev}, got {route}"
            )

    def test_default_policy_resolvable_by_search_gets_research_only(self) -> None:
        """RESOLVABLE_BY_SEARCH -> RESEARCH_ONLY regardless of severity."""
        for sev in FindingSeverity:
            route = resolve_route(
                FindingCategory.RESOLVABLE_BY_SEARCH,
                sev,
                DEFAULT_REMEDIATION_POLICY,
            )
            assert route == RemediationRoute.RESEARCH_ONLY, (
                f"Expected RESEARCH_ONLY for RESOLVABLE_BY_SEARCH/{sev}, got {route}"
            )

    def test_default_policy_stale_evidence_severity_differentiation(self) -> None:
        """STALE_EVIDENCE routes differ by severity:
        CRITICAL -> RESEARCH_THEN_REPAIR
        WARNING -> RESEARCH_ONLY
        INFO -> REPORT_ONLY"""
        expected = {
            FindingSeverity.CRITICAL: RemediationRoute.RESEARCH_THEN_REPAIR,
            FindingSeverity.WARNING: RemediationRoute.RESEARCH_ONLY,
            FindingSeverity.INFO: RemediationRoute.REPORT_ONLY,
        }
        for sev, expected_route in expected.items():
            route = resolve_route(
                FindingCategory.STALE_EVIDENCE,
                sev,
                DEFAULT_REMEDIATION_POLICY,
            )
            assert route == expected_route, (
                f"Expected {expected_route} for STALE_EVIDENCE/{sev}, got {route}"
            )
