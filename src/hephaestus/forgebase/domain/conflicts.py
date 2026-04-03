"""Conflict detection predicates for branch merge."""
from __future__ import annotations

from enum import Enum

from hephaestus.forgebase.domain.values import Version


class ConflictCheckResult(str, Enum):
    CLEAN = "clean"
    CONFLICTED = "conflicted"
    NO_BRANCH_CHANGE = "no_branch_change"


def detect_entity_conflict(
    *,
    base_version: Version,
    branch_version: Version | None,
    canonical_version: Version | None,
) -> ConflictCheckResult:
    """Determine if a single entity has a merge conflict.

    Args:
        base_version: The entity version when the branch was created.
        branch_version: The entity's current branch-local head, or None if untouched.
        canonical_version: The entity's current canonical head, or None if archived.

    Returns:
        CLEAN if merge can proceed without conflict.
        CONFLICTED if both branch and canonical diverged from base.
        NO_BRANCH_CHANGE if the branch never touched this entity.
    """
    if branch_version is None:
        return ConflictCheckResult.NO_BRANCH_CHANGE

    if canonical_version is None:
        # Canonical was archived but branch modified — conflict
        return ConflictCheckResult.CONFLICTED

    if canonical_version == base_version:
        # Canonical didn't change — branch wins cleanly
        return ConflictCheckResult.CLEAN

    # Both diverged
    return ConflictCheckResult.CONFLICTED
