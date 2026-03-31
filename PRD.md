# HEPHAESTUS — Product Requirements Document
### The Invention Engine
**Version:** 1.0
**Date:** 2026-03-31
**Authors:** Theyab & Butters

---

## 1. EXECUTIVE SUMMARY

Hephaestus is an open-source invention engine that produces **genuinely novel solutions** to any problem by discovering and translating solved patterns from distant knowledge domains. It is powered by a deep LLM harness (`deepforge`) that forces frontier models (Claude Opus, GPT-5.4) off their default reasoning paths through cognitive interference, convergence pruning, and anti-training pressure.

Every output is provably novel — accompanied by a structural novelty proof, a domain lineage trace, and a prior art check.

**One-liner:** *The AI that invents things that don't exist yet.*

**CLI:**
```bash
heph "I need a load balancer that handles unpredictable traffic spikes"
```

**Output:** A genuinely novel architecture derived from ant colony foraging behavior, with full structural mapping, implementation pseudocode, and novelty proof. Cost: ~$1.25.

---

## 2. THE PROBLEM

LLMs are consensus machines. They produce the most statistically likely output — the average answer. Ask any frontier model a creative question and you get a well-structured, articulate, **predictable** response. The same shaped answer a million other users received.

This happens because:

1. **RLHF creates grooves** — training rewards convergent, safe, expected outputs
2. **Temperature is noise, not creativity** — increasing randomness produces incoherence, not novelty
3. **Prompting is begging** — "be creative" doesn't change the probability distribution
4. **Every user gets the same model** — no personalization of creative process

The result: the most powerful reasoning engines ever built are systematically incapable of producing genuinely new ideas. They recombine existing text. They do not invent.

**Market evidence:**
- Every major AI lab markets "creativity" but measures "helpfulness"
- No existing tool guarantees structural novelty of output
- The $2.1T consulting industry (McKinsey, BCG, Bain) sells "novel strategy" that is recycled pattern-matching at $500/hour
- Patent attorneys spend weeks on prior art searches that could be automated
- Academic researchers spend months on literature reviews to find cross-domain connections

---

## 3. THE SOLUTION

Hephaestus is two systems in one:

| Layer | Name | Function |
|-------|------|----------|
| Engine | **deepforge** | LLM harness that forces novel reasoning at inference level |
| Product | **genesis** | Invention pipeline that uses deepforge to produce novel solutions |

### 3.1 deepforge — The LLM Harness

deepforge wraps around any frontier LLM and makes it structurally impossible to produce predictable output. Three mechanisms:

#### Mechanism 1: Cognitive Interference
During chain-of-thought reasoning, deepforge **injects foreign axioms** mid-reasoning — not at the prompt level but inside the model's active thought process. The model is forced to continue reasoning from a foreign conceptual frame.

**Implementation:**
- Anthropic: Assistant prefill injection (native API support)
- OpenAI: System prompt injection with structured output constraints
- Open-weight: Direct context injection during generation

**Axiom Library:** A curated and expandable library of **cognitive lenses** — axiom sets from 200+ knowledge domains (biology, physics, military strategy, music theory, urban planning, game theory, mycology, linguistics, thermodynamics, etc.). For any problem, the harness selects the lens that is most structurally distant from the problem's native domain while still mapping onto its mathematical shape.

#### Mechanism 2: Convergence Pruning
deepforge monitors the model's output stream in real-time. When it detects the model heading toward a known convergence point (common answer pattern, cliché solution, well-trodden path), it **kills the generation and retries** with the detected path explicitly blocked.

**Implementation:**
- Streaming interception on both Anthropic and OpenAI APIs
- Pattern detection via embedding similarity against a convergence database
- Blocked paths accumulate per-session — each retry seals another exit
- Typical problem requires 2-4 retries before reaching genuinely novel territory

**Convergence Database:** Continuously growing index of "obvious answers" per problem class. Seeded from common LLM outputs, expanded through usage. This is NOT a novelty database (no cold-start problem) — it's a banality database. Easy to build because the default answers are the ones everyone already has.

#### Mechanism 3: Anti-Training Pressure
The harness applies counter-pressure against the model's RLHF-trained preferences, pushing it into the long tail of its output distribution where novel solutions live.

**Implementation (API models):**
- **Adversarial Mirror:** Ask the model for its default answer, then feed it back as a structural prohibition. The model's own consensus response becomes the wall it must climb over.
- **Multi-round stacking:** Round 1 blocks the default. Round 2 blocks the first alternative. Round 3 forces the model past its top 3 convergence points into genuinely unexplored territory.
- **Structural incompatibility verification:** The harness verifies that each round's output is genuinely structurally different (not surface rephrasing) by checking reasoning path divergence.

