"""Perplexity-backed research modules for Hephaestus.

This module keeps Perplexity in the grounding/evidence layer rather than the
core invention loop. It supports six concrete use cases:

A. Prior art / novelty verification
B. External grounding for invention reports
C. State-of-the-art reconnaissance before invention
D. Research dossier mode for codebases
E. Architecture validation / implementation risk review
F. Benchmark corpus generation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "sonar-pro"
_DEFAULT_TIMEOUT = 45.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_DELAY = 1.0
_DEFAULT_MAX_RETRY_DELAY = 8.0
_API_URL = "https://api.perplexity.ai/chat/completions"
_RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class ResearchError(RuntimeError):
    """Raised when a Perplexity research call fails irrecoverably."""


class ResearchArtifact:
    """Common serialization helpers for research artifacts."""

    def to_dict(self) -> dict[str, Any]:
        return _artifact_to_dict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class ResearchCitation(ResearchArtifact):
    """A citation returned by Perplexity."""

    url: str
    title: str = ""


@dataclass
class PriorArtFinding(ResearchArtifact):
    """A grounded prior-art candidate or adjacent implementation."""

    title: str
    url: str = ""
    relationship: str = "ADJACENT_MECHANISM"
    why_similar: str = ""


@dataclass
class BaselineDossier(ResearchArtifact):
    """Current state-of-the-art / baseline reconnaissance for a problem."""

    summary: str = ""
    standard_approaches: list[str] = field(default_factory=list)
    common_failure_modes: list[str] = field(default_factory=list)
    known_bottlenecks: list[str] = field(default_factory=list)
    keywords_to_avoid: list[str] = field(default_factory=list)
    representative_systems: list[str] = field(default_factory=list)
    citations: list[ResearchCitation] = field(default_factory=list)
    raw_text: str = ""

    def to_prompt_text(self) -> str:
        parts = ["=== STATE OF THE ART RECONNAISSANCE ==="]
        if self.summary:
            parts.append(f"Summary: {self.summary}")
        if self.standard_approaches:
            parts.append("Standard approaches:")
            parts.extend(f"- {item}" for item in self.standard_approaches[:6])
        if self.common_failure_modes:
            parts.append("Common failure modes:")
            parts.extend(f"- {item}" for item in self.common_failure_modes[:6])
        if self.known_bottlenecks:
            parts.append("Known bottlenecks:")
            parts.extend(f"- {item}" for item in self.known_bottlenecks[:6])
        if self.keywords_to_avoid:
            parts.append("Mechanisms/keywords already conventional in the target domain:")
            parts.extend(f"- {item}" for item in self.keywords_to_avoid[:8])
        if self.representative_systems:
            parts.append("Representative systems / papers / products:")
            parts.extend(f"- {item}" for item in self.representative_systems[:8])
        parts.append("=== END RECONNAISSANCE ===")
        return "\n".join(parts)


@dataclass
class ExternalGroundingReport(ResearchArtifact):
    """Grounding annex for an invention report."""

    summary: str = ""
    closest_related_work: list[str] = field(default_factory=list)
    adjacent_fields: list[str] = field(default_factory=list)
    practitioner_risks: list[str] = field(default_factory=list)
    notable_projects: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    citations: list[ResearchCitation] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ImplementationRiskReview(ResearchArtifact):
    """Operational and implementation risk review for an invention."""

    summary: str = ""
    major_risks: list[str] = field(default_factory=list)
    operational_constraints: list[str] = field(default_factory=list)
    likely_failure_modes: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    citations: list[ResearchCitation] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class WorkspaceResearchDossier(ResearchArtifact):
    """Research dossier for a repo / codebase."""

    product_category: str = ""
    summary: str = ""
    comparable_tools: list[str] = field(default_factory=list)
    architecture_patterns: list[str] = field(default_factory=list)
    relevant_literature: list[str] = field(default_factory=list)
    differentiation_opportunities: list[str] = field(default_factory=list)
    implementation_risks: list[str] = field(default_factory=list)
    citations: list[ResearchCitation] = field(default_factory=list)
    raw_text: str = ""

    def to_prompt_text(self) -> str:
        parts = ["=== EXTERNAL CODEBASE DOSSIER ==="]
        if self.product_category:
            parts.append(f"Product category: {self.product_category}")
        if self.summary:
            parts.append(f"Summary: {self.summary}")
        if self.comparable_tools:
            parts.append("Comparable tools:")
            parts.extend(f"- {item}" for item in self.comparable_tools[:8])
        if self.architecture_patterns:
            parts.append("Architecture patterns in the wild:")
            parts.extend(f"- {item}" for item in self.architecture_patterns[:8])
        if self.relevant_literature:
            parts.append("Relevant literature / adjacent work:")
            parts.extend(f"- {item}" for item in self.relevant_literature[:6])
        if self.differentiation_opportunities:
            parts.append("Differentiation opportunities:")
            parts.extend(f"- {item}" for item in self.differentiation_opportunities[:6])
        if self.implementation_risks:
            parts.append("Known product / implementation risks:")
            parts.extend(f"- {item}" for item in self.implementation_risks[:6])
        parts.append("=== END DOSSIER ===")
        return "\n".join(parts)

    def to_markdown(self) -> str:
        lines = ["# Workspace Research Dossier", ""]
        if self.product_category:
            lines.append(f"**Product Category:** {self.product_category}")
            lines.append("")
        if self.summary:
            lines.append(self.summary)
            lines.append("")
        _markdown_list(lines, "Comparable Tools", self.comparable_tools)
        _markdown_list(lines, "Architecture Patterns", self.architecture_patterns)
        _markdown_list(lines, "Relevant Literature", self.relevant_literature)
        _markdown_list(lines, "Differentiation Opportunities", self.differentiation_opportunities)
        _markdown_list(lines, "Implementation Risks", self.implementation_risks)
        _markdown_citations(lines, self.citations)
        return "\n".join(lines).rstrip() + "\n"


@dataclass
class BenchmarkCase(ResearchArtifact):
    """One benchmarkable real-world problem instance."""

    problem: str
    baseline_solution: str = ""
    common_failure_modes: list[str] = field(default_factory=list)
    evaluation_axes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class BenchmarkCorpus(ResearchArtifact):
    """A benchmark corpus generated from grounded external research."""

    topic: str
    summary: str = ""
    cases: list[BenchmarkCase] = field(default_factory=list)
    citations: list[ResearchCitation] = field(default_factory=list)
    raw_text: str = ""

    def to_markdown(self) -> str:
        lines = [f"# Benchmark Corpus: {self.topic}", ""]
        if self.summary:
            lines.append(self.summary)
            lines.append("")

        if not self.cases:
            lines.append("No benchmark cases were generated.")
            lines.append("")
        for idx, case in enumerate(self.cases, start=1):
            lines.append(f"## Case {idx}: {case.problem}")
            lines.append("")
            if case.baseline_solution:
                lines.append(f"**Baseline Solution:** {case.baseline_solution}")
                lines.append("")
            _markdown_list(lines, "Common Failure Modes", case.common_failure_modes)
            _markdown_list(lines, "Evaluation Axes", case.evaluation_axes)
            _markdown_list(lines, "Sources", case.sources)

        _markdown_citations(lines, self.citations)
        return "\n".join(lines).rstrip() + "\n"


class PerplexityClient:
    """Minimal Perplexity client with JSON-first prompting."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        enabled: bool | None = None,
        model: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay: float = _DEFAULT_RETRY_BASE_DELAY,
        max_retry_delay: float = _DEFAULT_MAX_RETRY_DELAY,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("PERPLEXITY_API_KEY")
        self.enabled = enabled if enabled is not None else _env_bool("HEPHAESTUS_USE_PERPLEXITY_RESEARCH", True)
        self.model = model or os.environ.get("HEPHAESTUS_PERPLEXITY_MODEL", _DEFAULT_MODEL)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        self.max_retry_delay = max(self.retry_base_delay, float(max_retry_delay))
        self._client = http_client
        self._owns_client = http_client is None

    def available(self) -> bool:
        return not self.unavailability_reason()

    def unavailability_reason(self) -> str:
        if not self.enabled:
            return "Perplexity research is disabled"
        if not self.api_key:
            return "PERPLEXITY_API_KEY is not configured"
        return ""

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "HephaestusAI/0.1 PerplexityClient"},
            )
        return self._client

    async def __aenter__(self) -> "PerplexityClient":
        await self._get_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _chat_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> tuple[dict[str, Any], list[ResearchCitation], str]:
        if not self.available():
            raise ResearchError(self.unavailability_reason())

        client = await self._get_client()
        total_attempts = self.max_retries + 1

        for attempt in range(total_attempts):
            try:
                response = await client.post(
                    _API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "return_citations": True,
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_retries:
                    raise ResearchError(
                        f"Perplexity request failed after {total_attempts} attempts: {exc}"
                    ) from exc
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Perplexity transport error on attempt %d/%d: %s; retrying in %.1fs",
                    attempt + 1,
                    total_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code != 200:
                detail = response.text[:300].strip() or "empty response"
                if response.status_code in _RETRIABLE_STATUS_CODES and attempt < self.max_retries:
                    delay = self._retry_delay(attempt, retry_after=response.headers.get("Retry-After"))
                    logger.warning(
                        "Perplexity returned HTTP %d on attempt %d/%d; retrying in %.1fs",
                        response.status_code,
                        attempt + 1,
                        total_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ResearchError(f"Perplexity API returned {response.status_code}: {detail}")

            try:
                payload = response.json()
            except ValueError as exc:
                if attempt >= self.max_retries:
                    raise ResearchError("Perplexity returned an invalid JSON response payload") from exc
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Perplexity returned invalid JSON payload on attempt %d/%d; retrying in %.1fs",
                    attempt + 1,
                    total_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            raw = (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            citations = _extract_citations(payload)
            try:
                data = _extract_json(raw)
            except ResearchError:
                if attempt >= self.max_retries:
                    raise
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Perplexity returned malformed model JSON on attempt %d/%d; retrying in %.1fs",
                    attempt + 1,
                    total_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            return data, citations, raw

        raise ResearchError("Perplexity request exhausted retries without returning a usable response")

    def _retry_delay(self, attempt: int, *, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                retry_after_seconds = float(retry_after)
            except (TypeError, ValueError):
                retry_after_seconds = 0.0
            if retry_after_seconds > 0:
                return min(retry_after_seconds, self.max_retry_delay)
        return min(self.retry_base_delay * (2 ** attempt), self.max_retry_delay)

    async def build_baseline_dossier(
        self,
        *,
        problem: str,
        native_domain: str = "",
        mathematical_shape: str = "",
    ) -> BaselineDossier:
        if not self.available():
            return BaselineDossier()

        system = (
            "You are a state-of-the-art reconnaissance analyst for engineering problems. "
            "Identify what strong practitioners already do today so an invention engine can avoid "
            "reinventing conventional patterns. Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "summary": "short synthesis of the state of the art",
  "standard_approaches": ["..."],
  "common_failure_modes": ["..."],
  "known_bottlenecks": ["..."],
  "keywords_to_avoid": ["mechanisms already conventional in this domain"],
  "representative_systems": ["named papers / products / repos / systems"]
}}

Problem:
{problem}

Native domain:
{native_domain or 'unknown'}

Mathematical shape:
{mathematical_shape or 'not specified'}
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        return BaselineDossier(
            summary=str(data.get("summary", "")),
            standard_approaches=_string_list(data.get("standard_approaches")),
            common_failure_modes=_string_list(data.get("common_failure_modes")),
            known_bottlenecks=_string_list(data.get("known_bottlenecks")),
            keywords_to_avoid=_string_list(data.get("keywords_to_avoid")),
            representative_systems=_string_list(data.get("representative_systems")),
            citations=citations,
            raw_text=raw,
        )

    async def assess_prior_art(
        self,
        *,
        invention_name: str,
        problem: str,
        source_domain: str = "",
        key_insight: str = "",
        architecture: str = "",
        native_domain: str = "",
    ) -> tuple[str, str, float, list[PriorArtFinding], list[ResearchCitation], str]:
        if not self.available():
            return "", "UNKNOWN", 0.0, [], [], ""

        system = (
            "You are a prior-art and novelty analyst. Find the closest existing work and classify the overlap. "
            "The key question is whether THIS SPECIFIC mechanism-domain combination already exists. "
            "Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "summary": "short verdict",
  "overlap_verdict": "SAME_MECHANISM|ADJACENT_MECHANISM|SAME_PROBLEM_DIFFERENT_MECHANISM|NO_STRONG_MATCH",
  "overlap_confidence": 0.0,
  "findings": [
    {{
      "title": "...",
      "url": "...",
      "relationship": "SAME_MECHANISM|ADJACENT_MECHANISM|SAME_PROBLEM_DIFFERENT_MECHANISM|BACKGROUND",
      "why_similar": "..."
    }}
  ],
  "takeaways": ["..."]
}}

Invention name: {invention_name}
Target problem: {problem}
Target domain: {native_domain or 'unknown'}
Source domain: {source_domain or 'unknown'}
Key insight: {key_insight}
Architecture:
{architecture[:3000]}
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        findings = [
            PriorArtFinding(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                relationship=str(item.get("relationship", "ADJACENT_MECHANISM")),
                why_similar=str(item.get("why_similar", "")),
            )
            for item in data.get("findings", [])
            if isinstance(item, dict) and item.get("title")
        ]
        return (
            str(data.get("summary", "")),
            str(data.get("overlap_verdict", "UNKNOWN")),
            _safe_float(data.get("overlap_confidence"), 0.0),
            findings,
            citations,
            raw,
        )

    async def ground_invention_report(
        self,
        *,
        problem: str,
        invention_name: str,
        source_domain: str,
        key_insight: str,
        architecture: str,
    ) -> ExternalGroundingReport:
        if not self.available():
            return ExternalGroundingReport()

        system = (
            "You are an external grounding analyst. Connect an invention to the real world: "
            "related work, adjacent fields, practitioner caveats, and relevant systems. Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "summary": "short synthesis",
  "closest_related_work": ["..."],
  "adjacent_fields": ["..."],
  "practitioner_risks": ["..."],
  "notable_projects": ["named companies / products / repos / papers"],
  "references": ["specific external references worth reading"]
}}

Problem: {problem}
Invention: {invention_name}
Source domain: {source_domain}
Key insight: {key_insight}
Architecture:
{architecture[:3000]}
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        return ExternalGroundingReport(
            summary=str(data.get("summary", "")),
            closest_related_work=_string_list(data.get("closest_related_work")),
            adjacent_fields=_string_list(data.get("adjacent_fields")),
            practitioner_risks=_string_list(data.get("practitioner_risks")),
            notable_projects=_string_list(data.get("notable_projects")),
            references=_string_list(data.get("references")),
            citations=citations,
            raw_text=raw,
        )

    async def review_implementation_risks(
        self,
        *,
        problem: str,
        invention_name: str,
        architecture: str,
        key_insight: str = "",
    ) -> ImplementationRiskReview:
        if not self.available():
            return ImplementationRiskReview()

        system = (
            "You are a production architecture risk reviewer. Focus on implementation traps, operating constraints, "
            "and mitigations observed in real systems. Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "summary": "short synthesis",
  "major_risks": ["..."],
  "operational_constraints": ["..."],
  "likely_failure_modes": ["..."],
  "mitigations": ["..."]
}}

