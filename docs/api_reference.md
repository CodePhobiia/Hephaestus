# API Reference

Complete reference for the Hephaestus Python SDK, Genesis pipeline, DeepForge harness, and CLI.

---

## SDK: `Hephaestus` Class

The main entry point for the Python API.

```python
from hephaestus import Hephaestus
```

### Constructor

```python
Hephaestus(
    anthropic_key: str | None = None,
    openai_key: str | None = None,
    *,
    model: str = "both",
    depth: int = 3,
    candidates: int = 8,
    domain: str | None = None,
    num_translations: int = 3,
    run_prior_art: bool = True,
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `anthropic_key` | `str \| None` | `None` | Anthropic API key. Falls back to `ANTHROPIC_API_KEY` env var. |
| `openai_key` | `str \| None` | `None` | OpenAI API key. Falls back to `OPENAI_API_KEY` env var. |
| `model` | `str` | `"both"` | Model strategy: `"opus"`, `"gpt5"`, or `"both"` |
| `depth` | `int` | `3` | Anti-training pressure depth (1–10). Higher = more novel, more cost. |
| `candidates` | `int` | `8` | Number of cross-domain search candidates |
| `domain` | `str \| None` | `None` | Optional domain hint for the pipeline |
| `num_translations` | `int` | `3` | Top-N candidates to translate in Stage 4 |
| `run_prior_art` | `bool` | `True` | Run prior art check in Stage 5 |

**Raises:** `ConfigurationError` if required API keys are missing for the selected model.

### Class Methods

#### `Hephaestus.from_env()`

```python
@classmethod
def from_env(
    cls,
    *,
    model: str = "both",
    depth: int = 3,
    candidates: int = 8,
) -> Hephaestus
```

Create a client using `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` environment variables.

```python
async with Hephaestus.from_env() as heph:
    result = await heph.invent("my problem")
```

### Instance Methods

#### `await heph.invent(problem)`

```python
async def invent(self, problem: str) -> InventionReport
```

Run the full 5-stage invention pipeline. Returns an `InventionReport`.

```python
result = await heph.invent("I need a caching strategy for unpredictable access patterns")
print(result.top_invention.invention_name)
```

#### `heph.invent_stream(problem)`

```python
async def invent_stream(self, problem: str) -> AsyncIterator[PipelineUpdate]
```

Run the pipeline with streaming progress updates.

```python
async for update in heph.invent_stream("my problem"):
    print(f"[{update.stage.name}] {update.message}")
    if update.stage.name == "COMPLETE":
        report = update.data
```

#### `await heph.deepforge(prompt)`

```python
async def deepforge(
    self,
    prompt: str,
    *,
    depth: int | None = None,
    model: str | None = None,
    system: str | None = None,
) -> ForgeResult
```

Run DeepForge directly — no Genesis pipeline. Returns a `ForgeResult`.

```python
result = await heph.deepforge("Design a trust mechanism for ephemeral actors", depth=5)
print(result.output)
print(f"Cost: ${result.trace.total_cost_usd:.4f}")
```

#### `heph.list_lenses()`

```python
def list_lenses(self) -> list[dict[str, Any]]
```

Returns a list of lens metadata dicts, each with keys: `lens_id`, `name`, `domain`, `subdomain`, `axiom_count`, `pattern_count`, `maps_to`, `tags`.

#### `heph.get_lens(lens_id)`

```python
def get_lens(self, lens_id: str) -> Lens
```

Load a specific lens by its ID. Raises `HephaestusError` if not found.

```python
lens = heph.get_lens("biology_immune")
print(lens.name)
for axiom in lens.axioms:
    print(f"  • {axiom}")
```

#### `heph.estimate_cost(problem)`

```python
def estimate_cost(self, problem: str) -> dict[str, float]
```

Estimate API cost before running. Returns `{low, mid, high, breakdown, depth, candidates, model, note}`.

```python
estimate = heph.estimate_cost("complex routing problem")
print(f"Estimated: ${estimate['mid']:.2f}")
print(f"Range: ${estimate['low']:.2f} — ${estimate['high']:.2f}")
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `model` | `str` | Configured model strategy |
| `depth` | `int` | Configured pressure depth |
| `candidates` | `int` | Configured search candidate count |

