# Pantheon Multi-Agent & Research Subsystems — Security & Quality Audit

**Audited:** 2026-04-03  
**Scope:** pantheon/, deepforge/harness.py + adapters/, research/perplexity.py, lenses/cards.py + loader.py + selector.py + state.py, core/json_utils.py, branchgenome/models.py (DAG references)  
**Total files read:** 20+

---

## CRITICAL

---

### CRIT-1 — Sequential agent calls in Pantheon (no concurrency)

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~690–730 (`deliberate()`), ~550–600 (`screen_translations()`)

```python
athena_vote = await self._athena_review(...)
hermes_vote = await self._hermes_review(...)
apollo_audit, apollo_vote = await self._apollo_audit(...)
```

**Problem:** All three council agents are called sequentially with individual `await` calls. With `max_rounds=4` and `max_survivors_to_council=2`, a worst-case run awaits `2 candidates × 4 rounds × 3 agents = 24` sequential LLM calls plus up to `3 reforge branches × 2 candidates = 6` more calls — all blocking one after another. Screening (`screen_translations`) has the same issue with Hermes + Apollo called back-to-back per candidate.

**Impact:** 10–100× slower than it needs to be. With 120s timeouts per call, a worst-case pipeline can block for **30+ minutes** when all three agents should run in parallel.

**Suggested fix:**
```python
athena_vote, hermes_vote, (apollo_audit, apollo_vote) = await asyncio.gather(
    self._athena_review(...),
    self._hermes_review(...),
    self._apollo_audit_coro(...),
)
```
Split `_apollo_audit` into a coroutine that returns the tuple; wrap in `asyncio.gather`. Add a shared `PantheonAccounting` lock or use `asyncio.Lock` if mutating accounting from concurrent tasks.

---

### CRIT-2 — `_resolve_missing_open_objections()` silently auto-resolves blocking objections

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~340–365

```python
def _resolve_missing_open_objections(self, *, state, candidate_id, round_index, seen_ids, stage):
    for objection in state.objection_ledger:
        if objection.candidate_id != candidate_id or objection.status != "OPEN":
            continue
        if objection.objection_id in seen_ids:
            continue
        objection.status = "RESOLVED"   # <-- silently resolved
        ...
```

**Problem:** Any open objection NOT re-raised by an agent in a given round is marked `RESOLVED` — even if it was never addressed, even `FATAL` ones. This means:
- Round 1: Apollo raises a FATAL truth objection.
- Round 2: Apollo forgets to re-raise it (LLM non-determinism, prompt got shorter, etc.).
- `_resolve_missing_open_objections()` marks the fatal objection `RESOLVED`.
- `_determine_outcome_tier()` sees no blocking issues → returns `UNANIMOUS_CONSENSUS`.

A single round of LLM forgetfulness can cause a FATAL objection to silently disappear, producing false consensus on an invalid invention.

**Suggested fix:** Do NOT auto-resolve FATAL objections. At minimum:
```python
if objection.severity == "FATAL":
    continue  # never auto-resolve fatal objections
```
Or require explicit discharge — only resolve when an agent explicitly lists it in a `discharge_ids` list.

---

## HIGH

---

### HIGH-1 — No timeout on individual `_forge_json` calls

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~210–225 (`_forge_json`)

```python
async def _forge_json(self, harness, prompt, *, system, accounting, agent):
    t_start = time.monotonic()
    result = await harness.forge(prompt, system=system)
    ...
```

**Problem:** No timeout is enforced here. `HarnessConfig.timeout_seconds` defaults to 120s but it only applies in `_forge_with_pruner` when `cfg.timeout_seconds != 120.0` — the default path never applies a timeout. If one Pantheon agent hangs (e.g., slow model, dangling stream), the entire pipeline blocks indefinitely.

**Suggested fix:**
```python
result = await asyncio.wait_for(
    harness.forge(prompt, system=system),
    timeout=300.0,  # or configurable per-agent
)
```

---

### HIGH-2 — `assert` statements in production path in `deliberate()`

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~670–680

```python
assert canon is not None
assert dossier is not None
```

**Problem:** Python's `assert` statements are silently removed when the interpreter runs with `-O` (optimized mode). In production deployments that use `-O` for performance, these checks disappear entirely, and `canon = None` / `dossier = None` would crash later with an `AttributeError` inside prompt formatting, producing an unreadable traceback with no context.