**Implementation (open-weight models, future):**
- Direct logit manipulation during inference
- Targeted downweighting of high-probability tokens
- Upweighting of unlikely-but-grammatically-valid continuations

### 3.2 genesis — The Invention Pipeline

genesis uses deepforge to execute a 5-stage invention pipeline:

#### Stage 1: DECOMPOSE (Opus 4.6)
Extract the abstract structural form of the user's problem. Strip domain-specific language. Identify the mathematical shape.

**Input:** "I need a reputation system for an anonymous marketplace that can't be gamed"
**Output:**
```yaml
structure: "Establish trust signal in a graph with ephemeral nodes and adversarial actors"
constraints:
  - no persistent identity
  - adversarial nodes present
  - trust must be earned not assigned
  - must resist sybil attack
mathematical_shape: "robust signal propagation in a graph with ephemeral nodes and Byzantine fault tolerance"
```

#### Stage 2: SEARCH (GPT-5.4)
Scan 200+ knowledge domains for solved problems with the same mathematical shape. Return 8-10 candidates from maximally distant fields.

**Output:** Candidate solutions from immune systems, mycelium networks, hawala banking, slime mold pathfinding, naval convoy systems, medieval guild systems, etc.

#### Stage 3: SCORE (either model)
Score each candidate on two axes:
- **Structural fidelity:** How precisely does the foreign solution map to the original problem?
- **Domain distance:** How far is the source field from the target field?

**Scoring function:** `score = fidelity × distance^α` where `α > 1` (superlinear reward for distance — the further the source domain, the more novel the invention).

Candidates from adjacent domains (e.g., "gossip protocols" for a distributed systems problem) are penalized or eliminated — that's not invention, that's a literature search.

#### Stage 4: TRANSLATE (Opus 4.6 via deepforge)
Take the top 3 candidates and build the structural bridge. Translate the foreign solution into the target domain with:
- Explicit element-by-element mapping
- Working architecture or pseudocode
- Mathematical proof of structural isomorphism
- Identification of where the analogy breaks (honesty about limits)

This stage runs through deepforge with cognitive interference active — ensuring the translation itself is creative, not mechanical.

#### Stage 5: VERIFY (cross-model adversarial)
- **Prior art check:** Search existing literature, patents, papers for this specific cross-domain solution
- **Structural validity:** Adversarial model challenges the mapping — does it hold under stress?
- **Implementation feasibility:** Can this be built with current technology?
- **Novelty proof generation:** Formal documentation of why this output is new

---

## 4. USER EXPERIENCE

### 4.1 CLI (Primary Interface)

```bash
# Basic usage
heph "describe your problem here"

# Specify target domain
heph --domain "distributed-systems" "how to handle trust without identity"

# Control creativity depth (more rounds = deeper into long tail)
heph --depth 5 "your problem"

# Output format
heph --format json|markdown|pdf "your problem"

# Use specific model
heph --model opus|gpt5|both "your problem"

# Show the full reasoning trace
heph --trace "your problem"

# Just run deepforge on a raw prompt (no invention pipeline)
heph --raw "your prompt here"
```

### 4.2 Output Format

Every output contains:

```markdown
═══════════════════════════════════════════════════
⚒️  HEPHAESTUS — Invention Report
═══════════════════════════════════════════════════

PROBLEM:
  [Original problem as stated]

STRUCTURAL FORM:
  [Abstract mathematical shape of the problem]

───────────────────────────────────────────────────
INVENTION: [Name]
SOURCE DOMAIN: [e.g., Immune System — T-Cell Memory]
DOMAIN DISTANCE: 0.94 (biology → distributed systems)
STRUCTURAL FIDELITY: 0.87
NOVELTY SCORE: 0.91
───────────────────────────────────────────────────

MECHANISM:
  [How the foreign solution works in its native domain]

TRANSLATION:
  [Element-by-element mapping to target domain]

ARCHITECTURE:
  [Actual implementation — pseudocode, diagrams, math]

WHERE THE ANALOGY BREAKS:
  [Honest limitations of the transfer]

PRIOR ART CHECK:
  [Search results — what exists, what doesn't]
  Status: NO PRIOR ART FOUND for this specific 
  cross-domain application.

NOVELTY PROOF:
  [Formal statement of why this is new]

───────────────────────────────────────────────────
ALTERNATIVE INVENTIONS (from other domains):
  2. [Second-ranked invention, summarized]
  3. [Third-ranked invention, summarized]
───────────────────────────────────────────────────

Cost: $1.18 | Models: Opus 4.6 + GPT-5.4 | Depth: 3
═══════════════════════════════════════════════════
```

