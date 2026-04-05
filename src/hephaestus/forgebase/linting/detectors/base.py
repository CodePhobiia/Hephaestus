"""LintDetector abstract base class and RawFinding dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.domain.values import EntityId

if TYPE_CHECKING:
    from hephaestus.forgebase.linting.state import VaultLintState


@dataclass
class RawFinding:
    """Unprocessed finding produced by a detector before fingerprinting/dedup.

    This is the detector's output; it does not yet have an ID, job
    reference, or persistence status. The ``LintEngine`` is responsible
    for converting accepted raw findings into persisted ``LintFinding``
    records.
    """

    category: FindingCategory
    severity: FindingSeverity
    description: str
    affected_entity_ids: list[EntityId] = field(default_factory=list)
    normalized_subject: str = ""
    suggested_action: str | None = None
    confidence: float = 1.0
    page_id: EntityId | None = None
    claim_id: EntityId | None = None


class LintDetector(ABC):
    """Abstract base class for pluggable lint detectors.

    Each concrete detector inspects some aspect of a vault's current
    state (via ``VaultLintState``) and produces zero or more
    ``RawFinding`` objects.

    Detectors must also implement ``is_resolved`` so the verification
    job can confirm whether a previously-opened finding has actually
    been fixed.
    """

    # ------------------------------------------------------------------
    # Required properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable name for this detector (e.g. 'stale_evidence')."""

    @property
    @abstractmethod
    def categories(self) -> list[FindingCategory]:
        """Finding categories this detector can produce."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string for the detector logic.

        Changing this version will cause fingerprints to differ, which
        means existing findings will *not* be deduplicated against new
        ones produced by the updated detector.  Bump deliberately.
        """

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def detect(self, state: VaultLintState) -> list[RawFinding]:
        """Run detection against the given vault state.

        Returns a list of raw findings (may be empty).
        """

    @abstractmethod
    def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Check whether *original_finding* is resolved in *current_state*.

        ``new_findings`` is the output of calling ``detect()`` on the
        current state — the implementation can compare fingerprints or
        inspect the state directly to decide.

        Returns ``True`` if the finding is confirmed resolved.
        """