**Suggested fix:**
```python
if canon is None or dossier is None:
    raise PantheonError("prepare_pipeline() must be called before deliberate()")
```

---

### HIGH-3 — `_json_block` regex `r"\{.*\}"` greedily spans multiple JSON objects

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~64–73; also `core/json_utils.py` lines ~102–103

```python
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
# and in coordinator.py:
match = re.search(r"\{.*\}", cleaned, re.DOTALL)
```

**Problem:** With `re.DOTALL`, the greedy `.*` matches from the first `{` to the **last** `}` in the string. If an LLM produces:
```
Here is the result: {"key": "val"} and also {"note": "extra"}
```
The regex captures `{"key": "val"} and also {"note": "extra"}` — the full span — which is invalid JSON and will fail to parse. The fix attempt (escape-fixing) also operates on this malformed span.

More subtly, if the model embeds a JSON example inside a string value:
```json
{"answer": "use {\"k\": 1} as a template"}
```
the greedy match may not be an issue in that case since the outer braces bound it, but nested `{}` in prose after the JSON block is a real failure mode.

**Suggested fix:** Use a balanced-bracket extractor or at minimum `r"\{[^{}]*((?:\{[^{}]*\})[^{}]*)*\}"` (one level of nesting). For robust parsing, use `json.JSONDecoder().raw_decode()` to find the first complete object.

---

### HIGH-4 — `loads_lenient` silent empty-dict return masks parse failures in Perplexity

**File:** `src/hephaestus/research/perplexity.py`, lines ~365–380 (`_extract_json`)

```python
def _extract_json(text: str) -> dict[str, Any]:
    ...
    try:
        payload = loads_lenient(match.group(), default={}, label="perplexity")
    except json.JSONDecodeError as exc:
        raise ResearchError(f"Could not parse Perplexity JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchError("Perplexity output was not a JSON object")
    return payload
```

**Problem:** `loads_lenient` **never raises** `json.JSONDecodeError` — it catches all exceptions internally and returns `default` (here: `{}`). So `except json.JSONDecodeError` is dead code. When parsing fails completely, `payload = {}` passes the `isinstance(payload, dict)` check and `_extract_json` returns `{}`. The caller then silently builds empty `BaselineDossier`, `ExternalGroundingReport`, etc. with no fields set.

This means a completely failed Perplexity response (bad JSON, truncated, model error) results in empty research data being used as if it were valid — poisoning the Genesis pipeline with empty groundings.

**Suggested fix:**
```python
payload = loads_lenient(match.group(), default=None, label="perplexity")
if not isinstance(payload, dict) or not payload:
    raise ResearchError(f"Could not parse Perplexity JSON from: {text[:200]}")
```
Use `default=None` not `{}` to distinguish "parsed empty object" from "parse failure".

---

### HIGH-5 — `ClaudeMaxAdapter.generate_stream()` doesn't handle `GenerationKilled`

**File:** `src/hephaestus/deepforge/adapters/claude_max.py`, lines ~290–320

```python
async def generate_stream(self, ...):
    self._reset_cancel()
    accumulated = prefill or ""
    async with self._client.messages.stream(...) as stream:
        async for text in stream.text_stream:
            if self.is_cancelled:
                break   # <-- silently exits loop
            accumulated += text
            yield StreamChunk(delta=text, accumulated=accumulated)

    msg = await stream.get_final_message()  # <-- called on incomplete stream
```

**Problem:** When `cancel_stream()` is called mid-stream, the loop `break`s but then `await stream.get_final_message()` is called on a stream that was abandoned mid-way. This can hang, raise an SDK exception, or silently return 0 tokens. The `GenerationKilled` exception is never raised, so the harness/pruner never knows the stream was killed — it just gets a partial accumulated result with no error.

Compare with `AnthropicAdapter.generate_stream()` which correctly raises `GenerationKilled` on cancel and skips the final message call.

**Suggested fix:**
```python
async for text in stream.text_stream:
    if self.is_cancelled:
        raise GenerationKilled("Stream cancelled", partial_output=accumulated)
    ...
```

---

### HIGH-6 — `CodexOAuthAdapter.generate_stream()` missing `_reset_cancel()`

**File:** `src/hephaestus/deepforge/adapters/codex_oauth.py`, ~line 195 (generate_stream)

```python
async def generate_stream(self, prompt, ...):
    proc = await asyncio.create_subprocess_exec(...)  # <-- no _reset_cancel()
```

