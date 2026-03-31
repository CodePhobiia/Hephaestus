# ⚒️ Hephaestus

### The god of the forge didn't ask permission. He just built things the other gods couldn't imagine.

**Hephaestus is an invention engine.** Give it a problem. It gives you a solution that has never existed — not by being random, but by finding solved patterns in distant fields and translating them into your domain.

Every output comes with a novelty proof.

```bash
pip install hephaestus-ai
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
heph "I need a load balancer that handles unpredictable traffic spikes"
```

> **Cost:** ~$1.25 per invention. **Time:** ~45 seconds. **Novelty:** Provable.

---

<p align="center">
  <a href="https://pypi.org/project/hephaestus-ai/"><img src="https://img.shields.io/pypi/v/hephaestus-ai?color=orange&label=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/hephaestus-ai/"><img src="https://img.shields.io/pypi/pyversions/hephaestus-ai" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="docs/architecture.md"><img src="https://img.shields.io/badge/docs-architecture-green" alt="Docs"></a>
</p>

---

## What is this?

LLMs are consensus machines. They produce the most statistically likely output — the average answer. Ask any frontier model a creative question and you get a well-structured, articulate, *predictable* response. The same shaped answer a million other users received. Temperature adds noise, not novelty. Prompting is begging. The model's probability distribution doesn't change because you asked nicely.

Hephaestus is different at the architectural level. It runs a 5-stage invention pipeline that: (1) strips your problem down to its abstract mathematical shape, (2) searches 51 knowledge domains for solved problems with that exact shape, (3) scores candidates by structural fidelity *and* domain distance (superlinear reward for distant domains), (4) builds the concrete structural bridge using the **DeepForge harness** — which actively prevents the model from defaulting to predictable solutions, and (5) adversarially verifies the invention against prior art and structural validity.

The output isn't a metaphor. It's a working architecture — element-by-element mapping, implementation pseudocode, mathematical proof of structural isomorphism, and honest documentation of where the analogy breaks. If you've ever read about TRIZ (the Soviet theory of inventive problem solving developed in 1946), this is automated TRIZ with unlimited domains and LLM-powered translation. If you haven't heard of TRIZ, you're about to understand why Hephaestus is different from everything else in the AI tooling space.

---

## Quick Start

```bash
# Install
pip install hephaestus-ai

# Set API keys (both required for default 'both' mode)
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# Run your first invention
heph "I need a reputation system for an anonymous marketplace that can't be gamed"
```

That's it. In ~45 seconds you'll have a novel architecture, a structural mapping, implementation guidance, and a novelty proof.

**Single model (cheaper):**
```bash
heph --model opus "my problem here"    # Claude only (~$0.90)
heph --model gpt5 "my problem here"   # OpenAI only (~$0.75)
```

**Python SDK:**
```python
import asyncio
from hephaestus import Hephaestus

async def main():
    async with Hephaestus.from_env() as heph:
        result = await heph.invent("I need a fraud detection system that adapts in real time")
        print(result.top_invention.invention_name)
        print(f"Source: {result.top_invention.source_domain}")
        print(f"Novelty: {result.top_invention.novelty_score:.2f}")
        print(f"Cost: ${result.total_cost_usd:.2f}")

asyncio.run(main())
```

---

## How It Works

