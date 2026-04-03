# Core Logic & Architecture Audit

**Scope:** `core/`, `config/layered.py`, `workspace/context.py`, `workspace/inventor.py`  
**Auditor:** Subagent (automated deep read)  
**Date:** 2026-04-03  

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 4 |
| MEDIUM   | 6 |
| LOW      | 5 |
| INFO     | 3 |

---

## CRITICAL

---

### [CRITICAL] `translator.py` — `_parse_translation` crashes on missing JSON (AttributeError)

**File:** `src/hephaestus/core/translator.py`  
**Lines:** ~706–718

**Code:**
```python
json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
if not json_match:
    # Empty or unparseable output — return safe defaults instead of crashing
    logger.warning(
        "Translation returned no parseable JSON for candidate (first 300 chars): %.300s; "
        "falling back to defaults",
        raw,
    )
    data = {}                                                    # ← sets data = {}

data = loads_lenient(json_match.group(), default={}, label="translator")  # ← json_match is still None!
```

**Problem:** When the LLM returns output with no JSON object (`json_match` is `None`), the code sets `data = {}` but then unconditionally executes `data = loads_lenient(json_match.group(), ...)`. `json_match` is still `None` at this point → `AttributeError: 'NoneType' object has no attribute 'group'`. The comment says "return safe defaults instead of crashing" — it does crash.

This was introduced when the original `raise TranslationError(...)` was replaced with a fallback path but the author forgot to add `return data` or restructure as `else:`.

**Impact:** Every translation where the LLM returns non-JSON output (e.g., blank response, server error text, refusal) crashes the pipeline with an unhandled AttributeError rather than gracefully applying defaults.

**Suggested fix:**
```python
json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
if not json_match:
    logger.warning(
        "Translation returned no parseable JSON for candidate (first 300 chars): %.300s; "
        "falling back to defaults",
        raw,
    )
    data = {}
else:
    data = loads_lenient(json_match.group(), default={}, label="translator")
```

---

## HIGH

---

### [HIGH] `verifier.py` — Wrong log label inside `mechanism_is_decorative` block

**File:** `src/hephaestus/core/verifier.py`  
**Lines:** ~387–401 (in `_verify_translation`)

**Code:**
```python
# Self-reported decorative transfer penalty
if getattr(translation, "mechanism_is_decorative", False):
    novelty_score *= 0.3  # 70% penalty — model itself says it's decorative
    logger.info(
        "Novelty score penalized (self-reported decorative): %.2f for %s. "
        "Known pattern: %s",
        novelty_score, translation.invention_name,
        getattr(translation, "known_pattern_if_decorative", "unknown"),
    )
    logger.info(                                      # ← inside "decorative" block
        "Novelty score penalized (load-bearing failed): %.2f for %s",  # ← says "load-bearing"!
        novelty_score, translation.invention_name,
    )
```

**Problem:** The second `logger.info` is _inside_ the `mechanism_is_decorative` if-block but says "load-bearing failed". This log fires when the mechanism is self-reported decorative — not when load-bearing fails. The `load_bearing_passed` penalty (×0.5) is applied separately and unconditionally above this block with no log message at all.

**Impact:** Misleading logs. When debugging a run, seeing "load-bearing failed" penalty will direct engineers to the wrong check. Load-bearing failure won't be logged, decorative failure will be logged twice with contradictory labels.

**Suggested fix:**
```python
if not load_bearing_passed:
    novelty_score *= 0.5
    logger.info(
        "Novelty score penalized (load-bearing failed): %.2f for %s",
        novelty_score, translation.invention_name,
    )

if getattr(translation, "mechanism_is_decorative", False):
    novelty_score *= 0.3
    logger.info(
        "Novelty score penalized (self-reported decorative): %.2f for %s. Known pattern: %s",
        novelty_score, translation.invention_name,
        getattr(translation, "known_pattern_if_decorative", "unknown"),
    )
```

---

### [HIGH] `genesis.py` — BranchGenome `source_candidate_index` not bounds-checked

**File:** `src/hephaestus/core/genesis.py`  
**Lines:** ~544–590 (in `invent_stream`, BranchGenome section)