**Problem:** `_reset_cancel()` is not called at the start of `generate_stream()`. If a previous call set the cancel event (e.g., via `cancel_stream()`), the new streaming call starts with the cancel flag already set. The loop processes its first event and either immediately cancels or just falls through depending on where `is_cancelled` is checked.

**Suggested fix:** Add `self._reset_cancel()` as the first line of `generate_stream()`.

---

### HIGH-7 — Fuzzy objection deduplication can suppress distinct real objections

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~310–330 (`_find_existing_objection`)

```python
def _find_existing_objection(...):
    ...
    score = _similarity_score(objection, statement, required_change, closure_test)
    ...
    return best_match if best_score >= 0.72 else None
```

**Problem:** Two genuinely different objections from the same agent about the same candidate can be merged if their keyword overlap exceeds the 0.72 Jaccard threshold. For example:
- Objection A: "The mechanism requires a distributed hash table which introduces O(n) network overhead"
- Objection B: "The mechanism requires a distributed consensus protocol which introduces O(n²) message complexity"

Both contain keywords: `mechanism`, `requires`, `distributed`, `introduces` — Jaccard similarity could exceed 0.72 even though they're entirely different issues. When merged, the `severity` is escalated to the strongest, but the `required_change` is silently replaced by whichever is longer. A fix that addresses only one issue would be judged as resolving both.

**Suggested fix:** Lower threshold to 0.85+ or require exact `issue_type` + `severity` match before considering any merge. Add explicit `opened_by` agent validation.

---

## MEDIUM

---

### MED-1 — `consensus_without_verification = True` always set in `_finalize_success()`

**File:** `src/hephaestus/pantheon/coordinator.py`, line ~860

```python
state.consensus_without_verification = True
```

**Problem:** This flag is set unconditionally in `_finalize_success()` regardless of outcome tier. `UNANIMOUS_CONSENSUS` is set to `consensus_without_verification = True` — which is semantically incorrect. The flag should only be `True` for `QUALIFIED_CONSENSUS` or `SALVAGED_CONSENSUS` where unresolved issues were waived. Setting it for unanimous clean consensus misleads downstream code.

**Suggested fix:**
```python
state.consensus_without_verification = outcome_tier in {"QUALIFIED_CONSENSUS", "SALVAGED_CONSENSUS"}
```

---

### MED-2 — `candidate_ids` mismatch risk in `deliberate()` when `survivor_candidate_ids` is short

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~660–670

```python
candidate_ids = list(current_state.survivor_candidate_ids)
if len(candidate_ids) < len(survivors):
    candidate_ids = [
        self._candidate_id(index, translation)
        for index, translation in enumerate(survivors, start=1)
    ]
```

**Problem:** If `survivor_candidate_ids` is shorter than `survivors` (e.g., 1 ID vs 2 survivors), the code regenerates ALL IDs from scratch (starting at index 1). The first survivor gets ID `candidate-1:...` but the objections recorded during `screen_translations()` used the original IDs (e.g., `candidate-3:...`). The existing objections in `objection_ledger` are now orphaned — no objections will be found for these candidates in `_candidate_objections()`, and prior screening's fatal issues are invisible to the council.

**Suggested fix:** Instead of regenerating all IDs, only add missing ones while preserving matched ones:
```python
while len(candidate_ids) < len(survivors):
    idx = len(candidate_ids) + 1
    candidate_ids.append(self._candidate_id(idx, survivors[idx - 1]))
```

---

### MED-3 — `AnthropicAdapter` retry does not cover HTTP 500 / InternalServerError

**File:** `src/hephaestus/deepforge/adapters/anthropic.py`, lines ~170–185

```python
except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
    if attempt >= self._max_retries:
        raise self._translate_error(exc) from exc
```

**Problem:** `anthropic.InternalServerError` (HTTP 500) is not in the retry list. Anthropic's API occasionally returns 500s on transient overloads. These are silently translated to `AdapterError` and raised immediately, causing the entire pipeline to fail on what would be a transient server error. The `with_retry` utility in `retry.py` would catch it via `is_retryable()` string matching (`"500"` is in `_RETRYABLE_STRINGS`), but only the harness's `retry_config` path uses that utility — the adapters have their own retry logic that doesn't cover 500s.

**Suggested fix:**
```python
except (anthropic.RateLimitError, anthropic.APITimeoutError, 
        anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
```

---

### MED-4 — `CodexCliAdapter` stdout parsing is fragile

