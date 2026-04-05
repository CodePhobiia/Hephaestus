# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Hephaestus is an "invention engine" — it takes hard engineering problems, decomposes them into abstract structural forms, searches 164 domain lenses (YAML axiom sets in `src/hephaestus/lenses/library/`) for structurally matching solved patterns in distant fields, then translates and verifies the result. The key differentiator is **DeepForge**, a harness that injects cognitive interference, prunes convergent output, and applies anti-training pressure to force models past their consensus responses.

## Build & Dev Commands

```bash
# Install for development (editable, all extras)
pip install -e ".[dev,web]"

# Run full test suite
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_deepforge/test_harness.py -v

# Run a single test by name
pytest tests/ -k "test_pressure_blocks_rephrasing" -v

# Tests with coverage
pytest tests/ -v --tb=short --cov=src/hephaestus --cov-report=term-missing

# Lint
python -m ruff check src/ web/ tests/
python -m mypy src/hephaestus --ignore-missing-imports

# Auto-format
python -m ruff check --fix src/ web/ tests/
python -m ruff format src/ web/ tests/

# Dev server (web UI)
python -m uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir src --reload-dir web

# CLI usage
heph "problem description"
heph --interactive
```

Makefile targets mirror these: `make test`, `make lint`, `make format`, `make serve`.

## Architecture

### The Genesis Pipeline (5 stages)

`src/hephaestus/core/genesis.py` orchestrates the full invention pipeline:

```
Problem → DECOMPOSE → SEARCH → SCORE → TRANSLATE → VERIFY → InventionReport
```

Each stage is a separate class in `src/hephaestus/core/`:
- `decomposer.py` — Extracts abstract structural form (Claude Opus, no DeepForge)
- `searcher.py` — Queries lens library for matching patterns (GPT-4o)
- `scorer.py` — Ranks by `fidelity × distance^1.5` (GPT-4o-mini + embeddings)
- `translator.py` — Builds element-by-element mapping (Claude Opus via DeepForge)
- `verifier.py` — Cross-model adversarial verification (GPT attacks, Claude defends)

Stage classes are lazy-imported in `genesis.py` via `_import_stage_classes()` to avoid circular imports. Tests patch them at `hephaestus.core.genesis.ProblemDecomposer` etc.

### DeepForge Harness

`src/hephaestus/deepforge/harness.py` — The anti-consensus engine, combines three mechanisms:

1. **Cognitive Interference** (`interference.py`) — Injects foreign-domain lens as Anthropic assistant prefill
2. **Convergence Pruner** (`pruner.py`) — Monitors stream, kills predictable output via embedding similarity
3. **Anti-Training Pressure** (`pressure.py`) — Adversarial mirror: gets model's default answer, then blocks it as a prohibition; multi-round stacking pushes past top-N convergence points

Model backends are in `deepforge/adapters/` (Anthropic, OpenAI, OpenRouter, Claude Max, Claude CLI). The provider layer in `src/hephaestus/providers/` provides a separate abstraction with diagnostics and embeddings.

### Pantheon (Multi-Agent Consensus)

`src/hephaestus/pantheon/` — Multi-model deliberation system where different LLM "personas" (Apollo, Athena, Hermes) vote on and critique inventions. `coordinator.py` orchestrates rounds of screening, objection, and resolution. `models.py` defines the typed state model (PantheonState, PantheonRound, PantheonVote, etc.). `state_machine.py` manages transitions.

### BranchGenome

`src/hephaestus/branchgenome/` — Evolutionary search over invention branches. `arena.py` manages candidate populations, `strategy.py` computes survival/promotion scores, `ledger.py` tracks rejections via structural fingerprints, and `assay.py` evaluates branch quality.

### Execution Layer

`src/hephaestus/execution/` — Run lifecycle management with admission control, concurrency semaphores (interactive/deep/research classes), dedup, and retry. `orchestrator.py` is the main RunOrchestrator; `run_store.py` provides persistence; `models.py` defines RunRecord/RunStatus.

### Lens System

`src/hephaestus/lenses/` — 164 YAML domain axiom sets in `library/`. Key modules:
- `loader.py` / `selector.py` — Discovery, validation, and selection
- `state.py` — Adaptive Bundle-Proof state with lineage, invalidation, composites
- `bundles.py` / `guards.py` / `lineage.py` — Bundle proofs, guard conditions, proof-carrying lineage
- `exclusion_ledger.py` — Tracks excluded lenses

### Session & Deliberation

