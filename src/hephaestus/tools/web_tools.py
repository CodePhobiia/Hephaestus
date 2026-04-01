"""Web tools: search and fetch."""

from __future__ import annotations

import html
import re

import httpx


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via a simple search API. Returns formatted results."""
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1", "t": "hephaestus"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return f"Search error: {exc}"
    except Exception as exc:
        return f"Search error: {exc}"

    results: list[str] = []
    # Abstract (instant answer)
    abstract = data.get("AbstractText", "")
    if abstract:
        results.append(f"Summary: {abstract}")
        source = data.get("AbstractURL", "")
        if source:
            results.append(f"Source: {source}")

    # Related topics
    for topic in data.get("RelatedTopics", [])[:max_results]:
        text = topic.get("Text", "")
        link = topic.get("FirstURL", "")
        if text:
            results.append(f"- {text}")
            if link:
                results.append(f"  {link}")

    if not results:
        return f"No results found for: {query}"
    return "\n".join(results)


def _extract_text(html_content: str) -> str:
    """Strip HTML tags and decode entities to plain text."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def web_fetch(url: str, max_chars: int = 15_000) -> str:
    """Fetch a URL and return extracted text content."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Fetch error: {exc}"
    except Exception as exc:
        return f"Fetch error: {exc}"

    content_type = resp.headers.get("content-type", "")
    if "text/html" in content_type:
        text = _extract_text(resp.text)
    else:
        text = resp.text

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
    return text