The invention pipeline has 5 stages:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HEPHAESTUS                                   │
│                                                                       │
│  Your Problem                                                         │
│      │                                                                │
│      ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Stage 1: DECOMPOSE  (Claude Opus)                              │ │
│  │  Strip domain language → extract abstract mathematical shape    │ │
│  │  "load balancer with traffic spikes"                            │ │
│  │       → "dynamic resource allocation under Poisson arrivals     │ │
│  │          with no central coordinator"                           │ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Stage 2: SEARCH  (GPT-5.4)                                     │ │
│  │  Query 51 domain lenses for solved problems with matching shape  │ │
│  │  Returns 8–10 candidates from distant fields                    │ │
│  │  e.g., ant colony foraging, mycelium networks, bird murmurations│ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Stage 3: SCORE                                                  │ │
│  │  score = fidelity × distance^1.5                                │ │
│  │  Adjacent domains (gossip protocols) get penalized              │ │
│  │  Distant domains (mycology, music theory) get rewarded          │ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Stage 4: TRANSLATE  (Claude Opus via DeepForge)                │ │
│  │  Build the structural bridge — element-by-element mapping       │ │
│  │  Cognitive interference ACTIVE → prevents conventional solutions│ │
│  │  Outputs: architecture, pseudocode, mathematical proof          │ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Stage 5: VERIFY  (cross-model adversarial)                     │ │
│  │  GPT attacks the mapping. Claude defends.                       │ │
│  │  Prior art check. Feasibility assessment. Novelty proof.        │ │
│  └────────────────────────────┬────────────────────────────────────┘ │
│                               │                                       │
│                               ▼                                       │
│  InventionReport: name, domain, mapping, architecture, proof, cost   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The DeepForge Harness

DeepForge is the engine underneath the pipeline. It makes frontier models structurally incapable of producing predictable output through three mechanisms:

### 1. Cognitive Interference
During translation, DeepForge injects foreign-domain axioms into the model's active reasoning — not as a prompt, but as assistant prefill. The model is forced to continue its chain-of-thought from inside an alien conceptual frame.

```
Normal model:              Interference active:
"The best approach is      "As if through the lens of an immune system:
 a consistent hashing       every request is an antigen. Trust is
 algorithm with virtual     antigen presentation. The server's
 nodes..."                  willingness to respond is..."
```

### 2. Convergence Pruning
The harness monitors the output stream in real-time. When the model starts heading toward a known solution (detected via embedding similarity against a banality database), the generation is killed and retried with that path explicitly blocked. Each retry seals another exit. After 3–4 rounds, the model is past its top convergence points.

### 3. Anti-Training Pressure
The adversarial mirror: ask the model for its default answer, feed it back as a structural prohibition. The model's own consensus response becomes the wall it must climb over. Round N blocks the N-th most obvious answer, forcing the model deeper into unexplored territory.

---

## Cognitive Lenses

The lens library is a collection of 51 curated domain axiom sets — the conceptual primitives of each field, structured to be injected as cognitive frames during generation.

Each lens contains:
- **Axioms**: Core truths of the domain (how the field understands the world)
- **Structural patterns**: Abstract mechanisms that map to common problem shapes
- **Injection prompt**: The framing text that activates this domain's perspective

**Example: Immune System lens (excerpt)**
```yaml
name: Immune System
domain: biology
axioms:
  - "Identity is not asserted — it is proven through molecular handshake."
  - "Memory is the most powerful adaptation: a system that survived an
     attack once responds 1000× faster the second time."
  - "Clonal selection amplifies success: strategies that work get
     duplicated; strategies that fail get pruned."

structural_patterns:
  - name: antigen_presentation
    abstract: "An entity publicly broadcasts proof of its interactions
               that any observer can independently verify"
    maps_to: [trust, reputation, authentication, audit_trail]
```

**Current lens library (51 domains):**

| Biology | Physics | Math | Strategy |
|---------|---------|------|----------|
| Immune System | Fluid Dynamics | Chaos Theory | Military Strategy |
| Swarm Intelligence | Thermodynamics | Topology | Game Theory |
| Evolution | Quantum Mechanics | Graph Theory | Military Logistics |
| Ecology | Optics | | Military Intelligence |
| Mycology | | | |

| Social | Engineering | Arts | Earth Sciences |
|--------|-------------|------|----------------|
| Sociology Networks | Cryptography | Music Theory | Geology/Tectonics |
| Urban Planning | Distributed Systems | Film Cinematography | Meteorology |
| Economics/Markets | Network Theory | | Oceanography |
| Behavioral Economics | Materials Science | | Astronomy/Orbital |
| Game Theory (Econ) | | | |

> Want to add a lens? See [docs/lens_authoring.md](docs/lens_authoring.md)

