"""Research augmentation interface -- separate from compiler core."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DiscoveredSource:
    """A source discovered by the augmentor."""

    url: str
    title: str
    summary: str
    relevance: float  # 0.0-1.0
    trust_tier: str = "standard"


@dataclass
class ContradictionResolution:
    """Result of resolving a contradiction between two claims."""

    summary: str
    resolution: str  # "claim_a_stronger", "claim_b_stronger", "both_valid", "insufficient_evidence"
    supporting_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class FreshnessCheck:
    """Result of checking claim freshness."""

    is_stale: bool
    reason: str
    newer_evidence: list[str] = field(default_factory=list)
    checked_at: datetime | None = None


class ResearchAugmentor(ABC):
    """External evidence augmentation -- separate from compiler core.

    Used only in Tier 2, and only when evidence is incomplete.
    Results become follow-on durable ingest jobs, not inline ingestion.
    """

    @abstractmethod
    async def find_supporting_evidence(
        self,
        concept: str,
        evidence_gaps: list[str],
    ) -> list[DiscoveredSource]: ...

    @abstractmethod
    async def resolve_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        context: str,
    ) -> ContradictionResolution: ...

    @abstractmethod
    async def check_freshness(
        self,
        claim: str,
        last_validated: datetime,
    ) -> FreshnessCheck: ...
