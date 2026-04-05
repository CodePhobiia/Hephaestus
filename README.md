# ⚒️ Hephaestus

### The Invention Engine — cross-domain structural transfer for novel solutions

<p align="center">
  <a href="https://pypi.org/project/hephaestus-ai/"><img src="https://img.shields.io/pypi/v/hephaestus-ai?color=orange&label=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/hephaestus-ai/"><img src="https://img.shields.io/pypi/pyversions/hephaestus-ai" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
</p>

> Give it a hard problem. It finds solved patterns in distant knowledge domains, maps the structure back, and returns an invention that has never existed — with a novelty proof.

```bash
pip install hephaestus-ai
heph "I need a load balancer that handles unpredictable traffic spikes"
```

**Cost:** ~$1.25 per invention. **Time:** ~45 seconds. **Novelty:** Provable.

---

## What is Hephaestus?

Hephaestus takes hard engineering problems — the kind where the obvious approaches have already been tried — and searches for solutions in places no engineer would think to look. Instead of asking an LLM to "be creative" (which produces the same well-worn answers everyone else gets), Hephaestus decomposes your problem into its abstract mathematical shape and then scans 164 knowledge domains — from ant colony foraging to thermodynamics to music theory — for solved problems that share that exact structure.

When it finds a structural match in a distant field, it doesn't hand you a metaphor. It builds a concrete, element-by-element translation: what each component in the source domain maps to in yours, how the mechanism works, implementation pseudocode, and where the analogy breaks down. The further the source domain is from your problem, the higher the novelty — and Hephaestus rewards distance with a superlinear scoring function that penalizes adjacent-domain matches and amplifies cross-disciplinary ones.

The engine runs a 5-stage pipeline powered by multiple frontier LLMs in adversarial configuration. The key innovation is **DeepForge**, a harness that makes models structurally incapable of producing predictable output. It injects cognitive interference from foreign domains, prunes convergent paths in real time, and applies anti-training pressure that blocks the model's own consensus responses. Temperature adds noise; DeepForge adds novelty.

Every invention report includes confidence scores for domain distance, structural fidelity, and novelty; a prior art analysis; an implementation roadmap; and an honest accounting of where the structural analogy breaks. If you've heard of TRIZ (the Soviet theory of inventive problem solving), this is automated TRIZ with unlimited domains and LLM-powered translation. If you haven't — you're about to understand why this is different from everything else in the AI tooling space.

---

## Quick Start

### Install

```bash
pip install hephaestus-ai
```

### Set API keys

```bash
# Both required for default cross-model mode
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# Optional but recommended for grounded research features
export PERPLEXITY_API_KEY=pplx-...
export HEPHAESTUS_USE_PERPLEXITY_RESEARCH=true
export HEPHAESTUS_PERPLEXITY_MODEL=sonar-pro
```

### Run your first invention

```bash
heph "I need a load balancer for unpredictable traffic spikes"
```

### Interactive REPL

```bash
heph --interactive
```

Opens a session with 22+ slash commands, session persistence, refinement loops, and live cost tracking. Type `/help` to see everything available.

### Project setup

```bash
heph init
```

Creates a `.hephaestus/` directory with a `config.yaml` for project-level defaults and an `instructions.md` for domain context that Hephaestus will include in every run.

### Single-model mode (cheaper)

```bash
heph --model opus "my problem"       # Claude only
heph --model gpt5 "my problem"      # OpenAI only
heph --model claude-max "my problem" # Claude Max (no API key needed)
```

### Grounded research and benchmark corpora

```bash
heph --research "Design a scheduler that remains stable under flash crowds"
heph --no-research "Design a scheduler that remains stable under flash crowds"
heph --benchmark-corpus "distributed systems" --benchmark-count 12 -o corpora/distributed-systems.md
```

### Adaptive Bundle-Proof lens-engine surfaces

Every modern invention report can now carry an inspectable lens-engine state in addition to the top invention text. The surfaced state is meant for debugging, reproducibility, and safe resume behavior:

