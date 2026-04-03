# Hephaestus Launch Audit — Production Hardening Review

Date: 2026-04-03  
Repo audited: `Hephaestus-main`

## Executive verdict

Hephaestus has strong architectural ambition and a lot of working surface area, but it is **not launch-ready yet** for a public production release.

The highest-risk blockers are:

1. **Unsafe calculator tool permits code execution**
2. **Workspace/file tool layer is broken and partially missing**
3. **Web / CLI / SDK contract drift: `depth`, `model`, and `domain` are exposed but not consistently wired**
4. **Pantheon mode has real correctness bugs**
5. **Translator can silently convert invalid model output into fake-looking successful inventions**
6. **Tool-permission defaults are fail-open for unknown tools**
7. **The web server lacks auth, rate limiting, cost controls, and disconnect-aware cancellation**

That said, the codebase is not a wreck. It compiled cleanly, and large parts of the test surface passed once provider-only optional imports were stubbed. The product has a real foundation; it needs a focused hardening pass before launch.

## What I verified

- `python -m compileall -q src tests web` passed.
- The repo has a substantial codebase across CLI, SDK, web, DeepForge, Genesis, Pantheon, workspace, memory, prompts, output, research.
- With lightweight stubs for unavailable provider/runtime dependencies, I directly ran **761 passing tests** across large portions of the suite (CLI, session, output, config, analytics, memory, agent, novelty, export, prompts, SDK, etc.).
- With those same stubs, the full suite still exposed structural breakage and logic defects in:
  - `tests/test_tools/test_defaults.py`
  - `tests/test_tools/test_file_ops.py`
  - `tests/test_workspace/test_mode.py`
  - `tests/test_core/test_translator.py::TestSolutionTranslator::test_bad_json_raises_translation_error`
  - `tests/test_pantheon/test_coordinator.py::test_pantheon_deliberation_reforges_after_veto`
  - `tests/test_pantheon/test_coordinator.py::test_pantheon_qualified_consensus_preserves_advisory_caveat`

## Severity scale

- **P0** — launch blocker / security-critical
- **P1** — major correctness / trust / production reliability issue
- **P2** — important hardening gap
- **P3** — cleanup / polish / drift

---

## P0 — Launch blockers

### 1) Calculator tool is remote-code-execution capable
**Files:** `src/hephaestus/tools/defaults.py:47-57`, `src/hephaestus/tools/defaults.py:288-301`

`_safe_eval()` uses raw `eval()`:

```python
result = eval(expression, {"__builtins__": allowed_builtins}, {})
```

That is not safe. Even with reduced builtins, Python object-graph traversal can recover dangerous objects. I verified code execution locally with an expression that reached `subprocess.Popen` and produced `pwned\n`.

**Impact**
- Any path exposing the calculator tool to user/model input becomes an RCE risk.
- This is an immediate no-launch issue.

**Fix**
- Replace with a strict AST evaluator that only allows numeric literals, arithmetic ops, unary ops, and a small allowlist of math functions.
- Reject attribute access, comprehensions, lambdas, subscripting, calls outside allowlist, names outside allowlist.
- Add negative tests for sandbox escapes.

---

### 2) File tool layer is broken at import time and workspace mode is not production-usable
**Files:**  
- `src/hephaestus/tools/defaults.py:11-17`
- `src/hephaestus/workspace/mode.py:173-179`
- `src/hephaestus/tools/file_ops.py:1-47`

`defaults.py` and `workspace/mode.py` import `grep_search` and `search_files`, but `file_ops.py` does not define them at all.

This breaks:
- default registry import
- workspace mode creation
- tool-related tests and imports

Observed failures:
- `tests/test_tools/test_defaults.py` import error
- `tests/test_tools/test_file_ops.py` import error
- `tests/test_workspace/test_mode.py` fails because workspace registry imports missing file ops

**Impact**
- Core agent/workspace tooling is partially nonfunctional
- “codebase-aware” / workspace experience is not launch-ready

