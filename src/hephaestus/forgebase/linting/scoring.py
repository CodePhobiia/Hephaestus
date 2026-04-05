"""Policy-versioned knowledge debt scoring."""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.enums import FindingSeverity


@dataclass
class DebtScoringPolicy:
    """Configuration for knowledge debt score computation.

    Attributes:
        policy_version: Semver string for tracking policy evolution.
        weights: Mapping from FindingSeverity to numeric weight.
            Severities not present in the map fall back to 1.0.
        normalization_base: Strategy name for the denominator used in
            score normalization (currently only "pages_plus_claims").
    """

    policy_version: str = "1.0.0"
    weights: dict[FindingSeverity, float] = field(
        default_factory=lambda: {
            FindingSeverity.CRITICAL: 10.0,
            FindingSeverity.WARNING: 3.0,
            FindingSeverity.INFO: 1.0,
        }
    )
    normalization_base: str = "pages_plus_claims"


DEFAULT_DEBT_POLICY = DebtScoringPolicy()


def compute_debt_score(
    findings_by_severity: dict[FindingSeverity, int],
    vault_size: int,
    policy: DebtScoringPolicy | None = None,
) -> float:
    """Compute knowledge debt score (0-100). Lower is healthier.

    The score is a raw weighted sum of findings, normalized by vault size.
    An empty vault or zero findings always returns 0.

    Args:
        findings_by_severity: Count of open findings per severity level.
        vault_size: Total number of entities in the vault (pages + claims,
            or whichever base the policy specifies).
        policy: Scoring policy to use. Defaults to DEFAULT_DEBT_POLICY.

    Returns:
        A float in [0.0, 100.0], rounded to one decimal place.
    """
    pol = policy or DEFAULT_DEBT_POLICY

    if vault_size == 0:
        return 0.0

    raw = sum(
        count * pol.weights.get(severity, 1.0) for severity, count in findings_by_severity.items()
    )

    # Normalize: raw / vault_size * 100, capped at 100
    score = min(100.0, (raw / vault_size) * 100)
    return round(score, 1)
