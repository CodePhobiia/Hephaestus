# Hephaestus Production Reliability Audit

Date: 2026-04-08
Scope: production-grade invention engine audit focused on pipeline correctness, long-running reliability, Pantheon/Olympus/tool-use risks, timeout/fallback behavior, observability, and test gaps.

## Critical

### 1. Dead repo-awareness / V2 prompt path
- Severity: CRITICAL
- Files:
  - `src/hephaestus/core/genesis.py:890`
  - `src/hephaestus/core/genesis.py:913`
  - `src/hephaestus/core/genesis.py:942`
  - `src/hephaestus/core/genesis.py:1094`
- Why it matters:
  - `v2_system_prompt` is built, Olympus/transliminality/crutch-filter are injected into it, and logs claim it is active, but Stage 1 still calls `decomposer.decompose(problem)` with no system override and later stages are instantiated without that prompt.
- Likely runtime symptom:
  - Silent degradation where runs claim repo-awareness and V2 constraints are active but core stages never see them.
- Suggested fix:
  - Either thread a typed `system_override` through decompose/search/translate/verify and assert it in tests, or delete the dead path so logs stop lying.

### 2. Structured-output stages still run through anti-consensus harnesses
- Severity: CRITICAL
- Files:
  - `src/hephaestus/core/genesis.py:2435`
  - `src/hephaestus/core/genesis.py:2473`
  - `src/hephaestus/core/genesis.py:2504`
  - `src/hephaestus/core/searcher.py:556`
  - `src/hephaestus/core/verifier.py:821`
  - `src/hephaestus/pantheon/coordinator.py:342`
- Why it matters:
  - Search, verifier, and all Pantheon judge harnesses still enable `use_pruner`/`use_pressure`, but they parse raw JSON with no deterministic schema repair pass.
- Likely runtime symptom:
  - Wrong-harness behavior where JSON corruption becomes "fewer candidates," verifier fallbacks, or Pantheon being silently skipped instead of a hard failure.
- Suggested fix:
  - Disable pressure/pruner for judge/JSON stages, or add an explicit schema-constrained second pass before parsing.

### 3. Long-running valid work is still vulnerable to outer kills and stale cleanup
- Severity: CRITICAL
- Files:
  - `src/hephaestus/execution/models.py:40`
  - `src/hephaestus/execution/orchestrator.py:168`
  - `src/hephaestus/execution/run_store.py:314`
  - `web/app.py:111`
  - `web/app.py:141`
- Why it matters:
  - Execution classes still cap runs at 120/600/900s while Codex OAuth and Pantheon `_forge_json` allow 2400s; the web worker also never writes stage heartbeats back to `RunStore`, so `updated_at` can sit at `STARTING` for an hour and get cleaned as stale.
- Likely runtime symptom:
  - Hidden timeout failures, stale-run flapping, and wrong `error_stage` attribution.
- Suggested fix:
  - Align outer and inner timeout envelopes, write stage heartbeats during long calls, and label timeout source explicitly (`orchestrator`, `provider`, `bridge`, `pantheon`).

### 4. Default transport/model semantics are wrong in library and web flows
- Severity: CRITICAL
- Files:
  - `src/hephaestus/core/genesis.py:209`
  - `src/hephaestus/core/genesis.py:2328`
  - `src/hephaestus/core/genesis.py:2598`
  - `web/app.py:111`
  - `web/app.py:362`
  - `README.md:45`
- Why it matters:
  - `GenesisConfig` defaults `use_codex_cli=True`, `_build_adapters()` coerces non-GPT stage models to `gpt-5.4`, and both `Genesis.from_env()` and the web `_pipeline_fn()` inherit that default, so `opus`/`gpt5`/`both` are largely cosmetic unless the caller explicitly overrides transport.
- Likely runtime symptom:
  - Wrong-model / wrong-provider behavior and readiness probes that check API keys while runtime actually depends on Codex OAuth.
- Suggested fix:
  - Make transport explicit, default `use_codex_cli=False` outside Codex-selected flows, and surface actual adapter/model mapping in run records and reports.

## High