---

## Example Output

Here's a real invention from Hephaestus. Problem: *"I need a load balancer that handles unpredictable traffic spikes"*

---

```
═══════════════════════════════════════════════════════════════
⚒️  HEPHAESTUS — Invention Report
═══════════════════════════════════════════════════════════════

PROBLEM:
  I need a load balancer that handles unpredictable traffic spikes

STRUCTURAL FORM:
  Dynamic resource allocation under stochastic arrival rates with
  no central coordinator and no predictable demand distribution.
  Mathematical shape: decentralized optimization over a routing
  graph with Poisson arrivals and time-varying capacity constraints.

───────────────────────────────────────────────────────────────
INVENTION: Pheromone-Gradient Load Balancer
SOURCE DOMAIN: Biology — Ant Colony Foraging (Swarm Intelligence)
DOMAIN DISTANCE: 0.91 (swarm biology → distributed systems)
STRUCTURAL FIDELITY: 0.88
NOVELTY SCORE: 0.93
───────────────────────────────────────────────────────────────

MECHANISM (native domain):
  Ant colonies solve the Traveling Salesman Problem in real time
  without a central planner. Each ant deposits pheromone on the
  path it travels. Shorter paths accumulate pheromone faster
  (more ants traverse them per unit time). Longer paths evaporate.
  The colony converges on optimal routes through this emergent
  gradient — with no ant ever seeing the global picture.

TRANSLATION:

  Ant                  → Individual request
  Pheromone            → Latency-weighted routing score
  Pheromone deposit    → Response time recorded at request completion
  Pheromone evaporation→ Exponential decay of routing scores (TTL)
  Path length          → Inverse of current server response time
  Colony               → The load balancer routing table
  Nest                 → Entry point (client-facing endpoint)
  Food source          → Available server capacity

ARCHITECTURE:

  Each server maintains a "pheromone level" P(s,t): a float in
  [0,1] representing how "attractive" it is at time t. Initial
  value: 0.5 for all servers.

  On request arrival:
    1. Route with probability proportional to P(s,t) for each server s
       (probabilistic, not deterministic — like ants choosing paths)
    2. Record actual response time T(s,request)
    3. Update: P(s,t+1) = (1-ρ)·P(s,t) + ρ·(1/T(s,request))
       where ρ is the evaporation rate (0.1–0.3)

  Key insight: during a spike, overloaded servers respond slowly.
  Their pheromone decays. Traffic automatically redistributes to
  faster servers — without any server reporting its load, without
  a health check endpoint, and with sub-millisecond routing decisions.

  For new server introduction: seed with P(s,0) = mean(P) + ε.
  New servers get a small initial bonus, pulled toward mean quickly.

  Pseudocode:
    class PheromoneRouter:
        def __init__(self, servers, rho=0.15, decay_interval=1.0):
            self.pheromones = {s: 0.5 for s in servers}
            self.rho = rho

        def route(self, request) -> Server:
            weights = {s: p for s, p in self.pheromones.items()}
            return weighted_random_choice(weights)

        def record_response(self, server, latency_ms):
            score = 1.0 / max(latency_ms, 1)
            p = self.pheromones[server]
            self.pheromones[server] = (1 - self.rho) * p + self.rho * score

        def decay(self):  # Called periodically
            for s in self.pheromones:
                self.pheromones[s] *= 0.99  # Global evaporation

WHERE THE ANALOGY BREAKS:
  • Ants have path memory; HTTP requests don't. Solution: track
    in-flight requests per server explicitly.
  • Ant pheromone is per-path; our pheromone is per-server.
    This loses path diversity. Mitigate with exploration bonus (ε-greedy).
  • Colonies handle node failure by path abandonment; you need an
    explicit health check fallback for dead servers.
  • The original algorithm assumes stationary demand; you'll need
    faster decay rates during detected spikes.

PRIOR ART CHECK:
  • "Ant Colony Optimization" (Dorigo, 1992) — foundational ACO work.
    Does NOT cover HTTP routing specifically.
  • "AntNet" (Di Caro & Dorigo, 1998) — network routing, not load
    balancing. Different topology and constraints.
  • Several patents on "adaptive load balancing" — none use
    pheromone-gradient specifically with latency-as-pheromone.
  Status: NO PRIOR ART for this specific cross-domain application.

NOVELTY PROOF:
  The structural isomorphism holds: both systems solve decentralized
  optimization over a routing graph with emergent, gradient-based
  path selection driven solely by local feedback signals. The key
  transfer is treating LATENCY as the inverse of PHEROMONE STRENGTH —
  a mapping that does not appear in prior load balancing literature,
  ACO literature, or their intersection. The use of pheromone
  evaporation as an automatic traffic spike dampener is novel.

───────────────────────────────────────────────────────────────
ALTERNATIVE INVENTIONS:
  2. Mycelium Network Router — fungal nutrient transport → request routing
     (score: 0.86, domain dist: 0.89)
  3. Flocking Murmuration Balancer — starling swarm dynamics → adaptive
     server clustering (score: 0.81, domain dist: 0.87)
───────────────────────────────────────────────────────────────

Cost: $1.18  |  Models: Claude Opus 4.5 + GPT-4o  |  Depth: 3  |  45s
═══════════════════════════════════════════════════════════════
```

