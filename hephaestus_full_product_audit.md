# Hephaestus Full Product Audit — latest zip

## Executive verdict

Hephaestus has advanced materially since the earlier repos. The project now has real production-oriented scaffolding: `GenesisConfig` parity work, execution models/run-store abstractions, CI/CD workflows, a multi-stage Docker image, stronger file-path safety, AST-based calculator hardening, stricter SSRF checks, provider modularization, and a much broader operational surface.

But the repo is **still not fully production-ready**.

The biggest reason is not one isolated bug; it is that several of the new Phase 2-style systems exist **as scaffolding rather than live integrated product paths**. The strongest examples are the durable execution plane, observability, and parts of the advanced Genesis/DeepForge runtime. On top of that, there are still a few live correctness defects in core runtime paths.

My bottom line:
- **Much stronger than the prior repo**
- **Production-capable in parts**
- **Not yet production-complete as a full product**

## What I verified

### Compile / import
- `python -m compileall -q src tests web` **passes**.
- Top-level package import works when the repo is on `PYTHONPATH` and missing provider/embedding SDKs are stubbed.

### Testability constraints in this environment
The container here does **not** have all repo dependencies installed, notably:
- `anthropic`
- `openai`
- `sentence_transformers`
- `aiosqlite`
- `asyncpg`

So I could not honestly confirm a clean full-suite result in a real dependency-complete environment.

### Full-suite attempt (stubbed)
With lightweight stubs for `anthropic`, `openai`, and `sentence_transformers`, a full `pytest tests/ -q` run still stopped during collection because convergence tests import `aiosqlite` at module import time:
- `tests/test_convergence/test_database.py`
- `tests/test_convergence/test_detector.py`
- `tests/test_convergence/test_seed.py`
- `tests/test_convergence/test_tracker.py`

### Targeted test pass (stubbed)
I ran a targeted batch over the most critical hardened areas:
- `tests/test_tools/test_defaults.py`
- `tests/test_tools/test_file_ops.py`
- `tests/test_tools/test_permissions.py`
- `tests/test_tools/test_web_tools.py`
- `tests/test_pantheon/test_coordinator.py`
- `tests/test_core/test_genesis.py`
- `tests/test_core/test_translator.py`

Result:
- **109 passed**
- **18 failed**

Some of those failures are stale-test/ABI drift, but several expose real runtime or integration issues.

### Direct runtime checks I executed
I also ran direct code-path checks outside pytest, including:
- actual default tool invocation through `ToolInvocation.execute(...)`
- specific config/runtime surface inspection
- execution-plane wiring inspection
- web API route inspection
- CI/CD and Docker inspection
- docs/product-truth consistency review

---

## What is genuinely better now

These are real improvements, not cosmetic:

### 1) Config surface is much healthier
`GenesisConfig` now explicitly includes:
- `depth`
- `domain_hint`
- `exploration_mode`
- `pressure_translate_enabled`
- `pressure_search_mode`

Relevant code:
- `src/hephaestus/core/genesis.py:186-209`

That resolves the earlier “public surfaces reference fields that GenesisConfig doesn’t accept” class of bug.

### 2) File workspace safety is materially stronger
The file tool layer now uses `Path.relative_to(...)`-style containment logic, append handling is fixed, and `search_files()` / `grep_search()` exist.

### 3) Calculator is no longer an `eval(...)` RCE trap
The calculator now uses AST parsing and a small allowlist.
- `src/hephaestus/tools/defaults.py:64-143`

### 4) CI/CD and Docker maturity improved
The repo now includes:
- CI workflow
- release workflow
- multi-stage Docker build
- `.dockerignore`
- `.env.example`

Relevant files:
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `Dockerfile`
- `docker-compose.yml`

### 5) SSRF posture is materially better
`web_fetch` now blocks:
- non-HTTP(S) schemes
- embedded credentials
- raw IP literals
- non-standard ports
- loopback/private/link-local/etc.
- unsafe redirects