### Context Manager

`Hephaestus` supports async context manager protocol:

```python
async with Hephaestus.from_env() as heph:
    result = await heph.invent("my problem")
# Resources released automatically
```

---

## Data Classes

### `InventionReport`

```python
from hephaestus.core.genesis import InventionReport
```

The complete output of a Genesis pipeline run.

| Attribute | Type | Description |
|-----------|------|-------------|
| `problem` | `str` | Original problem as submitted |
| `structure` | `ProblemStructure` | Stage 1 output: abstract structural form |
| `all_candidates` | `list[SearchCandidate]` | Stage 2 output: all search candidates |
| `scored_candidates` | `list[ScoredCandidate]` | Stage 3 output: scored candidates |
| `translations` | `list[Translation]` | Stage 4 output: full translations |
| `verified_inventions` | `list[VerifiedInvention]` | Stage 5 output: verified inventions |
| `cost_breakdown` | `CostBreakdown` | Per-stage USD costs |
| `total_cost_usd` | `float` | *(property)* Total cost |
| `total_duration_seconds` | `float` | Wall-clock pipeline time |
| `model_config` | `dict[str, str]` | Models used per stage |
| `top_invention` | `VerifiedInvention \| None` | *(property)* Highest-ranked invention |
| `alternative_inventions` | `list[VerifiedInvention]` | *(property)* All except top |

**Methods:**
- `to_dict() -> dict` — serialize to dictionary
- `summary() -> str` — one-line human-readable summary

---

### `ProblemStructure`

Stage 1 output. The abstract structural form of the problem.

| Attribute | Type | Description |
|-----------|------|-------------|
| `original_problem` | `str` | Original user input verbatim |
| `structure` | `str` | Domain-neutral description |
| `constraints` | `list[str]` | Hard constraints the solution must satisfy |
| `mathematical_shape` | `str` | Formal characterization (graph theory, optimization, etc.) |
| `native_domain` | `str` | Detected domain (e.g., "distributed_systems") |
| `problem_maps_to` | `set[str]` | Abstract problem type tags |
| `cost_usd` | `float` | API cost for this stage |
| `duration_seconds` | `float` | Time for this stage |
| `forge_trace` | `ForgeTrace` | Full harness trace |

---

### `SearchCandidate`