**File:** `src/hephaestus/deepforge/adapters/codex_cli.py`, lines ~155–165

```python
if "\ncodex\n" in stdout:
    stdout = stdout.split("\ncodex\n", 1)[-1].strip()
if "\ntokens used\n" in stdout:
    stdout = stdout.split("\ntokens used\n", 1)[0].strip()
elif stdout.endswith("tokens used"):
    stdout = stdout.rsplit("tokens used", 1)[0].strip()
```

**Problem:** If the LLM-generated response content itself contains the literal string `\ncodex\n` or `tokens used` (e.g., in a code sample explaining codex usage or cost analysis), the response is silently truncated at that point. The caller receives partial output with no error or warning.

**Suggested fix:** Use structured JSON output from the CLI (`--output-json` if available) or parse the codex transcript format more robustly (e.g., via line-prefix markers rather than content matching).

---

### MED-5 — Perplexity has no per-session result caching

**File:** `src/hephaestus/research/perplexity.py`

**Problem:** `PerplexityClient` has no caching layer. The same `problem + native_domain` pair for `build_baseline_dossier()` could be called multiple times within the same Genesis session (e.g., once in `prepare_pipeline()` and once in a retry). Each call costs API credits and latency. There's no TTL cache or in-memory deduplication.

**Suggested fix:** Add a simple `functools.lru_cache`-style dict keyed on `hashlib.sha256(f"{problem}:{native_domain}".encode()).hexdigest()` with a per-session cache dict on the client instance.

---

### MED-6 — `LensLoader.get_card()` passes `reference_context=None` to validation

**File:** `src/hephaestus/lenses/loader.py`, lines ~340–350

```python
def get_card(self, lens_id: str) -> LensCard:
    if lens_id in self._derived_cards:
        valid_ids = set(self._validate_derived(reference_context=None))  # <-- None
        if lens_id not in valid_ids and lens_id in self._derived_invalid:
            reasons = ", ".join(self._derived_invalid[lens_id])
            raise ValueError(f"Derived lens card {lens_id!r} is stale: {reasons}")
```

**Problem:** When validating derived lenses in `get_card()`, `reference_context=None` is passed to `_validate_derived()`. If the derived lens's lineage was created with a specific `reference_context` (e.g., a `ReferenceLot` sequence), validation with `None` may incorrectly mark it as valid (or stale) depending on the `validate_lineage` logic. This means a derived composite lens that should be invalidated by a reference change could remain in service.

**Suggested fix:** `get_card()` should accept an optional `reference_context` parameter and pass it through.

---

### MED-7 — `_fix_json_escapes` doesn't handle `\UXXXXXXXX` (8-digit Unicode)

**File:** `src/hephaestus/core/json_utils.py`, lines ~55–90

```python
if nxt == "u" and i + 5 < n and _HEX4.match(text, i + 2, i + 6):
    # Valid \uXXXX → pass through
```

**Problem:** Only 4-digit `\uXXXX` escapes are recognized as valid. Python's `\UXXXXXXXX` (8-hex-digit) escape sequences appear in LLM output when models are reasoning about Unicode in code. These are not valid JSON anyway, but the current code will double-backslash the `\U` and then leave the 8 hex digits as literal text — changing a predictable invalid escape into a corrupted string. There's no warning.

This also means `\N{UNICODE NAME}` sequences will be double-backslashed.

**Suggested fix:** Document explicitly that only JSON-standard `\uXXXX` is handled; add a warning log for `\U` patterns.

---

## LOW

---

### LOW-1 — `_objection_summary()` uses colon as delimiter but text can contain colons

**File:** `src/hephaestus/pantheon/coordinator.py`, lines ~230–235

```python
def _objection_summary(objection: PantheonObjection) -> str:
    return (
        f"{objection.objection_id}:{objection.issue_type}:{objection.severity}:"
        f"{objection.claim_text or objection.statement}"
    )
```

**Problem:** `claim_text` can contain colons (e.g., "Mechanism: relies on undefined tokens: this breaks..."). The summary format uses `:` as a delimiter, so `unresolved_vetoes` strings can't be reliably parsed back into fields. This matters if any downstream consumer tries to parse the veto summaries.

**Suggested fix:** Use `|` or `\t` as delimiter, or serialize to a small JSON object.

---

### LOW-2 — `OpenRouterAdapter` silently uses `api_key=None` if env var missing

