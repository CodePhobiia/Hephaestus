"""Merge rules and version reconciliation logic."""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.conflicts import ConflictCheckResult, detect_entity_conflict
from hephaestus.forgebase.domain.enums import EntityKind, MergeVerdict
from hephaestus.forgebase.domain.values import EntityId, Version


@dataclass
class MergeEntityChange:
    """One entity's version state for merge analysis."""

    entity_kind: EntityKind
    entity_id: EntityId
    base_version: Version
    branch_version: Version | None  # None = branch didn't touch
    canonical_version: Version | None  # None = canonical archived


@dataclass
class MergeAnalysis:
    """Result of analyzing all branch changes against canonical."""

    verdict: MergeVerdict
    clean_changes: list[MergeEntityChange] = field(default_factory=list)
    conflicts: list[MergeEntityChange] = field(default_factory=list)
    skipped: list[MergeEntityChange] = field(default_factory=list)


def analyze_merge(changes: list[MergeEntityChange]) -> MergeAnalysis:
    """Analyze a set of branch changes against canonical versions.

    Returns a MergeAnalysis with the overall verdict and per-entity breakdown.
    """
    clean: list[MergeEntityChange] = []
    conflicts: list[MergeEntityChange] = []
    skipped: list[MergeEntityChange] = []

    for change in changes:
        result = detect_entity_conflict(
            base_version=change.base_version,
            branch_version=change.branch_version,
            canonical_version=change.canonical_version,
        )
        if result == ConflictCheckResult.CLEAN:
            clean.append(change)
        elif result == ConflictCheckResult.CONFLICTED:
            conflicts.append(change)
        else:
            skipped.append(change)

    verdict = MergeVerdict.CLEAN if not conflicts else MergeVerdict.CONFLICTED

    return MergeAnalysis(
        verdict=verdict,
        clean_changes=clean,
        conflicts=conflicts,
        skipped=skipped,
    )
