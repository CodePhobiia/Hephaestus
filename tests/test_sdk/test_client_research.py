from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.research.perplexity import BenchmarkCase, BenchmarkCorpus
from hephaestus.sdk import BenchmarkCorpusBuilder, ConfigurationError, Hephaestus, PerplexityClient


class TestSdkResearchExports:
    def test_public_exports_available(self) -> None:
        assert Hephaestus is not None
        assert BenchmarkCorpusBuilder is not None
        assert PerplexityClient is not None


class TestHephaestusResearchClient:
    @pytest.mark.asyncio
    async def test_build_benchmark_corpus(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")

        corpus = BenchmarkCorpus(
            topic="distributed systems",
            summary="Grounded corpus",
            cases=[BenchmarkCase(problem="Handle failover")],
        )
        fake_client = MagicMock()
        fake_client.available.return_value = True
        fake_client.build_benchmark_corpus = AsyncMock(return_value=corpus)
        fake_client.close = AsyncMock()

        with patch("hephaestus.research.PerplexityClient", return_value=fake_client):
            client = Hephaestus(model="gpt5")
            result = await client.build_benchmark_corpus("distributed systems", count=1)

        assert result.topic == "distributed systems"
        fake_client.build_benchmark_corpus.assert_awaited_once_with(
            topic="distributed systems", count=1
        )
        fake_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_benchmark_corpus_requires_research(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")

        client = Hephaestus(model="gpt5", use_perplexity_research=False)

        with pytest.raises(ConfigurationError, match="disabled"):
            await client.build_benchmark_corpus("distributed systems")
