# HEPHAESTUS — Full Production Build Plan

## Architecture Overview

```
hephaestus/
├── src/hephaestus/
│   ├── __init__.py
│   ├── core/
│   │   ├── genesis.py          # Main invention pipeline orchestrator
│   │   ├── decomposer.py       # Stage 1: Problem → abstract structure
│   │   ├── searcher.py         # Stage 2: Cross-domain pattern search
│   │   ├── scorer.py           # Stage 3: Candidate scoring (fidelity × distance)
│   │   ├── translator.py       # Stage 4: Foreign solution → target domain
│   │   └── verifier.py         # Stage 5: Novelty verification + prior art
│   │
│   ├── deepforge/
│   │   ├── __init__.py
│   │   ├── harness.py          # Main harness orchestrator
│   │   ├── interference.py     # Cognitive interference (axiom injection)
│   │   ├── pruner.py           # Convergence detection + stream killing
│   │   ├── pressure.py         # Anti-training pressure (adversarial mirror)
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── base.py         # Abstract adapter interface
│   │       ├── anthropic.py    # Claude adapter (prefill + streaming)
│   │       └── openai.py       # GPT adapter (streaming + structured)
│   │
│   ├── lenses/
│   │   ├── __init__.py
│   │   ├── loader.py           # Lens library manager
│   │   ├── selector.py         # Domain distance calculation + lens selection
│   │   └── library/            # 50+ YAML lens files
│   │       ├── biology_immune.yaml
│   │       ├── biology_ecology.yaml
│   │       ├── biology_mycology.yaml
│   │       ├── biology_swarm.yaml
│   │       ├── biology_evolution.yaml
│   │       ├── physics_thermodynamics.yaml
│   │       ├── physics_fluid_dynamics.yaml
│   │       ├── physics_quantum.yaml
│   │       ├── physics_optics.yaml
│   │       ├── chemistry_catalysis.yaml
│   │       ├── chemistry_polymers.yaml
│   │       ├── math_topology.yaml
│   │       ├── math_game_theory.yaml
│   │       ├── math_chaos.yaml
│   │       ├── cs_network_theory.yaml
│   │       ├── cs_cryptography.yaml
│   │       ├── cs_distributed_systems.yaml
│   │       ├── military_strategy.yaml
│   │       ├── military_logistics.yaml
│   │       ├── military_intelligence.yaml
│   │       ├── economics_markets.yaml
│   │       ├── economics_behavioral.yaml
│   │       ├── economics_game_theory.yaml
│   │       ├── music_theory.yaml
│   │       ├── music_acoustics.yaml
│   │       ├── linguistics_syntax.yaml
│   │       ├── linguistics_semantics.yaml
│   │       ├── neuroscience_memory.yaml
│   │       ├── neuroscience_perception.yaml
│   │       ├── neuroscience_plasticity.yaml
│   │       ├── urban_planning.yaml
│   │       ├── architecture_structural.yaml
│   │       ├── materials_science.yaml
│   │       ├── geology_tectonics.yaml
│   │       ├── meteorology.yaml
│   │       ├── oceanography.yaml
│   │       ├── astronomy_orbital.yaml
│   │       ├── sociology_networks.yaml
│   │       ├── psychology_cognitive.yaml
│   │       ├── psychology_evolutionary.yaml
│   │       ├── philosophy_logic.yaml
│   │       ├── agriculture.yaml
│   │       ├── cooking_fermentation.yaml
│   │       ├── textiles_weaving.yaml
│   │       ├── forestry_management.yaml
│   │       ├── epidemiology.yaml
│   │       ├── mythology_narrative.yaml
│   │       ├── sports_strategy.yaml
│   │       ├── film_cinematography.yaml
│   │       ├── martial_arts.yaml
│   │       └── navigation_wayfinding.yaml
│   │
│   ├── convergence/
│   │   ├── __init__.py
│   │   ├── detector.py         # Embedding-based convergence detection
│   │   ├── database.py         # SQLite convergence store
│   │   └── seed.py             # Seed data generator
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── formatter.py        # Markdown/JSON/PDF output
│   │   ├── proof.py            # Novelty proof generator
│   │   └── prior_art.py        # Patent/paper search
│   │
│   ├── sdk/
│   │   ├── __init__.py
│   │   └── client.py           # Python SDK (Hephaestus class)
│   │
│   └── cli/
│       ├── __init__.py
│       ├── main.py             # Click CLI
│       └── display.py          # Rich terminal rendering
│
├── tests/
│   ├── conftest.py
│   ├── test_deepforge/
│   │   ├── test_harness.py
│   │   ├── test_interference.py
│   │   ├── test_pruner.py
│   │   ├── test_pressure.py
│   │   └── test_adapters.py
│   ├── test_core/
│   │   ├── test_genesis.py
│   │   ├── test_decomposer.py
│   │   ├── test_searcher.py
│   │   ├── test_scorer.py
│   │   ├── test_translator.py
│   │   └── test_verifier.py
│   ├── test_lenses/
│   │   ├── test_loader.py
│   │   └── test_selector.py
│   ├── test_convergence/
│   │   ├── test_detector.py
│   │   └── test_database.py
│   ├── test_output/
│   │   └── test_formatter.py
│   ├── test_cli/
│   │   └── test_main.py
│   └── test_integration/
│       └── test_full_pipeline.py
│
├── examples/
│   ├── load_balancer.md
│   ├── reputation_system.md
│   ├── traffic_optimization.md
│   ├── recommendation_engine.md
│   └── fraud_detection.md
│
├── docs/
│   ├── architecture.md
│   ├── deepforge.md
│   ├── lens_authoring.md
│   ├── api_reference.md
│   └── benchmarks.md
│
├── web/
│   ├── app.py                  # FastAPI server
│   ├── templates/
│   │   └── index.html          # HTMX streaming UI
│   └── static/
│       ├── style.css
│       └── app.js
│
├── pyproject.toml
├── README.md
├── LICENSE
├── Makefile
├── Dockerfile
├── docker-compose.yml
└── .github/
    └── workflows/
        ├── test.yml
        └── publish.yml
```

