"""Tests for conflict detection predicates."""
from __future__ import annotations

from hephaestus.forgebase.domain.conflicts import (
    detect_entity_conflict,
    ConflictCheckResult,
)
from hephaestus.forgebase.domain.values import Version


class TestDetectEntityConflict:
    def test_clean_when_canonical_unchanged(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(1),
        )
        assert result == ConflictCheckResult.CLEAN

    def test_conflict_when_both_changed(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=Version(3),
        )
        assert result == ConflictCheckResult.CONFLICTED

    def test_clean_when_only_canonical_changed_and_branch_untouched(self):
        """Branch didn't touch the entity — no branch head exists."""
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=None,
            canonical_version=Version(2),
        )
        assert result == ConflictCheckResult.NO_BRANCH_CHANGE

    def test_conflict_when_canonical_deleted_branch_modified(self):
        result = detect_entity_conflict(
            base_version=Version(1),
            branch_version=Version(2),
            canonical_version=None,  # canonical deleted/archived
        )
        assert result == ConflictCheckResult.CONFLICTED
