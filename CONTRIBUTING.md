# Contributing to Hephaestus

## Quick Setup

```bash
git clone https://github.com/CodePhobiia/hephaestus.git
cd hephaestus
pip install -e ".[dev,web]"
```

Requires Python 3.11+.

## Development Workflow

```bash
# Lint
python -m ruff check src/ web/ tests/
python -m mypy src/hephaestus --ignore-missing-imports

# Auto-format
python -m ruff check --fix src/ web/ tests/
python -m ruff format src/ web/ tests/

# Run tests (targeted — see note below)
pytest tests/test_core/ -v --tb=short
```

> **RAM warning:** The full test suite loads PyTorch via sentence-transformers and can consume 10+ GB of RAM. Run targeted tests by module instead of `pytest tests/`. See `CLAUDE.md` for the full list of heavy test modules.

## Code Style

- **Linting**: ruff with rules E, F, I, N, W, UP, B, A, SIM. Line length: 100 (format) / 120 (lint).
- **Types**: mypy strict mode. Use `TYPE_CHECKING` guards for heavy imports.
- **Heavy deps**: numpy and sentence-transformers must be lazy-loaded via `_lazy_np()` / `_lazy_st()` helpers, never at module level. See `CLAUDE.md` for the full pattern.
- **Dataclasses**: Prefer `@dataclass` over Pydantic for internal models. Web layer uses Pydantic `BaseModel`.
- **Async**: All pipeline, adapter, tool, and orchestrator code is async.

## Adding a Domain Lens

Lenses live in `src/hephaestus/lenses/library/` as YAML files. Each lens needs:

- `name`, `domain`, `subdomain` — metadata
- `axioms` — 6+ structural principles of the domain (not surface facts)
- `structural_patterns` — 5+ patterns with `maps_to` tags for cross-domain matching
- `injection_prompt` — framing text for cognitive interference

See `docs/lens_authoring.md` for the full schema and `src/hephaestus/lenses/library/biology_immune.yaml` for a reference example.

Validate your lens:
```bash
python -c "from hephaestus.lenses.loader import LensLoader; LensLoader().load_all()"
```

## Pull Requests

- Keep PRs focused — one feature or fix per PR.
- All CI checks must pass (ruff, mypy, tests, pip-audit).
- Include a brief description of what and why.
- Add tests for new functionality.

## Project Structure

See `CLAUDE.md` for a full architecture guide including the Genesis pipeline, DeepForge harness, Pantheon system, BranchGenome, and ForgeBase.