### 4.3 Python SDK

```python
from hephaestus import Hephaestus

heph = Hephaestus(
    anthropic_key="...",
    openai_key="...",
)

# Full invention pipeline
result = heph.invent("your problem here")

print(result.invention)          # The novel solution
print(result.source_domain)      # Where it came from
print(result.novelty_score)      # 0.0 - 1.0
print(result.structural_map)     # Element-by-element mapping
print(result.prior_art)          # Prior art search results
print(result.proof)              # Novelty proof
print(result.alternatives)       # Runner-up inventions
print(result.cost)               # Total API cost

# Just the deepforge harness (no invention pipeline)
from hephaestus import DeepForge

forge = DeepForge(model="opus-4-6")
result = forge.generate(
    prompt="your prompt",
    depth=3,                     # rounds of anti-training pressure
    lenses=["biology", "physics"], # cognitive interference domains
    block_convergence=True,       # kill predictable outputs
)
```

### 4.4 Web Interface (Phase 2)

Simple single-page app:
- Text input for problem
- Real-time streaming of the invention process (shows each stage)
- Visual graph of the structural mapping between domains
- Gallery of past inventions (opt-in public sharing)
- Cost counter

---

## 5. TECHNICAL ARCHITECTURE

### 5.1 System Design

```
┌─────────────────────────────────────────────────────┐
│                    HEPHAESTUS                        │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │              genesis (pipeline)                │  │
│  │                                               │  │
│  │  DECOMPOSE → SEARCH → SCORE → TRANSLATE →    │  │
│  │  VERIFY                                       │  │
│  │                                               │  │
│  │  Each stage calls deepforge-wrapped models    │  │
│  └──────────────────┬────────────────────────────┘  │
│                     │                               │
│  ┌──────────────────▼────────────────────────────┐  │
│  │             deepforge (harness)                │  │
│  │                                               │  │
│  │  ┌─────────────┐  ┌──────────────────────┐   │  │
│  │  │  Cognitive   │  │  Convergence         │   │  │
│  │  │  Interference│  │  Pruner              │   │  │
│  │  │  Engine      │  │  (stream monitor)    │   │  │
│  │  └─────────────┘  └──────────────────────┘   │  │
│  │  ┌─────────────┐  ┌──────────────────────┐   │  │
│  │  │  Anti-Train  │  │  Lens Library        │   │  │
│  │  │  Pressure    │  │  (200+ domain axiom  │   │  │
│  │  │  Engine      │  │   sets)              │   │  │
│  │  └─────────────┘  └──────────────────────┘   │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │  Model Adapters                         │  │  │
│  │  │  ├── AnthropicAdapter (prefill + stream)│  │  │
│  │  │  ├── OpenAIAdapter (stream + structured)│  │  │
│  │  │  └── LocalAdapter (logit manipulation)  │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  Supporting Systems                           │  │
│  │  ├── Convergence Database (banality index)    │  │
│  │  ├── Lens Library (cognitive axiom sets)      │  │
│  │  ├── Novelty Verifier (cross-model checker)   │  │
│  │  ├── Prior Art Searcher (patents/papers)      │  │
│  │  └── Cost Tracker                             │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 5.2 Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Core engine | **Python 3.12+** | ML ecosystem, async support, fastest prototyping |
| CLI | **Click + Rich** | Beautiful terminal output, progress indicators |
| Anthropic SDK | `anthropic` official | Prefill, streaming, prompt caching |
| OpenAI SDK | `openai` official | Streaming, structured outputs |
| Embeddings | **Sentence Transformers** (local) | Convergence detection without API calls |
| Convergence DB | **SQLite + numpy** | Zero-dependency local storage |
| Lens Library | **YAML files** | Human-editable, version-controllable axiom sets |
| Web UI (Phase 2) | **FastAPI + HTMX** | Lightweight, streaming-friendly |
| Package | **PyPI (`hephaestus-ai`)** | Standard Python distribution |

### 5.3 File Structure

```
hephaestus/
├── README.md
├── LICENSE (MIT)
├── pyproject.toml
├── heph                          # CLI entry point
├── src/
│   ├── hephaestus/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── genesis.py        # Invention pipeline orchestrator
│   │   │   ├── decomposer.py     # Stage 1: Problem decomposition
│   │   │   ├── searcher.py       # Stage 2: Cross-domain search
│   │   │   ├── scorer.py         # Stage 3: Candidate scoring
│   │   │   ├── translator.py     # Stage 4: Solution translation
│   │   │   └── verifier.py       # Stage 5: Novelty verification
│   │   │
│   │   ├── deepforge/
│   │   │   ├── harness.py        # Main harness orchestrator
│   │   │   ├── interference.py   # Cognitive interference engine
│   │   │   ├── pruner.py         # Convergence detection + killing
│   │   │   ├── pressure.py       # Anti-training pressure (adversarial mirror)
│   │   │   └── adapters/
│   │   │       ├── base.py       # Abstract model adapter
│   │   │       ├── anthropic.py  # Claude adapter (prefill + stream)
│   │   │       ├── openai.py     # GPT adapter (stream + structured)
│   │   │       └── local.py      # Open-weight adapter (logit manip)
│   │   │
│   │   ├── lenses/
│   │   │   ├── loader.py         # Lens library manager
│   │   │   ├── selector.py       # Domain distance + lens selection
│   │   │   └── library/          # 200+ YAML lens files
│   │   │       ├── biology.yaml
│   │   │       ├── physics.yaml
│   │   │       ├── military.yaml
│   │   │       ├── music_theory.yaml
│   │   │       ├── mycology.yaml
│   │   │       ├── economics.yaml
│   │   │       ├── thermodynamics.yaml
│   │   │       └── ...
│   │   │
│   │   ├── convergence/
│   │   │   ├── detector.py       # Embedding-based convergence detection
│   │   │   ├── database.py       # SQLite convergence store
│   │   │   └── seed_data/        # Pre-built banality patterns
│   │   │
│   │   ├── output/
│   │   │   ├── formatter.py      # Markdown/JSON/PDF output formatting
│   │   │   ├── proof.py          # Novelty proof generator
│   │   │   └── prior_art.py      # Patent/paper search integration
│   │   │
│   │   └── cli/
│   │       ├── main.py           # Click CLI definition
│   │       └── display.py        # Rich terminal rendering
│   │
│   └── web/                      # Phase 2
│       ├── app.py
│       ├── templates/
│       └── static/
│
├── tests/
│   ├── test_deepforge.py
│   ├── test_genesis.py
│   ├── test_lenses.py
│   ├── test_convergence.py
│   └── benchmarks/
│       └── novelty_benchmark.py  # Measure actual novelty of outputs
│
├── examples/
│   ├── load_balancer.md          # Full example invention
│   ├── reputation_system.md
│   └── creative_writing.md
│
└── docs/
    ├── architecture.md
    ├── deepforge.md
    ├── lens_authoring.md         # How to create new lenses
    └── api_reference.md
