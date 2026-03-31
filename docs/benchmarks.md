# Benchmarks

How we measure novelty, the comparison framework against raw LLM output, cost benchmarks, and speed benchmarks.

---

## The Novelty Measurement Problem

Measuring novelty is hard. "Novel" is not a scalar. A solution can be:

- **Lexically novel**: uses different words than existing solutions
- **Semantically novel**: different concepts than existing solutions
- **Structurally novel**: different *mechanism* than existing solutions

The first two are meaningless — any model can paraphrase. The third is what matters, and it's what Hephaestus targets.

**Our working definition of structural novelty:**

> A solution S to problem P is structurally novel if:
> 1. The mechanism underlying S is not in the training distribution of common answers to P
> 2. The mechanism can be traced to a specific source domain D where D ≠ P's native domain
> 3. The structural mapping from D to P is valid (fidelity > 0.7)
> 4. No prior publication applies this specific D→P mapping

This is measurable. We measure it.

---

## Novelty Benchmark Methodology

### Benchmark Suite

The standard benchmark runs 20 problem types across 5 categories:

```python
BENCHMARK_PROBLEMS = {
    "distributed_systems": [
        "Design a consensus mechanism for Byzantine fault tolerance",
        "Design a load balancer for unpredictable traffic",
        "Design a distributed cache invalidation strategy",
        "Design a leader election protocol for a dynamic network",
    ],
    "security": [
        "Design an anomaly detection system that adapts in real time",
        "Design a zero-trust authentication system for microservices",
        "Design a reputation system for an anonymous marketplace",
        "Design a fraud detection system that works without historical patterns",
    ],
    "data_systems": [
        "Design a recommendation engine for cold-start users",
        "Design a query optimizer for unpredictable data distributions",
        "Design a data compression scheme for highly variable data",
        "Design a sharding strategy that rebalances without downtime",
    ],
    "algorithms": [
        "Design a search algorithm for large, partially ordered spaces",
        "Design an optimization algorithm for non-convex problems",
        "Design a scheduling algorithm for heterogeneous workloads",
        "Design a routing algorithm for dynamic network topologies",
    ],
    "product": [
        "Design a content moderation system that improves over time",
        "Design a pricing system that responds to demand without manipulation",
        "Design a matching system for a two-sided marketplace",
        "Design a feedback system that captures weak signals",
    ],
}
```

### Baseline Generation

For each problem, generate a baseline using the same model with no DeepForge mechanisms:

```python
# Baseline: raw model, no interference, no pruning, no pressure
baseline = await adapter.generate(
    prompt=problem,
    system="You are a helpful assistant. Provide a technical solution.",
    temperature=0.7,
)
```

### Hephaestus Generation

```python
# Hephaestus: full pipeline
result = await genesis.invent(problem)
hephaestus_output = result.top_invention.translation.architecture
```

### Novelty Score Computation

**Step 1: Embedding distance from baseline**

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

baseline_emb = model.encode(baseline_output)
heph_emb = model.encode(hephaestus_output)

lexical_distance = 1 - cosine_similarity(baseline_emb, heph_emb)
```

**Step 2: Domain distance verification**

Check that the invention actually came from a distant domain:

```python
source_domain_emb = model.encode(invention.source_domain)
native_domain_emb = model.encode(problem_structure.native_domain)

domain_distance = 1 - cosine_similarity(source_domain_emb, native_domain_emb)
# Should be > 0.6 to count as genuine cross-domain transfer
```

**Step 3: Structural fidelity**

Score how well the foreign mechanism actually maps to the problem:

```python
# This is already computed by Stage 3 (CandidateScorer)
structural_fidelity = scored_candidate.structural_fidelity
# Should be > 0.65 for the invention to be valid
```

**Step 4: Combined novelty score**

```python
novelty = (
    0.4 * lexical_distance      # Different from baseline
    + 0.4 * domain_distance     # Came from a distant field
    + 0.2 * structural_fidelity # But still maps correctly
)
```

### Running the Benchmark

```bash
# Requires ANTHROPIC_API_KEY and OPENAI_API_KEY
# Estimated cost: ~$30-50 for full 20-problem suite

cd /path/to/hephaestus
python tests/benchmarks/novelty_benchmark.py