- bundle proofs with cohesion and higher-order support scores
- proof-carrying lineage for selected and derived lenses
- fold-state summaries for active/supporting/fallback bundles
- guards, invalidations, and recomposition events
- derived composite lenses with versioned invalidation metadata
- research/reference generations bound to Perplexity-backed evidence

These surfaces appear in session JSON (`lens_engine_state`), invention-report JSON (`lens_engine`), markdown/plain exports (`LENS ENGINE`), and the REPL status/full-report views.

---

## The Pipeline

```
 Problem
    │
    ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ DECOMPOSE│──▶│  SEARCH  │──▶│  SCORE   │──▶│TRANSLATE │──▶│  VERIFY  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
    │               │               │               │               │
 Extract         Scan 164      Rank by        Build the       Adversarial
 abstract       domain lenses   fidelity ×     structural      attack,
 structural     for matching    distance^1.5   bridge via      prior art
 form           shapes                         DeepForge       check, proof
                                                                    │
                                                                    ▼
                                                            Invention Report
```

| Stage | What it does |
|-------|-------------|
| **Decompose** | Strips domain-specific language to extract the abstract mathematical shape of your problem |
| **Search** | Queries 164 curated domain lenses for solved problems with a matching structural signature |
| **Score** | Ranks candidates by `fidelity × distance^1.5` — distant domains are superlinearly rewarded |
| **Translate** | Builds a concrete element-by-element mapping via the DeepForge harness with cognitive interference active |
| **Verify** | Cross-model adversarial verification: one model attacks the mapping, another defends. Prior art check and novelty proof |

---

## Features

### Output Modes

Seven structural shapes for invention reports, selected with `--output-mode`:

| Mode | Description |
|------|-------------|
| `MECHANISM` | Component-level architecture with element mapping (default) |
| `FRAMEWORK` | Conceptual framework with principles and decision rules |
| `NARRATIVE` | Story-driven explanation of how the invention works |
| `SYSTEM` | Full system design with modules, interfaces, and data flow |
| `PROTOCOL` | Step-by-step protocol with actors, messages, and state transitions |
| `TAXONOMY` | Classification system with categories and boundary definitions |
| `INTERFACE` | API surface design with contracts and interaction patterns |

### Divergence Intensity

Control how far from consensus the engine pushes, with `--intensity`:

| Intensity | Behavior |
|-----------|----------|
| `STANDARD` | Balanced novelty and feasibility (default) |
| `AGGRESSIVE` | Stronger interference, deeper anti-training pressure |
| `MAXIMUM` | Full divergence — maximally distant solutions, higher cost |

### Core Capabilities

- **164 domain lenses** — curated axiom sets spanning biology, physics, mathematics, economics, military strategy, arts, agriculture, psychology, engineering, earth sciences, linguistics, and mythology
- **DeepForge harness** — cognitive interference injection, convergence pruning, and anti-training pressure to prevent predictable output
- **Session management** — typed transcripts, session persistence, and compaction with continuation summaries that preserve invention state
- **Adaptive lens-engine state** — bundle proofs, lineage, fold states, guards, invalidations, recomposition history, and composites
- **MCP tool integration** — JSON-RPC 2.0 stdio client with multi-server manager and namespaced tool routing
- **Multiple backends** — Anthropic (Claude), OpenAI (GPT), OpenRouter, Claude Max, and Claude CLI
- **Interactive REPL** — 22+ slash commands with aliases, categories, tab completion, session history, refinement loops, and live cost tracking
- **Layered configuration** — 5-level precedence: defaults < user (`~/.hephaestus/`) < project < local < environment variables
- **Prior art search** — automated check against known solutions in both the source and target domains
- **Novelty proof generation** — structural isomorphism verification with honest documentation of where the analogy breaks
- **Permission system** — READ_ONLY, WORKSPACE_WRITE, and FULL_ACCESS modes for tool execution
- **Budgeted context assembly** — instruction discovery up the directory tree with dedup, per-source limits, and dynamic boundary markers

