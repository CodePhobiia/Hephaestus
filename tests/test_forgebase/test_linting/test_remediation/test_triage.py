"""Tests for triage — route assignment and override."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    FindingStatus,
    RemediationRoute,
    RouteSource,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.linting.remediation.policy import (
    RemediationPolicy,
    RemediationRule,
)
from hephaestus.forgebase.linting.remediation.triage import (
    override_route,
    triage_finding,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eid(prefix: str, suffix: str) -> EntityId:
    """Build an EntityId with a deterministic 26-char ULID-like string."""
    padded = (suffix * 5)[:26]
    return EntityId(f"{prefix}_{padded}")


def _finding(
    category: FindingCategory = FindingCategory.UNSUPPORTED_CLAIM,
    severity: FindingSeverity = FindingSeverity.WARNING,
) -> LintFinding:
    return LintFinding(
        finding_id=_eid("find", "aaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        job_id=_eid("job", "bbbbbbbbbbbbbbbbbbbbbbbbbbb"),
        vault_id=_eid("vault", "ccccccccccccccccccccccccccc"),
        category=category,
        severity=severity,
        page_id=None,
        claim_id=None,
        description="Test finding",
        suggested_action=None,
        status=FindingStatus.OPEN,
    )


# ---------------------------------------------------------------------------
# triage_finding tests
# ---------------------------------------------------------------------------


class TestTriageFinding:
    def test_triage_assigns_route_from_policy(self) -> None:
        """triage_finding resolves the route via the policy and returns POLICY source."""
        policy = RemediationPolicy(
            rules=[
                RemediationRule(
                    FindingCategory.UNSUPPORTED_CLAIM,
                    FindingSeverity.WARNING,
                    RemediationRoute.RESEARCH_ONLY,
                    priority=5,
                ),
            ],
            default_route=RemediationRoute.REPORT_ONLY,
        )
        finding = _finding(
            category=FindingCategory.UNSUPPORTED_CLAIM,
            severity=FindingSeverity.WARNING,
        )
        route, source = triage_finding(finding, policy)
        assert route == RemediationRoute.RESEARCH_ONLY
        assert source == RouteSource.POLICY

    def test_triage_uses_default_when_no_rule_matches(self) -> None:
        """When no rules match, triage returns the policy default."""
        policy = RemediationPolicy(
            rules=[
                RemediationRule(
                    FindingCategory.STALE_EVIDENCE,
                    FindingSeverity.CRITICAL,
                    RemediationRoute.RESEARCH_THEN_REPAIR,
                    priority=10,
                ),
            ],
            default_route=RemediationRoute.REPORT_ONLY,
        )
        finding = _finding(
            category=FindingCategory.ORPHANED_PAGE,
            severity=FindingSeverity.INFO,
        )
        route, source = triage_finding(finding, policy)
        assert route == RemediationRoute.REPORT_ONLY
        assert source == RouteSource.POLICY

    def test_triage_does_not_mutate_finding(self) -> None:
        """triage_finding should not modify the finding object."""
        policy = RemediationPolicy(
            rules=[
                RemediationRule(
                    FindingCategory.UNSUPPORTED_CLAIM,
                    FindingSeverity.WARNING,
                    RemediationRoute.RESEARCH_ONLY,
                    priority=5,
                ),
            ],
        )
        finding = _finding()
        original_route = finding.remediation_route
        original_source = finding.route_source
        triage_finding(finding, policy)
        assert finding.remediation_route == original_route
        assert finding.route_source == original_source


# ---------------------------------------------------------------------------
# override_route tests
# ---------------------------------------------------------------------------


class TestOverrideRoute:
    def test_override_changes_route_and_source(self) -> None:
        """override_route returns the new route with USER source by default."""
        finding = _finding()
        route, source = override_route(finding, RemediationRoute.REPAIR_ONLY)
        assert route == RemediationRoute.REPAIR_ONLY
        assert source == RouteSource.USER

    def test_override_with_custom_source(self) -> None:
        """override_route accepts a custom RouteSource."""
        finding = _finding()
        route, source = override_route(
            finding,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            source=RouteSource.AUTOMATION,
        )
        assert route == RemediationRoute.RESEARCH_THEN_REPAIR
        assert source == RouteSource.AUTOMATION

    def test_override_does_not_mutate_finding(self) -> None:
        """override_route should not modify the finding object."""
        finding = _finding()
        original_route = finding.remediation_route
        override_route(finding, RemediationRoute.REPAIR_ONLY)
        assert finding.remediation_route == original_route
