# 🔍 HEPHAESTUS PRODUCTION HARDNESS AUDIT — MASTER REPORT

**Date:** 2026-04-03 00:17 UTC  
**4 of 5 auditors completed** (Tests/Quality timed out — retry pending)  
**Auditors:** Core Logic, Config/Pipeline, Security, Pantheon/Research  

---

## SCORECARD

| Severity | Core Logic | Config/Pipeline | Security | Pantheon/Research | **Total** |
|----------|-----------|-----------------|----------|-------------------|-----------|
| 🔴 **CRITICAL** | 1 | 3 | 0 | 2 | **6** |
| 🟠 **HIGH** | 4 | 6 | 4 | 7 | **21** |
| 🟡 **MEDIUM** | 6 | 7 | 7 | 7 | **27** |
| 🟢 **LOW** | 5 | 5 | 6 | 6 | **22** |
| ℹ️ **INFO** | 3 | 4 | 5 | 4 | **16** |
| **TOTAL** | 19 | 25 | 22 | 26 | **92** |

> 20+ additional findings in the Tests/Quality audit (timed out — retry needed)

---

## 🔴 CRITICAL FIXES (6) — Ship Blockers

### C-1: `translator.py` — `AttributeError` on missing JSON output
**File:** `core/translator.py` ~line 706-718  
When LLM returns no parseable JSON (blank response, server error, refusal), `json_match` is None but the code calls `json_match.group()` anyway. Crashes instead of falling back to defaults.
```python
json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
if not json_match:
    data = {}
data = loads_lenient(json_match.group(), ...)  # ← AttributeError!
```
**Fix:** Add `else:` block — `if not json_match: return defaults else: data = loads_lenient(...)`

### C-2: Wrong entry point — all CLI subcommands unreachable
**File:** `pyproject.toml` line 47  
```toml
heph = "hephaestus.cli.main:cli"  # should be main:main
```
`cli()` is a plain Click command (not a group), so `heph init` runs invention pipeline on "init" as the problem text.
**Fix:** Change to `heph = "hephaestus.cli.main:main"`

### C-3: `NameError: AMBER` in `init_cmd`
**File:** `cli/main.py` ~line 530  
`AMBER` imported in `repl.py` but never imported in `main.py`. Running `heph init` on existing directory crashes.
**Fix:** Add `from hephaestus.cli.display import AMBER` to main.py

### C-4: `_coerce()` raises uncaught `ValueError` for bad env vars
**File:** `config/layered.py` ~line 112  
`int("abc")` raises ValueError that propagates unhandled through `resolve()`. `HEPHAESTUS_DEPTH=abc` crashes startup.
**Fix:** Wrap `int(raw)` in try/except, return None on failure so caller uses merged default

### C-5: Sequential Pantheon agents — no concurrency
**File:** `pantheon/coordinator.py` lines ~690-730 (`deliberate()`), ~550-600 (`screen_translations()`)  
All 3 council agents (Athena, Hermes, Apollo) awaited back-to-back. Worst case: 24+ sequential LLM calls × 120s = 30+ minutes when it could run in parallel.
**Fix:** `asyncio.gather(athena, hermes, apollo)` for parallel execution

### C-6: FATAL objections auto-resolved silently
**File:** `pantheon/coordinator.py` ~lines 340-365  
`_resolve_missing_open_objections()` marks ANY open objection as `RESOLVED` if agent forgets to re-raise in next round — including FATAL truth objections. Single round of LLM forgetfulness can produce false unanimous consensus on invalid invention.
**Fix:** `if objection.severity == "FATAL": continue` — never auto-resolve fatal

---

## 🟠 HIGH PRIORITY (21)

