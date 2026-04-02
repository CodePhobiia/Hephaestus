"""
Prior Art Searcher.

Searches Google Patents and Semantic Scholar for existing work that might
overlap with a proposed invention.  Combines results into a
:class:`PriorArtReport`.

Both APIs are accessed via plain HTTP (``httpx``).  The searcher handles:

- Rate limit responses (429) with exponential back-off
- Network / timeout errors (returns a graceful ``"search unavailable"`` result)
- API quota exhaustion
- Empty / malformed responses

If both APIs are unavailable, the searcher returns a :class:`PriorArtReport`
with ``search_available=False`` rather than crashing.

Usage
-----
::

    from hephaestus.output.prior_art import PriorArtSearcher

    searcher = PriorArtSearcher()
    report = await searcher.search(
        query="ant colony pheromone trail load balancing distributed systems",
        invention_name="Pheromone-Gradient Load Balancer",
    )

    if report.has_prior_art:
        print(f"Found {len(report.patents)} patents and "
              f"{len(report.papers)} papers")
    else:
        print("No prior art found — novelty confirmed!")
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from hephaestus.research.perplexity import PerplexityClient, PriorArtFinding

logger = logging.getLogger(__name__)

# API endpoints
_SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
_GOOGLE_PATENTS_BASE = "https://patents.google.com/xhr/query"

# Request settings
_DEFAULT_TIMEOUT = 15.0
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds
_MAX_RESULTS_PER_SOURCE = 5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PatentResult:
    """
    A single patent result from Google Patents.

    Attributes
    ----------
    patent_id:
        Google Patent ID (e.g. ``"US10234567B2"``).
    title:
        Patent title.
    abstract:
        Patent abstract excerpt.
    filing_date:
        Filing date string.
    assignee:
        Assignee / owner.
    url:
        Direct URL to the patent page.
    relevance_snippet:
        Short excerpt explaining why this result was returned.
    """

    patent_id: str
    title: str
    abstract: str = ""
    filing_date: str = ""
    assignee: str = ""
    url: str = ""
    relevance_snippet: str = ""


@dataclass
class PaperResult:
    """
    A single academic paper result from Semantic Scholar.

    Attributes
    ----------
    paper_id:
        Semantic Scholar paper ID.
    title:
        Paper title.
    abstract:
        Paper abstract excerpt.
    authors:
        List of author names.
    year:
        Publication year.
    venue:
        Journal or conference name.
    citation_count:
        Number of citations.
    url:
        Direct URL to the paper page.
    """

    paper_id: str
    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    citation_count: int = 0
    url: str = ""


@dataclass
class PriorArtReport:
    """
    Combined prior art search results from all sources.

    Attributes
    ----------
    query:
        The search query used.
    invention_name:
        Name of the invention being checked.
    patents:
        Patent results from Google Patents.
    papers:
        Academic paper results from Semantic Scholar.
    search_available:
        Whether at least one search succeeded (``False`` = all APIs unavailable).
    search_errors:
        List of error messages from failed searches.
    searched_at:
        UTC timestamp when the search was performed.
    has_prior_art:
        ``True`` if any results were found.
    novelty_status:
        Human-readable verdict: ``"NO_PRIOR_ART_FOUND"``,
        ``"POSSIBLE_PRIOR_ART"``, ``"SEARCH_UNAVAILABLE"``.
    summary:
        Human-readable summary of the prior art situation.
    """

    query: str
    invention_name: str
    patents: list[PatentResult] = field(default_factory=list)
    papers: list[PaperResult] = field(default_factory=list)
    related_work: list[PriorArtFinding] = field(default_factory=list)
    overlap_verdict: str = "UNKNOWN"
    overlap_confidence: float = 0.0
    perplexity_summary: str = ""
    citations: list[str] = field(default_factory=list)
    search_available: bool = True
    search_errors: list[str] = field(default_factory=list)
    searched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    @property
    def has_prior_art(self) -> bool:
        """Whether any prior art was found."""
        return bool(self.patents or self.papers or self.related_work)

    @property
    def novelty_status(self) -> str:
        """Machine-readable novelty verdict."""
        if not self.search_available:
            return "SEARCH_UNAVAILABLE"
        if self.has_prior_art:
            return "POSSIBLE_PRIOR_ART"
        return "NO_PRIOR_ART_FOUND"

    @property
    def summary(self) -> str:
        """Human-readable prior art summary."""
        if not self.search_available:
            return (
                "Prior art search was unavailable (API unreachable or rate-limited). "
                "Manual review recommended."
            )
        if self.perplexity_summary:
            parts = [self.perplexity_summary]
            if self.related_work:
                parts.append("Closest grounded matches:")
                for finding in self.related_work[:4]:
                    rel = finding.relationship.replace("_", " ").title()
                    line = f"  • {finding.title} [{rel}]"
                    if finding.url:
                        line += f" — {finding.url}"
                    parts.append(line)
            if self.patents or self.papers:
                parts.append(
                    f"Secondary search signals: {len(self.patents)} patent(s), {len(self.papers)} paper(s)."
                )
            return "\n".join(parts)
        total = len(self.patents) + len(self.papers)
        if total == 0:
            return (
                f"No prior art found for '{self.invention_name}'. "
                "This specific cross-domain application appears to be novel."
            )
        parts: list[str] = [
            f"Found {total} potentially related work(s) for '{self.invention_name}':"
        ]
        if self.patents:
            parts.append(f"  • {len(self.patents)} patent(s)")
            for p in self.patents[:3]:
                parts.append(f"    - {p.title} ({p.patent_id})")
        if self.papers:
            parts.append(f"  • {len(self.papers)} academic paper(s)")
            for p in self.papers[:3]:
                parts.append(f"    - {p.title} ({p.year or 'n.d.'})")
        parts.append(
            "Note: Review required to confirm these are not direct precedents."
        )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# PriorArtSearcher
# ---------------------------------------------------------------------------


class PriorArtSearcher:
    """
    Searches Google Patents and Semantic Scholar for prior art.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds (default 15).
    max_retries:
        Maximum number of retries on transient errors (default 3).
    max_results_per_source:
        Maximum results to fetch from each source (default 5).
    http_client:
        Pre-constructed :class:`httpx.AsyncClient` for testing.
    """

    def __init__(
        self,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        max_results_per_source: int = _MAX_RESULTS_PER_SOURCE,
        use_perplexity_review: bool = True,
        perplexity_model: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_results = max_results_per_source
        self._use_perplexity_review = use_perplexity_review
        self._perplexity_model = perplexity_model
        self._http_client = http_client
        self._owns_client = http_client is None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating one if needed."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "HephaestusAI/0.1 PriorArtSearcher (+https://github.com/CodePhobiia/hephaestus)"
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._http_client is not None and self._owns_client:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "PriorArtSearcher":
        await self._get_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Main search entry point
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        invention_name: str = "",
        include_patents: bool = True,
        include_papers: bool = True,
    ) -> PriorArtReport:
        """
        Search all configured sources and return a combined report.

        Parameters
        ----------
        query:
            Natural-language search query describing the invention.
        invention_name:
            Human-readable name of the invention (for the report).
        include_patents:
            Whether to search Google Patents (default ``True``).
        include_papers:
            Whether to search Semantic Scholar (default ``True``).

        Returns
        -------
        PriorArtReport
            Combined results (never raises — errors are captured in the report).
        """
        report = PriorArtReport(query=query, invention_name=invention_name)

        tasks: list[Any] = []
        if include_patents:
            tasks.append(self._search_google_patents(query))
        if include_papers:
            tasks.append(self._search_semantic_scholar(query))
        if self._use_perplexity_review:
            tasks.append(self._search_perplexity_review(query, invention_name))

        if not tasks:
            report.search_available = False
            report.search_errors.append("No search sources enabled")
            return report

        results = await asyncio.gather(*tasks, return_exceptions=True)

        any_success = False
        for result in results:
            if isinstance(result, Exception):
                err_msg = f"{type(result).__name__}: {result}"
                report.search_errors.append(err_msg)
                logger.warning("Prior art search error: %s", err_msg)
            elif isinstance(result, list) and result:
                # Determine type from first item
                if result and isinstance(result[0], PatentResult):
                    report.patents.extend(result)
                    any_success = True
                elif result and isinstance(result[0], PaperResult):
                    report.papers.extend(result)
                    any_success = True
                elif result and isinstance(result[0], PriorArtFinding):
                    report.related_work.extend(result)
                    any_success = True
                else:
                    any_success = True  # empty list but no error
            elif isinstance(result, dict):
                if result:
                    report.perplexity_summary = str(result.get("summary", ""))
                    report.overlap_verdict = str(result.get("overlap_verdict", "UNKNOWN"))
                    report.overlap_confidence = float(result.get("overlap_confidence", 0.0) or 0.0)
                    report.related_work.extend(result.get("findings", []))
                    report.citations.extend(result.get("citations", []))
                    any_success = True
            else:
                any_success = True  # empty results but search worked

        # If we got exceptions for all tasks, mark as unavailable
        if not any_success and report.search_errors:
            report.search_available = False

        logger.info(
            "Prior art search complete: %d patents, %d papers, available=%s",
            len(report.patents),
            len(report.papers),
            report.search_available,
        )
        return report

    async def _search_perplexity_review(self, query: str, invention_name: str) -> dict[str, Any]:
        """Use Perplexity as the grounded prior-art layer when configured."""
        client = PerplexityClient(
            timeout=max(self._timeout, 30.0),
            model=self._perplexity_model,
            enabled=self._use_perplexity_review,
        )
        if not client.available():
            return {}

        try:
            summary, overlap_verdict, overlap_confidence, findings, citations, _raw = (
                await client.assess_prior_art(
                    invention_name=invention_name or query[:80],
                    problem=query,
                )
            )
            return {
                "summary": summary,
                "overlap_verdict": overlap_verdict,
                "overlap_confidence": overlap_confidence,
                "findings": findings,
                "citations": [c.url for c in citations],
            }
        finally:
            await client.close()

    # ------------------------------------------------------------------
    # Google Patents
    # ------------------------------------------------------------------

    async def _search_google_patents(self, query: str) -> list[PatentResult]:
        """
        Search Google Patents via their public XHR endpoint.

        Returns up to ``max_results_per_source`` results.  Returns an empty
        list (not an exception) if the search returns no results.
        """
        client = await self._get_client()

        # Google Patents accepts query parameters for their XHR API
        params = {
            "url": f"q={urllib.parse.quote(query)}&num={self._max_results}",
            "exp": "",
        }

        for attempt in range(self._max_retries):
            try:
                response = await client.get(
                    _GOOGLE_PATENTS_BASE,
                    params=params,
                    timeout=self._timeout,
                )

                if response.status_code == 429:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Google Patents rate limited (attempt %d/%d), waiting %.1fs",
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 200:
                    return self._parse_google_patents_response(response.json())

                # Non-retriable error
                logger.warning(
                    "Google Patents returned status %d", response.status_code
                )
                return []

            except httpx.TimeoutException:
                logger.warning(
                    "Google Patents timeout (attempt %d/%d)",
                    attempt + 1,
                    self._max_retries,
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                raise

            except httpx.ConnectError as exc:
                logger.warning("Google Patents connection error: %s", exc)
                raise

        return []

    def _parse_google_patents_response(self, data: Any) -> list[PatentResult]:
        """
        Parse the Google Patents XHR JSON response.

        The XHR API returns a complex nested structure.  We extract the most
        useful fields defensively.
        """
        results: list[PatentResult] = []
        try:
            # The response typically has a 'results' key with 'hits'
            hits: list[dict[str, Any]] = []

            if isinstance(data, dict):
                # Try various known response shapes
                if "results" in data and isinstance(data["results"], dict):
                    hits = data["results"].get("cluster", [{}])[0].get("result", [])
                elif "hits" in data:
                    hits = data.get("hits", [])

            for hit in hits[: self._max_results]:
                patent = hit.get("patent", {}) if isinstance(hit, dict) else {}
                pid = patent.get("publication_number", hit.get("id", "UNKNOWN"))
                title = patent.get("title", [{}])
                title_text = title[0].get("text", "") if isinstance(title, list) else str(title)
                abstract = patent.get("abstract", [{}])
                abstract_text = (
                    abstract[0].get("text", "") if isinstance(abstract, list) else str(abstract)
                )

                results.append(
                    PatentResult(
                        patent_id=str(pid),
                        title=title_text[:200],
                        abstract=abstract_text[:500],
                        filing_date=patent.get("filing_date", ""),
                        assignee=str(patent.get("assignee", "")),
                        url=f"https://patents.google.com/patent/{pid}",
                    )
                )
        except (KeyError, IndexError, TypeError) as exc:
            logger.debug("Error parsing Google Patents response: %s", exc)

        return results

    # ------------------------------------------------------------------
    # Semantic Scholar
    # ------------------------------------------------------------------

    async def _search_semantic_scholar(self, query: str) -> list[PaperResult]:
        """
        Search Semantic Scholar's paper search API.

        Returns up to ``max_results_per_source`` paper results.
        """
        client = await self._get_client()

        fields = "title,abstract,authors,year,venue,citationCount,externalIds"
        params = {
            "query": query,
            "limit": self._max_results,
            "fields": fields,
        }
        url = f"{_SEMANTIC_SCHOLAR_BASE}/paper/search"

        for attempt in range(self._max_retries):
            try:
                response = await client.get(
                    url,
                    params=params,
                    timeout=self._timeout,
                )

                if response.status_code == 429:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Semantic Scholar rate limited (attempt %d/%d), waiting %.1fs",
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 200:
                    return self._parse_semantic_scholar_response(response.json())

                logger.warning(
                    "Semantic Scholar returned status %d", response.status_code
                )
                return []

            except httpx.TimeoutException:
                logger.warning(
                    "Semantic Scholar timeout (attempt %d/%d)",
                    attempt + 1,
                    self._max_retries,
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                raise

            except httpx.ConnectError as exc:
                logger.warning("Semantic Scholar connection error: %s", exc)
                raise

        return []

    def _parse_semantic_scholar_response(self, data: Any) -> list[PaperResult]:
        """Parse the Semantic Scholar paper search JSON response."""
        results: list[PaperResult] = []
        try:
            papers = data.get("data", []) if isinstance(data, dict) else []

            for paper in papers[: self._max_results]:
                if not isinstance(paper, dict):
                    continue

                paper_id = paper.get("paperId", "")
                title = paper.get("title", "Untitled")
                abstract = paper.get("abstract") or ""
                year = paper.get("year")
                venue = paper.get("venue") or ""
                citation_count = paper.get("citationCount", 0) or 0

                authors_raw = paper.get("authors", [])
                authors = [
                    a.get("name", "") for a in authors_raw if isinstance(a, dict)
                ]

                # Build URL
                url = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""

                results.append(
                    PaperResult(
                        paper_id=paper_id,
                        title=title[:200],
                        abstract=abstract[:500],
                        authors=authors[:5],  # limit to first 5
                        year=int(year) if year else None,
                        venue=venue[:100],
                        citation_count=int(citation_count),
                        url=url,
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Error parsing Semantic Scholar response: %s", exc)

        return results
