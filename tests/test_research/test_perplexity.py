from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.research.benchmark_builder import BenchmarkCorpusBuilder
from hephaestus.research.perplexity import (
    BaselineDossier,
    BenchmarkCase,
    BenchmarkCorpus,
    PerplexityClient,
    ResearchCitation,
    ResearchError,
    _extract_json,
    build_research_reference_state,
    snapshot_research_artifact,
)


def _mock_response(payload: dict, *, status_code: int = 200, text: str = "ok", headers: dict[str, str] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    resp.json.return_value = payload
    return resp


class TestExtractJson:
    def test_extracts_fenced_json(self) -> None:
        data = _extract_json("```json\n{\"summary\": \"ok\"}\n```")
        assert data["summary"] == "ok"

    def test_raises_when_missing_json(self) -> None:
        with pytest.raises(ResearchError):
            _extract_json("no json here")


class TestPerplexityClient:
    @pytest.mark.asyncio
    async def test_build_baseline_dossier(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(return_value=_mock_response({
            "choices": [{"message": {"content": '{"summary":"Modern systems use queues","standard_approaches":["Token buckets"],"common_failure_modes":["stampedes"],"known_bottlenecks":["hot shards"],"keywords_to_avoid":["retry with backoff"],"representative_systems":["Envoy"]}'}}],
            "citations": ["https://example.com/a"],
        }))
        p = PerplexityClient(api_key="test", http_client=client)
        dossier = await p.build_baseline_dossier(problem="test problem", native_domain="distributed_systems")
        assert isinstance(dossier, BaselineDossier)
        assert dossier.summary == "Modern systems use queues"
        assert dossier.keywords_to_avoid == ["retry with backoff"]
        assert dossier.citations[0].url == "https://example.com/a"

    @pytest.mark.asyncio
    async def test_assess_prior_art(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(return_value=_mock_response({
            "choices": [{"message": {"content": '{"summary":"Closest work is adjacent, not identical","overlap_verdict":"ADJACENT_MECHANISM","overlap_confidence":0.72,"findings":[{"title":"Paper A","url":"https://example.com/paper-a","relationship":"ADJACENT_MECHANISM","why_similar":"Similar control loop"}]}'}}],
            "citations": ["https://example.com/paper-a"],
        }))
        p = PerplexityClient(api_key="test", http_client=client)
        summary, verdict, confidence, findings, citations, _raw = await p.assess_prior_art(
            invention_name="Test Invention",
            problem="test problem",
        )
        assert summary.startswith("Closest work")
        assert verdict == "ADJACENT_MECHANISM"
        assert confidence == pytest.approx(0.72)
        assert findings[0].title == "Paper A"
        assert citations[0].url == "https://example.com/paper-a"

    @pytest.mark.asyncio
    async def test_workspace_dossier_and_benchmark_corpus(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            _mock_response({
                "choices": [{"message": {"content": '{"product_category":"developer-tooling","summary":"Competitive space is crowded","comparable_tools":["Tool A"],"architecture_patterns":["queue-backed workers"],"relevant_literature":["Paper X"],"differentiation_opportunities":["better grounding"],"implementation_risks":["prompt drift"]}'}}],
                "citations": ["https://example.com/tool-a"],
            }),
            _mock_response({
                "choices": [{"message": {"content": '{"summary":"Good corpus","cases":[{"problem":"Handle traffic spikes","baseline_solution":"Autoscaling + queue","common_failure_modes":["cold starts"],"evaluation_axes":["p99 latency"],"sources":["https://example.com/spikes"]}]}'}}],
                "citations": ["https://example.com/spikes"],
            }),
        ])
        p = PerplexityClient(api_key="test", http_client=client)
        dossier = await p.build_workspace_dossier(workspace_name="hephaestus", workspace_context="ctx")
        assert dossier.product_category == "developer-tooling"
        assert dossier.comparable_tools == ["Tool A"]

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                self.inner = PerplexityClient(api_key="test", http_client=client)

            async def build_benchmark_corpus(self, *, topic: str, count: int):
                return await self.inner.build_benchmark_corpus(topic=topic, count=count)

            async def close(self):
                return None

        monkeypatch.setattr("hephaestus.research.benchmark_builder.PerplexityClient", _FakeClient)
        builder = BenchmarkCorpusBuilder(topic="distributed systems", count=1)
        corpus = await builder.build()
        assert corpus.summary == "Good corpus"
        assert corpus.cases[0].problem == "Handle traffic spikes"

    @pytest.mark.asyncio
    async def test_unavailable_client_returns_empty_objects(self) -> None:
        p = PerplexityClient(api_key="", http_client=AsyncMock())
        dossier = await p.build_baseline_dossier(problem="x")
        assert dossier.summary == ""
        corpus = await p.build_benchmark_corpus(topic="x", count=2)
        assert corpus.topic == "x"
        assert corpus.cases == []

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            _mock_response({}, status_code=429, text="slow down", headers={"Retry-After": "0"}),
            _mock_response({
                "choices": [{"message": {"content": '{"summary":"Modern systems use queues","standard_approaches":["Token buckets"]}'}}],
                "citations": [],
            }),
        ])
        sleep = AsyncMock()
        monkeypatch.setattr("hephaestus.research.perplexity.asyncio.sleep", sleep)

        p = PerplexityClient(api_key="test", http_client=client, max_retries=2)
        dossier = await p.build_baseline_dossier(problem="test problem")

        assert dossier.summary == "Modern systems use queues"
        assert client.post.await_count == 2
        sleep.assert_awaited()

    @pytest.mark.asyncio
    async def test_retries_on_malformed_model_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = AsyncMock()
        client.post = AsyncMock(side_effect=[
            _mock_response({
                "choices": [{"message": {"content": "not json"}}],
                "citations": [],
            }),
            _mock_response({
                "choices": [{"message": {"content": '{"summary":"Good corpus","cases":[{"problem":"Handle traffic spikes"}]}'}}],
                "citations": [],
            }),
        ])
        sleep = AsyncMock()
        monkeypatch.setattr("hephaestus.research.perplexity.asyncio.sleep", sleep)

        p = PerplexityClient(api_key="test", http_client=client, max_retries=1)
        corpus = await p.build_benchmark_corpus(topic="distributed systems", count=1)

        assert corpus.summary == "Good corpus"
        assert corpus.cases[0].problem == "Handle traffic spikes"
        assert client.post.await_count == 2
        sleep.assert_awaited()

    @pytest.mark.asyncio
    async def test_disabled_client_reports_unavailability(self) -> None:
        p = PerplexityClient(api_key="test", enabled=False, http_client=AsyncMock())

        assert not p.available()
        assert p.unavailability_reason() == "Perplexity research is disabled"

        dossier = await p.build_baseline_dossier(problem="x")
        assert dossier.summary == ""

    def test_benchmark_corpus_serialization_helpers(self) -> None:
        corpus = BenchmarkCorpus(
            topic="distributed systems",
            summary="Grounded benchmark cases for reliability problems.",
            cases=[
                BenchmarkCase(
                    problem="Handle regional failover",
                    baseline_solution="Active-passive replication",
                    common_failure_modes=["split brain"],
                    evaluation_axes=["failover latency"],
                    sources=["https://example.com/failover"],
                )
            ],
            citations=[ResearchCitation(url="https://example.com/failover", title="Failover Paper")],
        )

        md = corpus.to_markdown()
        assert "Benchmark Corpus: distributed systems" in md
        assert "Handle regional failover" in md
        assert "Failover Paper" in md

        payload = corpus.to_dict()
        assert payload["cases"][0]["problem"] == "Handle regional failover"
        assert payload["citations"][0]["title"] == "Failover Paper"