## Build Phases (Sequential — each depends on prior)

### PHASE 1: Foundation (deepforge harness)
**Agent 1 — deepforge core**
- `src/hephaestus/deepforge/adapters/base.py` — Abstract adapter interface
- `src/hephaestus/deepforge/adapters/anthropic.py` — Claude adapter with prefill + streaming
- `src/hephaestus/deepforge/adapters/openai.py` — GPT adapter with streaming + structured output
- `src/hephaestus/deepforge/interference.py` — Cognitive interference engine
- `src/hephaestus/deepforge/pruner.py` — Convergence stream pruner
- `src/hephaestus/deepforge/pressure.py` — Adversarial mirror engine
- `src/hephaestus/deepforge/harness.py` — Main orchestrator
- All tests for above

### PHASE 2: Knowledge (lens library)
**Agent 2 — lenses**
- `src/hephaestus/lenses/loader.py` — YAML loader + validator
- `src/hephaestus/lenses/selector.py` — Domain distance + selection algorithm
- All 50 YAML lens files with axioms, patterns, injection prompts
- Tests

### PHASE 3: Pipeline (genesis invention engine)
**Agent 3 — genesis core** (DEPENDS ON Phase 1 + 2)
- `src/hephaestus/core/decomposer.py`
- `src/hephaestus/core/searcher.py`
- `src/hephaestus/core/scorer.py`
- `src/hephaestus/core/translator.py`
- `src/hephaestus/core/verifier.py`
- `src/hephaestus/core/genesis.py` — Main orchestrator
- All tests

### PHASE 4: Intelligence (convergence + output)
**Agent 4 — convergence + output** (DEPENDS ON Phase 1)
- `src/hephaestus/convergence/detector.py`
- `src/hephaestus/convergence/database.py`
- `src/hephaestus/convergence/seed.py`
- `src/hephaestus/output/formatter.py`
- `src/hephaestus/output/proof.py`
- `src/hephaestus/output/prior_art.py`
- Tests

### PHASE 5: Interface (CLI + SDK)
**Agent 5 — CLI + SDK** (DEPENDS ON Phase 3 + 4)
- `src/hephaestus/cli/main.py`
- `src/hephaestus/cli/display.py`
- `src/hephaestus/sdk/client.py`
- `pyproject.toml` — Full package config
- Tests

### PHASE 6: Web + Packaging
**Agent 6 — web + deploy** (DEPENDS ON Phase 5)
- `web/app.py` — FastAPI streaming server
- `web/templates/index.html` — HTMX UI
- `Dockerfile` + `docker-compose.yml`
- `.github/workflows/` — CI/CD
- `Makefile`

### PHASE 7: Documentation + Examples
**Agent 7 — docs**
- `README.md` — The killer README
- `docs/` — All documentation
- `examples/` — 5 full example inventions
- `LICENSE`

## Parallel Execution Plan
- Phase 1 + Phase 2 can run in PARALLEL (no deps)
- Phase 3 + Phase 4 can run in PARALLEL (both depend on P1, not each other)
- Phase 5 depends on P3+P4
- Phase 6 depends on P5
- Phase 7 can start after P5

## Git Strategy
- Main branch: `main`
- Each phase gets a worktree: `phase-1-deepforge`, `phase-2-lenses`, etc.
- Merge into main after each phase passes tests