### 5. Agentic/Olympus assume tool-call support that most adapters do not implement
- Severity: HIGH
- Files:
  - `src/hephaestus/core/genesis.py:813`
  - `src/hephaestus/core/genesis.py:2539`
  - `src/hephaestus/deepforge/agentic.py:545`
  - `src/hephaestus/deepforge/adapters/claude_max.py:296`
  - `src/hephaestus/deepforge/adapters/codex_oauth.py:200`
- Why it matters:
  - Genesis wraps stages in `AgenticHarness` and hands Olympus the raw decompose adapter without any capability gate, but only Claude Max and Codex OAuth expose `generate_with_tools()`.
- Likely runtime symptom:
  - On OpenAI/Anthropic/OpenRouter/Claude CLI transports, repo-aware/tool-use modes fail or silently degrade via downstream exception swallowing.
- Suggested fix:
  - Gate agentic/Olympus on an explicit `FUNCTION_CALLING`/`generate_with_tools` capability check and fail closed with a clear message instead of wrapping unsupported adapters.

### 6. Web runs can finish "successfully" without any durable result
- Severity: HIGH
- Files:
  - `web/app.py:148`
  - `web/app.py:436`
  - `src/hephaestus/execution/models.py:80`
- Why it matters:
  - `_pipeline_fn()` sets `result_ref = "completed_artifact"` but never persists the `InventionReport`; SSE state lives only in `_pubsub`, so reconnecting after completion yields keepalives, not the result.
- Likely runtime symptom:
  - False success and non-replayable durable runs.
- Suggested fix:
  - Persist the final report to a real artifact path/key, store that in `result_ref`, and seed late subscribers from persisted state.

### 7. Olympus cache invalidation is weak and Stage 0 can self-poison on its own cache
- Severity: HIGH
- Files:
  - `src/hephaestus/core/olympus.py:188`
  - `src/hephaestus/core/olympus.py:357`
  - `src/hephaestus/deepforge/agentic.py:245`
  - `src/hephaestus/deepforge/agentic.py:265`
- Why it matters:
  - Olympus fingerprints only `problem + git HEAD`, so dirty/untracked repo changes do not invalidate `OLYMPUS.md`, and the tool executor does not exclude `.hephaestus`, which lets Stage 0 rediscover stale `OLYMPUS.md`/fingerprint content.
- Likely runtime symptom:
  - Stale or self-referential Olympus context that looks fresh.
- Suggested fix:
  - Include dirty state or file mtimes in the fingerprint and exclude `.hephaestus` from list/grep/read paths.

### 8. Agentic exploration can exhaust rounds without concluding, and the timeout knob is dead
- Severity: HIGH
- Files:
  - `src/hephaestus/deepforge/agentic.py:153`
  - `src/hephaestus/deepforge/agentic.py:219`
  - `src/hephaestus/deepforge/agentic.py:541`
  - `src/hephaestus/deepforge/agentic.py:593`
- Why it matters:
  - `tool_timeout_seconds` is declared but never enforced, there is no Olympus-style final no-tool wrap-up phase, and the loop returns whatever `final_text` last held even if the model never actually finished.
- Likely runtime symptom:
  - Runaway token burn or partial exploration summaries being fed into final invention prompts.
- Suggested fix:
  - Enforce per-tool timeouts, detect no-progress/repeated tool loops, and require an explicit wrap-up round before returning exploration output.

### 9. AntiTrainingPressure's threshold semantics are weaker than the config/docs claim
- Severity: HIGH
- Files:
  - `src/hephaestus/deepforge/pressure.py:175`
  - `src/hephaestus/deepforge/pressure.py:314`
  - `src/hephaestus/deepforge/pressure.py:399`
- Why it matters:
  - The field is named `structural_distance_threshold`, but acceptance uses `distance >= 1 - threshold`; with the default `0.75`, a candidate only needs `0.25` distance to pass.
- Likely runtime symptom:
  - Shallow rephrasings survive pressure and look "novel."
- Suggested fix:
  - Pick one semantic and make name, docs, and predicate match it; add a test for default-threshold behavior, not just `0.5`.

### 10. Pantheon's repair/discharge path is currently red, and verifier override leaves contradictory state
- Severity: HIGH
- Files:
  - `src/hephaestus/pantheon/coordinator.py:1667`
  - `src/hephaestus/pantheon/coordinator.py:2222`
  - `src/hephaestus/pantheon/coordinator.py:2022`
  - `src/hephaestus/pantheon/coordinator.py:2395`
  - `tests/test_pantheon/test_coordinator.py:558`
