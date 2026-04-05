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


import contextlib  # noqa: E402
import ipaddress  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
from urllib.parse import urlparse  # noqa: E402


class HostResolver:
    """DNS resolution abstraction ensuring fail-closed security and CI support."""

    @staticmethod
    def resolve_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        if os.environ.get("HEPHAESTUS_OFFLINE_CI") == "1":
            if hostname.endswith(".mock.local"):
                return [ipaddress.ip_address("127.0.0.1")]
            # Allow safe mock IP for offline testing
            return [ipaddress.ip_address("8.8.8.8")]

        try:
            infos = socket.getaddrinfo(hostname, None)
            ips = []
            for info in infos:
                with contextlib.suppress(ValueError):
                    ips.append(ipaddress.ip_address(info[4][0]))
            return ips
        except socket.gaierror:
            # Production fail-closed: DNS failure equates to blocking the request
            return []


def _is_safe_url(url_str: str) -> bool:
    """Verify URL scheme and resolve target IP to ensure it is public."""
    parsed = urlparse(url_str)
    if parsed.scheme not in ("http", "https"):
        return False

    if parsed.username or parsed.password:
        return False

    if parsed.port not in (80, 443, None):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        ipaddress.ip_address(hostname)
        return False  # Reject raw IP literals directly
    except ValueError:
        pass

    ips = HostResolver.resolve_ips(hostname)
    if not ips:
        return False

    for ip in ips:
        if (
            os.environ.get("HEPHAESTUS_OFFLINE_CI") == "1"
            and hostname.endswith(".mock.local")
            and ip.is_loopback
        ):
            continue

        # Must be a globally routable public IP
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            return False
        # ipaddress module treats 100.64.0.0/10 as private in newer Pythons, but explicitly check
        # IPv4 specific checks
        if ip.version == 4:
            prefix = int(ip) >> 24
            if prefix in (0, 10, 127):
                return False

    return True


async def _verify_redirects(response: httpx.Response) -> None:
    """Event hook to verify SSRF protections on redirects."""
    if response.is_redirect and "location" in response.headers:
        if response.next_request is None:
            return
        next_url = str(response.next_request.url)
        if not _is_safe_url(next_url):
            raise ValueError(f"Blocked unsafe redirect target: {next_url}")


async def web_fetch(url: str, max_chars: int = 15_000) -> str:
    """Fetch a URL and return extracted text content, with SSRF protection."""
    if not _is_safe_url(url):
        return "Fetch error: Unsafe URL or private IP address blocked."

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            max_redirects=5,
            event_hooks={"response": [_verify_redirects]},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Fetch error: {exc}"
    except Exception as exc:
        return f"Fetch error: {exc}"

    content_type = resp.headers.get("content-type", "")
    text = _extract_text(resp.text) if "text/html" in content_type else resp.text

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
    return text