**Fix**
- Implement `search_files()` and `grep_search()` or remove all references to them until complete.
- Reconcile file tool API with tests and handlers.
- Add smoke tests that instantiate the default registry and workspace mode in CI.

---

### 3) Workspace path boundary check is vulnerable to prefix bypass
**File:** `src/hephaestus/tools/file_ops.py:12-19`

Current check:

```python
if _workspace_root is not None and not str(resolved).startswith(str(_workspace_root)):
```

This is not a safe workspace boundary check. A sibling path like `/tmp/ws2` can pass when the workspace is `/tmp/ws`.

**Impact**
- Path traversal / workspace escape
- Violates expected permission boundary

**Fix**
- Use `resolved.is_relative_to(_workspace_root)` on Python 3.9+ or compare `resolved.parents`.
- Normalize symlinks carefully.
- Add adversarial tests for sibling-prefix bypass and symlink escape.

---

### 4) Unknown tools default to `safe` in permission policy
**File:** `src/hephaestus/tools/permissions.py:53-61`

`_tool_category()` returns `"safe"` for anything not in explicit allowlists.

**Impact**
- Newly registered tools become implicitly allowed if classification is forgotten.
- This is especially dangerous for MCP/external tools and future expansion.

**Fix**
- Default-deny unknown tools.
- Require explicit category registration.
- Fail startup if any registered tool lacks a recognized category.

---

## P1 — Major correctness / trust issues

### 5) Web UI exposes `depth` and `model`, but the server does not wire them into `GenesisConfig`
**Files:**  
- `web/templates/index.html:61-90`
- `web/static/app.js:85-90`
- `web/app.py:232-267`

The UI collects:
- `depth`
- `model`
- `candidates`

The server only passes:
- `num_candidates`
- `num_translations`

It does **not** pass `depth` or `model` into `GenesisConfig`.

**Impact**
- Product trust issue: the UI promises control that the backend ignores.
- Users think they are selecting more novelty / cost / model routing when they are not.

**Fix**
- Add explicit server-side wiring from request → model preset → `GenesisConfig`.
- Either implement true `depth` in Genesis or remove the control from web/CLI/SDK until it works.
- Add integration tests validating that request parameters change the effective pipeline config.

---

### 6) CLI and SDK also expose `depth` / `domain`, but Genesis path ignores them
**Files:**  
- `src/hephaestus/sdk/client.py:116-119`
- `src/hephaestus/sdk/client.py:572-586`
- `src/hephaestus/cli/main.py:942-1105`
- `src/hephaestus/cli/main.py:932-933`

`Hephaestus` stores `self._depth` and `self._domain`, but `_build_genesis()` does not pass either into `GenesisConfig`.

CLI `_build_genesis_config()` accepts `depth` and `domain`, but neither affects the returned `GenesisConfig`.

Also `_bridge_report()` hardcodes `depth=3`.

**Impact**
- Public API contract drift
- Docs/flags misrepresent actual behavior
- Telemetry/reporting can misstate run configuration

**Fix**
- Thread `depth` and `domain` through end-to-end or remove them from public interfaces until done.
- Fix report bridge to reflect actual runtime depth.
- Add contract tests for CLI, SDK, and web parity.

---

### 7) DeepForge anti-training pressure is effectively disabled in the Genesis pipeline
**Files:**  
- `src/hephaestus/core/genesis.py:1973-2084`
- `src/hephaestus/core/translator.py:675-683`
- `src/hephaestus/core/decomposer.py:25-27`

Every stage harness in `Genesis._build_harnesses()` is created with `use_pressure=False`. Translation also explicitly sets:

```python
use_pressure=False, # Pressure not needed — interference is active
```

This conflicts with product messaging around pressure depth and anti-training pressure being central to novelty.

**Impact**
- Core value proposition is overstated relative to implementation
- `depth` becomes mostly cosmetic outside raw DeepForge mode

**Fix**
- Decide whether Genesis is meant to use pressure in some or all stages.
- If yes: wire it cleanly, benchmark it, and expose it honestly.
- If no: remove or soften claims across UI/docs/CLI.

