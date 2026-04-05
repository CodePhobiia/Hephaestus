"""Remediation policy engine — assigns routes to findings."""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.enums import (
    FindingCategory,
    FindingSeverity,
    RemediationRoute,
)


@dataclass
class RemediationRule:
    category: FindingCategory | None = None  # None = any
    severity: FindingSeverity | None = None  # None = any
    route: RemediationRoute = RemediationRoute.REPORT_ONLY
    priority: int = 0  # higher wins on conflict


@dataclass
class RemediationPolicy:
    policy_version: str = "1.0.0"
    default_route: RemediationRoute = RemediationRoute.REPORT_ONLY
    rules: list[RemediationRule] = field(default_factory=list)


def resolve_route(
    category: FindingCategory,
    severity: FindingSeverity,
    policy: RemediationPolicy,
) -> RemediationRoute:
    """Resolve the remediation route for a finding.

    Resolution order:
    1. Exact match (category + severity) -- highest priority wins
    2. Category-only match (severity=None) -- highest priority wins
    3. Severity-only match (category=None) -- highest priority wins
    4. Default route
    """
    best_match: RemediationRoute | None = None
    best_priority = -1
    best_specificity = -1  # 2 = exact, 1 = partial, 0 = default

    for rule in policy.rules:
        cat_match = rule.category is None or rule.category == category
        sev_match = rule.severity is None or rule.severity == severity

        if not (cat_match and sev_match):
            continue

        # Determine specificity
        specificity = 0
        if rule.category is not None:
            specificity += 1
        if rule.severity is not None:
            specificity += 1

        # Higher specificity wins, then higher priority
        if specificity > best_specificity or (
            specificity == best_specificity and rule.priority > best_priority
        ):
            best_match = rule.route
            best_priority = rule.priority
            best_specificity = specificity

    return best_match if best_match is not None else policy.default_route


# Default policy matching the spec
DEFAULT_REMEDIATION_POLICY = RemediationPolicy(
    policy_version="1.0.0",
    rules=[
        # Contradictions always research first
        RemediationRule(
            FindingCategory.CONTRADICTORY_CLAIM,
            FindingSeverity.CRITICAL,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            10,
        ),
        RemediationRule(
            FindingCategory.CONTRADICTORY_CLAIM,
            FindingSeverity.WARNING,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            10,
        ),
        RemediationRule(
            FindingCategory.CONTRADICTORY_CLAIM,
            FindingSeverity.INFO,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            10,
        ),
        # Unsupported claims
        RemediationRule(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.CRITICAL,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            8,
        ),
        RemediationRule(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.WARNING,
            RemediationRoute.RESEARCH_ONLY,
            8,
        ),
        RemediationRule(
            FindingCategory.UNSUPPORTED_CLAIM,
            FindingSeverity.INFO,
            RemediationRoute.REPORT_ONLY,
            8,
        ),
        # Source gaps
        RemediationRule(
            FindingCategory.SOURCE_GAP,
            None,
            RemediationRoute.RESEARCH_ONLY,
            5,
        ),
        # Stale evidence
        RemediationRule(
            FindingCategory.STALE_EVIDENCE,
            FindingSeverity.CRITICAL,
            RemediationRoute.RESEARCH_THEN_REPAIR,
            7,
        ),
        RemediationRule(
            FindingCategory.STALE_EVIDENCE,
            FindingSeverity.WARNING,
            RemediationRoute.RESEARCH_ONLY,
            7,
        ),
        RemediationRule(
            FindingCategory.STALE_EVIDENCE,
            FindingSeverity.INFO,
            RemediationRoute.REPORT_ONLY,
            7,
        ),
        # Structural: repair directly
        RemediationRule(
            FindingCategory.DUPLICATE_PAGE,
            None,
            RemediationRoute.REPAIR_ONLY,
            5,
        ),
        RemediationRule(
            FindingCategory.ORPHANED_PAGE,
            None,
            RemediationRoute.REPAIR_ONLY,
            5,
        ),
        RemediationRule(
            FindingCategory.BROKEN_REFERENCE,
            None,
            RemediationRoute.REPAIR_ONLY,
            5,
        ),
        # Low priority: report only
        RemediationRule(
            FindingCategory.MISSING_CANONICAL,
            None,
            RemediationRoute.REPORT_ONLY,
            3,
        ),
        RemediationRule(
            FindingCategory.UNRESOLVED_TODO,
            None,
            RemediationRoute.REPORT_ONLY,
            3,
        ),
        RemediationRule(
            FindingCategory.MISSING_FIGURE_EXPLANATION,
            None,
            RemediationRoute.REPORT_ONLY,
            3,
        ),
        # Resolvable by search
        RemediationRule(
            FindingCategory.RESOLVABLE_BY_SEARCH,
            None,
            RemediationRoute.RESEARCH_ONLY,
            4,
        ),
    ],
)
