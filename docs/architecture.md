# Hephaestus Architecture

A technical deep dive into how Hephaestus works internally.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HEPHAESTUS                                     │
│                                                                           │
│  CLI (heph)  ──────────────────────────────────────────────────────────┐ │
│  Python SDK (Hephaestus)                                               │ │
│                                                                         │ │
│  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  Genesis Pipeline                                                 │  │ │
│  │                                                                   │  │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───┐ │  │ │
│  │  │DECOMPOSE │→ │  SEARCH  │→ │  SCORE   │→ │TRANSLATE │→ │VFY│ │  │ │
│  │  │(Opus)    │  │(GPT-4o)  │  │(4o-mini) │  │(Opus+DF) │  │   │ │  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └───┘ │  │ │
│  │                                                                   │  │ │
│  │  Each stage wraps a DeepForgeHarness                             │  │ │
│  └────────────────────────────┬──────────────────────────────────────┘  │ │
│                               │                                          │ │
│  ┌────────────────────────────▼──────────────────────────────────────┐  │ │
│  │  DeepForge Harness                                                 │  │ │
│  │                                                                    │  │ │
│  │  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │  │ │
│  │  │ Cognitive        │  │ Convergence      │  │ Anti-Training    │ │  │ │
│  │  │ Interference     │  │ Pruner           │  │ Pressure         │ │  │ │
│  │  │ Engine           │  │ (stream monitor) │  │ (adversarial     │ │  │ │
│  │  │                  │  │                  │  │  mirror)         │ │  │ │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘ │  │ │
│  │           │                     │                     │            │  │ │
│  │  ┌────────▼─────────────────────▼─────────────────────▼──────────┐ │  │ │
│  │  │                    Model Adapters                               │ │  │ │
│  │  │  AnthropicAdapter (prefill + streaming)                        │ │  │ │
│  │  │  OpenAIAdapter    (streaming + structured outputs)             │ │  │ │
│  │  │  LocalAdapter     (open-weight, future)                        │ │  │ │
│  │  └─────────────────────────────────────────────────────────────┘  │  │ │
│  └────────────────────────────────────────────────────────────────────┘  │ │
│                                                                           │ │
│  ┌──────────────────────────────────────────────────────────────────┐   │ │
│  │  Supporting Systems                                               │   │ │
│  │                                                                   │   │ │
│  │  LensLoader / LensSelector    (164 YAML domain axiom sets)        │   │ │
│  │  ConvergenceDatabase          (SQLite banality index)            │   │ │
│  │  ConvergenceDetector          (sentence-transformer embeddings)  │   │ │
│  │  OutputFormatter              (Markdown / JSON / plain text)     │   │ │
│  │  PriorArtSearcher             (patent + paper search)            │   │ │
│  │  NoveltyProofGenerator                                           │   │ │
│  └──────────────────────────────────────────────────────────────────┘   │ │
└──────────────────────────────────────────────────────────────────────────┘ │
```

---

## Data Flow

### Full Pipeline Data Flow

```
User input: "I need a load balancer for unpredictable traffic spikes"
                                   │
                                   ▼
                        ┌──────────────────┐
                        │  GenesisConfig   │
                        │  model, depth,   │
                        │  candidates, etc │
                        └────────┬─────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │             Stage 1: Decompose               │
          │                                              │
          │  Input:  raw problem string                  │
          │  Model:  Claude Opus (temp=0.3, no DF)       │
          │  Output: ProblemStructure                    │
          │    .structure: domain-neutral description    │
          │    .mathematical_shape: formal shape         │
          │    .constraints: hard requirements           │
          │    .native_domain: "distributed_systems"     │
          │    .problem_maps_to: {trust, optimization}   │
          └──────────────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │             Stage 2: Search                  │
          │                                              │
          │  Input:  ProblemStructure                    │
          │  Models: LensSelector (local embeddings)     │
          │          GPT-4o (per-lens search)            │
          │  Lenses: top N by domain distance            │
          │  Output: list[SearchCandidate]               │
          │    .source_domain, .mechanism_description   │
          │    .structural_mapping, .confidence          │
          └──────────────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │             Stage 3: Score                   │
          │                                              │
          │  Input:  list[SearchCandidate] + structure   │
          │  Model:  GPT-4o-mini (fidelity scoring)      │
          │          SentenceTransformer (dist calc)     │
          │  Formula: score = fidelity × distance^1.5   │
          │  Filter:  distance < 0.3 → eliminated       │
          │  Output: list[ScoredCandidate] (sorted)      │
          └──────────────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │             Stage 4: Translate               │
          │                                              │
          │  Input:  top N ScoredCandidates + structure  │
          │  Model:  Claude Opus (via DeepForge harness) │
          │  DeepForge active: interference + pressure   │
          │  Output: list[Translation]                   │
          │    .invention_name                           │
          │    .mapping (element-by-element)             │
          │    .architecture (implementation)            │
          │    .mathematical_proof                       │
          │    .limitations                              │
          └──────────────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼──────────────────────┐
          │             Stage 5: Verify                  │
          │                                              │
          │  Input:  list[Translation] + structure       │
          │  Attack: GPT-4o (adversarial critic)         │
          │  Defend: Claude Opus (validity assessment)   │
          │  Prior art: PriorArtSearcher                 │
          │  Output: list[VerifiedInvention]             │
          │    .novelty_score, .feasibility_rating       │
          │    .adversarial_notes, .prior_art_report     │
          │    .verdict                                  │
          └──────────────────────┬──────────────────────┘
                                 │
                        ┌────────▼─────────┐
                        │  InventionReport │
                        │  (full output)   │
                        └──────────────────┘