---

## Example Output

Problem: *"I need a load balancer that handles unpredictable traffic spikes"*

```
═══════════════════════════════════════════════════════════════
⚒️  HEPHAESTUS — Invention Report
═══════════════════════════════════════════════════════════════

PROBLEM:
  I need a load balancer that handles unpredictable traffic spikes

STRUCTURAL FORM:
  Dynamic resource allocation under stochastic arrival rates
  with no central coordinator and no predictable demand distribution.
  Shape: decentralized optimization over a routing graph with
  Poisson arrivals and time-varying capacity constraints.

───────────────────────────────────────────────────────────────
INVENTION: Pheromone-Gradient Load Balancer
SOURCE DOMAIN: Biology — Ant Colony Foraging (Swarm Intelligence)

  Domain Distance     ████████░░  0.91
  Structural Fidelity ████████░░  0.88
  Novelty Score       █████████░  0.93
───────────────────────────────────────────────────────────────

MECHANISM:
  Ant colonies solve the Traveling Salesman Problem in real time
  without a central planner. Each ant deposits pheromone on the
  path it travels. Shorter paths accumulate pheromone faster.
  Longer paths evaporate. The colony converges on optimal routes
  through this emergent gradient — no ant ever sees the global picture.

TRANSLATION:
  Ant                   → Individual request
  Pheromone             → Latency-weighted routing score
  Pheromone deposit     → Response time recorded at request completion
  Pheromone evaporation → Exponential decay of routing scores (TTL)
  Path length           → Inverse of current server response time
  Colony                → The load balancer routing table
  Nest                  → Client-facing endpoint
  Food source           → Available server capacity

ARCHITECTURE:
  Each server maintains a pheromone level P(s,t): a float in [0,1].
  On request arrival:
    1. Route with probability ∝ P(s,t)
    2. Record response time T(s)
    3. Update: P(s,t+1) = (1-ρ)·P(s,t) + ρ·(1/T(s))

  During a spike, overloaded servers respond slowly → pheromone
  decays → traffic redistributes automatically. No health checks,
  no load reporting, sub-millisecond routing decisions.

IMPLEMENTATION ROADMAP:
  Phase 1: Core router with pheromone table and weighted random
           selection. Validate against round-robin baseline.
  Phase 2: Add evaporation scheduler and spike detection with
           adaptive decay rates.
  Phase 3: In-flight request tracking (compensates for ants
           having path memory, which HTTP requests lack).
  Phase 4: Integrate health-check fallback for dead servers.
           Add ε-greedy exploration bonus for path diversity.

WHERE THE ANALOGY BREAKS:
  • Ants have path memory; HTTP requests don't → track in-flight
    requests per server explicitly.
  • Pheromone is per-path; ours is per-server → loses path diversity.
    Mitigate with exploration bonus (ε-greedy).
  • Colonies handle node failure by path abandonment → need explicit
    health check fallback for dead servers.

PRIOR ART CHECK:
  • "Ant Colony Optimization" (Dorigo, 1992) — foundational ACO.
    Does NOT cover HTTP routing.
  • "AntNet" (Di Caro & Dorigo, 1998) — network routing, not
    load balancing. Different topology and constraints.
  • No prior art for latency-as-pheromone in load balancing.
  Status: NOVEL ✓

───────────────────────────────────────────────────────────────
ALTERNATIVES:
  2. Mycelium Network Router (score: 0.86, distance: 0.89)
  3. Flocking Murmuration Balancer (score: 0.81, distance: 0.87)
───────────────────────────────────────────────────────────────
Cost: $1.18  |  Models: Claude Opus + GPT  |  45s
═══════════════════════════════════════════════════════════════
```

---

## Configuration

### Project config (`.hephaestus/config.yaml`)

Created by `heph init`. These override your global `~/.hephaestus/config.yaml`:

```yaml
# Hephaestus project configuration
backend: api                    # api | claude-max | claude-cli
depth: 3                        # Anti-training pressure rounds (1-10)
candidates: 8                   # Cross-domain search candidates (1-20)
divergence_intensity: STANDARD  # STANDARD | AGGRESSIVE | MAXIMUM
output_mode: MECHANISM          # MECHANISM | FRAMEWORK | NARRATIVE | SYSTEM | PROTOCOL | TAXONOMY | INTERFACE
use_perplexity_research: true   # Enable grounded research annexes and dossier mode
perplexity_model: sonar-pro     # Perplexity model for research and benchmark tasks
auto_save: true                 # Auto-save session transcripts
```

Project-level instructions go in `.hephaestus/instructions.md` — Hephaestus includes them as context in every run within that directory.

Local overrides (not committed to git) go in `.hephaestus/local.yaml`.

### Configuration precedence

```
defaults < ~/.hephaestus/config.yaml < .hephaestus/config.yaml < .hephaestus/local.yaml < env vars < CLI flags
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For opus/both modes | Anthropic API key |
| `OPENAI_API_KEY` | For gpt5/both modes | OpenAI API key |
| `OPENROUTER_API_KEY` | For OpenRouter backend | OpenRouter API key |
| `PERPLEXITY_API_KEY` | No | Perplexity API key for research annexes and benchmark corpora |
| `HEPHAESTUS_DEPTH` | No | Default pressure depth |
| `HEPHAESTUS_MODEL` | No | Default model preset |
| `HEPHAESTUS_USE_PERPLEXITY_RESEARCH` | No | Enable or disable grounded research features by default |
| `HEPHAESTUS_PERPLEXITY_MODEL` | No | Default Perplexity model for research tasks |
| `HEPHAESTUS_LENS_DIR` | No | Custom lens library directory |
| `HEPHAESTUS_LOG_LEVEL` | No | Log level (DEBUG/INFO/WARNING) |

---

## Architecture

```
src/hephaestus/
├── core/               # Genesis pipeline — 5-stage invention engine
│   ├── genesis.py      #   Pipeline orchestrator and streaming interface
│   └── cross_model.py  #   Model presets and backend routing
├── deepforge/          # DeepForge harness — anti-consensus engine
│   ├── harness.py      #   Interference injection, pruning, pressure
│   └── adapters/       #   Anthropic, OpenAI, OpenRouter, Claude Max, Claude CLI
├── lenses/             # Domain lens library (164 YAML axiom sets)
│   ├── loader.py       #   Lens discovery and validation
│   ├── state.py        #   Adaptive Bundle-Proof state, lineage, invalidation, composites
│   └── library/        #   Individual lens files by domain
├── cli/                # Command-line interface
│   ├── main.py         #   Click CLI with all flags and options
│   ├── repl.py         #   Interactive REPL session loop
│   ├── commands.py     #   22+ slash commands with aliases and categories
│   └── display.py      #   Rich terminal output — score bars, stage progress
├── config/             # Configuration
│   └── layered.py      #   5-level config precedence resolver
├── session/            # Session management
│   ├── schema.py       #   Typed transcript model with persistence
│   ├── reference_lots.py # Resume-safety anchors for tools, permissions, and lens state
│   ├── todos.py        #   Working-memory todo list
│   └── compact.py      #   Session compaction with continuation summaries
├── prompts/            # Prompt construction
│   ├── system_prompt.py#   Core invention philosophy prompt
│   └── context_loader.py#  Instruction discovery and budgeted assembly
├── tools/              # Tool system
│   ├── registry.py     #   Tool registry with profiles
│   ├── permissions.py  #   Permission policy enforcement
│   ├── file_ops.py     #   File read/write/search operations
│   ├── web_tools.py    #   Web search and fetch
│   └── mcp/            #   MCP stdio client and multi-server manager
├── agent/              # Conversation runtime
│   └── runtime.py      #   Pluggable adapter, tool dispatch, transcript recording
├── memory/             # Memory subsystem
│   ├── anti_memory.py  #   Anti-memory for convergence prevention
│   └── transparency.py #   Memory hit reporting and context surfaces
├── convergence/        # Convergence detection and pruning
├── novelty/            # Novelty scoring and proof generation
├── output/             # Output formatting
│   ├── formatter.py    #   Markdown, JSON, and plain text renderers
│   ├── prior_art.py    #   Prior art report generation
│   └── proof.py        #   Novelty proof construction
├── analytics/          # Cost tracking and usage analytics
└── sdk/                # Python SDK (Hephaestus class)
```

---

## Development

### Prerequisites

- Python 3.11+
- API keys for Anthropic and/or OpenAI (for integration tests)

### Setup

```bash
git clone https://github.com/CodePhobiia/hephaestus.git
cd hephaestus
pip install -e ".[dev]"
```

### Running tests

```bash
# Full suite (920 tests)
pytest tests/