Relevant code:
- `src/hephaestus/tools/web_tools.py:63-165`

### 6) Pantheon and translator both show real hardening work
Examples:
- translator now fail-fast parses instead of silently inventing fake success objects when JSON is malformed
  - `src/hephaestus/core/translator.py:1033-1088`
- Pantheon objection-ID canonicalization is stricter
  - `src/hephaestus/pantheon/coordinator.py:1503-1545`

---

## Critical blockers still standing

## 1) Durable execution plane is **not actually wired into the live product**
This is the single largest production-gap remaining.

The repo has real execution abstractions:
- `RunRecord`
- `RunStore`
- `SQLiteRunStore`
- `PostgresRunStore`
- `RunOrchestrator`

But the live web invention route still bypasses them and runs Genesis inline:
- `web/app.py:304-377`

The `/api/runs` endpoints also instantiate a brand-new `SQLiteRunStore()` **per request**, with the default path `":memory:"`:
- `web/app.py:469-529`
- `src/hephaestus/execution/run_store.py:419`

That means the “run listing / get / cancel” surface is effectively ephemeral and disconnected from the actual `/api/invent` work.

Worse, the orchestrator itself is incomplete as a live scheduler:
- `submit()` queues a record, but does not launch execution: `src/hephaestus/execution/orchestrator.py:77-118`
- `execute()` can run a job manually: `src/hephaestus/execution/orchestrator.py:120-170`
- `_active_runs` is declared but never populated anywhere in the file
- there is no queue worker / dispatcher loop

**Impact:** the product has execution-plane scaffolding, but not a real durable run system in the live web product.

## 2) Async web tools are broken in the actual tool runtime
The new tool ABI is partly in place:
- `ToolInvocation.execute(...)` calls handlers as `(context, **kwargs)`
- `ToolRegistry` wraps handlers into `ToolInvocation`

Relevant code:
- `src/hephaestus/tools/invocation.py:22-46`

However, the built-in `web_search` and `web_fetch` handlers still do this:
- `src/hephaestus/tools/defaults.py:186-197`

```python
return asyncio.run(web_search(...))
return asyncio.run(web_fetch(...))
```

That explodes when called from the actual async agent runtime. I verified it directly:
- runtime result: `ToolInvocationError: Tool error (web_search): asyncio.run() cannot be called from a running event loop`

**Impact:** default web tools are not actually usable through the async runtime path.

## 3) DeepForge pressure semantics are still internally inconsistent
There is now real wiring from `GenesisConfig` into search/translate harness config:
- `src/hephaestus/core/genesis.py:2008-2043`

That is progress.

But the underlying pressure engine still has two semantic problems:

### 3a) `max_rounds=1` means “mirror only,” not “one pressure round”
In `pressure.py`, round 0 is the mirror/default answer, and pressure rounds are:
- `for round_idx in range(1, self._max_rounds)`
- `src/hephaestus/deepforge/pressure.py:257-349`

So a budget of `1` does **zero actual pressure rounds**.

### 3b) The novelty threshold math still appears inverted
The code accepts novelty when:
- `min_dist >= (1.0 - self._threshold)`
- `src/hephaestus/deepforge/pressure.py:312`

With `_STRUCTURAL_DISTANCE_THRESHOLD = 0.75` (`src/hephaestus/deepforge/pressure.py:63`), this behaves like accepting distance `>= 0.25`, not `>= 0.75`.

### 3c) `exploration_budget` still forces `pressure_max_rounds >= 1` even in standard mode
- `src/hephaestus/core/genesis.py:203-207`

So standard mode can still carry a pressure-round budget value of `1`, which in practice means mirror-only behavior.

**Impact:** the control surface is more wired than before, but the engine semantics are still not truthful or calibrated enough for a production claim.

## 4) Translator’s new schema pass adds hidden behavior and breaks expectations
The translator now does a second “deterministic schema pass” whenever pressure is enabled:
- `src/hephaestus/core/translator.py:783-786`
- `src/hephaestus/core/translator.py:824-827`
- `src/hephaestus/core/translator.py:920-935`