**File:** `src/hephaestus/deepforge/adapters/openrouter.py`, lines ~155–165

```python
resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
super().__init__(model=config, api_key=resolved_key, ...)
```

**Problem:** If `OPENROUTER_API_KEY` is not set and no `api_key` is passed, `resolved_key=None`. This is passed silently to `OpenAIAdapter` which passes it to `openai.AsyncOpenAI(api_key=None)` — the client is created successfully but every API call will fail with `AuthenticationError`. There's no eager validation at construction time.

**Suggested fix:**
```python
if not resolved_key:
    raise AuthenticationError("OpenRouter API key not found. Set OPENROUTER_API_KEY.")
```

---

### LOW-3 — Subscription-backed adapters report `cost_usd=0.0` breaking accounting

**File:** `adapters/claude_cli.py`, `adapters/codex_cli.py`, `adapters/claude_max.py`, `adapters/codex_oauth.py`

**Problem:** All subscription-backed adapters return `cost_usd=0.0` for every call. `PantheonAccounting` aggregates cost via `accounting.record(cost_usd=...)`. Total cost telemetry is misleading — pipelines using the Max/CLI adapters will report $0 cost regardless of actual model usage. If cost-based budget limits are ever added, subscription adapter users would never hit them.

**Suggested fix:** Either track estimated cost based on token count and public pricing, or add a `cost_model: "subscription"` flag to `GenerationResult` so consumers can distinguish zero-cost-by-design from zero-cost-by-error.

---

### LOW-4 — `BranchGenome.continuity_signature()` can raise unhandled `TypeError`

**File:** `src/hephaestus/branchgenome/models.py`, lines ~125–155

```python
def continuity_signature(self) -> str:
    payload = {
        ...
        "novelty_vector": self.metrics.novelty_vector.to_dict(),
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
```

**Problem:** If `NoveltyVector.to_dict()` returns any non-JSON-serializable value (e.g., a `numpy.float32`, a dataclass, or a set), `json.dumps` will raise `TypeError`. This crashes `continuity_signature()`, which is called from `runtime_hooks()` and potentially many places that need branch identity. There's no `try/except` around the dump.

**Suggested fix:** Wrap in `try/except TypeError` and log a warning; fall back to a hash of `repr(payload)`.

---

### LOW-5 — `LensLoader.__len__()` returns inconsistent count for stale derived lenses

**File:** `src/hephaestus/lenses/loader.py`, lines ~480–485

```python
def __len__(self) -> int:
    return len(self._cache) + len(
        [lens_id for lens_id in self._derived_lenses if lens_id not in self._derived_invalid]
    )
```

**Problem:** `_derived_invalid` is only populated after `_validate_derived()` is called. Before the first call to `load_all()` or `load_one()`, `_derived_invalid` is empty and all derived lenses (even stale ones registered before validation) count toward `__len__`. After validation, stale lenses are excluded. This means `len(loader)` can return different values depending on whether validation has run — violating the principle of least surprise.

---

### LOW-6 — `with_retry` in `retry.py` retries non-retryable exceptions via string match

**File:** `src/hephaestus/deepforge/retry.py`, lines ~20–25

```python
_RETRYABLE_STRINGS = ("rate limit", "429", "timeout", "connection", "503", "502", "overloaded")

def is_retryable(exc: Exception, config: RetryConfig | None = None) -> bool:
    if isinstance(exc, cfg.retryable_exceptions):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in _RETRYABLE_STRINGS)
```

**Problem:** String matching on the exception message is fragile and can cause false positives. For example: an `AuthenticationError` with the message "Your API key connection was refused (rate limit exceeded in your plan)" would match both `"connection"` and `"rate limit"` and trigger retries — burning all retry attempts before eventually re-raising the unrecoverable auth error.

**Suggested fix:** Apply string matching only after confirming the exception is from a known transient exception type. `AuthenticationError` and `ModelNotFoundError` should be in an explicit never-retry list.

---

## INFO

---

### INFO-1 — BranchGenome uses mixed mutability model

**File:** `src/hephaestus/branchgenome/models.py`

`BranchGenome` uses frozen/immutable tuples for structural fields (`commitments`, `recovery_operators`, `open_questions`, `rejected_patterns`) but mutable dataclasses for `BranchMetrics` and `BranchStateSummary`. This means `continuity_signature()` (which hashes metrics) can produce a different hash on the same `BranchGenome` object if metrics are updated in-place. The signature is not truly stable between calls unless the caller ensures metrics are not mutated between signature computations.