Stage 2 output. One candidate cross-domain solution.

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_domain` | `str` | Domain the candidate comes from |
| `mechanism_name` | `str` | Name of the mechanism within that domain |
| `mechanism_description` | `str` | How the mechanism works in its native domain |
| `structural_mapping` | `str` | How it maps to the target problem |
| `confidence` | `float` | Search confidence score (0–1) |
| `lens_id` | `str` | Which lens produced this candidate |
| `cost_usd` | `float` | API cost for this candidate |

---

### `ScoredCandidate`

Stage 3 output. A `SearchCandidate` with fidelity and distance scores.

| Attribute | Type | Description |
|-----------|------|-------------|
| *(all SearchCandidate fields)* | | |
| `structural_fidelity` | `float` | Fidelity score (0–1) from LLM assessment |
| `domain_distance` | `float` | Cosine distance from native domain (0–1) |
| `combined_score` | `float` | `fidelity × distance^1.5` |
| `fidelity_reasoning` | `str` | LLM explanation of fidelity score |
| `strong_mappings` | `list[str]` | Well-mapping element pairs |
| `weak_mappings` | `list[str]` | Where the mapping struggles |
| `scoring_cost_usd` | `float` | API cost for this scoring |

---

### `Translation`

Stage 4 output. A full structural bridge between domains.

| Attribute | Type | Description |
|-----------|------|-------------|
| `invention_name` | `str` | Short memorable name (e.g., "Pheromone-Gradient Load Balancer") |
| `source_candidate` | `ScoredCandidate` | The input candidate |
| `mapping` | `TranslationMapping` | Element-by-element structural mapping |
| `architecture` | `str` | Working implementation description / pseudocode |
| `mathematical_proof` | `str` | Formal structural isomorphism statement |
| `limitations` | `list[str]` | Where the analogy breaks |
| `implementation_notes` | `str` | Practical engineering notes |
| `key_insight` | `str` | Single most important insight |
| `cost_usd` | `float` | API cost for this translation |
| `forge_trace` | `ForgeTrace` | Full harness trace (with interference details) |

**`TranslationMapping`:**
Contains a list of `MappingElement` objects, each with:
- `source_element` — component in the foreign domain
- `target_element` — corresponding component in the target domain
- `mechanism` — how this mapping works

---

### `VerifiedInvention`

Stage 5 output. An adversarially verified invention.

| Attribute | Type | Description |
|-----------|------|-------------|
| `invention_name` | `str` | Same as Translation.invention_name |
| `source_domain` | `str` | Source domain |
| `translation` | `Translation` | The full translation |
| `novelty_score` | `float` | Final novelty score (0–1) |
| `feasibility_rating` | `str` | "high" / "medium" / "low" |
| `adversarial_notes` | `str` | Attack findings (if any) |
| `defense_reasoning` | `str` | Validity defense |
| `prior_art_report` | `PriorArtReport \| None` | Prior art search results |
| `verdict` | `str` | "validated" / "partially_valid" / "rejected" |
| `verification_cost_usd` | `float` | API cost for verification |

---

### `ForgeResult`

Output of `DeepForgeHarness.forge()`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `output` | `str` | The final generated text |
| `trace` | `ForgeTrace` | Full execution trace |
| `success` | `bool` | Whether output is considered genuinely novel |
| `stop_reason` | `str` | `"end_turn"` / `"pressure_complete"` / `"max_retries_exhausted"` |

---

### `ForgeTrace`

Execution trace for a single `forge()` call.

| Attribute | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Original prompt |
| `attempts` | `int` | Number of generation attempts |
| `interference_injections` | `list[InjectionResult]` | Injections per attempt |
| `pruner_kills` | `int` | Number of convergence kills |
| `pruner_session` | `PrunerSession \| None` | Pruner state (blocked paths) |
| `pressure_trace` | `PressureTrace \| None` | Pressure engine trace |
| `total_cost_usd` | `float` | Total API cost |
| `total_input_tokens` | `int` | Total input tokens |
| `total_output_tokens` | `int` | Total output tokens |
| `wall_time_seconds` | `float` | Elapsed time |
| `mechanisms_used` | `list[str]` | Active mechanisms |

---

### `CostBreakdown`

Per-stage cost breakdown.

| Attribute | Type | Description |
|-----------|------|-------------|
| `decomposition_cost` | `float` | Stage 1 cost (USD) |
| `search_cost` | `float` | Stage 2 cost (USD) |
| `scoring_cost` | `float` | Stage 3 cost (USD) |
| `translation_cost` | `float` | Stage 4 cost (USD) |
| `verification_cost` | `float` | Stage 5 cost (USD) |
| `total` | `float` | *(property)* Sum of all stages |

**Methods:** `to_dict() -> dict[str, float]`

---

## Genesis Class

Lower-level access to the invention pipeline.

```python
from hephaestus.core.genesis import Genesis, GenesisConfig
```

### `GenesisConfig`

```python
@dataclass
class GenesisConfig:
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Model selection
    decompose_model: str = "claude-opus-4-5"
    search_model: str = "gpt-4o"
    score_model: str = "gpt-4o-mini"
    translate_model: str = "claude-opus-4-5"
    attack_model: str = "gpt-4o"
    defend_model: str = "claude-opus-4-5"

    # Pipeline parameters
    num_search_lenses: int = 10
    num_candidates: int = 8
    min_search_confidence: float = 0.4
    min_domain_distance: float = 0.3
    num_translations: int = 3

    # Feature flags
    use_interference_in_search: bool = False
    use_interference_in_translate: bool = True
    run_prior_art: bool = True

    # Token budgets
    max_tokens_decompose: int = 1024
    max_tokens_search: int = 800
    max_tokens_score: int = 600
    max_tokens_translate: int = 2500
    max_tokens_verify: int = 800

    # Library override
    lens_library_dir: str | None = None