**Code:**
```python
for branch in branch_arena.active_branches():
    candidate = scored[branch.source_candidate_index]   # ← no bounds check
    branch.metrics = assay_branch(...)

for branch in recovery_branches:
    candidate = scored[branch.source_candidate_index]   # ← same pattern

for branch in crossover_branches:
    candidate = scored[branch.source_candidate_index]   # ← same pattern
```

**Problem:** `branch.source_candidate_index` is an integer index into `scored`. If the BranchGenome arena produces branches referencing indices beyond the length of `scored` (e.g., after filtering removed candidates, or if crossover branches are seeded with out-of-range indices), this raises `IndexError`.

There are three separate instances of this pattern (active_branches, recovery_branches, crossover_branches) with no defensive bounds check.

**Suggested fix:**
```python
for branch in branch_arena.active_branches():
    idx = branch.source_candidate_index
    if idx >= len(scored):
        logger.warning("Branch %s has out-of-range index %d (scored=%d); skipping", branch.branch_id, idx, len(scored))
        continue
    candidate = scored[idx]
    ...
```

---

### [HIGH] `workspace/inventor.py` — `_parse_problems` uses `json.loads` instead of `loads_lenient`

**File:** `src/hephaestus/workspace/inventor.py`  
**Lines:** ~276–295 (`_parse_problems` function)

**Code:**
```python
def _parse_problems(text: str) -> list[IdentifiedProblem]:
    import json
    import re

    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group())       # ← standard json.loads, not loads_lenient
    except json.JSONDecodeError:
        return []                              # ← silently returns empty list
    ...
```

**Problem:** The entire codebase uses `loads_lenient()` for LLM JSON parsing precisely because LLMs (especially Qwen and others) emit invalid escape sequences that crash `json.loads`. This function is the sole exception — it uses standard `json.loads`. If the analysis model returns JSON with invalid escapes (e.g. `\s`, `\p`, `\d` in regex patterns within the analysis), the problems list will silently be empty and the workspace invention run produces zero inventions with no useful error logged.

The fix is trivially adding `from hephaestus.core.json_utils import loads_lenient` and using it.

**Suggested fix:**
```python
from hephaestus.core.json_utils import loads_lenient

def _parse_problems(text: str) -> list[IdentifiedProblem]:
    import re
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []

    data = loads_lenient(match.group(), default=None, label="workspace_problems")
    if data is None or not isinstance(data, list):
        return []
    ...
```

---

### [HIGH] `json_fix.py` — Dead code: trailing backslash check is unreachable

**File:** `src/hephaestus/core/json_fix.py`  
**Lines:** ~53–60

**Code:**
```python
if text[i] == '\\' and i + 1 < len(text):   # ← outer condition: i+1 MUST be < len(text)
    nxt = text[i + 1]

    # ... other checks ...

    # Backslash at end of string — leave as-is
    if i + 1 >= len(text):          # ← DEAD CODE: contradicts outer condition
        out.append(text[i:])
        i = len(text)
        continue
```

**Problem:** The outer `if` requires `i + 1 < len(text)`. The inner `if i + 1 >= len(text)` is the logical negation — it can never be `True` when the outer condition is met. This means a trailing backslash at the end of the JSON string will fall through to the "invalid escape" branch (`out.append('\\\\')` + `out.append(nxt)`), but `nxt = text[i+1]` would have already raised `IndexError`... except the outer condition guards against that.

The real issue is the trailing-backslash case is simply not handled for `json_fix.py`. By contrast, `json_utils.py` correctly handles it in a separate `elif` branch at the outer loop level:
```python
elif text[i] == "\\" and i + 1 >= n:
    # Trailing backslash → double it
    out.append("\\\\")
    i += 1
    continue
```

Note: `json_fix.py` has a parallel/duplicate implementation of `json_utils.py`. If both are maintained, they have divergent behavior on trailing backslash edge case.

**Suggested fix:** Remove the dead inner check and add handling at the outer loop level, or consolidate to a single implementation.

---

## MEDIUM

---

### [MEDIUM] `config/layered.py` — `_coerce()` raises unhandled `ValueError` for malformed env vars