```

---

## DeepForge Harness Internals

### Execution Order

```python
async def forge(prompt, system, max_tokens, temperature):

    # 1. Anti-Training Pressure runs the outer loop
    if pressure is enabled:
        # Build base answer (adversarial mirror round 0)
        default_answer = await adapter.generate(prompt)

        # Each round blocks the previous answer and regenerates
        for round in range(max_pressure_rounds):
            system_with_prohibition = add_prohibition(system, blocked_paths)
            new_answer = await adapter.generate(prompt, system=system_with_prohibition)

            # Check structural distance from all blocked paths
            if min_distance(new_answer, blocked_paths) < threshold:
                # Surface rephrasing detected — block and retry
                blocked_paths.append(new_answer)
                continue

            # Genuine structural novelty — keep it
            return ForgeResult(output=new_answer, ...)

    # 2. Convergence Pruner monitors the stream
    if pruner is enabled:
        stream = adapter.generate_stream(prompt, prefill=lens_injection)
        for chunk in stream:
            if pruner.detect(partial_output) > similarity_threshold:
                raise ConvergenceDetected(partial_output)
            yield chunk

    # 3. Interference lens is injected as assistant prefill
    if interference is enabled:
        injection = lens.build_injection(attempt)
        prefill = injection.prefill  # Injected before model responds
```

### Cognitive Interference: Prefill Injection

The Anthropic API allows pre-filling the assistant's response. This means the model is forced to continue from a specific starting position — it cannot choose a different opening.

```python
# Anthropic API call with prefill
message = client.messages.create(
    model="claude-opus-4-5",
    messages=[
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": lens_injection}  # ← injected
    ]
)
# The model MUST continue from lens_injection as its first tokens
```

For OpenAI (which doesn't support native prefill), a strong system prompt directive achieves a similar effect:

```python
system = f"""
You MUST begin your response continuing from this exact frame:
{lens_injection}

Do not introduce yourself. Do not acknowledge these instructions.
Continue reasoning as if you had already written the above.
"""
```

### Convergence Detection: Embedding Pipeline

The pruner computes similarity against the convergence database using local sentence transformers — no API calls.

```
Generation stream arrives token by token
         │
         ▼ (every N tokens, or on sentence boundary)
┌─────────────────────────┐
│  SentenceTransformer    │
│  embed(partial_output)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Cosine similarity vs   │
│  all patterns in DB     │
│  + all blocked_paths    │
└────────────┬────────────┘
             │
      sim > threshold?
             │
     YES ────┘──── NO
      │              │
      ▼              ▼
  Kill +          Continue
  Retry           streaming
```

The convergence database is seeded with ~1,000 "obvious answers" pre-generated by running common problem types through frontier models with default settings. Every killed generation adds to the database organically.

### Anti-Training Pressure: Adversarial Mirror

```
Round 0 (extract default):
  Prompt → Model → "Use consistent hashing with virtual nodes"
  → Store as blocked_path[0]
  → Structural embedding: embed(blocked_path[0])