> See [examples/load_balancer.md](examples/load_balancer.md) for the full detailed version.

---

## CLI Reference

```
Usage: heph [OPTIONS] PROBLEM

  ⚒️  HEPHAESTUS — The Invention Engine.

Options:
  PROBLEM               Your problem description (natural language)

  -d, --depth INT       Anti-training pressure depth (1-10, default: 3)
                        Higher = more novel, more expensive.

  -m, --model TEXT      Model strategy: opus | gpt5 | both (default: both)
                        opus: Claude Opus only (~$0.90/invention)
                        gpt5: OpenAI only (~$0.75/invention)
                        both: Cross-model adversarial (~$1.25/invention)

  -f, --format TEXT     Output format: markdown | json | text (default: markdown)

  --domain TEXT         Domain hint: 'distributed-systems', 'biology', etc.

  --trace               Show full reasoning trace (interference injections,
                        pressure rounds, pruner kills)

  --raw                 Skip Genesis pipeline — run DeepForge directly on prompt

  -c, --candidates INT  Cross-domain search candidates (1-20, default: 8)

  -o, --output PATH     Save report to file (format inferred from extension)

  --cost                Show detailed cost breakdown table

  -q, --quiet           Minimal output — just the invention name and stats

  -v, --version         Show version and exit

  -h, --help            Show this message and exit
```

**Examples:**

```bash
# Basic invention
heph "I need a fraud detection system that doesn't rely on historical patterns"

# More depth, trace enabled
heph --depth 5 --trace "a caching system that predicts future access patterns"

# Opus only, JSON output saved to file
heph --model opus --format json --output invention.json "my problem"

# Raw DeepForge — skip the pipeline, just force novel generation
heph --raw "Design a consensus mechanism for a network with Byzantine actors"

# Quiet mode (good for scripts)
heph --quiet --format json "routing problem" | jq .top_invention.name
```

---

## Python SDK

### 1. Basic Invention

```python
import asyncio
from hephaestus import Hephaestus

async def main():
    async with Hephaestus.from_env() as heph:
        result = await heph.invent("I need a caching strategy for unpredictable access patterns")

        inv = result.top_invention
        print(f"Invention: {inv.invention_name}")
        print(f"From: {inv.source_domain}")
        print(f"Novelty: {inv.novelty_score:.2f}")
        print(f"Cost: ${result.total_cost_usd:.2f}")

asyncio.run(main())
```

### 2. Streaming Pipeline Progress