---

### 8) Translator silently converts invalid model output into a fake successful translation
**File:** `src/hephaestus/core/translator.py:995-1042`

If no JSON is found, `_parse_translation()` logs a warning and returns defaults like:
- `"Cross-Domain Invention"`
- `"Architecture generation failed"`
- empty mapping

Observed failing test:
- `tests/test_core/test_translator.py::TestSolutionTranslator::test_bad_json_raises_translation_error`
- result was **1 bogus translation** instead of skipping the failed candidate

**Impact**
- False positives
- Corrupt quality metrics
- Can show users “successful” inventions that are really parser fallbacks

**Fix**
- Treat no-JSON / invalid JSON as a hard translation failure.
- Retry or skip candidate.
- Emit structured error metadata so the pipeline can reason about failure rates.

---

### 9) Pantheon JSON extraction breaks valid nested JSON
**File:** `src/hephaestus/pantheon/coordinator.py:86-97`

`_json_block()` uses:

```python
match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
```

The non-greedy regex stops at the first closing brace, which truncates nested JSON payloads.

Observed failing test:
- `tests/test_pantheon/test_coordinator.py::test_pantheon_qualified_consensus_preserves_advisory_caveat`

**Impact**
- Pantheon can fail on valid model outputs
- Advisory objections / nested structures are brittle

**Fix**
- Stop using regex for nested JSON extraction.
- Use a balanced-brace parser or attempt full-string parse first, then fenced-block extraction.

---

### 10) Pantheon reforge logic is too brittle about objection IDs
**File:** `src/hephaestus/pantheon/coordinator.py:1414-1482`

`_reforge_branch()` trusts `metadata["addressed_objection_ids"]` from the model output. If the model echoes a non-exact alias instead of the actual targeted objection ID, the original objection remains open and the candidate can fail closed.

Observed failing test:
- `tests/test_pantheon/test_coordinator.py::test_pantheon_deliberation_reforges_after_veto`

**Impact**
- Good repair attempts can be discarded because the model did not reproduce opaque IDs exactly.
- Pantheon mode becomes brittle and lower-yield than intended.

**Fix**
- Default to targeted objection IDs unless the model response can be reconciled to them.
- Use semantic matching / intersection / alias resolution rather than exact opaque-ID dependence.

---

### 11) MCP integration is incomplete: discovered tools register with `handler=None`
**Files:**  
- `src/hephaestus/tools/mcp/manager.py:32-39`
- `src/hephaestus/agent/runtime.py:249-269`

`MCPManager.add_server()` registers discovered tools in the registry with `handler=None`. The runtime explicitly errors when a tool has no handler.

**Impact**
- MCP may appear integrated but cannot be executed through the normal runtime path.
- This is a sharp edge for launch messaging around extensibility.

**Fix**
- Register actual call-through handlers that invoke `MCPManager.call()`.
- Add end-to-end MCP smoke tests.

---

### 12) MCP stdio client is not robust enough for production protocol behavior
**File:** `src/hephaestus/tools/mcp/client.py:56-158`

Problems:
- Reads a single line from stdout and assumes that is the matching response
- No handling for notifications or out-of-order responses
- No stderr draining/consumption strategy
- `env=self.config.env or None` replaces environment instead of merging with `os.environ`

**Impact**
- Protocol deadlocks / misreads / startup failures with real MCP servers
- PATH-dependent tools may fail to start

**Fix**
- Merge env with `os.environ`
- Maintain a response pump keyed by request id
- Drain stderr in background
- Support notifications and non-matching frames

---

## P2 — Important hardening gaps

### 13) File ops contract is inconsistent with tests and handlers
**Files:**  
- `src/hephaestus/tools/file_ops.py:22-47`
- `src/hephaestus/tools/defaults.py:63-97`
- `tests/test_tools/test_file_ops.py:18-152`