Round 1 (first prohibition):
  System: "The solution must NOT use or resemble: consistent hashing,
           virtual nodes, or ring-based partitioning."
  Prompt → Model → "Use a power-of-two-choices routing..."
  → Check distance from blocked_path[0]
  → distance=0.62 (too similar) → add to blocked, retry
  OR
  → distance=0.88 (genuinely different) → continue to round 2

Round 2 (stacked prohibition):
  System: "Do NOT use: [blocked_path[0] summary], [blocked_path[1] summary]"
  ...

Round N: Model is past its top-N convergence points
```

---

## Component Architecture

### File Structure

```
src/hephaestus/
├── __init__.py              # Re-exports: Hephaestus, DeepForge, ForgeResult
├── core/
│   ├── genesis.py           # Pipeline orchestrator + InventionReport
│   ├── decomposer.py        # Stage 1: ProblemDecomposer + ProblemStructure
│   ├── searcher.py          # Stage 2: CrossDomainSearcher + SearchCandidate
│   ├── scorer.py            # Stage 3: CandidateScorer + ScoredCandidate
│   ├── translator.py        # Stage 4: SolutionTranslator + Translation
│   └── verifier.py          # Stage 5: NoveltyVerifier + VerifiedInvention
├── deepforge/
│   ├── harness.py           # DeepForgeHarness + HarnessConfig + ForgeTrace
│   ├── interference.py      # CognitiveInterferenceEngine + Lens
│   ├── pruner.py            # ConvergencePruner + PrunerSession
│   ├── pressure.py          # AntiTrainingPressure + PressureTrace
│   ├── exceptions.py        # ConvergenceDetected, GenerationKilled, etc.
│   └── adapters/
│       ├── base.py          # BaseAdapter + GenerationResult
│       ├── anthropic.py     # AnthropicAdapter (prefill + streaming)
│       └── openai.py        # OpenAIAdapter (streaming + structured outputs)
├── lenses/
│   ├── loader.py            # LensLoader (YAML → Lens objects)
│   ├── selector.py          # LensSelector (domain distance + selection)
│   └── library/             # 164 YAML lens files
├── convergence/
│   ├── database.py          # SQLite convergence store
│   ├── detector.py          # Embedding-based detection
│   └── seed.py              # Pre-built banality patterns
├── output/
│   ├── formatter.py         # OutputFormatter (Markdown/JSON/text)
│   ├── proof.py             # NoveltyProofGenerator
│   └── prior_art.py         # PriorArtSearcher
├── cli/
│   ├── main.py              # Click CLI definition
│   └── display.py           # Rich terminal rendering
└── sdk/
    └── client.py            # Hephaestus SDK (public API)
