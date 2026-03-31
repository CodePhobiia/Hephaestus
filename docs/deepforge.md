# DeepForge Harness

DeepForge is the LLM harness that powers Hephaestus. It wraps any frontier model and makes it structurally incapable of producing predictable output through three mechanisms. You can use it standalone — without the Genesis invention pipeline — for any task where you need a model to escape its default reasoning patterns.

---

## Three Mechanisms

### Mechanism 1: Cognitive Interference

**What it does:** Injects foreign-domain axioms into the model's active reasoning at the start of generation.

**How it works:** On the Anthropic API, the harness uses *assistant prefill injection* — it pre-fills the start of the model's response with a domain lens. The model is forced to continue from inside an alien conceptual frame. It cannot choose a different opening. The first thing the model "says" is the lens framing, and it must reason forward from there.

```
Without interference:
  User: "Design a consensus mechanism for Byzantine fault tolerance"
  Model: "The most robust approach is a PBFT variant with..."
          ↑ Same answer everyone gets

With immune system lens:
  User: "Design a consensus mechanism for Byzantine fault tolerance"
  Prefill: "Reasoning through the lens of biological immune response:
            every node is a lymphocyte that must perform antigen
            presentation before its vote is accepted..."
  Model: [continues from this frame, cannot restart]
          ↑ Novel territory
```