**File:** `src/hephaestus/config/layered.py`  
**Lines:** ~144–155 (`_coerce` function, called in `resolve()` ~line 104)

**Code:**
```python
def _coerce(field_name: str, raw: str) -> Any:
    """Coerce a string env var value to the appropriate type."""
    if field_name in _INT_FIELDS:
        return int(raw)           # ← raises ValueError for "abc", "1.5", ""
    if field_name in _BOOL_FIELDS:
        return raw.lower() in ("1", "true", "yes")
    return raw
```

**Called from:**
```python
for env_var, field_name in _ENV_MAP.items():
    raw = os.environ.get(env_var)
    if raw is not None and field_name in config_fields:
        merged[field_name] = _coerce(field_name, raw)    # ← no try/except
```

**Problem:** If `HEPHAESTUS_DEPTH=abc` or `HEPHAESTUS_CANDIDATES=` is set, `int(raw)` raises `ValueError` with the message "invalid literal for int() with base 10: 'abc'". This error propagates up through `resolve()` with no helpful context (no mention of which env var caused it). Users will see a confusing traceback.

**Suggested fix:**
```python
def _coerce(field_name: str, raw: str) -> Any:
    if field_name in _INT_FIELDS:
        try:
            return int(raw)
        except ValueError:
            raise ConfigValidationError(
                f"Invalid integer value for {field_name}: {raw!r}. Expected a whole number."
            )
    if field_name in _BOOL_FIELDS:
        return raw.lower() in ("1", "true", "yes")
    return raw
```

---

### [MEDIUM] `config/layered.py` — `_deep_merge` unused; nested YAML dicts replaced wholesale

**File:** `src/hephaestus/config/layered.py`  
**Lines:** ~69–78 (`_deep_merge`), ~88–110 (`resolve()`)

**Code:**
```python
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (returns new dict, no mutation)."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged
```

**Problem:** `_deep_merge` is defined and exported in `__all__` but never called within `resolve()`. Config layering uses direct key assignment instead:
```python
for key, value in data.items():
    if key in valid_fields:
        merged[key] = value      # ← replaces nested dicts wholesale
```

Currently `HephaestusConfig` is flat so this doesn't bite. However:
1. If nested config keys are ever added, projects upgrading from user config to project config will silently lose partial overrides
2. The `_deep_merge` function is exported as if it's the intended merge strategy, creating an API/implementation mismatch that will confuse future contributors

**Note:** `_deep_merge` may be intended for use by external callers, but given it's exported via `__all__` and is the more "correct" name for how layering should work, document clearly whether it's meant to be internal utility or the canonical merge path.

---

### [MEDIUM] `config/layered.py` — Resolved config is cached as mutable dataclass (shared-state risk)

**File:** `src/hephaestus/config/layered.py`  
**Lines:** ~108–111

**Code:**
```python
self._resolved = HephaestusConfig(**{k: v for k, v in merged.items() if k in config_fields})
return self._resolved
```

**Problem:** The cached resolved config is returned directly. `HephaestusConfig` is a `dataclass` (not frozen), so callers can mutate it:
```python
cfg = layered.resolve()
cfg.depth = 99  # mutates the cache
cfg2 = layered.resolve()  # returns mutated version
assert cfg2.depth == 99  # True — unexpected behavior
```

This is a shared-state hazard. CLI commands that mutate the config object (e.g., applying overrides) would corrupt the LayeredConfig cache for all subsequent callers in the same process.

**Suggested fix:** Return a copy:
```python
import dataclasses
return dataclasses.replace(self._resolved)
```
Or freeze the config at resolve time:
```python
@dataclass(frozen=True)
class HephaestusConfig: ...
```

---

### [MEDIUM] `genesis.py` — Module-level stage class globals have no thread-safety guarantee

**File:** `src/hephaestus/core/genesis.py`  
**Lines:** ~101–107 (module-level globals), ~700–720 (`_ensure_built`)

**Code:**
```python
# Module-level — shared across all Genesis instances
ProblemDecomposer: Any = None
CrossDomainSearcher: Any = None
CandidateScorer: Any = None
SolutionTranslator: Any = None
NoveltyVerifier: Any = None

# In _ensure_built():
import hephaestus.core.genesis as _self
(
    _self.ProblemDecomposer,
    _self.CrossDomainSearcher,
    ...
) = _import_stage_classes()
```