Problems:
- `list_directory()` returns `list[str]`, but handlers/tests expect formatted text
- handler passes `max_entries`, but `list_directory()` does not accept it
- tests expect `write_file(..., workspace_root=...)`, but function has no such parameter
- tests expect friendly error strings, but current code raises exceptions
- return wording mismatches (`"Written"` vs expected `"Wrote"`)

**Impact**
- Tooling UX and contracts are unstable
- likely to cause downstream breakage even after missing functions are restored

**Fix**
- Define a stable tool contract:
  - exceptions vs error strings
  - return type text vs structured object
  - workspace root handling
  - max entries / truncation behavior
- Update code and tests together.

---

### 14) Append mode in `write_file()` is silently broken
**File:** `src/hephaestus/tools/file_ops.py:33-39`

The function computes:

```python
mode = "a" if append else "w"
```

but then ignores it and always uses `write_text()`.

**Impact**
- Data loss / false confidence in append semantics

**Fix**
- Open file explicitly with the chosen mode.
- Add append behavior tests.

---

### 15) Web tools are labeled `safe` despite being operationally dangerous
**Files:**  
- `src/hephaestus/tools/defaults.py:245-285`
- `src/hephaestus/tools/permissions.py:37-42`

`web_search` and `web_fetch` are registered as `category="safe"` in the default registry, while the permission policy separately categorizes them as dangerous by name.

**Impact**
- Inconsistent policy model
- Future code may trust registry metadata and accidentally weaken enforcement

**Fix**
- Use one source of truth for tool risk classification.
- Ensure registry category and permission policy agree.

---

### 16) `web_fetch()` has no SSRF protections
**File:** `src/hephaestus/tools/web_tools.py:58-77`

It follows arbitrary URLs and redirects with no local-address or metadata-IP protections.

**Impact**
- SSRF risk if exposed in hosted agent/server contexts

**Fix**
- Block private IP ranges, localhost, link-local, metadata addresses, and file-like schemes.
- Resolve DNS and validate final targets after redirects.

---

### 17) Import-time coupling makes the package fragile and hard to operate modularly
**Files:**  
- `src/hephaestus/__init__.py:29-56`
- `src/hephaestus/sdk/client.py:46-51`
- `src/hephaestus/core/genesis.py:35-43`
- `src/hephaestus/deepforge/adapters/__init__.py:16-20`
- `src/hephaestus/deepforge/pressure.py:34-35`

Importing light modules can cascade into provider SDK / embedding model imports.

**Observed behavior**
- Without stubs, test collection originally broke on missing optional dependencies.
- This is a packaging/modularity smell even if production installs all deps.

**Impact**
- Worse startup characteristics
- Harder testing
- Harder partial-use adoption
- Optional features are not truly optional

**Fix**
- Move provider/embedding imports behind feature boundaries and lazy initialization.
- Avoid heavyweight imports in package `__init__`.
- Split optional extras cleanly.

---

### 18) Web server lacks production access controls and cost guards
**File:** `web/app.py:232-313`

Current `/api/invent` has:
- no auth
- no rate limiting
- no per-IP / per-user quotas
- no API key for clients
- no request budgeting
- no queue/backpressure
- no tenant isolation

**Impact**
- Public endpoint can be abused for direct cost burn and provider quota exhaustion

**Fix**
- Add authentication
- Add rate limits and concurrency quotas
- Add spend budgets / circuit breakers
- Add admission control and job cancellation

---

### 19) SSE path is not disconnect-aware
**File:** `web/app.py:257-305`

The event generator does not use `Request` for `is_disconnected()` checks and does not cancel work when clients go away.

**Impact**
- Burned tokens/cost after client disconnects
- orphaned long-running jobs

**Fix**
- Pass `Request` into the generator and abort on disconnect.
- Propagate cancellation to pipeline tasks.

---

### 20) Health endpoint is too shallow for production
**File:** `web/app.py:208-218`

`/api/health` only reports process liveness and whether environment variables exist.

**Impact**
- False positives in orchestration/monitoring
- does not prove provider readiness, lens availability, or background dependencies

**Fix**
- Add readiness endpoint separate from liveness.
- Verify critical startup state:
  - config load
  - lens library load
  - model/provider configuration
  - optional dependency availability

