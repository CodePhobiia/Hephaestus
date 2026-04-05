"""Source trust model — citation quality scoring and domain-based trust tiers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class TrustTier:
    """Trust tier constants."""

    AUTHORITATIVE = "AUTHORITATIVE"
    STANDARD = "STANDARD"
    LOW = "LOW"
    UNTRUSTED = "UNTRUSTED"


# Domain patterns mapped to trust tiers
_AUTHORITATIVE_DOMAINS = {
    "arxiv.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "nature.com",
    "science.org",
    "pnas.org",
    "github.com",
    "gitlab.com",
    "docs.python.org",
    "pytorch.org",
    "tensorflow.org",
}

_LOW_TRUST_PATTERNS = [
    re.compile(r"(reddit\.com|quora\.com|stackexchange\.com)"),
    re.compile(r"(medium\.com|substack\.com|wordpress\.com)"),
    re.compile(r"(pinterest\.com|instagram\.com|tiktok\.com)"),
]

_UNTRUSTED_PATTERNS = [
    re.compile(r"(bit\.ly|t\.co|goo\.gl|tinyurl\.com)"),  # URL shorteners
]


@dataclass
class TrustScore:
    """Trust assessment for a single source."""

    url: str
    domain: str = ""
    tier: str = TrustTier.STANDARD
    has_title: bool = False
    has_url: bool = False
    from_known_domain: bool = False
    quality_score: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "domain": self.domain,
            "tier": self.tier,
            "quality_score": round(self.quality_score, 3),
            "has_title": self.has_title,
            "has_url": self.has_url,
            "from_known_domain": self.from_known_domain,
        }


class SourceTrustModel:
    """Assigns trust tiers and quality scores to research sources."""

    def __init__(
        self,
        *,
        authoritative_domains: set[str] | None = None,
        custom_rules: list[tuple[re.Pattern[str], str]] | None = None,
    ) -> None:
        self._authoritative = authoritative_domains or _AUTHORITATIVE_DOMAINS
        self._custom_rules = custom_rules or []
        self._seen_urls: set[str] = set()

    def score_citation(
        self,
        url: str,
        *,
        title: str = "",
    ) -> TrustScore:
        """Score a citation URL and return a TrustScore."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")

        tier = self._classify_domain(domain, url)
        has_title = bool(title and title.strip())
        has_url = bool(url and url.strip() and url.startswith("http"))
        from_known = domain in self._authoritative

        # Quality score: 0.0 to 1.0
        quality = 0.5
        if tier == TrustTier.AUTHORITATIVE:
            quality = 0.9
        elif tier == TrustTier.LOW:
            quality = 0.3
        elif tier == TrustTier.UNTRUSTED:
            quality = 0.1

        if has_title:
            quality = min(1.0, quality + 0.1)
        if not has_url:
            quality *= 0.5

        return TrustScore(
            url=url,
            domain=domain,
            tier=tier,
            has_title=has_title,
            has_url=has_url,
            from_known_domain=from_known,
            quality_score=quality,
        )

    def deduplicate_urls(self, urls: list[str]) -> list[str]:
        """Remove duplicate URLs, preserving order."""
        seen: set[str] = set()
        result: list[str] = []
        for url in urls:
            normalized = url.strip().rstrip("/").lower()
            if normalized not in seen:
                seen.add(normalized)
                result.append(url)
        return result

    def is_new_url(self, url: str) -> bool:
        """Check if a URL has been seen before in this session."""
        normalized = url.strip().rstrip("/").lower()
        if normalized in self._seen_urls:
            return False
        self._seen_urls.add(normalized)
        return True

    def filter_by_tier(
        self,
        scores: list[TrustScore],
        *,
        min_tier: str = TrustTier.LOW,
    ) -> list[TrustScore]:
        """Filter scores by minimum trust tier."""
        tier_order = [
            TrustTier.UNTRUSTED,
            TrustTier.LOW,
            TrustTier.STANDARD,
            TrustTier.AUTHORITATIVE,
        ]
        min_idx = tier_order.index(min_tier) if min_tier in tier_order else 0
        return [s for s in scores if tier_order.index(s.tier) >= min_idx]

    def _classify_domain(self, domain: str, url: str) -> str:
        """Classify a domain into a trust tier."""
        # Custom rules first
        for pattern, tier in self._custom_rules:
            if pattern.search(url):
                return tier

        # Authoritative
        if domain in self._authoritative:
            return TrustTier.AUTHORITATIVE

        # Check parent domain
        parts = domain.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            if parent in self._authoritative:
                return TrustTier.AUTHORITATIVE

        # Untrusted patterns
        for pattern in _UNTRUSTED_PATTERNS:
            if pattern.search(url):
                return TrustTier.UNTRUSTED

        # Low trust patterns
        for pattern in _LOW_TRUST_PATTERNS:
            if pattern.search(url):
                return TrustTier.LOW

        return TrustTier.STANDARD


__all__ = [
    "SourceTrustModel",
    "TrustScore",
    "TrustTier",
]