`src/hephaestus/session/` — Typed transcript persistence (`schema.py`), session compaction with continuation summaries (`compact.py`), resume-safety anchors (`reference_lots.py`), working-memory todos (`todos.py`), and deliberation graph with runtime orchestration state (`deliberation.py`).

### Tool System

`src/hephaestus/tools/` — Tool registry with profiles and permission enforcement (READ_ONLY, WORKSPACE_WRITE, FULL_ACCESS). `defaults.py` pre-registers built-in tools (file ops, web, calculator, todos). `invocation.py` wraps handlers in a ToolInvocation ABI. `mcp/` provides JSON-RPC 2.0 stdio client with multi-server manager.

### Entry Points

- **CLI**: `src/hephaestus/cli/main.py` (Click CLI) → `repl.py` (interactive REPL) → `commands.py` (slash commands)
- **SDK**: `src/hephaestus/sdk/client.py` (async `Hephaestus` class, `from_env()` factory)
- **Web**: `web/app.py` (FastAPI with SSE streaming, lens browsing REST API)

### Config

5-level precedence: `defaults < ~/.hephaestus/config.yaml < .hephaestus/config.yaml < .hephaestus/local.yaml < env vars < CLI flags`. Implemented in `src/hephaestus/config/layered.py`.

## Test Organization

Tests mirror source structure under `tests/test_<module>/`. All tests use `pytest-asyncio` with `asyncio_mode = "auto"`. The `conftest.py` adds `src/` to `sys.path` for direct source-tree testing. LLM calls are mocked in unit tests; `tests/test_integration/` requires real API keys.

### Running Tests Without Crashing

**The full test suite can consume 10+ GB of RAM.** This is caused by numpy and sentence-transformers (which pulls in PyTorch) being loaded during test collection.

**Safe (lightweight) test commands:**

```bash
# Run tests for a specific module (recommended for dev)
pytest tests/test_core/ -v --tb=short

# Run tests excluding heavy embedding/convergence tests
pytest tests/ --ignore=tests/test_convergence --ignore=tests/test_forgebase/test_fusion -v --tb=short

# Run a single test file
pytest tests/test_deepforge/test_pressure.py -v
```

**Heavy test modules** (load numpy + sentence-transformers):
- `tests/test_convergence/` — convergence detection with real embeddings
- `tests/test_forgebase/test_fusion/` — fusion candidate generation with numpy matrices
- `tests/test_lenses/test_selector.py` — lens scoring with cosine distance

**Never run the full suite on a machine with <16 GB RAM.** Use targeted test runs instead.

### Lazy Import Pattern for Heavy Dependencies

numpy and sentence-transformers are loaded lazily via `_lazy_np()` / `_lazy_st()` helper functions (NOT at module level). This keeps `import hephaestus` fast and prevents RAM bloat during test collection.

When mocking in tests, patch the lazy helper, not the library:
```python
# CORRECT — patches the lazy factory
with patch("hephaestus.convergence.seed._lazy_st", return_value=mock_model):

# WRONG — the module-level name no longer exists
with patch("hephaestus.convergence.seed.SentenceTransformer", ...):
```

Source files using this pattern:
- `convergence/detector.py`, `convergence/seed.py` — `_lazy_st()` for SentenceTransformer
- `convergence/database.py`, `core/scorer.py`, `forgebase/factory.py`, `forgebase/fusion/candidates.py`, `lenses/selector.py` — `_lazy_np()` for numpy
- `deepforge/pressure.py`, `deepforge/pruner.py` — both `_lazy_np()` and `_lazy_st()`

## Key Patterns

- **Lazy imports**: Heavy dependencies (numpy, sentence-transformers) are lazy-loaded via `_lazy_np()` / `_lazy_st()` helper functions to prevent multi-GB imports at collection time
- **Dataclass-heavy models**: Most data types are `@dataclass` rather than Pydantic (except web layer which uses Pydantic `BaseModel`)
- **Async throughout**: Pipeline, adapters, tools, and orchestrator are all async. Tests use `pytest-asyncio`
- **Build system**: Hatchling (configured in `pyproject.toml`); package lives in `src/hephaestus/`

## Code Style

- Python 3.11+, ruff for linting (rules: E, F, I, N, W, UP, B, A, SIM), line length 100 (format) / 120 (lint)
- mypy strict mode with targeted per-module overrides for LLM-interface modules (see `pyproject.toml`)
- Type annotations required on all public APIs
- Per-file-ignores for E501 in SQL repos, prompt templates, and CLI display files (see `pyproject.toml`)