```

---

## 6. LENS LIBRARY SPEC

Each cognitive lens is a YAML file defining a domain's core axioms, patterns, and metaphorical mappings:

```yaml
# lenses/library/immune_system.yaml
name: Immune System
domain: biology
distance_vector: [0.95, 0.12, 0.88, 0.03, ...]  # embedding for domain distance calc

axioms:
  - "Every entity must prove it belongs. Identity is earned through molecular handshake, not declaration."
  - "Memory is distributed. No single cell holds the full picture."
  - "Response scales with threat severity. Minor irritants get minor responses."
  - "The system attacks self-similar threats preferentially (clonal selection)."
  - "Recovery creates permanent readiness (memory T-cells)."

structural_patterns:
  - name: "antigen_presentation"
    abstract: "An entity publicly displays proof of interaction that others can verify"
    maps_to: ["trust", "verification", "reputation", "authentication"]

  - name: "clonal_selection"
    abstract: "Solutions that work get amplified; solutions that fail get pruned"
    maps_to: ["optimization", "selection", "ranking", "evolution"]

  - name: "immune_memory"
    abstract: "Past successful responses are stored for instant future recall"
    maps_to: ["caching", "learning", "pattern_recognition"]

  - name: "self_nonself_discrimination"
    abstract: "Distinguish what belongs from what doesn't, with tolerance for edge cases"
    maps_to: ["classification", "access_control", "fraud_detection"]

injection_prompt: |
  You are now reasoning as if this problem exists inside a biological
  immune system. Every component is a cell. Every interaction is
  molecular. Trust is antigen presentation. Memory is T-cell persistence.
  Failure is inflammation. Continue reasoning from this frame.