| ID | File | Issue | Fix |
|----|------|-------|-----|
| H-1 | `core/verifier.py` | Log says "load-bearing failed" inside decorative block | Move log to correct block |
| H-2 | `core/genesis.py` | `branch.source_candidate_index` not bounds-checked in 3 places across BranchGenome section | Add bounds check: `if 0 <= idx < len(scored)` |
| H-3 | `workspace/inventor.py` | `_parse_problems()` uses raw `json.loads` not `loads_lenient` — bad escapes produce empty problem list | Replace with `loads_lenient` |
| H-4 | `core/json_fix.py` | Dead code: trailing-backslash handler in `_fix_escapes` is unreachable | Remove or restructure |
| H-5 | `config/layered.py` | Config errors swallowed with bare `except Exception: pass` | Log at minimum, warn user |
| H-6 | `output/formatter.py` | `depth` hardcoded as `3` in all exported reports, ignores config | Pass depth through from config |
| H-7 | `config/layered.py` | `"codex"` missing from valid model allowlist | Add to model validation list |
| H-8 | `config/layered.py` | No upper bound on `candidates` in LayeredConfig | Add validation: `if candidates > 50: candidates = 50` |
| H-9 | `output/adapter.py` | Workspace analysis adapter ignoring configured backend | Wire config through |
| H-10 | `pantheon/coordinator.py` | No timeout on individual `_forge_json` calls — hangs block pipeline forever | `asyncio.wait_for(..., timeout=300)` |
| H-11 | `pantheon/coordinator.py` | `assert` in production path — disabled by `python -O` | Replace with proper exception |
| H-12 | `core/json_utils.py` | Greedy `{.*}` regex spans multiple objects | Use `{[^{}]*(?:{[^{}]*}[^{}]*)*}` |
| H-13 | `research/perplexity.py` | `loads_lenient` returns `{}` on parse failure, treated as valid data | Raise on empty result |
| H-14 | `deepforge/adapters/claude_max.py` | Stream cancel doesn't raise `GenerationKilled` — silently yields partial output | Raise on cancel |
| H-15 | `deepforge/adapters/claude_max.py` | CodexOAuthAdapter missing `_reset_cancel()` — cancel state bleeds through | Add reset call |
| H-16 | `pantheon/coordinator.py` | Fuzzy objection dedup at 0.72 Jaccard merges different objections | Lower threshold or require exact match |
| H-17 | `web/app.py` | No rate limiting on `/api/invent` — anyone can trigger unlimited LLM calls | Add `slowapi` or API key |
| H-18 | `deepforge/adapters/claude_max.py` | OAT token prefix leaked in error message (first 20 chars) | Redact token: `token[:4] + "***"` |
| H-19 | `web/app.py` | `.env.docker` tracked in git — users could accidentally commit real keys | Add to `.gitignore` |
| H-20 | `core/tools.py` or similar | `read_file` has no path traversal protection | Validate against workspace root |
| H-21 | `core/subprocess.py` or similar | Git commands run in user-controlled directories — git hook RCE risk | Use `git --no-optional-locks` and sandbox |

---

## 🟡 MEDIUM PRIORITY (27) — Fix Before Production
- Config cache returns mutable dataclass — callers can corrupt future `resolve()` calls
- `_deep_merge` defined, exported, never called in `resolve()`
- Unprotected `__import__` calls in session loading
- Enum comparison done via string `.name`
- `default_model` never validated
- OpenAI/Anthropic retry missing HTTP 500 coverage
- Perplexity API has no caching — duplicates burn credits
- Subprocess calls to git in user-controlled directories
- Claude CLI uses `--permission-mode bypassPermissions` on every call
- No dependency lock file (supply chain risk)
- `wildcard CORS + credentials` misconfiguration
- `consensus_without_verification=True` always set even for unanimous clean consensus
- Weak prompt injection detection
- Potential prompt injection via `.format()` with LLM-derived values in prompt templates
- CodexCLI stdout parsing truncates on keyword match
- Module-level stage class globals have race under concurrent construction
- Config `_coerce()` raises bare `ValueError` on malformed env vars
- `readline` completion missing all workspace commands
- Test infra (`PYTEST_CURRENT_TEST`) leaks into production config loading
- `_deep_merge` implicit API/implementation mismatch
- `default_model` validation missing
- Dead code: `_deep_merge` never called
- Pytest guard skips user config but not project config (asymmetric isolation)
- `task_names`/`research_tasks` zip in verifier could silently mismatch after refactor
- `v2_system_prompt` built but never passed to any stage
- `invent_stream` 700+ lines deeply nested
- Score formula compresses top-range scores (max ~2.09 clipped to 1.0)

---

## 📁 Individual Reports
- **Core Logic:** `audits/core_logic.md` (594 lines, 19 findings)
- **Config/Pipeline:** `audits/config_pipeline.md` (603 lines, 25 findings)
- **Security:** `audits/security.md` (555 lines, 22 findings — no hardcoded secrets found)
- **Pantheon/Research:** `audits/pantheon_research.md` (544 lines, 26 findings)
- **Tests/Quality:** `audits/tests_quality.md` — **TIMED OUT** (retry needed)

---

## 🚀 TRIAGE: WHAT TO FIX FIRST

### Immediate (blocks any production use)
1. **C-1** translator.py crash — every LLM error crashes instead of recovering
2. **C-2** Wrong entry point — entire CLI is unreachable
3. **C-3** Init command crashes on existing directory
4. **C-5** Pantheon runs sequentially — 10-100x slower than needed

### High priority (data loss / wrong results / security)
5. **C-4** Env var crash on non-integer
6. **C-6** Fatal objections silently disappear
7. **H-1, H-3** JSON parsing inconsistencies
8. **H-17** No rate limiting on API endpoint

### Good to have (correctness polish)
9-27. Everything else

Want me to start fixing the criticals? Or should we get the Tests/Quality audit running first?
