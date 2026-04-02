# Perplexity Research Integration

Hephaestus uses Perplexity as a grounding layer, not as the invention engine.
The invention loop still lives in decomposition, lens search, scoring,
translation, and adversarial verification. Perplexity adds external evidence,
state-of-the-art context, and production-risk reconnaissance around that loop.

## What It Covers

1. Prior art / novelty verification
2. External grounding for invention reports
3. State-of-the-art reconnaissance before invention
4. Research dossier mode for codebases
5. Architecture validation / implementation risk review
6. Benchmark corpus generation

## Configuration

Required for live Perplexity calls:

```bash
export PERPLEXITY_API_KEY=pplx-...
```

Optional environment overrides:

```bash
export HEPHAESTUS_USE_PERPLEXITY_RESEARCH=true
export HEPHAESTUS_PERPLEXITY_MODEL=sonar-pro
```

Project or user config can also set the same defaults:

```yaml
use_perplexity_research: true
perplexity_model: sonar-pro
```

CLI overrides:

```bash
heph --research --research-model sonar-pro "Design a coordination system for drone swarms"
heph --no-research "Design a coordination system for drone swarms"
```

## Runtime Behavior

- Perplexity requests retry on transient transport errors and HTTP `408`, `409`,
  `425`, `429`, `500`, `502`, `503`, and `504`.
- `Retry-After` is respected when present.
- Malformed model JSON is retried before the request is treated as failed.
- If Perplexity is disabled or `PERPLEXITY_API_KEY` is absent, the invention
  pipeline degrades gracefully: the core invention pipeline still runs, but
  external research sections are omitted.
- Explicit benchmark corpus generation is treated as a user-requested research
  action and fails fast if Perplexity research is unavailable.

## CLI Usage

Normal invention run with research enabled:

```bash
heph --research --research-model sonar-pro "I need a scheduler that remains stable under bursty demand"
```

Generate a benchmark corpus directly from the CLI:

```bash
heph --benchmark-corpus "distributed systems" --benchmark-count 12
heph --benchmark-corpus "trust and safety" --format json -o corpora/trust-safety.json
heph --benchmark-corpus "retrieval and ranking" --research-model sonar-pro -o corpora/rag.md
```

## Python Usage

High-level SDK:

```python
from hephaestus import Hephaestus

async with Hephaestus.from_env(
    model="both",
    use_perplexity_research=True,
    perplexity_model="sonar-pro",
) as heph:
    report = await heph.invent("Design a scheduler that stays efficient under flash crowds")
    corpus = await heph.build_benchmark_corpus("distributed systems", count=8)
```

Direct benchmark builder:

```python
from hephaestus.research import BenchmarkCorpusBuilder

builder = BenchmarkCorpusBuilder(
    topic="retrieval and ranking",
    count=10,
    model="sonar-pro",
)
corpus = await builder.build()
```

## Output Surfaces

Invention reports now carry research sections where available:

- `baseline_dossier`
- `grounding_report`
- `implementation_risk_review`

Research artifacts expose serialization helpers:

- `to_dict()`
- `to_json()`
- `to_markdown()` on benchmark corpora and workspace dossiers
- `snapshot_research_artifact()` for stable artifact fingerprints
- `build_research_reference_state()` for reference-generation surfaces

When invention reports also carry lens-engine state, these research artifacts are
collapsed into a stable `reference_generation` and `reference_signature`. That
reference surface is then used to:

- bind research-backed reference lots for resume safety
- invalidate bundle proofs and derived composites when evidence changes
- surface recomposition events in the session and report outputs

That makes it straightforward to persist or inspect research outputs outside the
core invention report flow.

## Use-Case Mapping

### 1. Prior art / novelty verification

- implemented through `PerplexityClient.assess_prior_art()`
- wired into `src/hephaestus/output/prior_art.py`
- surfaced on `PriorArtReport`

### 2. External grounding for invention reports

- implemented through `PerplexityClient.ground_invention_report()`
- wired into `src/hephaestus/core/verifier.py`
- rendered through formatter and markdown export surfaces

### 3. State-of-the-art reconnaissance before invention

- implemented through `PerplexityClient.build_baseline_dossier()`
- wired into `src/hephaestus/core/genesis.py`
- attached to `ProblemStructure` and `InventionReport`

### 4. Research dossier mode for codebases

- implemented through `PerplexityClient.build_workspace_dossier()`
- wired into `src/hephaestus/workspace/inventor.py`
- available as structured data and markdown export

### 5. Architecture validation / implementation risk review

- implemented through `PerplexityClient.review_implementation_risks()`
- wired into `src/hephaestus/core/verifier.py`
- rendered alongside grounded invention output

### 6. Benchmark corpus generation

- implemented through `PerplexityClient.build_benchmark_corpus()`
- exposed through `BenchmarkCorpusBuilder`
- available directly from `heph --benchmark-corpus ...`