```

**Phase 1 target:** 50 high-quality lenses covering the most structurally rich domains.
**Phase 2 target:** 200+ lenses, community-contributed.

---

## 7. CONVERGENCE DATABASE SPEC

The banality index stores known-predictable outputs to detect and block convergence:

```sql
CREATE TABLE convergence_patterns (
    id INTEGER PRIMARY KEY,
    problem_class TEXT,           -- abstract problem type
    pattern_embedding BLOB,       -- semantic embedding of the common answer
    frequency INTEGER DEFAULT 1,  -- how often this pattern appears
    source TEXT,                  -- which model produced it
    blocked_count INTEGER DEFAULT 0, -- how many times we've killed this
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Seeding strategy (no cold-start):**
1. Pre-generate: Run 100 common problem types through GPT-5.4 and Opus with default settings. Store all outputs. These are the "obvious answers" — the exact things we want to block.
2. Grow organically: Every time the convergence pruner kills a generation, the killed output gets added to the database.
3. Community contribution: Users can opt-in to contribute their killed convergence patterns (anonymized).

---

## 8. COST MODEL

### Per-Invention Cost Breakdown

| Stage | Model | Calls | Est. Tokens | Est. Cost |
|-------|-------|-------|-------------|-----------|
| Decompose | Opus 4.6 | 1 | ~2K in / ~1K out | $0.15 |
| Search | GPT-5.4 | 1 | ~2K in / ~2K out | $0.12 |
| Score | GPT-5.4 | 1 | ~3K in / ~500 out | $0.05 |
| Translate (via deepforge) | Opus 4.6 | 2-3 | ~4K in / ~3K out × 2.5 | $0.45 |
| Convergence kills | Either | 2-4 partial | ~1K per partial | $0.15 |
| Adversarial mirror | Opus 4.6 | 3 | ~2K in / ~1K out × 3 | $0.25 |
| Verify + prior art | Both | 2 | ~3K in / ~1K out × 2 | $0.15 |
| **TOTAL** | | **~12-15 calls** | | **~$1.30** |

**With Anthropic prompt caching** (structural prompt components cached): **~$0.85** per invention after first run.

### Pricing Tiers (if monetized)

| Tier | Price | Inventions/mo | Cost to us | Margin |
|------|-------|---------------|------------|--------|
| Free | $0 | 5 | $6.50 | Loss leader |
| Builder | $29/mo | 50 | $42.50 | ~-30% (growth) |
| Pro | $99/mo | 250 | $212.50 | ~-50% (scale to profit) |
| Enterprise | Custom | Unlimited | Variable | Positive at volume |

**Note:** Margins are negative at current API prices. Path to profitability:
1. Open-weight model support (Llama, Mistral) eliminates per-call cost
2. Prompt caching reduces repeat costs by ~35%
3. Volume pricing from Anthropic/OpenAI at scale
4. Enterprise contracts with custom pricing

**Alternative monetization:** Open-source core engine, paid hosted service + premium lenses + team features.

---

## 9. DEVELOPMENT PHASES

### Phase 1: MVP (2-3 weeks)
**Goal:** Working CLI that produces genuinely novel output for technical problems.

| Week | Deliverable |
|------|------------|
| Week 1 | deepforge harness — Anthropic adapter with prefill injection, streaming convergence pruner, adversarial mirror. Working on a raw prompt. |
| Week 2 | genesis pipeline — All 5 stages wired together. 20 initial lenses (biology, physics, military, economics, music, ecology, mycology, game theory, thermodynamics, logistics, neuroscience, materials science, urban planning, linguistics, chemistry, network theory, fluid dynamics, evolutionary psychology, cryptography, swarm intelligence). |
| Week 3 | CLI + output formatting + 10 example inventions in README. PyPI package. GitHub launch. |

### Phase 2: Polish + Web (Weeks 4-6)
- OpenAI adapter (GPT-5.4 support)
- Web interface with streaming invention process
- 50+ lenses
- Convergence database seeding
- Prior art search integration (Google Patents API, Semantic Scholar API)
- Benchmark suite: measure novelty scores across 100 standard problems

### Phase 3: Scale + Community (Weeks 7-12)
- 200+ community-contributed lenses
- Open-weight model support (Llama 4, Mistral Large)
- Invention gallery (opt-in public sharing of outputs)
- Team features (shared invention history, collaborative problem sessions)
- API for programmatic access
- VS Code extension

### Phase 4: Enterprise (Month 4+)
- Custom lens libraries per industry
- Integration with patent filing workflows
- Bulk invention pipelines (run 100 problems overnight)
- On-premise deployment for sensitive IP
- White-label OEM licensing

---

## 10. SUCCESS METRICS

### Launch (Week 3)
- [ ] Working CLI producing novel output for 90%+ of test problems
- [ ] 10 compelling example inventions in README
- [ ] < 60 seconds per invention
- [ ] < $1.50 per invention

### Month 1
- [ ] 500+ GitHub stars
- [ ] 100+ unique users (CLI installs via PyPI)
- [ ] Featured in at least one AI newsletter
- [ ] 50+ lenses in library

### Month 3
- [ ] 5,000+ GitHub stars
- [ ] 1,000+ monthly active users
- [ ] Community lens contributions
- [ ] Web interface live
- [ ] $1,000+ MRR (if monetized)

### Month 6
- [ ] 15,000+ GitHub stars
- [ ] 10,000+ monthly active users
- [ ] Integration with at least 2 enterprise workflows
- [ ] Academic paper published on the deepforge methodology
- [ ] Referenced in patent filings

---

## 11. COMPETITIVE LANDSCAPE

| Product | What it does | Why Hephaestus is different |
|---------|-------------|---------------------------|
| ChatGPT/Claude | General-purpose LLM | Produces consensus output. No novelty guarantee. |
| Perplexity | AI search | Finds existing knowledge. Doesn't create new knowledge. |
| Ideaflow/Miro AI | Brainstorming tools | Surface-level ideation. No structural depth. No novelty proof. |
| Patent AI tools | Prior art search | Searches what EXISTS. Doesn't create what DOESN'T. |
| GitHub Copilot | Code completion | Autocompletes known patterns. Doesn't invent new architectures. |

**No direct competitor exists.** The closest concept is TRIZ (Theory of Inventive Problem Solving, developed in USSR in 1946) — but TRIZ is a manual methodology, not an automated engine, and it operates within a fixed set of 40 inventive principles rather than searching across all human knowledge.

Hephaestus is **automated TRIZ with unlimited domains and LLM-powered translation.**

---

## 12. RISKS AND MITIGATIONS

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Model outputs aren't actually novel (just rephrased) | Critical | Structural novelty verification with embedding distance + adversarial cross-model checking |
| Translations are superficial metaphors, not working solutions | Critical | Stage 4 requires explicit element-by-element mapping + pseudocode + math. Stage 5 adversarially attacks weak mappings. |
| API costs make it unprofitable | High | Open-weight model support in Phase 3 + prompt caching + volume pricing |
| Novelty claims are unfalsifiable | High | Prior art search integration + formal novelty proof structure + honest "where the analogy breaks" section in every output |
| Lens library is hard to scale | Medium | YAML format is contributor-friendly + community contribution pipeline + LLM-assisted lens generation |
| Users expect magic, get mixed results | Medium | Clear documentation of what works well (technical/structural problems) vs. less well (purely subjective/artistic problems) |
| Anthropic/OpenAI change API capabilities | Low | Adapter pattern isolates model-specific code + open-weight fallback |

---

## 13. OPEN QUESTIONS

1. **Naming conflict check:** Is "Hephaestus" trademarked in the software space? Need to verify.
2. **License model:** MIT (maximum adoption) vs. Apache 2.0 (patent protection) vs. AGPL (force sharing)?
3. **Lens quality control:** How do we validate community-contributed lenses? Peer review? Automated testing?
4. **Benchmark design:** How do we rigorously measure "novelty" in a reproducible way? Need a formal benchmark suite.
5. **Prior art search depth:** Google Patents API is limited. Do we need a Semantic Scholar integration? ArXiv? Both?
6. **Local model viability:** How much quality is lost running deepforge on Llama 4 vs. Opus? Need benchmarks.

---

## 14. THE README HOOK

The GitHub README opens with:

> # ⚒️ Hephaestus
> ### The god of the forge didn't ask permission. He just built things the other gods couldn't imagine.
>
> **Hephaestus is an invention engine.** Give it a problem. It gives you a solution that has never existed — not by being random, but by finding solved patterns in distant fields and translating them into your domain.
>
> Every output comes with a novelty proof.
>
> ```bash
> pip install hephaestus-ai
> heph "I need a load balancer that handles unpredictable traffic spikes"
> ```
>
> **Cost:** ~$1.25 per invention. **Time:** ~45 seconds. **Novelty:** Provable.

---

*This document is the forge. Now we build the fire.*
