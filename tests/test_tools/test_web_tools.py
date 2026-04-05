"""Tests for web_search and web_fetch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.tools.web_tools import _extract_text, web_fetch, web_search


def _mock_client(mock_resp):
    """Build an async httpx client mock returning mock_resp."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_returns_abstract_and_topics(self):
        resp = MagicMock()
        resp.json.return_value = {
            "AbstractText": "Python is a programming language.",
            "AbstractURL": "https://python.org",
            "RelatedTopics": [
                {"Text": "Python tutorial", "FirstURL": "https://docs.python.org"},
            ],
        }
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_search("python programming")
        assert "Python is a programming language" in result
        assert "Python tutorial" in result

    @pytest.mark.asyncio
    async def test_returns_no_results(self):
        resp = MagicMock()
        resp.json.return_value = {"AbstractText": "", "RelatedTopics": []}
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_search("xyzzy_nonexistent")
        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.HTTPError("refused"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=client):
            result = await web_search("test")
        assert "Search error" in result

    @pytest.mark.asyncio
    async def test_respects_max_results(self):
        topics = [{"Text": f"Topic {i}", "FirstURL": f"https://x.com/{i}"} for i in range(20)]
        resp = MagicMock()
        resp.json.return_value = {"AbstractText": "", "RelatedTopics": topics}
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_search("test", max_results=3)
        assert result.count("Topic") <= 3

    @pytest.mark.asyncio
    async def test_handles_generic_exception(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=client):
            result = await web_search("test")
        assert "Search error" in result


class TestWebFetch:
    @pytest.mark.asyncio
    async def test_fetches_html(self):
        resp = MagicMock()
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        resp.text = "<html><body><p>Hello world</p></body></html>"
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_fetch("https://example.com")
        assert "Hello world" in result

    @pytest.mark.asyncio
    async def test_truncates(self):
        resp = MagicMock()
        resp.headers = {"content-type": "text/plain"}
        resp.text = "x" * 20000
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_fetch("https://example.com", max_chars=100)
        assert "truncated" in result

    @pytest.mark.asyncio
    async def test_handles_error(self):
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.HTTPError("404"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=client):
            result = await web_fetch("https://example.com/404")
        assert "Fetch error" in result

    @pytest.mark.asyncio
    async def test_plain_text(self):
        resp = MagicMock()
        resp.headers = {"content-type": "text/plain"}
        resp.text = "Just plain text"
        resp.raise_for_status = MagicMock()
        with patch("hephaestus.tools.web_tools.httpx.AsyncClient", return_value=_mock_client(resp)):
            result = await web_fetch("https://example.com/f.txt")
        assert result == "Just plain text"


class TestExtractText:
    def test_strips_tags(self):
        assert "Hello" in _extract_text("<p>Hello</p>")

    def test_strips_scripts(self):
        result = _extract_text("<script>alert('x')</script><p>Content</p>")
        assert "alert" not in result
        assert "Content" in result

    def test_strips_styles(self):
        result = _extract_text("<style>body{color:red}</style><p>Content</p>")
        assert "color" not in result
        assert "Content" in result

    def test_decodes_entities(self):
        assert "&" in _extract_text("&amp;")
        assert "<" in _extract_text("&lt;")