- Why it matters:
  - The current objection-ID canonicalization / discharge bookkeeping is brittle enough that `test_pantheon_deliberation_reforges_after_veto` now fails, and when verification later rejects consensus, `consensus_without_verification` is never cleared.
- Likely runtime symptom:
  - A repairable candidate can still die as `NO_OUTPUT`, and Pantheon state can claim pre-verification consensus after verifier override.
- Suggested fix:
  - Keep canonical objection IDs stable end-to-end, test alias IDs explicitly, and reset all consensus flags when verifier override occurs.

### 11. The Codex OAuth bridge/stream layer is not operationally safe on Windows or long streams
- Severity: HIGH
- Files:
  - `scripts/codex_oauth_bridge.mjs:19`
  - `scripts/codex_oauth_bridge.mjs:30`
  - `scripts/codex_oauth_bridge.mjs:81`
  - `src/hephaestus/deepforge/adapters/codex_oauth.py:169`
  - `src/hephaestus/deepforge/adapters/codex_oauth.py:320`
  - `src/hephaestus/deepforge/adapters/base.py:294`
- Why it matters:
  - The bridge hardcodes a Linux OpenClaw `node_modules` path, resolves auth via `HOME` only, and `buildModel()` uses the same 1.05M/128k limits for every model ID; on the Python side, `_bridge_call()` kills on timeout without awaiting cleanup, `generate_stream()` has no read timeout, and the adapter overrides `_reset_cancel()` incorrectly while never checking `is_cancelled`.
- Likely runtime symptom:
  - Windows/portable failures, leaked subprocesses, and pruner cancellations that do nothing.
- Suggested fix:
  - Make bridge discovery OS-aware, model-aware, and cleanup-safe; add stream read timeouts and honor the base cancel contract.

### 12. Per-stage token budgets are dead and concurrency fanout is uncapped
- Severity: HIGH
- Files:
  - `src/hephaestus/core/genesis.py:2419`
  - `src/hephaestus/core/searcher.py:378`
  - `src/hephaestus/core/searcher.py:556`
  - `src/hephaestus/core/scorer.py:455`
  - `src/hephaestus/core/translator.py:797`
  - `src/hephaestus/core/verifier.py:401`
- Why it matters:
  - Genesis sets `max_tokens_*` into harness configs, then search/scoring/translation/verification override them everywhere with hardcoded `16000`, and several stages fan out with raw `asyncio.gather()` over expensive model calls.
- Likely runtime symptom:
  - Runaway token burn, rate-limit spikes, and config changes that appear accepted but do nothing.
- Suggested fix:
  - Remove the hardcoded `16000`s, use harness-configured budgets, and add per-stage semaphores.

### 13. Search and verification degrade silently and can still produce a top invention
- Severity: HIGH
- Files:
  - `src/hephaestus/core/searcher.py:378`
  - `src/hephaestus/core/verifier.py:401`
  - `src/hephaestus/core/verifier.py:1285`
  - `src/hephaestus/core/genesis.py:1887`
  - `src/hephaestus/core/genesis.py:457`
- Why it matters:
  - Search drops broken lenses and keeps going; verifier converts exceptions into low-confidence fallback inventions; `InventionReport.top_invention` then blindly takes element 0.
- Likely runtime symptom:
  - False success where the report completes with a fallback-verified "winner" even though verification actually broke.
- Suggested fix:
  - Track degraded stage status explicitly and refuse `COMPLETE` unless at least one non-fallback verified invention exists.

## Medium

### 14. JSON extraction outside Pantheon is still brittle
- Severity: MEDIUM
- Files:
  - `src/hephaestus/core/decomposer.py:319`
  - `src/hephaestus/core/searcher.py:690`
  - `src/hephaestus/core/scorer.py:576`
  - `src/hephaestus/core/scorer.py:597`
  - `src/hephaestus/core/verifier.py:1278`
- Why it matters:
  - These stages still use greedy `re.search(r"\\{.*\\}")`, unlike Pantheon's balanced-brace extractor, so multiple JSON objects or brace-heavy prose can be misparsed.