That is a sensible pattern architecturally.

But two real issues remain:

### 4a) The second pass cost is not accounted into the translation trace/cost
`_deterministic_schema_pass()` performs a second model call via `self._harness.adapter.generate(...)`, but `_build_translation()` only receives the original forge trace.
- cost building path: `src/hephaestus/core/translator.py:937-1021`

So when pressure is enabled, translation cost appears undercounted.

### 4b) The new async second-pass behavior still breaks current translator tests
Targeted tests that used simple mocks now fail because `_deterministic_schema_pass()` awaits an async adapter call and the patched object is a plain `MagicMock`.

Some of that is test drift, but it also confirms this subsystem changed materially and is not yet reconciled across the codebase.

## 5) Pantheon still has a live reforge/discharge correctness problem
Pantheon’s logic is better, but not done.

Targeted test still failing:
- `tests/test_pantheon/test_coordinator.py::test_pantheon_deliberation_reforges_after_veto`

The ledger machinery around fatal objections is now stricter:
- `_resolve_missing_open_objections(...)`: `src/hephaestus/pantheon/coordinator.py:565-594`
- reforge canonicalization: `src/hephaestus/pantheon/coordinator.py:1501-1562`
- discharge path: `src/hephaestus/pantheon/coordinator.py:2007-2018`

But the failing test strongly suggests the successful reforge path is **still not fully reconciling addressed objections back into the authoritative ledger** before the next round.

**Impact:** Pantheon is closer, but not yet reliable enough to call production-complete.

---

## Major production gaps (not necessarily single bugs, but incomplete systems)

## 6) Observability exists mostly as infrastructure, not live instrumentation
Telemetry modules exist:
- metrics
- tracing
- events
- cost governance

But repo-wide usage is thin.

For example, `get_metrics()` is only surfaced in the metrics endpoint:
- `web/app.py:450-454`

A repo-wide search did **not** find meaningful runtime usage of metric increment/observe calls outside the telemetry module itself.

So `/api/metrics` exists, but the product does not appear to be extensively instrumented yet.

### Additional observability gap
OpenTelemetry is optional in `pyproject.toml`:
- `pyproject.toml:45-49`

But the Docker image installs only `.[web]`:
- `Dockerfile:21-22`

So the production container will not include OTLP exporter packages unless the image build changes.

**Impact:** observability is present as code, but not yet a trustworthy operating plane.

## 7) Web auth/rate-limit/spend controls are still single-process stopgaps
The web server now has real controls, but they remain in-memory process-local primitives:
- auth key: `web/app.py:38, 68-75`
- rate bucket: `web/app.py:43-65`
- global spend variable: `web/app.py:46-52`
- semaphore: `web/app.py:40-41`

Also:
- if `HEPH_API_KEY` is unset, the service is open: `web/app.py:70-71`
- `/api/metrics` is unauthenticated

These are fine for a single-process internal deployment, but not a complete production control plane.

**Impact:** safer than before, but still not robust for real multi-instance/public deployment.

## 8) Docs and product truth still drift
The repo is much better here, but still not clean.

### Lens count drift
Actual YAML lens count:
- `164` files under `src/hephaestus/lenses/library`

README is mostly standardized to `160+`, which is good:
- `README.md:24, 118, 130, 165, 327`

But PRD still contains multiple `200+` claims:
- `PRD.md:115, 297, 366, 459, 543`

### Depth semantics drift
Docs still describe `depth` mostly as pure “anti-training pressure rounds” even though the code now uses depth more broadly for exploration budget and candidate expansion:
- `README.md:281, 308, 430`
- `docs/api_reference.md:23, 38, 56, 105, 161, 707, 739`
- `docs/benchmarks.md:182, 237, 262-264`
- `docs/deepforge.md:420, 422`

### Surface parity drift
The API supports:
- `domain_hint`
- `depth`
- `exploration_mode`
- `pressure_translate_enabled`
- `pressure_search_mode`