class TestResearchReferenceState:
    def test_snapshot_research_artifact_is_stable(self) -> None:
        artifact = BaselineDossier(
            summary="Queues and token buckets dominate.",
            citations=[ResearchCitation(url="https://example.com/a", title="A")],
            raw_text="raw baseline text",
        )
        snap_a = snapshot_research_artifact("baseline_dossier", artifact, model="sonar-pro")
        snap_b = snapshot_research_artifact("baseline_dossier", artifact, model="sonar-pro")
        assert snap_a is not None
        assert snap_a["signature"] == snap_b["signature"]
        assert snap_a["citation_count"] == 1

    def test_build_research_reference_state_changes_when_inputs_change(self) -> None:
        baseline = BaselineDossier(
            summary="Queues and token buckets dominate.",
            citations=[ResearchCitation(url="https://example.com/a", title="A")],
            raw_text="raw baseline text",
        )
        grounding = BaselineDossier(
            summary="Closest public systems use adaptive routing.",
            citations=[ResearchCitation(url="https://example.com/b", title="B")],
            raw_text="raw grounding text",
        )
        state_a = build_research_reference_state(
            baseline_dossier=baseline,
            grounding_report=grounding,
            model="sonar-pro",
        )
        grounding.citations.append(ResearchCitation(url="https://example.com/c", title="C"))
        state_b = build_research_reference_state(
            baseline_dossier=baseline,
            grounding_report=grounding,
            model="sonar-pro",
        )
        assert state_a is not None and state_b is not None
        assert state_a["reference_signature"] != state_b["reference_signature"]
        assert len(state_b["artifacts"]) == 2
