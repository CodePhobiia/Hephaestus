# Hephaestus latest zip audit (2026-04-03)

## What was verified
- Extracted `Hephaestus_backup.zip` and inspected the live source tree.
- `python -m compileall -q src tests web` passes.
- Full `pytest tests/ -q` could not be completed in this environment because required runtime dependencies (`anthropic`, `sentence_transformers`) are not installed here.
- With lightweight local stubs for those missing SDK/ML packages, targeted tests were run for the hardened areas.

## Launch blockers still present

### 1) Web invent path is broken at runtime
`web/app.py:342-354` builds `GenesisConfig(..., domain_hint=request_body.domain_hint)`, but `GenesisConfig` does not define `domain_hint`.

`src/hephaestus/core/genesis.py:171-232` defines `GenesisConfig`; it has no `domain_hint`, `depth`, or `pressure_translate_rounds` fields.

This means `/api/invent` will raise:
- `TypeError: GenesisConfig.__init__() got an unexpected keyword argument 'domain_hint'`

### 2) CLI Genesis path is broken at runtime
`src/hephaestus/cli/main.py:941-1105` passes `depth`, `domain_hint`, and `pressure_translate_rounds` into `GenesisConfig`, but those fields do not exist.

This means normal CLI Genesis execution will raise:
- `TypeError: GenesisConfig.__init__() got an unexpected keyword argument 'depth'`

### 3) Depth rollback is incomplete and inconsistent
Public UI depth slider is gone, but the feature is still public in multiple places:
- README still documents `--depth` and `HEPHAESTUS_DEPTH` (`README.md:281`, `README.md:308`, `README.md:430`)
- CLI still exposes `--depth` and `--domain` (`src/hephaestus/cli/main.py:84-113`)
- Web API still accepts `domain_hint` (`web/app.py:111-118`)
- SDK still exposes raw DeepForge `depth` plus internal depth state (`src/hephaestus/sdk/client.py:112`, `src/hephaestus/sdk/client.py:275-337`)

### 4) DeepForge pressure is still disabled in Genesis translate
- `src/hephaestus/core/genesis.py:2007-2017` sets `use_pressure=False` on the translate harness.
- `src/hephaestus/core/translator.py:687-695` also builds translation harness config with `use_pressure=False` and comments “Pressure not needed”.

So the repo still does **not** implement real Genesis-mode DeepForge pressure.

### 5) Default tool handlers do not match the runtime calling convention
Default handlers in `src/hephaestus/tools/defaults.py:146-212` all accept a single `params` dict, e.g. `_handle_read_file(params)`, `_handle_calculator(params)`.

But the runtime calls handlers as keyword arguments in `src/hephaestus/agent/runtime.py:279-287`:
- `tool_def.handler(**tool_input)`

That means the default registry will fail under the real runtime with errors like:
- `TypeError: _handle_calculator() got an unexpected keyword argument 'expression'`
- `TypeError: _handle_read_file() got an unexpected keyword argument 'path'`

### 6) Pantheon still has a live reforge-resolution bug
Targeted Pantheon tests still fail. In particular:
- `tests/test_pantheon/test_coordinator.py::test_pantheon_deliberation_reforges_after_veto`

The likely root cause is that explicit `addressed_objection_ids` from a successful reforge record are not applied to the state ledger before the next council round. Fatal objections therefore remain open unless they are re-issued and then explicitly discharged by some later path.

Relevant code:
- Reforge record creation: `src/hephaestus/pantheon/coordinator.py:1499-1558`
- Reforge vote emission: `src/hephaestus/pantheon/coordinator.py:1691-1704`
- Missing-open auto-resolution skips fatal objections: `src/hephaestus/pantheon/coordinator.py:565-590`
- Council flow: `src/hephaestus/pantheon/coordinator.py:1965-2043`

### 7) File search / grep contract regressed
`search_files()` and `grep_search()` now raise `NotADirectoryError` on missing directories instead of returning an error string like the rest of the file tools.

Code:
- `src/hephaestus/tools/file_ops.py:112-114`
- `src/hephaestus/tools/file_ops.py:156-158`

This breaks current tests and changes the surface contract.

