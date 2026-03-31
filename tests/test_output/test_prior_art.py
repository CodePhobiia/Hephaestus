"""
Tests for the Prior Art Searcher.

All HTTP calls are mocked to avoid real network requests in tests.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hephaestus.output.prior_art import (
    PaperResult,
    PatentResult,
    PriorArtReport,
    PriorArtSearcher,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ss_response(papers: list[dict]) -> dict:
    """Build a Semantic Scholar API response."""
    return {"data": papers, "total": len(papers), "offset": 0}


def _make_ss_paper(
    paper_id: str = "abc123",
    title: str = "Test Paper",
    year: int = 2024,
    venue: str = "IEEE",
    citation_count: int = 42,
    abstract: str = "An interesting paper.",
) -> dict:
    return {
        "paperId": paper_id,
        "title": title,
        "abstract": abstract,
        "year": year,
        "venue": venue,
        "citationCount": citation_count,
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
    }


def _make_google_patents_response(patents: list[dict]) -> dict:
    """Build a plausible Google Patents XHR response."""
    results = []
    for p in patents:
        results.append(
            {
                "patent": {
                    "publication_number": p.get("id", "US9999999"),
                    "title": [{"text": p.get("title", "A Patent")}],
                    "abstract": [{"text": p.get("abstract", "Abstract")}],
                    "filing_date": p.get("filing_date", "2020-01-01"),
                    "assignee": p.get("assignee", "ACME Corp"),
                }
            }
        )
    return {
        "results": {
            "cluster": [
                {"result": results}
            ]
        }
    }


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# PriorArtReport data class
# ---------------------------------------------------------------------------


class TestPriorArtReport:
    def test_no_results_no_prior_art(self) -> None:
        r = PriorArtReport(query="test", invention_name="test", search_available=True)
        assert not r.has_prior_art

    def test_with_patents_has_prior_art(self) -> None:
        r = PriorArtReport(
            query="test",
            invention_name="test",
            patents=[PatentResult(patent_id="US1", title="x")],
        )
        assert r.has_prior_art

    def test_with_papers_has_prior_art(self) -> None:
        r = PriorArtReport(
            query="test",
            invention_name="test",
            papers=[PaperResult(paper_id="p1", title="y")],
        )
        assert r.has_prior_art

    def test_novelty_status_no_prior_art(self) -> None:
        r = PriorArtReport(query="q", invention_name="I", search_available=True)
        assert r.novelty_status == "NO_PRIOR_ART_FOUND"

    def test_novelty_status_possible(self) -> None:
        r = PriorArtReport(
            query="q",
            invention_name="I",
            patents=[PatentResult(patent_id="US1", title="x")],
        )
        assert r.novelty_status == "POSSIBLE_PRIOR_ART"

    def test_novelty_status_unavailable(self) -> None:
        r = PriorArtReport(query="q", invention_name="I", search_available=False)
        assert r.novelty_status == "SEARCH_UNAVAILABLE"

    def test_summary_no_prior_art(self) -> None:
        r = PriorArtReport(query="q", invention_name="My Invention", search_available=True)
        assert "No prior art found" in r.summary
        assert "My Invention" in r.summary

    def test_summary_unavailable(self) -> None:
        r = PriorArtReport(query="q", invention_name="I", search_available=False)
        assert "unavailable" in r.summary.lower()

    def test_summary_with_results(self) -> None:
        r = PriorArtReport(
            query="q",
            invention_name="I",
            patents=[
                PatentResult(patent_id="US1", title="Patent A"),
                PatentResult(patent_id="US2", title="Patent B"),
            ],
        )
        assert "2" in r.summary


# ---------------------------------------------------------------------------
# PatentResult & PaperResult
# ---------------------------------------------------------------------------


class TestPatentResult:
    def test_minimal_creation(self) -> None:
        p = PatentResult(patent_id="US123", title="My Patent")
        assert p.patent_id == "US123"
        assert p.abstract == ""

    def test_full_creation(self) -> None:
        p = PatentResult(
            patent_id="US456",
            title="Full Patent",
            abstract="Full abstract",
            filing_date="2023-05-01",
            assignee="BigCorp",
            url="https://patents.google.com/patent/US456",
        )
        assert p.filing_date == "2023-05-01"


class TestPaperResult:
    def test_minimal_creation(self) -> None:
        p = PaperResult(paper_id="abc", title="A Paper")
        assert p.paper_id == "abc"
        assert p.authors == []

    def test_full_creation(self) -> None:
        p = PaperResult(
            paper_id="xyz",
            title="Full Paper",
            abstract="Abstract text",
            authors=["Alice", "Bob"],
            year=2024,
            venue="NeurIPS",
            citation_count=100,
            url="https://semanticscholar.org/xyz",
        )
        assert p.year == 2024
        assert p.citation_count == 100


# ---------------------------------------------------------------------------
# PriorArtSearcher — HTTP mocking
# ---------------------------------------------------------------------------


class TestPriorArtSearcherSemanticScholar:
    async def test_successful_ss_search(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                200,
                _make_ss_response([_make_ss_paper(paper_id="p1", title="NeurIPS Paper")]),
            )
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "ant colony load balancing",
            include_patents=False,
            include_papers=True,
        )

        assert report.search_available
        assert len(report.papers) == 1
        assert report.papers[0].title == "NeurIPS Paper"

    async def test_ss_rate_limit_then_success(self) -> None:
        mock_client = AsyncMock()
        responses = [
            _mock_response(429),
            _mock_response(
                200,
                _make_ss_response([_make_ss_paper(paper_id="p1")]),
            ),
        ]
        mock_client.get = AsyncMock(side_effect=responses)

        searcher = PriorArtSearcher(http_client=mock_client, max_retries=3)

        with patch("asyncio.sleep", new=AsyncMock()):
            report = await searcher.search(
                "query",
                include_patents=False,
                include_papers=True,
            )

        assert len(report.papers) == 1

    async def test_ss_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query",
            include_patents=False,
            include_papers=True,
        )

        assert not report.search_available
        assert len(report.search_errors) > 0

    async def test_ss_timeout(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        searcher = PriorArtSearcher(http_client=mock_client, max_retries=1)
        with patch("asyncio.sleep", new=AsyncMock()):
            report = await searcher.search(
                "query",
                include_patents=False,
                include_papers=True,
            )

        assert not report.search_available

    async def test_ss_non_200_non_429(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(500))

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query",
            include_patents=False,
            include_papers=True,
        )

        # Should succeed but return no papers (empty result, not error)
        assert len(report.papers) == 0

    async def test_ss_empty_results(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(200, _make_ss_response([]))
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query",
            include_patents=False,
            include_papers=True,
        )

        assert report.search_available
        assert report.papers == []
        assert not report.has_prior_art

    async def test_ss_parses_authors(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                200,
                _make_ss_response(
                    [_make_ss_paper(paper_id="p1", title="Test")]
                ),
            )
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query", include_patents=False, include_papers=True
        )
        assert "Alice" in report.papers[0].authors
        assert "Bob" in report.papers[0].authors


class TestPriorArtSearcherGooglePatents:
    async def test_successful_patent_search(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                200,
                _make_google_patents_response(
                    [{"id": "US9999999", "title": "Test Patent"}]
                ),
            )
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "load balancer pheromone",
            include_patents=True,
            include_papers=False,
        )

        assert report.search_available
        assert len(report.patents) == 1
        assert report.patents[0].title == "Test Patent"

    async def test_patents_rate_limit(self) -> None:
        mock_client = AsyncMock()
        responses = [
            _mock_response(429),
            _mock_response(
                200,
                _make_google_patents_response(
                    [{"id": "US1", "title": "Patent"}]
                ),
            ),
        ]
        mock_client.get = AsyncMock(side_effect=responses)

        searcher = PriorArtSearcher(http_client=mock_client, max_retries=3)
        with patch("asyncio.sleep", new=AsyncMock()):
            report = await searcher.search(
                "q", include_patents=True, include_papers=False
            )

        assert len(report.patents) == 1

    async def test_patents_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "q", include_patents=True, include_papers=False
        )

        assert not report.search_available

    async def test_patents_empty_response(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(200, {})
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "q", include_patents=True, include_papers=False
        )

        assert report.search_available
        assert report.patents == []


class TestPriorArtSearcherCombined:
    async def test_both_sources_combined(self) -> None:
        patent_resp = _mock_response(
            200,
            _make_google_patents_response([{"id": "US1", "title": "Patent"}]),
        )
        paper_resp = _mock_response(
            200,
            _make_ss_response([_make_ss_paper(paper_id="p1", title="Paper")]),
        )

        call_count = [0]
        async def get_side_effect(url: str, **kwargs: object) -> MagicMock:
            call_count[0] += 1
            if "patents.google.com" in url:
                return patent_resp
            return paper_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=get_side_effect)

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "combined query",
            include_patents=True,
            include_papers=True,
        )

        assert len(report.patents) == 1
        assert len(report.papers) == 1
        assert report.has_prior_art

    async def test_both_fail_search_unavailable(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query",
            include_patents=True,
            include_papers=True,
        )

        assert not report.search_available
        assert len(report.search_errors) >= 1

    async def test_no_sources_enabled(self) -> None:
        searcher = PriorArtSearcher()
        report = await searcher.search(
            "query",
            include_patents=False,
            include_papers=False,
        )

        assert not report.search_available

    async def test_one_source_fails_other_succeeds(self) -> None:
        paper_resp = _mock_response(
            200,
            _make_ss_response([_make_ss_paper(paper_id="p1", title="Paper")]),
        )

        async def get_side_effect(url: str, **kwargs: object) -> MagicMock:
            if "patents.google.com" in url:
                raise httpx.ConnectError("refused")
            return paper_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=get_side_effect)

        searcher = PriorArtSearcher(http_client=mock_client)
        report = await searcher.search(
            "query", include_patents=True, include_papers=True
        )

        # Papers should be found, patent error captured
        assert len(report.papers) == 1
        # partial success: search_available depends on whether any succeeded
        assert len(report.search_errors) >= 1


class TestPriorArtSearcherContextManager:
    async def test_context_manager(self) -> None:
        async with PriorArtSearcher() as searcher:
            assert searcher._http_client is not None
        # After exit, client is closed

    async def test_close_method(self) -> None:
        searcher = PriorArtSearcher()
        await searcher._get_client()
        assert searcher._http_client is not None
        await searcher.close()
        assert searcher._http_client is None

    async def test_not_close_external_client(self) -> None:
        """Should NOT close an externally provided client."""
        external_client = AsyncMock(spec=httpx.AsyncClient)
        searcher = PriorArtSearcher(http_client=external_client)
        await searcher.close()
        external_client.aclose.assert_not_called()