But the shipped web UI only sends:
- `problem`
- `model`
- `candidates`

Relevant code:
- UI payload: `web/static/app.js:77-81`
- API request model: `web/app.py:119-129`

**Impact:** product story is still drifting between CLI/API/docs/UI.

## 9) CI/CD gates improved, but are not fully trustworthy yet
The repo now has serious CI scaffolding. That is good.

But there are still two issues:

### 9a) Security scan is non-blocking
`pip-audit` is effectively ignored because the step ends with `|| true`:
- `.github/workflows/ci.yml:57-59`

### 9b) Release workflow likely misuses the CI workflow as a reusable workflow
`release.yml` does:
- `uses: ./.github/workflows/ci.yml`
- `.github/workflows/release.yml:12-15`

But `ci.yml` is declared only with `push` / `pull_request` triggers and does **not** define `workflow_call`.
- `.github/workflows/ci.yml:3-7`

That looks like an invalid reusable-workflow setup.

**Impact:** CI/CD is a major improvement, but I would not trust the release gate yet without fixing those two points.

---

## Medium-risk issues

## 10) `web_fetch` is safer, but still not fully hardened
The SSRF direction is much better, but there are two remaining concerns:

### 10a) Validation/connection are not resolution-pinned
`_is_safe_url()` resolves the hostname separately from the actual `httpx` connection.
- `src/hephaestus/tools/web_tools.py:87-127`

That still leaves a DNS rebinding / TOCTOU-style gap in principle.

### 10b) Response-size limiting is post-download truncation, not streaming cap
`web_fetch()` reads `resp.text` and only truncates after content is already downloaded.
- `src/hephaestus/tools/web_tools.py:157-165`

So it limits output size, but not network/body download size.

## 11) `SQLiteRunStore` semantics are not production-grade even as fallback
Even aside from the web route misuse, the fallback store has semantic gaps:
- default path is `":memory:"`: `src/hephaestus/execution/run_store.py:419`
- duplicate detection ignores `ttl_seconds`: `src/hephaestus/execution/run_store.py:557-569`
- stale cleanup ignores `max_age_seconds`: `src/hephaestus/execution/run_store.py:571-583`

That is acceptable for dev scaffolding, but not as a serious production fallback.

## 12) Package import boundaries are still heavier than they need to be
Top-level package import still eagerly pulls in:
- SDK client
- Genesis
- DeepForge harness
- research surface

Relevant code:
- `src/hephaestus/__init__.py:29-56`

That undercuts some of the modularization progress in provider/dependency design.

This is not a launch blocker by itself, but it is still technical debt.

---

## Targeted test failures: what I think they mean

Not every targeted pytest failure is equally important.

### Mostly test/ABI drift
These are real mismatches, but not necessarily product defects:
- `tests/test_tools/test_defaults.py` assumes handlers are directly callable bare functions, but the runtime now wraps them in `ToolInvocation`
- `tests/test_tools/test_permissions.py` still expects unknown tools to classify as `dangerous`, while the code now uses explicit fail-deny via `unknown`

Those tests need updating to the new runtime contract.

### Failures that do point to real product issues
- `test_pantheon_deliberation_reforges_after_veto` → Pantheon ledger/discharge still not correct
- translator tests around schema pass / skipped candidates → translator flow changed enough that behavior still needs reconciliation
- runtime check of `web_search` via `ToolInvocation.execute(...)` → definitely a real bug
- `test_web_fetch` failures under no-DNS conditions → indicates offline/CI brittleness in the safety model, though production behavior may be okay with live DNS

---

## Product-grade verdict by subsystem

## Intelligence core
### Genesis
**Status:** materially improved, but not fully calibrated.

Positives:
- config parity restored
- pressure surfaces wired into config/harness

Remaining issues:
- depth semantics still not fully truthful
- standard vs forge semantics still need calibration

### DeepForge
**Status:** still not complete.

Positives:
- pressure path is wired into Genesis surfaces now

