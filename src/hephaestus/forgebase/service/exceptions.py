"""Service-layer exceptions for ForgeBase."""

from __future__ import annotations


class ConflictError(Exception):
    """Raised when optimistic concurrency check fails.

    The caller supplied an ``expected_version`` that no longer matches
    the current head version of the aggregate.
    """

    def __init__(self, entity_id: str, expected: int, actual: int) -> None:
        self.entity_id = entity_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Conflict on {entity_id}: expected version {expected}, but current head is {actual}"
        )


class StaleMergeError(Exception):
    """Raised when the canonical head has moved since the merge was proposed.

    The merge proposal's target_revision_id no longer matches the vault's
    current head_revision_id, meaning another merge or edit has landed
    in between.
    """

    def __init__(self, merge_id: str, expected_rev: str, actual_rev: str) -> None:
        self.merge_id = merge_id
        self.expected_rev = expected_rev
        self.actual_rev = actual_rev
        super().__init__(
            f"Stale merge {merge_id}: expected vault head {expected_rev}, "
            f"but current head is {actual_rev}"
        )


class UnresolvedConflictsError(Exception):
    """Raised when attempting to execute a merge that has unresolved conflicts."""

    def __init__(self, merge_id: str, unresolved_count: int) -> None:
        self.merge_id = merge_id
        self.unresolved_count = unresolved_count
        super().__init__(f"Merge {merge_id} has {unresolved_count} unresolved conflict(s)")


class EntityNotFoundError(Exception):
    """Raised when a required entity is not found."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")