### 8) SSRF hardening improved, but current implementation breaks mocked fetch tests and depends on live DNS
`src/hephaestus/tools/web_tools.py:62-108` resolves DNS inside `_is_safe_url()`. If DNS lookup fails, the URL is rejected before the mocked HTTP client is even exercised.

In this environment, that caused targeted failures even for `https://example.com` in:
- `tests/test_tools/test_web_tools.py::TestWebFetch::*`

This is not purely a unit-test issue. The fetch tool now fails closed on transient DNS lookup failures, and the resolver logic is tightly coupled to runtime network availability.

### 9) Docs are still inconsistent on lens counts and depth semantics
- README uses **160+** (`README.md:24`, `README.md:118`, `README.md:130`, `README.md:165`, `README.md:327`)
- PRD still uses **200+** in several places (`PRD.md:115`, `PRD.md:297`, `PRD.md:366`, `PRD.md:459`, `PRD.md:543`)
- Actual YAML lens count in `src/hephaestus/lenses/library` is **164**
- `docs/architecture.md:70` still mentions `model, depth`

## What is genuinely improved in this zip
- Calculator no longer uses raw `eval`; AST-based restriction is in place (`src/hephaestus/tools/defaults.py:47-144`).
- Workspace path boundary protection is improved with `Path.relative_to(...)` (`src/hephaestus/tools/file_ops.py:26-37`).
- `write_file(..., append=True)` now appends correctly (`src/hephaestus/tools/file_ops.py:54-67`).
- `search_files()` / `grep_search()` now exist (`src/hephaestus/tools/file_ops.py:95-193`).
- Permission policy defaults unknown tools to dangerous and can use registry categories (`src/hephaestus/tools/permissions.py:17-25`).
- Translator now fails on malformed or substantively empty JSON instead of fabricating a successful translation (`src/hephaestus/core/translator.py:1007-1071`).
- Pantheon nested JSON extraction was fixed with brace-depth parsing (`src/hephaestus/pantheon/coordinator.py:86-128`).
- `.dockerignore` exists and `.env.example` replaced `.env.docker`.
- Multi-stage Dockerfile is present.
- Web UI no longer shows a depth slider.

## Test results run here
### Direct compile check
- `python -m compileall -q src tests web` ✅

### Full suite
- `pytest tests/ -q` ❌ collection blocked in this environment by missing installed deps:
  - `anthropic`
  - `sentence_transformers`

### Targeted tests with local stubs for missing deps
Command run:
- `pytest -q tests/test_tools/test_file_ops.py tests/test_tools/test_permissions.py tests/test_tools/test_web_tools.py tests/test_core/test_translator.py tests/test_pantheon/test_coordinator.py`

Result:
- **71 passed, 6 failed**

Failures observed:
- `tests/test_tools/test_file_ops.py::TestSearchFiles::test_missing_dir`
- `tests/test_tools/test_file_ops.py::TestGrepSearch::test_missing_dir`
- `tests/test_tools/test_web_tools.py::TestWebFetch::test_fetches_html`
- `tests/test_tools/test_web_tools.py::TestWebFetch::test_truncates`
- `tests/test_tools/test_web_tools.py::TestWebFetch::test_plain_text`
- `tests/test_pantheon/test_coordinator.py::test_pantheon_deliberation_reforges_after_veto`

Additional targeted test:
- `pytest -q tests/test_tools/test_defaults.py`
- **26 passed, 1 failed**
- failure: `web_search` is now `dangerous`, but the test still expects it to be `safe`

Additional smoke check:
- `python test_phase0_verify.py` ❌ fails in its permissions section because that script assumes `_tool_category("calculator") == "safe"` without supplying a registry, which is no longer true under the current default-deny design.

## Bottom line
This zip contains real hardening progress, but it is **not ready for early-access launch yet**.

The highest-priority fixes are:
1. Repair the `GenesisConfig` contract mismatch across web/CLI.
2. Finish the depth/domain rollback consistently across public surfaces.
3. Fix the default tool handler signature mismatch with `ConversationRuntime`.
4. Fix Pantheon reforge objection discharge so fatal objections can actually clear.
5. Decide and standardize the `search_files` / `grep_search` error contract.
6. Make SSRF checks testable and less brittle under DNS failure while keeping the public-internet-only policy.