**For OpenAI models** (which don't support native prefill), the interference is applied via a strong system prompt directive that instructs the model to begin reasoning from the lens frame and prohibits breaking out of it.

**Injection strategies:**

| Strategy | Behavior | Use case |
|----------|----------|----------|
| `FULL` | Inject all lens axioms | Maximum disruption, broadest interference |
| `SINGLE` | Inject the most structurally distant axiom | Surgical, coherent transfer |
| `PROGRESSIVE` | Add one more axiom per retry | Escalating pressure across attempts |

**Lens rotation:** On each retry (after a pruner kill), the harness rotates to a different lens, ensuring the model explores different conceptual frames across attempts.

---

### Mechanism 2: Convergence Pruning

**What it does:** Monitors the output stream in real time and kills the generation when it detects the model heading toward a predictable answer.

**How it works:**

1. Generation streams token by token
2. Every N tokens (or on sentence boundaries), the pruner computes an embedding of the partial output
3. This embedding is compared against the convergence database (known-boring patterns) and the session's blocked paths via cosine similarity
4. If similarity exceeds the threshold (default: 0.82), the generation is killed immediately
5. The killed partial output is stored as a blocked path, a new lens is applied, and generation restarts

```
Stream: "The best approach to this routing problem is a consistent hash—"
Pruner: "Cosine similarity to 'consistent hashing' pattern: 0.89 > 0.82"
Action: KILL + RETRY with 'consistent hashing' explicitly blocked
```

**The convergence database** is a SQLite store of pre-computed embeddings of "boring answers" — the outputs frontier models produce when you ask common questions without any interference. It's seeded with ~1,000 patterns across common problem classes. Every pruner kill adds to the database organically.

Key insight: **this is a banality database, not a novelty database**. We don't need to know what's novel — we just need to know what's boring. The boring answers are the ones everyone already has.

**Configuration:**

```python
from hephaestus.deepforge.pruner import ConvergencePattern

patterns = [
    ConvergencePattern(text="consistent hashing with virtual nodes"),
    ConvergencePattern(text="cap theorem tradeoffs"),
]

config = HarnessConfig(
    use_pruner=True,
    similarity_threshold=0.82,    # Lower = more aggressive killing
    max_pruner_retries=5,         # Max retries before accepting best output
    convergence_patterns=patterns, # Seed patterns for this session
)
```

---

### Mechanism 3: Anti-Training Pressure

**What it does:** Applies counter-pressure against the model's RLHF-trained preferences by using the model's own default answer as a wall to climb over.

**The adversarial mirror:**

```
Round 0: Get the model's default answer
  Prompt → Model → "Use consistent hashing with virtual nodes [...]"
  → Store as blocked_path_0

Round 1: Feed it back as a prohibition
  System: "Do NOT produce a solution that resembles, restates, or is
           structurally similar to: 'consistent hashing, ring-based
           partitioning, or virtual node assignment'"
  Prompt → Model → "Consider a power-of-two-choices approach with..."
  → Check structural distance from blocked_path_0
  → If similarity > 0.75: this is a rephrasing, block and retry
  → If similarity < 0.75: genuine structural difference, keep it

Round 2: Stack both prohibitions
  System: "Do NOT use: [summary_0], [summary_1]"
  Prompt → Model → [forced into third alternative]

Round N: The model is past its top-N convergence points
```

**Structural incompatibility verification:** Between rounds, the harness checks that the new output isn't just a surface rephrasing of a blocked path. It uses embedding cosine distance — if the new output is too similar to any blocked path (above the `structural_distance_threshold`), it's treated as a rephrasing and blocked.

**Configuration:**

```python
config = HarnessConfig(
    use_pressure=True,
    max_pressure_rounds=3,              # How many rounds of stacking
    structural_distance_threshold=0.75,  # Similarity above which = rephrasing
)
```

Higher `max_pressure_rounds` = more novel output = more expensive.

---

## Using DeepForge Standalone

You don't need the Genesis pipeline to use DeepForge. Use it directly for any task where you want the model to escape its defaults.

### Basic Usage

```python
import asyncio
from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter

async def main():
    adapter = AnthropicAdapter(model="claude-opus-4-5")
    harness = DeepForgeHarness(adapter)

    result = await harness.forge(
        "Design a consensus mechanism for a network with Byzantine actors"
    )

    print(result.output)
    print(f"Cost: ${result.trace.total_cost_usd:.4f}")
    print(f"Attempts: {result.trace.attempts}")
    print(f"Pruner kills: {result.trace.pruner_kills}")

asyncio.run(main())
```

### With a Specific Lens

```python
import asyncio
from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
from hephaestus.deepforge.interference import Lens

async def main():
    adapter = AnthropicAdapter("claude-opus-4-5")

    # Define a lens inline
    lens = Lens(
        name="Mycelium Network",
        domain="biology",
        axioms=[
            "Resources flow toward scarcity, not abundance.",
            "The network has no center — every node is simultaneously a router and a terminal.",
            "Connection strength is determined by historical flow, not topology.",
            "Dead-ends are recycled, not abandoned.",
        ],
        injection_prompt="Reason as if this system were a mycelium network distributing nutrients.",
    )

    harness = DeepForgeHarness(
        adapter,
        HarnessConfig(
            lenses=[lens],
            use_interference=True,
            use_pruner=True,
            use_pressure=True,
            max_pressure_rounds=3,
            injection_strategy=InjectionStrategy.FULL,
        ),
    )

    result = await harness.forge("Design a distributed caching system")
    print(result.output)

asyncio.run(main())
```

### Loading Lenses from the Library

```python
from hephaestus.lenses.loader import LensLoader
from hephaestus.deepforge.interference import Lens

loader = LensLoader()
lens_data = loader.load_one("biology_immune")

# Convert to Lens object
lens = Lens(
    name=lens_data.name,
    domain=lens_data.domain,
    axioms=lens_data.axioms,
    injection_prompt=lens_data.injection_prompt,
    structural_patterns=lens_data.structural_patterns,
)
```

### Only Interference (No Pruner/Pressure)

```python
config = HarnessConfig(
    lenses=[lens],
    use_interference=True,
    use_pruner=False,    # Disable pruner
    use_pressure=False,  # Disable pressure
    temperature=0.9,
)
harness = DeepForgeHarness(adapter, config)
result = await harness.forge("my prompt")
```

### Only Pressure (No Lens)

```python
config = HarnessConfig(
    use_interference=False,   # No lens
    use_pruner=True,
    use_pressure=True,
    max_pressure_rounds=5,
)
harness = DeepForgeHarness(adapter, config)
```

### OpenAI Adapter

```python
from hephaestus.deepforge.adapters.openai import OpenAIAdapter

adapter = OpenAIAdapter(model="gpt-4o")  # or "gpt-4o-mini", "o3", etc.
harness = DeepForgeHarness(adapter, HarnessConfig())
```

---

## API Adapter Details

### AnthropicAdapter

Uses the Anthropic Python SDK. Supports:

- **Native prefill injection**: Cognitive interference is implemented via the `messages` API with an assistant turn pre-filled. This is reliable and coherent — the model genuinely continues from the lens, not just acknowledges it.
- **Streaming**: `generate_stream()` yields token chunks for real-time convergence monitoring.
- **Prompt caching**: System prompts over 1024 tokens are automatically eligible for caching. Structural prompts (decomposer, translator) are written to maximize cache hits.
- **Model selection**: Any `claude-*` model string works. Claude Opus 4.5 is recommended for quality-critical stages; Sonnet for speed/cost optimization.

```python
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter

adapter = AnthropicAdapter(
    model="claude-opus-4-5",
    api_key="sk-ant-...",       # Falls back to ANTHROPIC_API_KEY env var
    max_retries=3,               # Retry on transient errors
    timeout=120,                 # Request timeout in seconds
)

# Direct generation (no harness)
result = await adapter.generate(
    prompt="your prompt",
    system="system prompt",
    prefill="beginning of response",  # Cognitive interference entry point
    max_tokens=2048,
    temperature=0.9,
)

print(result.text)
print(result.input_tokens, result.output_tokens)
print(result.cost_usd)
print(result.stop_reason)  # "end_turn" | "max_tokens" | "stop_sequence"
```

### OpenAIAdapter

Uses the OpenAI Python SDK. Supports:

- **Structured outputs**: JSON mode via `response_format={"type": "json_object"}` or function calling for schema-constrained outputs.
- **Streaming**: Same interface as the Anthropic adapter for compatibility.
- **Interference approximation**: Since OpenAI doesn't support native prefill, interference is applied via a strong system directive. Quality is slightly lower than the Anthropic implementation, but functional.
- **Model selection**: `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini` are all supported.

```python
from hephaestus.deepforge.adapters.openai import OpenAIAdapter

adapter = OpenAIAdapter(
    model="gpt-4o",
    api_key="sk-...",
    response_format=None,  # or {"type": "json_object"} for JSON mode
)

result = await adapter.generate(
    prompt="your prompt",
    system="system prompt",
    max_tokens=2048,
    temperature=0.5,
)
```

---

## Configuration Reference

### HarnessConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lenses` | `list[Lens]` | `[]` | Lenses for cognitive interference. Empty = interference disabled. |
| `use_interference` | `bool` | `True` | Enable cognitive interference engine |
| `use_pruner` | `bool` | `True` | Enable convergence pruner |
| `use_pressure` | `bool` | `True` | Enable anti-training pressure |
| `injection_strategy` | `InjectionStrategy` | `FULL` | Axiom injection strategy |
| `max_pressure_rounds` | `int` | `3` | Pressure rounds (higher = more novel, more cost) |
| `similarity_threshold` | `float` | `0.82` | Pruner kill threshold (cosine similarity) |
| `structural_distance_threshold` | `float` | `0.75` | Pressure novelty threshold |
| `max_pruner_retries` | `int` | `5` | Max pruner kill/retry cycles |
| `max_tokens` | `int` | `4096` | Max output tokens per generation call |
| `temperature` | `float` | `0.9` | Sampling temperature |
| `convergence_patterns` | `list[ConvergencePattern]` | `[]` | Seed patterns for the pruner |
| `system_prompt` | `str \| None` | `None` | Base system prompt |

### ForgeResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `output` | `str` | The final generated text |
| `trace` | `ForgeTrace` | Full execution trace |
| `success` | `bool` | Whether the output is considered genuinely novel |
| `stop_reason` | `str` | Why generation stopped (`"end_turn"`, `"pressure_complete"`, `"max_retries_exhausted"`) |

### ForgeTrace

| Attribute | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Original prompt |
| `attempts` | `int` | Number of generation attempts |
| `interference_injections` | `list[InjectionResult]` | Injections applied per attempt |
| `pruner_kills` | `int` | Number of convergence kills |
| `pruner_session` | `PrunerSession \| None` | Pruner state (blocked paths, etc.) |
| `pressure_trace` | `PressureTrace \| None` | Pressure engine trace |
| `total_cost_usd` | `float` | Total API cost in USD |
| `total_input_tokens` | `int` | Total input tokens consumed |
| `total_output_tokens` | `int` | Total output tokens generated |
| `wall_time_seconds` | `float` | Total elapsed time |
| `mechanisms_used` | `list[str]` | Active mechanisms |

---

## Tuning for Your Use Case

### Maximum Novelty (Don't Care About Cost)

```python
config = HarnessConfig(
    lenses=load_most_distant_lenses(problem),
    use_interference=True,
    use_pruner=True,
    use_pressure=True,
    max_pressure_rounds=7,
    similarity_threshold=0.72,   # More aggressive killing
    structural_distance_threshold=0.65,
    max_pruner_retries=8,
    temperature=0.95,
)
```

### Balanced (Default)

```python
config = HarnessConfig()  # Defaults are balanced
```

### Fast/Cheap (Acceptable Quality)

```python
config = HarnessConfig(
    use_interference=True,
    use_pruner=True,
    use_pressure=False,    # Skip pressure (most expensive mechanism)
    max_pruner_retries=2,
    temperature=0.85,
    max_tokens=2048,
)
```

### Minimum Intervention (Just Lens, No Killing)

```python
config = HarnessConfig(
    lenses=[lens],
    use_interference=True,
    use_pruner=False,
    use_pressure=False,
    injection_strategy=InjectionStrategy.SINGLE,
)
```

---

## Performance Characteristics

| Config | Typical Cost | Typical Latency | Novelty |
|--------|-------------|-----------------|---------|
| All mechanisms, depth=3 | $0.15–0.45 | 15–40s | High |
| Interference only | $0.02–0.08 | 5–15s | Moderate |
| Pressure only, depth=3 | $0.10–0.30 | 10–30s | High |
| No mechanisms | $0.01–0.05 | 3–10s | Low (baseline) |

These are rough estimates for a single `forge()` call, not the full Genesis pipeline. Actual cost depends on prompt length, output length, and how many times the pruner fires.