```python
import asyncio
from hephaestus import Hephaestus

async def main():
    async with Hephaestus.from_env() as heph:
        async for update in heph.invent_stream("trust system for ephemeral actors"):
            print(f"[{update.stage.name:12}] {update.message}")
            if update.stage.name == "COMPLETE":
                report = update.data
                print(f"\nTop invention: {report.top_invention.invention_name}")

asyncio.run(main())
```

### 3. Raw DeepForge (No Pipeline)

```python
import asyncio
from hephaestus import Hephaestus

async def main():
    async with Hephaestus.from_env(depth=5) as heph:
        result = await heph.deepforge(
            "Design a consensus mechanism for a network with unreliable nodes",
            depth=5,
        )
        print(result.output)
        print(f"Cost: ${result.trace.total_cost_usd:.4f}")
        print(f"Pruner kills: {result.trace.pruner_kills}")

asyncio.run(main())
```

### 4. Lens Introspection

```python
from hephaestus import Hephaestus

heph = Hephaestus.from_env()

# List all 51 lenses
lenses = heph.list_lenses()
for lens in lenses[:5]:
    print(f"{lens['lens_id']:30} {lens['domain']:15} {lens['axiom_count']} axioms")

# Load a specific lens
immune = heph.get_lens("biology_immune")
print(immune.name)
for axiom in immune.axioms:
    print(f"  • {axiom}")
```

### 5. Cost Estimation Before Running

```python
from hephaestus import Hephaestus

heph = Hephaestus.from_env(depth=5, candidates=12)

estimate = heph.estimate_cost("I need a fraud detection system")
print(f"Estimated: ${estimate['mid']:.2f}")
print(f"Range: ${estimate['low']:.2f} — ${estimate['high']:.2f}")
print(f"Breakdown: {estimate['breakdown']}")
```

### Full SDK Reference → [docs/api_reference.md](docs/api_reference.md)

---

## Web UI

> **Coming in Phase 2.**

```bash
# Run the web interface locally
pip install "hephaestus-ai[web]"
heph-web
# Open http://localhost:8000
```

The web UI provides:
- Real-time streaming of the invention process (watch each stage)
- Visual graph of the structural domain mapping
- Gallery of past inventions (opt-in sharing)
- Cost counter

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (opus/both) | Anthropic API key for Claude Opus |
| `OPENAI_API_KEY` | Yes (gpt5/both) | OpenAI API key for GPT models |
| `HEPHAESTUS_DEPTH` | No | Default pressure depth (overrides CLI default of 3) |
| `HEPHAESTUS_MODEL` | No | Default model (opus/gpt5/both) |
| `HEPHAESTUS_LENS_DIR` | No | Custom lens library directory |
| `HEPHAESTUS_LOG_LEVEL` | No | Log level (DEBUG/INFO/WARNING) |

### Model Selection

| Mode | Decompose | Search | Translate | Verify | Cost |
|------|-----------|--------|-----------|--------|------|
| `both` (default) | Claude Opus | GPT-4o | Claude Opus | Cross-model | ~$1.25 |
| `opus` | Claude Opus | Claude Opus | Claude Opus | Claude Opus | ~$0.90 |
| `gpt5` | GPT-4o | GPT-4o | GPT-4o | GPT-4o | ~$0.75 |

Cross-model (`both`) gives the best results — different model families have different failure modes, so the adversarial verification is more meaningful.

### SDK Configuration

```python
from hephaestus import Hephaestus

# Full configuration
heph = Hephaestus(
    anthropic_key="sk-ant-...",
    openai_key="sk-...",
    model="both",          # opus | gpt5 | both
    depth=3,               # 1-10, default 3
    candidates=8,          # search candidates, default 8
    num_translations=3,    # candidates to translate, default 3
    run_prior_art=True,    # prior art check in stage 5
)
```

---

## How Is This Different From Just Prompting?

The honest answer: prompting has a ceiling. Here's the comparison:

| | Raw Prompting | Hephaestus |
|---|---|---|
| **"Be creative!"** | Asks nicely. Model ignores. | Changes the probability distribution. |
| **Source domains** | Whatever the model recalls from training | 51 curated lenses, structurally matched |
| **Novelty guarantee** | None | Structural novelty proof + prior art check |
| **Predictability** | Model takes the path of least resistance | Convergence pruner kills predictable paths |
| **Translation quality** | Metaphor-level ("it's like...") | Element-by-element structural mapping |
| **Cost** | $0.01 | ~$1.25 |
| **Output type** | Text | Working architecture + pseudocode |

The gap isn't prompt engineering. It's architecture. The model's probability distribution over "creative" outputs is heavily concentrated on a few well-worn solutions. Increasing temperature spreads probability mass over incoherent outputs — not novel ones. DeepForge shifts where the probability mass lives by actively blocking the high-probability paths.

---

## Cost

**Per invention: approximately $0.85–$1.50 depending on depth and model.**

| Stage | Model | Est. Cost |
|-------|-------|-----------|
| Decompose | Claude Opus | $0.15 |
| Search (8 candidates) | GPT-4o | $0.12 |
| Score | GPT-4o-mini | $0.05 |
| Translate (top 3, deepforge) | Claude Opus | $0.45 |
| Convergence kills (~3 retries) | Mixed | $0.15 |
| Verify + prior art | Both | $0.15 |
| **Total** | | **~$1.07** |

With Anthropic prompt caching (structural prompts are reused): **~$0.75** after the first run.

**Use `--cost` to see the actual breakdown after every run:**
```bash
heph --cost "your problem"
```

**Estimate before running:**
```bash
python -c "from hephaestus import Hephaestus; h = Hephaestus.from_env(); print(h.estimate_cost('your problem'))"
```

---

## Contributing

### Adding a Lens

The fastest way to contribute. Each lens is a single YAML file in `src/hephaestus/lenses/library/`.

```bash
cp src/hephaestus/lenses/library/biology_immune.yaml src/hephaestus/lenses/library/my_domain.yaml
# Edit the file
python -m pytest tests/test_lenses.py -k my_domain
```

See [docs/lens_authoring.md](docs/lens_authoring.md) for the full schema and best practices.

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/                          # Full test suite
pytest tests/test_deepforge.py         # DeepForge harness tests
pytest tests/test_genesis.py           # Pipeline tests (mocked LLM calls)
pytest tests/test_lenses.py            # Lens validation
pytest tests/benchmarks/               # Novelty benchmarks (requires API keys)
```

### Submitting a PR

1. Fork and create a branch: `git checkout -b feat/your-feature`
2. Make changes, add tests
3. Run `pytest` and `ruff check src/`
4. Open a PR — describe what problem your change solves

**High-value contributions:**
- New cognitive lenses (especially rare/unexpected domains)
- Convergence pattern seeds (examples of "boring" LLM outputs to block)
- Benchmark improvements
- Open-weight model adapters (Llama, Mistral)

---

## Architecture Deep Dive → [docs/architecture.md](docs/architecture.md)

## DeepForge Documentation → [docs/deepforge.md](docs/deepforge.md)

## Lens Authoring Guide → [docs/lens_authoring.md](docs/lens_authoring.md)

## Full API Reference → [docs/api_reference.md](docs/api_reference.md)

## Benchmarks → [docs/benchmarks.md](docs/benchmarks.md)

---

## Examples

- [Load Balancer → Ant Colony Foraging](examples/load_balancer.md)
- [Reputation System → Immune System](examples/reputation_system.md)
- [Traffic Optimization → Fluid Dynamics](examples/traffic_optimization.md)
- [Recommendation Engine → Mycorrhizal Networks](examples/recommendation_engine.md)
- [Fraud Detection → Antigen Presentation](examples/fraud_detection.md)

---

## License

MIT — see [LICENSE](LICENSE).

Built by [Theyab](https://github.com/theyab) and [Butters](https://github.com/theyab/hephaestus). 2026.

---

*The name comes from Hephaestus, Greek god of the forge — the craftsman who built things the Olympians used but couldn't make themselves. He worked alone, in fire, making the impossible real.*