**Problem:** If two `Genesis` instances are created concurrently in different threads (e.g., in an async web server handling two requests), both could call `_ensure_built()` simultaneously. The check `if self._stages_built: return` is also a non-atomic check-then-act sequence. While the assignment is idempotent (always assigns the same classes), a race between `if self._stages_built` and `self._stages_built = True` means both instances could fully initialize (harmless but wasteful). The bigger risk is if `_stages_built` ever checks something other than the stage classes.

The `_stages_built` flag on `self` is per-instance (not module-level), so multiple Genesis instances in the same thread work correctly. The thread concern is if a SINGLE instance is used concurrently (unlikely given it's async, but not impossible from thread-pool executors).

**Suggested fix:** Either document that Genesis is single-use / not thread-safe, or use a module-level lock around the import-and-assign block.

---

### [MEDIUM] `genesis.py` — `invent_stream` is 700+ lines; deeply nested state management

**File:** `src/hephaestus/core/genesis.py`  
**Lines:** ~320–680 (`invent_stream` method body)

**Problem:** The `invent_stream` method is approximately 360 lines of inline pipeline logic. It manages:
- Cost tracking (CostBreakdown mutations)
- Deliberation graph recording
- BranchGenome arena lifecycle
- Pantheon coordination
- 5 pipeline stages (each with their own error paths)
- Multiple fallback flows (bundle fallback, singleton fallback, translation retry)

This single method has high cyclomatic complexity and deeply nested conditionals. The BranchGenome section alone (~100 lines) is embedded inline with no extraction. Failure paths for individual stages are interleaved with happy paths.

**Impact:** Hard to test individual stages. Hard to understand failure modes. Difficult to add new pipeline stages. Any exception in a stage yields `FAILED` through the outer catch-all, losing stage-specific context.

**Suggested fix (architectural):** Extract each stage into a dedicated `async def _run_stage_X()` method or use a stage runner pattern. The pipeline graph/accounting callbacks could be injected via a context object rather than threading through every call.

---

## LOW

---

### [LOW] `scorer.py` — Dead `except json.JSONDecodeError` blocks

**File:** `src/hephaestus/core/scorer.py`  
**Lines:** ~331–334, ~356–359

**Code:**
```python
try:
    data = loads_lenient(json_match.group(), default={"structural_fidelity": 0.5}, ...)
except json.JSONDecodeError:          # ← DEAD: loads_lenient never raises this
    return {"structural_fidelity": 0.5}
```

**Problem:** `loads_lenient()` catches all `json.JSONDecodeError` internally and returns the `default` value instead. It never re-raises. These `except` blocks are dead code that give a false impression of error handling. The same pattern appears in both `_parse_fidelity` and `_parse_mechanism_novelty`.

The same dead pattern also exists in `decomposer.py` line ~230:
```python
except (DecompositionError, KeyError, ValueError, json.JSONDecodeError) as exc:
```
`json.JSONDecodeError` from `loads_lenient` will never be caught here.

**Suggested fix:** Remove the dead `except json.JSONDecodeError` clauses from scorer.py. Update exception list in decomposer.py.

---

### [LOW] `json_utils.py` vs `json_fix.py` — Duplicate implementations with behavioral divergence

**Files:** `src/hephaestus/core/json_utils.py`, `src/hephaestus/core/json_fix.py`

**Problem:** There are two separate lenient JSON parsing implementations:
- `json_utils.py` → `loads_lenient()` — used by all core modules
- `json_fix.py` → `loads()` — appears to be a Qwen-specific patch

They have slightly different behavior:
1. `json_fix.py` tries `\[.*\]` (array extraction) after `\{.*\}` — `json_utils.py` only tries `\{.*\}`
2. `json_fix.py` has the unreachable trailing-backslash guard (see HIGH above) while `json_utils.py` handles it correctly
3. The logging level differs (DEBUG in json_fix vs WARNING in json_utils for parse failures)

**Impact:** Modules that might need array-level JSON parsing (like `workspace/inventor.py`) are using neither — they use raw `json.loads`. Two implementations to maintain, with subtle behavioral differences.

**Suggested fix:** Consolidate into `json_utils.py`. Add `\[.*\]` extraction as a fallback after `\{.*\}` if arrays are needed. Delete `json_fix.py` or mark it deprecated.

---

### [LOW] `verifier.py` — `_compute_novelty_score` multiplicative formula compresses top scores

**File:** `src/hephaestus/core/verifier.py`  
**Lines:** ~395–455

**Code:**
```python
# quality_bonus max = 1.3, surprise_mult max = 1.15, structural_novelty_mult max = 1.4
raw = (
    structural_validity        # max 1.0
    * novelty_risk_penalty     # max 1.0
    * prior_mult               # max 1.0
    * fatal_penalty            # max 1.0
    * distance_bonus           # max 1.0 (distance=1.0)
    * surprise_mult            # max 1.15
    * quality_bonus            # max 1.3
    * structural_novelty_mult  # max 1.4
)
return float(np.clip(raw, 0.0, 1.0))
```

**Problem:** Maximum theoretical raw score: `1.0 × 1.0 × 1.0 × 1.0 × 1.0 × 1.15 × 1.3 × 1.4 = 2.093`. Any score above 1.0 is clipped. This means the top ~50% of the scoring range (`0.48 to 2.09`) all compress into `0.48 to 1.0`. Excellent candidates that differ only in quality/surprise/structural novelty will have novelty_score differences compressed into the top half.

In practice, most runs will produce scores of 0.4–0.8, making differentiation difficult. When all three booster multipliers are active (clean quality gate, SURPRISING mechanism, high structural novelty), the score doesn't provide meaningful ranking above the compression threshold.

**Suggested fix:** Either cap the booster multipliers so the theoretical max is ≤ 1.0 (e.g., max `quality_bonus = 1.0`, `surprise_mult = 1.0`), or normalize the score against theoretical max before clipping.

---

### [LOW] `workspace/context.py` — Budget inconsistency between planning and actual repo_dossier output

**File:** `src/hephaestus/workspace/context.py`  
**Lines:** ~37–44

**Code:**
```python
if ctx.repo_dossier is not None:
    repo_text = ctx.repo_dossier.to_prompt_text(max_chars=min(7_000, budget_chars // 3))
    chars_used += len(repo_text)
    # repo_text is computed but NOT stored — discarded after budget accounting

# Later in to_prompt_text():
if self.repo_dossier:
    sections.append(self.repo_dossier.to_prompt_text(max_chars=7_000))  # ← always 7_000!
```

**Problem:** The budget planning calls `to_prompt_text(max_chars=min(7_000, budget_chars // 3))` — for a 24_000-char budget this is `min(7_000, 8_000) = 7_000`. But when `budget_chars < 21_000`, the planning uses less than 7_000 while `to_prompt_text()` unconditionally uses 7_000 — over-budgeting for small context windows.

The `repo_text` computed during planning is immediately discarded; the repo dossier text is regenerated without the budget-aware `max_chars` when actually rendering.

**Impact:** Low — `budget_chars` defaults to 24_000 and the typical cap is 7_000 in both places. Only matters for callers that set a small `budget_chars`.

---

### [LOW] `genesis.py` — `invent()` return annotation uses `type: ignore[return-value]`

**File:** `src/hephaestus/core/genesis.py`  
**Lines:** ~228–231

**Code:**
```python
if update.stage == PipelineStage.COMPLETE:
    return update.data  # type: ignore[return-value]
```

**Problem:** `update.data` is typed as `Any`. The ignore comment suppresses what could be a legitimate type-narrowing opportunity. If `update.data` is ever not an `InventionReport` at the `COMPLETE` stage (a programmer error elsewhere in the pipeline), this will silently return a wrongly-typed object. A runtime assertion would be safer:

```python
if update.stage == PipelineStage.COMPLETE:
    assert isinstance(update.data, InventionReport), f"Expected InventionReport, got {type(update.data)}"
    return update.data
```

---

## INFO

---

### [INFO] `config/layered.py` — Under pytest, user config is skipped but project config is not

**File:** `src/hephaestus/config/layered.py`  
**Lines:** ~88–94

**Code:**
```python
user_config = self._user_config_dir / "config.yaml"
if not (os.environ.get("PYTEST_CURRENT_TEST") and 
        Path(self._user_config_dir).resolve() == Path(HEPHAESTUS_DIR).resolve()):
    self._apply_yaml(user_config, merged, config_fields, str(user_config))
```

**Observation:** There's a special pytest guard to skip the user's `~/.hephaestus/config.yaml` during tests. However, the project `.hephaestus/config.yaml` (layer 3) is NOT guarded. If a developer has a `.hephaestus/config.yaml` in their project root (which they might for their workflow), test runs could behave differently on their machine vs. CI. This asymmetry is worth documenting clearly.

---

### [INFO] `genesis.py` — Perplexity + prior-art research tasks share a single `asyncio.gather` with mixed error handling

**File:** `src/hephaestus/core/verifier.py`  
**Lines:** ~300–335

**Observation:** The research tasks (prior-art, grounding, risk-review) are gathered with `return_exceptions=True` and then individually checked:
```python
research_results = await asyncio.gather(*research_tasks, return_exceptions=True)
for name, result in zip(task_names, research_results):
    if isinstance(result, Exception):
        logger.warning(...)
        continue
```

This is correct resilience pattern. The issue is that `task_names` and `research_tasks` are built with `extend()` in sequence, so the `zip` ordering is correct only if both lists are appended in the same order (which they are). If someone refactors and adds a task to `research_tasks` without adding to `task_names`, the zip silently produces wrong label→result pairings. Consider using a dict or named tuple instead.

---

### [INFO] `core/genesis.py` — `v2_system_prompt` built but NOT passed to any stage

**File:** `src/hephaestus/core/genesis.py`  
**Lines:** ~395–430, ~473, ~490

**Code (comment in code):**
```python
# V2 system prompt is NOT passed to translator — it conflicts with
# the JSON output format. Creativity forcing happens through the
# mechanical constraints (burn-off, anti-memory, crutch filter,
# lens selection, cognitive interference) not prompt overrides.
```

**Observation:** `v2_system_prompt` is built (including the CrutchFilter injection) but never passed to any harness or stage. The comment explains why it's not used for translation. But it's also not used for decomposition, search, or scoring — stages that don't have JSON schema conflicts.

This is not a bug (it's intentional per the comment), but the code builds a potentially large string that is silently discarded. The variable exists in scope for the entire pipeline without being used. Consider removing the build entirely or documenting the intent more clearly, or use it for decomposition (which benefits from context about what to avoid).

---

## Data Flow & Contract Summary

### Implicit contracts between stages (potential fragility):

| Contract | Where assumed | Where set | Risk |
|----------|--------------|-----------|------|
| `scored[branch.source_candidate_index]` is valid | genesis.py BranchGenome section | BranchGenome arena | IndexError if arena goes out of sync with scored list |
| `translation.source_candidate.candidate.runtime_context["candidate_id"]` chain | verifier.py `_candidate_id_for_translation` | searcher.py `_query_lens` | AttributeError if any link in chain is None (guarded by getattr but degrades to fallback ID) |
| `SearchRuntimeResult.invalidated_lens_ids` populated on translator | genesis.py fallback path | translator.py `_last_runtime` | If translator's `last_runtime` is None (no prior run), fallback gets empty set — which is correct, but the None check happens only in a conditional |
| `translator.last_runtime` must exist for translation retry path | genesis.py ~line 530 | translator.py after translation | `getattr(translator, "last_runtime", None)` guards this |

### State mutation safety:

- `CostBreakdown` is mutated in place across the pipeline and read at the end — no concurrency issues since pipeline is sequential.
- `DeliberationGraph` is passed by reference and mutated by multiple helpers (`_register_search_candidates`, `_sync_scored_candidates`, etc.) — could produce inconsistent state if any helper throws after partial mutation. Currently these are all fire-and-forget with no rollback. Acceptable given they're observability-only.
- `baselines` list is extended in place by `burn_off_results` — shared across the entire pipeline run. Correct but makes it hard to distinguish which baselines came from config vs burn-off in post-hoc analysis.
