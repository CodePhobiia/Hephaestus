"""Tests for merge rules and version reconciliation."""

from __future__ import annotations

from hephaestus.forgebase.domain.enums import EntityKind, MergeVerdict
from hephaestus.forgebase.domain.merge import (
    MergeEntityChange,
    analyze_merge,
)
from hephaestus.forgebase.domain.values import EntityId, Version


def _eid(prefix: str, n: int = 1) -> EntityId:
    return EntityId(f"{prefix}_{n:026d}")


class TestAnalyzeMerge:
    def test_clean_merge_no_canonical_changes(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page"),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(1),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CLEAN
        assert len(result.conflicts) == 0
        assert len(result.clean_changes) == 1

    def test_conflicted_merge(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page"),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(3),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CONFLICTED
        assert len(result.conflicts) == 1
        assert len(result.clean_changes) == 0

    def test_mixed_clean_and_conflicted(self):
        changes = [
            MergeEntityChange(
                entity_kind=EntityKind.PAGE,
                entity_id=_eid("page", 1),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(1),
            ),
            MergeEntityChange(
                entity_kind=EntityKind.CLAIM,
                entity_id=_eid("claim", 2),
                base_version=Version(1),
                branch_version=Version(2),
                canonical_version=Version(4),
            ),
        ]
        result = analyze_merge(changes)
        assert result.verdict == MergeVerdict.CONFLICTED
        assert len(result.clean_changes) == 1
        assert len(result.conflicts) == 1