# By subsystem
pytest tests/test_deepforge.py          # DeepForge harness
pytest tests/test_genesis.py            # Pipeline (mocked LLM)
pytest tests/test_lenses.py             # Lens validation
pytest tests/test_session/              # Session management
pytest tests/test_config/               # Layered config
pytest tests/test_tools/                # Tools and MCP
pytest tests/benchmarks/                # Novelty benchmarks (requires API keys)
```

### Project structure

```
hephaestus/
├── src/hephaestus/     # Source code
├── tests/              # Test suite (920 tests)
├── docs/               # Documentation
├── examples/           # Example invention reports
└── web/                # Web UI (coming soon)
```

### Adding a lens

The fastest way to contribute. Each lens is a single YAML file:

```bash
cp src/hephaestus/lenses/library/biology_immune.yaml \
   src/hephaestus/lenses/library/my_domain.yaml
# Edit the file with domain axioms and structural patterns
pytest tests/test_lenses.py -k my_domain
```

---

## CLI Reference

```
Usage: heph [OPTIONS] [PROBLEM]

Options:
  -d, --depth INT          Anti-training pressure depth (1-10, default: 3)
  -m, --model TEXT         claude-max | claude-cli | opus | gpt5 | both
  -f, --format TEXT        markdown | json | text
  --domain TEXT            Domain hint (e.g. 'distributed-systems')
  --intensity TEXT         STANDARD | AGGRESSIVE | MAXIMUM
  --output-mode TEXT       MECHANISM | FRAMEWORK | NARRATIVE | SYSTEM |
                           PROTOCOL | TAXONOMY | INTERFACE
  --trace                  Show full reasoning trace
  --raw                    Run DeepForge directly, skip Genesis pipeline
  -c, --candidates INT     Search candidates (1-20, default: 8)
  -o, --output PATH        Save report to file
  --cost                   Show detailed cost breakdown
  -q, --quiet              Minimal output
  -i, --interactive        Launch interactive REPL
  --verbose                Debug logging
  -v, --version            Show version and exit
  -h, --help               Show help
```

---

## Python SDK

```python
import asyncio
from hephaestus import Hephaestus

async def main():
    async with Hephaestus.from_env() as heph:
        result = await heph.invent(
            "I need a fraud detection system that adapts in real time"
        )
        inv = result.top_invention
        print(f"Invention: {inv.invention_name}")
        print(f"Source: {inv.source_domain}")
        print(f"Novelty: {inv.novelty_score:.2f}")
        print(f"Cost: ${result.total_cost_usd:.2f}")

asyncio.run(main())
```

Streaming, raw DeepForge mode, lens introspection, and cost estimation are also available. See [docs/api_reference.md](docs/api_reference.md).

---

## License

MIT — see [LICENSE](LICENSE).

Built by [Theyab](https://github.com/theyab). 2026.

---

*The name comes from Hephaestus, Greek god of the forge — the craftsman who built things the Olympians used but couldn't make themselves. He worked alone, in fire, making the impossible real.*