---

### INFO-2 — BranchArena DAG has no cycle detection

**File:** `src/hephaestus/branchgenome/arena.py`

`BranchArena` maintains a `children: dict[str, list[str]]` DAG. No cycle detection exists. While the current creation flow (parent_id from existing branch) makes cycles unlikely by convention, there's no enforcement. If `add_branch()` is called with a `parent_id` that is a descendant of the new branch, a cycle exists and any traversal (DFS, ancestry lookup) would loop infinitely.

---

### INFO-3 — Pantheon prompts module not directly audited

**File:** `src/hephaestus/pantheon/prompts.py`

This file was not read in detail. Prompt injection risks (LLM-generated content interpolated into prompt templates via `.format(...)`) should be reviewed separately, especially in `HEPHAESTUS_REFORGE_PROMPT`, `ATHENA_REVIEW_PROMPT`, and `APOLLO_AUDIT_PROMPT` which interpolate `_translation_to_text(translation)` directly — translation fields come from prior LLM responses that could contain `{` / `}` characters that would break Python's `.format()`.

**Suggested fix:** Use `str.format_map` with a custom dict that escapes `{`/`}` in values, or switch to a template engine like Jinja2.

---

### INFO-4 — `classify_domain_family()` fallback uses raw token hints

**File:** `src/hephaestus/lenses/loader.py`

The domain classification falls back to token intersection between the normalized domain name and `_DOMAIN_FAMILY_TOKEN_HINTS`. This is a reasonable heuristic but can misclassify: `"mathematical_finance"` would match `"mathematics"` family via the `"math"` token, while practitioners would expect `"economics"` classification. No override mechanism exists at the lens YAML level except `domain_family:` explicit field.

---

## Summary Table

| ID | Severity | System | Issue |
|----|----------|--------|-------|
| CRIT-1 | CRITICAL | Pantheon | Sequential agent calls — no concurrency |
| CRIT-2 | CRITICAL | Pantheon | Auto-resolves FATAL objections silently |
| HIGH-1 | HIGH | Pantheon | No timeout on `_forge_json` agent calls |
| HIGH-2 | HIGH | Pantheon | `assert` in production code (disabled by `-O`) |
| HIGH-3 | HIGH | JSON/Pantheon | Greedy regex `{.*}` spans multiple JSON objects |
| HIGH-4 | HIGH | Research | `loads_lenient` silent `{}` return masks parse failure |
| HIGH-5 | HIGH | Adapters | ClaudeMaxAdapter stream cancel doesn't raise GenerationKilled |
| HIGH-6 | HIGH | Adapters | CodexOAuthAdapter missing `_reset_cancel()` in stream |
| HIGH-7 | HIGH | Pantheon | Fuzzy objection dedup at 0.72 can merge real objections |
| MED-1 | MEDIUM | Pantheon | `consensus_without_verification` always True |
| MED-2 | MEDIUM | Pantheon | `candidate_ids` mismatch when survivor list shorter |
| MED-3 | MEDIUM | Adapters | Anthropic retry doesn't cover HTTP 500 |
| MED-4 | MEDIUM | Adapters | CodexCLI stdout parsing truncates on keyword match |
| MED-5 | MEDIUM | Research | No per-session caching in PerplexityClient |
| MED-6 | MEDIUM | Lenses | `get_card()` passes `None` reference context to validation |
| MED-7 | MEDIUM | JSON | `_fix_json_escapes` doesn't handle `\UXXXXXXXX` |
| LOW-1 | LOW | Pantheon | Colon-delimited objection summary breaks if text has colons |
| LOW-2 | LOW | Adapters | OpenRouterAdapter silently uses None API key |
| LOW-3 | LOW | Adapters | Subscription adapters report `cost_usd=0.0` |
| LOW-4 | LOW | BranchGenome | `continuity_signature()` unhandled TypeError |
| LOW-5 | LOW | Lenses | `__len__` returns inconsistent count before validation |
| LOW-6 | LOW | Retry | String-match retry logic can retry unrecoverable errors |
| INFO-1 | INFO | BranchGenome | Mixed mutability makes signature unstable |
| INFO-2 | INFO | BranchGenome | No cycle detection in DAG |
| INFO-3 | INFO | Pantheon | Prompt injection via `.format()` with LLM-derived values |
| INFO-4 | INFO | Lenses | Domain classification heuristic can misclassify |