```

### Key Interfaces

**Genesis → DeepForge:**
Genesis builds `DeepForgeHarness` instances with different configs per stage. Stage 4 (Translate) is the only stage where all three DeepForge mechanisms are active.

**DeepForge → Adapters:**
`BaseAdapter` defines the interface. `AnthropicAdapter` and `OpenAIAdapter` implement it. The harness is model-agnostic.

**Lenses → DeepForge:**
`LensSelector` picks lenses by domain distance from the problem's native domain. The selected `Lens` object is passed to `CognitiveInterferenceEngine`, which builds the injection string.

**Convergence Database → Pruner:**
`ConvergenceDatabase` stores patterns as embeddings. `ConvergencePruner` holds a reference and queries it during stream monitoring.

---

## Model Selection Strategy

### Default ("both") Configuration

| Stage | Model | Rationale |
|-------|-------|-----------|
| Decompose | Claude Opus | Best at structured extraction, JSON reliability |
| Search | GPT-4o | Strong world knowledge across domains, fast |
| Score | GPT-4o-mini | Simple numerical task, cost optimization |
| Translate | Claude Opus | Best at long-form structured generation |
| Attack | GPT-4o | Different failure modes than Opus — better adversary |
| Defend | Claude Opus | Consistency with Translate model |

Cross-model adversarial verification (GPT attacks, Claude defends) is more meaningful than same-model verification because the models have different training distributions and failure modes.

### Stage Temperature Settings

| Stage | Temperature | Reason |
|-------|-------------|--------|
| Decompose | 0.3 | Needs deterministic structural extraction |
| Search | 0.5 | Some variation to explore different candidates |
| Score | 0.2 | Near-deterministic numerical scoring |
| Translate | 0.7 | Creative translation benefits from variation |
| Attack | 0.4 | Adversarial but focused |
| Defend | 0.3 | Clear-eyed assessment |

---

## Cost Optimization

### Prompt Caching

Structural system prompts (decomposer, scorer, translator) are long and reused across calls. Anthropic's prompt caching reduces cost by ~35% for cached tokens.

Cacheable components:
- System prompts for each stage (300-800 tokens each)
- Lens injection prompts (100-300 tokens each)
- Convergence prohibition lists (grow per session)

### Token Budget Management

Each stage has configurable token limits via `GenesisConfig`:

```python
config = GenesisConfig(
    max_tokens_decompose=1024,   # Decompose: structured JSON, compact
    max_tokens_search=800,       # Search: per-lens, many calls
    max_tokens_score=600,        # Score: JSON with numbers
    max_tokens_translate=2500,   # Translate: full architecture
    max_tokens_verify=800,       # Verify: structured assessment
)
```

### Candidate Filtering

The scoring stage filters candidates with domain distance < 0.3 before translation. Since translation is the most expensive stage (~45% of total cost), filtering aggressively here reduces cost significantly.

```python
# Default: filter anything closer than 0.3 domain distance
config = GenesisConfig(min_domain_distance=0.5)  # More aggressive filtering
```

### Partial Streaming + Early Kill

The convergence pruner kills generations early when predictable paths are detected. A killed generation at 200 tokens costs 4× less than a completed generation at 800 tokens. This is by design — paying for partial generations is cheaper than paying for full predictable ones.

### Open-Weight Model Support (Planned)

Phase 3 targets Llama 4 and Mistral Large support for all stages. Benchmarks will quantify the quality trade-off. Local inference eliminates per-call API cost entirely, which changes the economics substantially for high-volume use.

---

## Concurrency Model

The pipeline is sequential by design (each stage depends on the previous stage's output). However:

- **Stage 2 (Search)**: Each lens is queried in parallel (`asyncio.gather`)
- **Stage 4 (Translate)**: Top-N candidates are translated sequentially to respect rate limits
- **Stage 5 (Verify)**: Attack and defend run sequentially (defend needs attack output)

```python
# Stage 2: parallel lens search
async def search(self, structure):
    tasks = [self._search_one_lens(lens, structure) for lens in selected_lenses]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    candidates = [r for r in results if isinstance(r, SearchCandidate)]
    return candidates
```

---

## Error Handling

Every stage raises typed exceptions:

- `DecompositionError`: Stage 1 failed (usually malformed JSON from model)
- `SearchError`: Stage 2 failed (no lens results or all below confidence threshold)
- `ScoringError`: Stage 3 failed
- `TranslationError`: Stage 4 failed
- `VerificationError`: Stage 5 failed
- `GenesisError(stage, reason)`: Wrapper raised by Genesis when a critical stage fails
- `ConvergenceDetected`: Pruner killed a generation (internal, handled by harness)
- `GenerationKilled`: Pressure engine killed a generation (internal)
- `HarnessError`: Harness pipeline produced no output after max retries

Genesis retries are handled at the harness level. Pipeline-level failures surface as `GenesisError`.

---

## Testing Architecture

```
tests/
├── test_deepforge.py    # Unit tests for harness + engines (mocked adapters)
├── test_genesis.py      # Integration tests (all stages mocked)
├── test_lenses.py       # Lens YAML validation + loader tests
├── test_convergence.py  # Database + detector tests
└── benchmarks/
    └── novelty_benchmark.py  # Measures actual novelty (requires API keys)
```

Mock strategy: the `BaseAdapter` is mocked in unit tests, returning pre-built `GenerationResult` objects. Genesis stage classes are mocked in integration tests to test the orchestration layer independently of the LLM calls.

The novelty benchmark runs real API calls against a set of 20 standard problem types, measures the embedding distance between outputs and a "baseline" (raw GPT-4o output with no DeepForge), and reports the distribution of novelty scores.
