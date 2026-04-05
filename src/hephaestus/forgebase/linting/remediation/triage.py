"""Triage: assign remediation routes to findings."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import (
    RemediationRoute,
    RouteSource,
)
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.remediation.policy import (
    RemediationPolicy,
    resolve_route,
)


def triage_finding(
    finding: LintFinding,
    policy: RemediationPolicy,
) -> tuple[RemediationRoute, RouteSource]:
    """Assign a remediation route to a finding.

    Returns (route, source) without mutating the finding.
    """
    route = resolve_route(finding.category, finding.severity, policy)
    return route, RouteSource.POLICY


def override_route(
    finding: LintFinding,
    new_route: RemediationRoute,
    source: RouteSource = RouteSource.USER,
) -> tuple[RemediationRoute, RouteSource]:
    """Override the remediation route. Returns new (route, source)."""
    return new_route, source