Blockers:
- mirror-only `max_rounds=1`
- threshold semantics still look inverted

### Translator
**Status:** improved, but not fully settled.

Positives:
- fail-fast parsing
- two-pass schema strategy is the right architecture

Blockers:
- hidden second-call cost accounting
- behavior/test contract not reconciled

### Pantheon
**Status:** closer, but not finished.

Blockers:
- live reforge/discharge defect still evident

## Tool/runtime layer
**Status:** mixed.

Positives:
- better ABI shape
- registry-driven categories/fail-deny direction
- file tools are much safer

Blockers:
- async web tools broken in real runtime path

## Web/API product
**Status:** stronger, but not full-production complete.

Positives:
- auth/rate limit/spend/concurrency primitives
- readiness endpoint
- provider health endpoint
- run endpoints exist

Blockers:
- live invention route still bypasses durable execution plane
- run APIs use ephemeral in-memory stores
- controls are not surfaced consistently in UI

## Execution plane
**Status:** mostly scaffolding.

Blockers:
- no live integration with web run path
- no dispatcher / worker loop
- not yet a real durable orchestration system

## Observability / operations
**Status:** infrastructure present, integration thin.

Blockers:
- metrics mostly unwired
- OTLP not in container build
- CI security/release gates incomplete

## Docs / product truth
**Status:** improved, still drifting.

Blockers:
- PRD still says 200+
- depth semantics docs outdated
- UI/API surface mismatch

---

## Priority fix list

## P0 — before calling the product production-ready
1. **Wire the durable run/orchestrator plane into the actual web product**
   - `/api/invent` should submit/stream a real run, not bypass orchestration
   - `/api/runs*` must use a shared persistent store, not fresh `:memory:` stores
   - add dispatcher/worker lifecycle that actually populates and manages `_active_runs`

2. **Fix async web tool handlers**
   - remove `asyncio.run(...)` from built-in handlers
   - make web tools truly async-aware in the runtime contract

3. **Finish Pantheon reforge/ledger reconciliation**
   - successful reforge must discharge canonical fatal objections in authoritative ledger state

4. **Fix DeepForge pressure semantics**
   - define whether user-facing depth counts mirror or actual pressure rounds
   - correct threshold semantics if current implementation is indeed inverted
   - stop standard mode from inheriting misleading pressure budgets

5. **Account for schema-pass cost and tokens in translation traces**
   - otherwise pressure-mode accounting is understated

## P1 — strong production hardening
6. **Turn telemetry from framework into real instrumentation**
   - stage metrics
   - provider/tool/Pantheon traces
   - queue/run gauges
   - cost counters

7. **Fix CI/release truthfulness**
   - make `pip-audit` blocking
   - fix reusable workflow configuration

8. **Clean docs and surface parity**
   - remove remaining `200+` PRD claims
   - rewrite depth docs to match actual semantics
   - decide whether advanced exploration controls belong in web UI now

9. **Harden `web_fetch` further**
   - resolution pinning / connection safety model
   - streaming size cap, not just truncation

10. **Make SQLite fallback semantics honest**
   - persistent dev path by default
   - real TTL handling
   - age-aware stale cleanup

## P2 — cleanup / maturity
11. **Reduce top-level import coupling**
12. **Tighten runtime/test contract around ToolInvocation**
13. **Review unauthenticated `/api/metrics` exposure based on deployment model**

---

## Final sign-off

**I do not sign off on this repo as fully production-ready yet.**

I *do* think it is on the right trajectory now. Compared with the earlier repo, this version is meaningfully closer to a real production system. But the hardest remaining problems are exactly the ones that matter most for a true production claim:
- durable execution is not actually live
- observability is not actually wired deeply enough
- DeepForge semantics still need correction
- Pantheon still has a live correctness defect
- one real tool runtime path is broken
- product truth still drifts across docs/UI/API

This is no longer a toy or a demo repo. But it is still in the **“strong pre-production system with important unfinished integrations”** zone, not the **“production-complete platform”** zone.