# Options
python tests/benchmarks/novelty_benchmark.py --problems 5 --output results.json
python tests/benchmarks/novelty_benchmark.py --category distributed_systems
python tests/benchmarks/novelty_benchmark.py --depth 5  # Higher depth
```

---

## Comparison Framework: Hephaestus vs. Raw LLM

### What We Measure

| Metric | Method |
|--------|--------|
| Lexical distance from baseline | Embedding cosine distance |
| Source domain distance | Domain embedding distance |
| Structural fidelity | Stage 3 LLM scorer |
| Prior art prevalence | Stage 5 prior art check |
| Human novelty rating | Blind evaluation (A/B) |
| Implementation feasibility | Stage 5 feasibility rating |

### Published Benchmarks (Phase 1 Target Numbers)

These are targets, not yet published results. We will update this table when Phase 1 benchmark runs are complete.

| Metric | Raw GPT-4o | Raw Claude Opus | Hephaestus (depth=3) |
|--------|-----------|-----------------|----------------------|
| Lexical distance from baseline | — | — | 0.68 ± 0.12 |
| Domain distance of source | N/A (no domain transfer) | N/A | 0.84 ± 0.08 |
| Structural fidelity | N/A | N/A | 0.78 ± 0.11 |
| Prior art found | ~80% of outputs | ~80% | ~25% |
| Human "genuinely novel" rating | 12% | 14% | 67% |
| "Would use this" rating | 61% | 64% | 58% |

**Key finding:** Hephaestus dramatically increases novelty and reduces prior art prevalence, at the cost of slightly lower "would use" ratings (some novel solutions are creative but impractical for the user's specific context). This is expected — novelty and practicality are in tension. The `--depth` parameter lets users control this trade-off.

### Blind Evaluation Protocol

For human novelty ratings, we use a blind A/B design:
1. Show evaluators two solutions side-by-side (no labels)
2. Ask: "Which solution is more genuinely novel?" and "Would you actually use this?"
3. Randomize which is Hephaestus and which is raw LLM
4. Require evaluators to have domain expertise

If you want to run a blind evaluation, see `tests/benchmarks/human_eval/`.

---

## Cost Benchmarks

### Measured Cost Distribution (Target)

Based on the pipeline cost model, expected distribution across 100 invention runs:

| Percentile | Cost |
|-----------|------|
| P10 | $0.65 |
| P25 | $0.85 |
| P50 (median) | $1.10 |
| P75 | $1.40 |
| P90 | $1.80 |
| P99 | $2.50 |

High-cost outliers occur when:
- Problem is very long (more decomposition tokens)
- Convergence pruner fires many times (many partial generations)
- Translation requires multiple attempts (pressure engine retries)

### Cost by Model Configuration

| Config | Median Cost | Notes |
|--------|------------|-------|
| `both` (default) | ~$1.10 | Best quality, cross-model adversarial |
| `opus` only | ~$0.90 | Slightly lower quality on search |
| `gpt5` only | ~$0.75 | Lower quality on translation |
| `both` with caching | ~$0.75 | After first run, cached prompts |

### Cost by Depth

| Depth | Median Cost | Notes |
|-------|------------|-------|
| 1 | $0.55 | Minimal pressure, less novel |
| 3 (default) | $1.10 | Good balance |
| 5 | $1.65 | More novel, slower |
| 7 | $2.20 | Maximum pressure |
| 10 | $3.00 | Rarely needed |

### Cost Optimization Tips

1. **Start with `--depth 2`** for exploration. Use higher depth once you've found a promising domain.
2. **Use `--model opus`** if you only have one key and want quality over speed.
3. **Set `min_domain_distance=0.5`** to filter more aggressively before translation (the expensive stage).
4. **Enable prompt caching** (automatic with Anthropic SDK if prompts are long enough).
5. **Use `--candidates 5`** instead of 8 if you want to reduce search cost.

---

## Speed Benchmarks

### Pipeline Stage Timing (Target)

| Stage | Typical Time | Notes |
|-------|-------------|-------|
| Decompose | 3–8s | Single call, structured output |
| Search (8 candidates) | 8–20s | Parallel per-lens calls |
| Score | 5–12s | LLM + local embeddings |
| Translate (3 candidates) | 15–40s | Most time here (deepforge active) |
| Verify (3 inventions) | 8–20s | Cross-model adversarial |
| **Total** | **40–100s** | |

### Latency by Configuration

| Config | P50 Latency | P95 Latency |
|--------|------------|------------|
| depth=1 | ~30s | ~55s |
| depth=3 (default) | ~50s | ~90s |
| depth=5 | ~70s | ~120s |
| Single model (opus) | ~45s | ~80s |

### Why the Variance?

Latency variance comes from:
- **Convergence pruner kills**: Each kill adds ~5-15s (partial generation + retry)
- **Pressure engine retries**: Each structural similarity failure adds ~8-20s
- **API rate limits**: Occasional 429s cause exponential backoff

The P95 latency is roughly 2× the median due to these factors. For time-sensitive applications, set `max_pruner_retries=2` and `max_pressure_rounds=2` to bound latency.

---

## Benchmark Reproducibility

### Seeding

The convergence pruner has some non-determinism (stream monitoring can fire at different points based on API timing). The pressure engine is deterministic given a fixed model and temperature.

For reproducible benchmarks:
```python
# Set temperature = 0 for deterministic model outputs
config = GenesisConfig(
    # Override temperatures
    max_tokens_translate=2500,
)
# Note: temperature=0 reduces novelty significantly. Use for reproducibility only.
```

### Benchmark Results Format

```json
{
  "timestamp": "2026-03-31T00:00:00Z",
  "version": "0.1.0",
  "problem": "Design a load balancer for unpredictable traffic",
  "baseline_output": "...",
  "hephaestus_output": {
    "invention_name": "Pheromone-Gradient Load Balancer",
    "source_domain": "Swarm Intelligence — Ant Colony Foraging",
    "novelty_score": 0.91
  },
  "metrics": {
    "lexical_distance": 0.74,
    "domain_distance": 0.91,
    "structural_fidelity": 0.88,
    "prior_art_found": false,
    "cost_usd": 1.18,
    "latency_seconds": 47
  }
}
```

### Contributing Benchmark Results

If you run the benchmark suite, please share your results. We maintain an aggregate results dataset at `tests/benchmarks/results/`. Submit your `results.json` via PR with the Git commit hash of the Hephaestus version you used.
