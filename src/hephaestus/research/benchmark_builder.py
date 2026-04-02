"""Benchmark corpus generation backed by Perplexity research."""

from __future__ import annotations

from dataclasses import dataclass

from hephaestus.research.perplexity import BenchmarkCorpus, PerplexityClient


@dataclass
class BenchmarkCorpusBuilder:
    """Build grounded benchmark corpora for Hephaestus evaluation."""

    topic: str
    count: int = 8
    api_key: str | None = None
    enabled: bool | None = None
    model: str | None = None

    async def build(self) -> BenchmarkCorpus:
        client = PerplexityClient(
            api_key=self.api_key,
            enabled=self.enabled,
            model=self.model,
        )
        try:
            return await client.build_benchmark_corpus(topic=self.topic, count=self.count)
        finally:
            await client.close()


__all__ = ["BenchmarkCorpusBuilder"]