---

### 21) Docker image is serviceable but not hardened
**Files:**  
- `Dockerfile:4-38`
- `docker-compose.yml:1-34`
- `.env.docker:1-3`

Issues:
- single-stage build
- `build-essential`, `curl`, `git` remain in runtime image
- editable install in production image
- no `.dockerignore`
- env template kept as `.env.docker` rather than safer example naming
- compose mounts lens library into source tree

**Impact**
- larger attack surface
- less reproducible builds
- more fragile deployment model

**Fix**
- Use multi-stage build
- install wheels into slim runtime stage
- add `.dockerignore`
- rename env template to `.env.example`
- mount data outside application code path if persistence is needed

---

## P3 — Drift / cleanup / product credibility

### 22) Product/docs claims are inconsistent with the actual repo state
**Files:**  
- `README.md:24, 130, 165, 327`
- `PRD.md:13, 69, 115, 366, 543, 639`
- `docs/architecture.md:48, 297`
- `web/templates/index.html:203`

Examples:
- README says **80+** lenses
- PRD says **200+**
- architecture doc says **51**
- actual repo currently contains **164 YAML lens files**
- PRD says every output is “provably novel”
- footer says “Every output structurally novel”

**Impact**
- Credibility risk at launch
- Users and contributors cannot tell what is true today

**Fix**
- Replace hardcoded counts with generated counts or looser language.
- Tone down unverifiable absolutes.
- Sync docs, tests, and product copy from the same source of truth.

---

### 23) Web model label is misleading
**File:** `web/templates/index.html:85-90`

The option value is `"gpt5"` but the label shown is `"GPT-4o only"`.

**Impact**
- User confusion
- product trust hit

**Fix**
- Align label, internal preset name, and actual routing behavior.

---

### 24) Report bridge hardcodes depth to 3
**File:** `src/hephaestus/cli/main.py:931-933`

**Impact**
- Exported reports can misstate how a run was configured

**Fix**
- Carry actual runtime depth into the formatter report.

---

## What is solid

There is real strength here too:

- Large portions of the codebase compiled cleanly.
- The CLI/test surface is much larger and more mature than a toy prototype.
- Output/session/config/export layers are relatively well-covered.
- The project already has substantive architecture for:
  - multi-stage invention pipeline
  - lenses
  - session/memory
  - Pantheon deliberation
  - output formatting
  - research/perplexity integration

This is not a rewrite situation. It is a hardening and truth-in-contract situation.

---

## Recommended hardening sequence

### Phase 0 — before any public launch
1. Replace calculator `eval` with AST evaluator
2. Fix file tool layer:
   - implement missing functions
   - fix path boundary enforcement
   - fix append behavior
   - reconcile return contracts
3. Default-deny unknown tools
4. Wire or remove `depth`, `model`, `domain` from all public interfaces
5. Fix translator invalid-output handling
6. Fix Pantheon JSON parsing and reforge objection resolution
7. Lock down web endpoint with auth + rate limits + spend controls

### Phase 1 — first production candidate
1. Add request cancellation / disconnect handling
2. Add readiness/liveness split
3. Add structured logs and per-run correlation IDs
4. Add queue/backpressure / concurrency control
5. Add CI gates:
   - smoke import test
   - default registry creation
   - workspace mode creation
   - targeted security tests

### Phase 2 — scale/reliability
1. Refactor lazy imports / optional dependency boundaries
2. Finish MCP runtime bridge
3. Harden web fetch against SSRF
4. Multi-stage Docker build + slimmer runtime
5. Sync docs/tests/marketing copy from code reality

---

## Launch gate recommendation

**Do not launch publicly yet.**

A realistic gate to green is:

- all P0 fixed
- all P1 fixed
- production web path protected by auth/rate-limits/budgeting
- CI includes regression tests for each issue above
- public copy updated to reflect what the product actually does today

Once that’s done, Hephaestus is much closer to a credible launch: not just impressive in demos, but trustworthy in production.