- Likely runtime symptom:
  - Parser defaults/fallbacks instead of clean structured-output errors.
- Suggested fix:
  - Reuse Pantheon's balanced extractor or a real schema parser everywhere.

### 15. Docs/tests/readiness probes are drifted from the actual product
- Severity: MEDIUM
- Files:
  - `README.md:18`
  - `README.md:45`
  - `README.md:266`
  - `web/app.py:365`
  - `tests/test_core/test_genesis.py:760`
- Why it matters:
  - README still describes a 45s/$1.25 Claude+GPT default; readiness only checks API keys, not the default Codex transport; one Genesis default test already expects `use_branchgenome_v1=False` while code ships `True`.
- Likely runtime symptom:
  - Operators and CI validate the wrong thing.
- Suggested fix:
  - Update docs/tests/probes from the selected transport/config path, not a historical implementation.

## Coverage Gaps

- There are no tests for `build_olympus()` cache invalidation, `.hephaestus` exclusion, or proving Olympus/V2 text actually reaches stage prompts.
- There is no integration test for `web.app._pipeline_fn()` that covers model preset selection, run-store stage updates, artifact persistence, and late-subscriber replay.
- There is no protection test asserting JSON-only stages are never wrapped in pressure/pruner/agentic harnesses.
- There is no long-run test for Codex OAuth bridge streaming with cancellation, stalled stdout, or subprocess timeout cleanup.
- There is no orchestrator test that simulates a >1h stage with cleanup_stale and verifies no false failure/completion flapping.

## Validation

- `pytest tests/test_core/test_genesis.py -k "genesis_config_defaults or build_harnesses_uses_dedicated_pantheon_models" -q`
  - Result: 1 failed, 1 passed
  - Failure: `GenesisConfig.use_branchgenome_v1` drift vs test expectation.
- `pytest tests/test_pantheon/test_coordinator.py -q`
  - Result: 1 failed, 8 passed
  - Failure: `test_pantheon_deliberation_reforges_after_veto`.
- `pytest tests/test_deepforge/test_codex_oauth.py -q`
  - Result: 1 failed, 7 passed
  - Failure is Windows test drift (`/usr/bin/node` fixture path), which also confirms the test suite is not transport-portable.
- `pytest tests/test_execution/test_models.py -q`
  - Result: 12 passed.
- No long-run real-bridge / GPT-5.4 xhigh integration run was executed.

## Top 5 Things To Fix Next

1. Make transport explicit and correct: stop defaulting web/from_env/library flows into Codex OAuth unless requested.
2. Align timeout, heartbeat, and stale-cleanup behavior across orchestrator, run store, bridge, and Pantheon.
3. Remove pressure/pruner from JSON-producing judge stages or add deterministic schema passes before parsing.
4. Wire Olympus/V2/transliminality prompt state into the stages that are supposed to consume it, or delete the dead path.
5. Persist final run artifacts and replayable state for web/durable runs.

## Top 5 Things Most Likely To Bite Us In Production

1. Web/API runs dying at the outer 120/600/900s limits while inner Codex/Pantheon work is still healthy.
2. "Successful" completed runs with no durable artifact and no way to retrieve the invention afterward.
3. Silent Pantheon/search/verifier degradation caused by structured JSON being forced through novelty harnesses.
4. Wrong-model routing where `opus`/`both` requests end up as Codex OAuth `gpt-5.4` anyway.
5. Olympus injecting stale or self-referential repo context because cache invalidation is tied only to `git HEAD`.

## Test Plan To Validate The Fixes

1. Add a fake-adapter integration test that captures actual system prompts and proves Olympus/V2/transliminality text reaches decompose/search/translate/verify.
2. Add transport-selection tests for `Genesis.from_env()`, CLI config builders, and `web.app._pipeline_fn()` that assert the real adapter class and model name used.
3. Add orchestrator lifecycle tests that simulate long stages, stage heartbeats, stale cleanup, cancellation, and timeout-source labeling.
4. Add Pantheon integration tests for malformed JSON, timeout in `_forge_json`, agentic/pressure contamination prevention, and successful objection discharge with canonical and alias IDs.
5. Add Codex OAuth subprocess tests on Windows and Linux for module discovery, auth-path resolution, streaming cancellation, stalled stdout timeout, and killed-process cleanup.