Problem: {problem}
Invention: {invention_name}
Key insight: {key_insight}
Architecture:
{architecture[:3000]}
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        return ImplementationRiskReview(
            summary=str(data.get("summary", "")),
            major_risks=_string_list(data.get("major_risks")),
            operational_constraints=_string_list(data.get("operational_constraints")),
            likely_failure_modes=_string_list(data.get("likely_failure_modes")),
            mitigations=_string_list(data.get("mitigations")),
            citations=citations,
            raw_text=raw,
        )

    async def build_workspace_dossier(
        self,
        *,
        workspace_name: str,
        workspace_context: str,
    ) -> WorkspaceResearchDossier:
        if not self.available():
            return WorkspaceResearchDossier()

        system = (
            "You are a product and architecture research analyst for software codebases. "
            "Given repo context, identify comparable tools, prevalent architecture patterns, gaps, and risks. "
            "Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "product_category": "...",
  "summary": "...",
  "comparable_tools": ["..."],
  "architecture_patterns": ["..."],
  "relevant_literature": ["..."],
  "differentiation_opportunities": ["..."],
  "implementation_risks": ["..."]
}}

Workspace name: {workspace_name}
Workspace context:
{workspace_context[:12000]}
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        return WorkspaceResearchDossier(
            product_category=str(data.get("product_category", "")),
            summary=str(data.get("summary", "")),
            comparable_tools=_string_list(data.get("comparable_tools")),
            architecture_patterns=_string_list(data.get("architecture_patterns")),
            relevant_literature=_string_list(data.get("relevant_literature")),
            differentiation_opportunities=_string_list(data.get("differentiation_opportunities")),
            implementation_risks=_string_list(data.get("implementation_risks")),
            citations=citations,
            raw_text=raw,
        )

    async def build_benchmark_corpus(
        self,
        *,
        topic: str,
        count: int = 8,
    ) -> BenchmarkCorpus:
        if not self.available():
            return BenchmarkCorpus(topic=topic)

        system = (
            "You are building an evaluation corpus for an invention engine. Select real engineering problems with strong baselines, "
            "clear failure modes, and measurable evaluation axes. Return ONLY valid JSON."
        )
        user = f"""
Return JSON with this schema:
{{
  "summary": "...",
  "cases": [
    {{
      "problem": "...",
      "baseline_solution": "...",
      "common_failure_modes": ["..."],
      "evaluation_axes": ["..."],
      "sources": ["..."]
    }}
  ]
}}

Topic: {topic}
Number of cases: {count}
The cases should be diverse and benchmarkable.
""".strip()
        data, citations, raw = await self._chat_json(system=system, user=user)
        cases = []
        for item in data.get("cases", []):
            if not isinstance(item, dict) or not item.get("problem"):
                continue
            cases.append(
                BenchmarkCase(
                    problem=str(item.get("problem", "")),
                    baseline_solution=str(item.get("baseline_solution", "")),
                    common_failure_modes=_string_list(item.get("common_failure_modes")),
                    evaluation_axes=_string_list(item.get("evaluation_axes")),
                    sources=_string_list(item.get("sources")),
                )
            )
        return BenchmarkCorpus(
            topic=topic,
            summary=str(data.get("summary", "")),
            cases=cases[:count],
            citations=citations,
            raw_text=raw,
        )


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, count=1)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ResearchError(f"No JSON found in Perplexity output: {text[:200]}")

    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise ResearchError(f"Could not parse Perplexity JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchError("Perplexity output was not a JSON object")
    return payload


def _extract_citations(payload: dict[str, Any]) -> list[ResearchCitation]:
    citations: list[ResearchCitation] = []
    for item in payload.get("citations", []):
        if isinstance(item, str) and item:
            citations.append(ResearchCitation(url=item))
            continue
        if isinstance(item, dict):
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if url or title:
                citations.append(ResearchCitation(url=url, title=title))
    return citations


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _artifact_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _artifact_to_dict(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _artifact_to_dict(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_artifact_to_dict(item) for item in value]
    return value


def _citation_urls(artifact: Any) -> list[str]:
    citations = getattr(artifact, "citations", []) or []
    urls: list[str] = []
    for item in citations:
        url = str(getattr(item, "url", item if isinstance(item, str) else "")).strip()
        if url:
            urls.append(url)
    return sorted(set(urls))


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_research_artifact(
    artifact_name: str,
    artifact: Any,
    *,
    provider: str = "perplexity",
    model: str = "",
) -> dict[str, Any] | None:
    """Return a stable fingerprint for a research artifact."""
    if artifact is None:
        return None

    summary = str(getattr(artifact, "summary", "") or "").strip()
    raw_text = str(getattr(artifact, "raw_text", "") or "").strip()
    citations = _citation_urls(artifact)
    payload = {
        "artifact_name": artifact_name,
        "provider": provider,
        "model": model,
        "summary": summary,
        "citations": citations,
        "raw_digest": _text_digest(raw_text) if raw_text else "",
    }
    signature_basis = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    payload["signature"] = _text_digest(signature_basis)
    payload["citation_count"] = len(citations)
    return payload


def build_research_reference_state(
    *,
    baseline_dossier: Any = None,
    grounding_report: Any = None,
    implementation_risk_review: Any = None,
    provider: str = "perplexity",
    model: str = "",
) -> dict[str, Any] | None:
    """Build a stable reference-generation surface from attached research artifacts."""
    artifacts = [
        snapshot_research_artifact("baseline_dossier", baseline_dossier, provider=provider, model=model),
        snapshot_research_artifact("grounding_report", grounding_report, provider=provider, model=model),
        snapshot_research_artifact(
            "implementation_risk_review",
            implementation_risk_review,
            provider=provider,
            model=model,
        ),
    ]
    compact = [artifact for artifact in artifacts if artifact is not None]
    if not compact:
        return None

    reference_signature = _text_digest(
        json.dumps(compact, sort_keys=True, ensure_ascii=False)
    )
    return {
        "reference_generation": 1,
        "provider": provider,
        "model": model,
        "reference_signature": reference_signature,
        "artifacts": compact,
    }


def _markdown_list(lines: list[str], title: str, items: list[str]) -> None:
    if not items:
        return
    lines.append(f"## {title}")
    lines.append("")
    lines.extend(f"- {item}" for item in items)
    lines.append("")


def _markdown_citations(lines: list[str], citations: list[ResearchCitation]) -> None:
    if not citations:
        return
    lines.append("## Citations")
    lines.append("")
    for citation in citations:
        label = citation.title or citation.url
        if citation.url and citation.title:
            lines.append(f"- {citation.title} — {citation.url}")
        else:
            lines.append(f"- {label}")
    lines.append("")


__all__ = [
    "BaselineDossier",
    "BenchmarkCase",
    "BenchmarkCorpus",
    "ExternalGroundingReport",
    "ImplementationRiskReview",
    "PerplexityClient",
    "PriorArtFinding",
    "ResearchArtifact",
    "ResearchCitation",
    "ResearchError",
    "WorkspaceResearchDossier",
    "build_research_reference_state",
    "snapshot_research_artifact",
]
