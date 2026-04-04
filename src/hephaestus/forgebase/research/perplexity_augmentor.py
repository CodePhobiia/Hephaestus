"""Perplexity-backed research augmentor."""
from __future__ import annotations

import logging
from datetime import datetime

from hephaestus.forgebase.research.augmentor import (
    ContradictionResolution,
    DiscoveredSource,
    FreshnessCheck,
    ResearchAugmentor,
)

logger = logging.getLogger(__name__)


class PerplexityAugmentor(ResearchAugmentor):
    """Research augmentor backed by Perplexity API.

    Wraps the existing PerplexityClient from hephaestus.research.perplexity.
    """

    def __init__(self, perplexity_client: object | None = None) -> None:
        """Initialize with an optional PerplexityClient.

        Args:
            perplexity_client: An instance of hephaestus.research.perplexity.PerplexityClient.
                             If None, creates one lazily from environment.
        """
        self._client = perplexity_client

    def _get_client(self) -> object:
        """Lazy-load the PerplexityClient."""
        if self._client is None:
            try:
                from hephaestus.research.perplexity import PerplexityClient

                self._client = PerplexityClient()
            except ImportError:
                raise RuntimeError(
                    "PerplexityClient not available. Install hephaestus research module."
                )
        return self._client

    @property
    def available(self) -> bool:
        """Check if Perplexity is configured and available."""
        try:
            client = self._get_client()
            return getattr(client, "available", lambda: False)()
        except RuntimeError:
            return False

    async def find_supporting_evidence(
        self,
        concept: str,
        evidence_gaps: list[str],
    ) -> list[DiscoveredSource]:
        """Use Perplexity to find sources that could fill evidence gaps."""
        client = self._get_client()
        if not getattr(client, "available", lambda: False)():
            logger.warning("Perplexity unavailable, returning empty results")
            return []

        try:
            # Use build_baseline_dossier as the closest existing method
            dossier = await client.build_baseline_dossier(
                problem=f"Find evidence about: {concept}. Gaps: {'; '.join(evidence_gaps)}",
            )
            sources: list[DiscoveredSource] = []
            for i, system in enumerate(
                getattr(dossier, "representative_systems", [])
            ):
                sources.append(
                    DiscoveredSource(
                        url="",
                        title=system,
                        summary=system,
                        relevance=max(0.1, 0.8 - (i * 0.1)),
                    )
                )
            for citation in getattr(dossier, "citations", []):
                sources.append(
                    DiscoveredSource(
                        url=getattr(citation, "url", ""),
                        title=getattr(citation, "title", ""),
                        summary=getattr(citation, "title", ""),
                        relevance=0.6,
                    )
                )
            return sources
        except Exception as e:
            logger.error("Perplexity augmentor error: %s", e)
            return []

    async def resolve_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        context: str,
    ) -> ContradictionResolution:
        """Use Perplexity to find evidence resolving a contradiction."""
        client = self._get_client()
        if not getattr(client, "available", lambda: False)():
            return ContradictionResolution(
                summary="Perplexity unavailable",
                resolution="insufficient_evidence",
            )

        try:
            dossier = await client.build_baseline_dossier(
                problem=(
                    f"Which claim is better supported? "
                    f"A: {claim_a} vs B: {claim_b}. Context: {context}"
                ),
            )
            return ContradictionResolution(
                summary=getattr(dossier, "summary", ""),
                resolution="insufficient_evidence",
                supporting_evidence=getattr(dossier, "standard_approaches", []),
                confidence=0.5,
            )
        except Exception as e:
            logger.error("Perplexity contradiction resolution error: %s", e)
            return ContradictionResolution(
                summary=str(e),
                resolution="insufficient_evidence",
            )

    async def check_freshness(
        self,
        claim: str,
        last_validated: datetime,
    ) -> FreshnessCheck:
        """Use Perplexity to check if a claim has newer evidence."""
        client = self._get_client()
        if not getattr(client, "available", lambda: False)():
            return FreshnessCheck(is_stale=False, reason="Perplexity unavailable")

        try:
            dossier = await client.build_baseline_dossier(
                problem=(
                    f"Is this claim still current? '{claim}' "
                    f"(last validated: {last_validated.isoformat()})"
                ),
            )
            return FreshnessCheck(
                is_stale=False,
                reason=getattr(
                    dossier, "summary", "No freshness issues detected"
                ),
                newer_evidence=getattr(dossier, "representative_systems", []),
            )
        except Exception as e:
            logger.error("Perplexity freshness check error: %s", e)
            return FreshnessCheck(is_stale=False, reason=str(e))


class NoOpAugmentor(ResearchAugmentor):
    """No-op augmentor for when research augmentation is not configured."""

    async def find_supporting_evidence(
        self,
        concept: str,
        evidence_gaps: list[str],
    ) -> list[DiscoveredSource]:
        return []

    async def resolve_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        context: str,
    ) -> ContradictionResolution:
        return ContradictionResolution(
            summary="Research augmentation not configured",
            resolution="insufficient_evidence",
        )

    async def check_freshness(
        self,
        claim: str,
        last_validated: datetime,
    ) -> FreshnessCheck:
        return FreshnessCheck(
            is_stale=False,
            reason="Research augmentation not configured",
        )