```

### `Genesis`

```python
class Genesis:
    def __init__(self, config: GenesisConfig | None = None)

    async def invent(self, problem: str) -> InventionReport
    async def invent_stream(self, problem: str) -> AsyncIterator[PipelineUpdate]

    @classmethod
    def from_env(cls) -> Genesis
```

---

## DeepForge Classes

```python
from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig, ForgeResult, ForgeTrace
from hephaestus.deepforge.interference import CognitiveInterferenceEngine, Lens, InjectionStrategy
from hephaestus.deepforge.pruner import ConvergencePruner, ConvergencePattern
from hephaestus.deepforge.pressure import AntiTrainingPressure
```

### `DeepForgeHarness`

```python
class DeepForgeHarness:
    def __init__(self, adapter: BaseAdapter, config: HarnessConfig | None = None)

    async def forge(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra_context: dict | None = None,
    ) -> ForgeResult

    # Properties
    adapter: BaseAdapter
    config: HarnessConfig
    pruner: ConvergencePruner | None
    interference_engine: CognitiveInterferenceEngine | None
    pressure_engine: AntiTrainingPressure | None
```

### `HarnessConfig`

See [docs/deepforge.md](deepforge.md#configuration-reference) for full parameter table.

### `Lens`

```python
@dataclass
class Lens:
    name: str
    domain: str
    axioms: list[str]
    injection_prompt: str = ""
    structural_patterns: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

### `InjectionStrategy`

```python
class InjectionStrategy(Enum):
    FULL = auto()        # Inject all axioms
    SINGLE = auto()      # Inject highest-priority axiom only
    PROGRESSIVE = auto() # Add one more axiom per attempt
```

---

## Model Adapters

```python
from hephaestus.deepforge.adapters.base import BaseAdapter, GenerationResult
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
from hephaestus.deepforge.adapters.openai import OpenAIAdapter
```

### `BaseAdapter` (Abstract)

```python
class BaseAdapter(ABC):
    model_name: str

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        prefill: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.9,
    ) -> GenerationResult

    async def generate_stream(
        self,
        prompt: str,
        system: str | None = None,
        prefill: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.9,
    ) -> AsyncIterator[str]
```

### `GenerationResult`

```python
@dataclass
class GenerationResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    stop_reason: str
    model: str
```

### `AnthropicAdapter`

```python
AnthropicAdapter(
    model: str = "claude-opus-4-5",
    api_key: str | None = None,
    max_retries: int = 3,
    timeout: float = 120,
)
```

### `OpenAIAdapter`

```python
OpenAIAdapter(
    model: str = "gpt-4o",
    api_key: str | None = None,
    response_format: dict | None = None,
    max_retries: int = 3,
    timeout: float = 120,
)
```

---

## Lens System

```python
from hephaestus.lenses.loader import LensLoader
from hephaestus.lenses.selector import LensSelector
```

### `LensLoader`

```python
class LensLoader:
    def __init__(self, library_dir: str | None = None)

    def load_one(self, lens_id: str) -> Lens
    # Raises FileNotFoundError if not found

    def load_many(self, lens_ids: list[str]) -> list[Lens]

    def load_all(self) -> list[Lens]

    def list_available(self, skip_errors: bool = True) -> list[dict]
    # Returns list of metadata dicts with lens_id, name, domain, etc.
```

### `LensSelector`

```python
class LensSelector:
    def __init__(self, loader: LensLoader)

    def select_for_problem(
        self,
        structure: ProblemStructure,
        n: int = 10,
        min_distance: float = 0.3,
    ) -> list[Lens]
    # Returns N lenses maximally distant from the problem's native domain

    def domain_distance(self, lens_id: str, target_domain: str) -> float
    # Cosine distance between lens embedding and target domain embedding
```

---

## Convergence System

```python
from hephaestus.convergence.database import ConvergenceDatabase
from hephaestus.convergence.detector import ConvergenceDetector
```

### `ConvergenceDatabase`

```python
class ConvergenceDatabase:
    def __init__(self, db_path: str | None = None)
    # Default: ~/.hephaestus/convergence.db

    def add_pattern(
        self,
        text: str,
        problem_class: str | None = None,
        source: str | None = None,
    ) -> None

    def find_similar(
        self,
        text: str,
        threshold: float = 0.82,
        limit: int = 10,
    ) -> list[ConvergenceMatch]

    def seed_from_file(self, path: str) -> int
    # Returns number of patterns added
```

---

## Pipeline Enums and Events

### `PipelineStage`

```python
class PipelineStage(Enum):
    STARTING    # Pipeline initializing
    DECOMPOSING # Stage 1 in progress
    DECOMPOSED  # Stage 1 complete
    SEARCHING   # Stage 2 in progress
    SEARCHED    # Stage 2 complete
    SCORING     # Stage 3 in progress
    SCORED      # Stage 3 complete
    TRANSLATING # Stage 4 in progress
    TRANSLATED  # Stage 4 complete
    VERIFYING   # Stage 5 in progress
    VERIFIED    # Stage 5 complete
    COMPLETE    # Pipeline done (data=InventionReport)
    FAILED      # Pipeline failed (data=Exception | None)
```

### `PipelineUpdate`

```python
@dataclass
class PipelineUpdate:
    stage: PipelineStage
    message: str
    data: Any = None           # Stage-specific data or InventionReport
    elapsed_seconds: float = 0.0
```

---

## Exceptions

```python
from hephaestus.sdk.client import HephaestusError, ConfigurationError
from hephaestus.core.genesis import GenesisError
from hephaestus.deepforge.exceptions import (
    HarnessError,
    ConvergenceDetected,
    GenerationKilled,
    InterferenceError,
    PressureError,
)
```

| Exception | Raised by | Meaning |
|-----------|-----------|---------|
| `HephaestusError` | SDK client | Base SDK exception |
| `ConfigurationError` | SDK client | Missing API keys or invalid config |
| `GenesisError` | Genesis pipeline | Critical stage failure (stage + reason) |
| `HarnessError` | DeepForgeHarness | Harness produced no output |
| `ConvergenceDetected` | ConvergencePruner | Generation killed (internal) |
| `GenerationKilled` | Pressure engine | Generation killed (internal) |
| `InterferenceError` | Interference engine | Injection failed |
| `PressureError` | Pressure engine | Pressure pipeline failed |

---

## CLI Reference

```
heph [OPTIONS] PROBLEM
```

### Options

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--depth` | `-d` | int 1-10 | 3 | Anti-training pressure depth |
| `--model` | `-m` | opus\|gpt5\|both | both | Model strategy |
| `--format` | `-f` | markdown\|json\|text | markdown | Output format |
| `--domain` | | str | None | Domain hint |
| `--trace` | | flag | False | Show reasoning trace |
| `--raw` | | flag | False | Run DeepForge only (skip Genesis) |
| `--candidates` | `-c` | int 1-20 | 8 | Search candidate count |
| `--output` | `-o` | path | None | Save report to file |
| `--cost` | | flag | False | Show cost breakdown |
| `--quiet` | `-q` | flag | False | Minimal output |
| `--version` | `-v` | flag | | Show version |
| `--help` | `-h` | flag | | Show help |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (API key missing, pipeline failed, etc.) |
| 130 | Keyboard interrupt |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `HEPHAESTUS_DEPTH` | Default depth (overrides CLI default) |
| `HEPHAESTUS_MODEL` | Default model |
| `HEPHAESTUS_LENS_DIR` | Custom lens library directory |
| `HEPHAESTUS_LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING` |
