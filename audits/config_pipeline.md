# Hephaestus Audit 2: Config, Pipeline & CLI Surface

**Scope audited:**
- `src/hephaestus/cli/` — commands.py, config.py, main.py, repl.py
- `src/hephaestus/config/layered.py`
- `src/hephaestus/output/` — formatter.py, `__init__.py`
- `.hephaestus/config.yaml` — (absent; see INFO-01)

**Note on `output/report_generator.py`:** The task scope references this file, but it does not exist in the repository. The output subsystem uses `formatter.py`, `proof.py`, and `prior_art.py`.

---

## CRITICAL

---

### CRIT-01 · Wrong entry point in `pyproject.toml` — all subcommands unreachable

**File:** `pyproject.toml`, line 47  
**Severity:** CRITICAL

```toml
[project.scripts]
heph = "hephaestus.cli.main:cli"
```

The installed `heph` binary calls `cli()` directly, bypassing the `main()` function that contains the subcommand dispatch (init, batch, lenses, workspace, scan). Click's `cli` is a plain `@click.command`, not a `@click.group`, so subcommand names are treated as the `problem` positional argument.

**Effect:**
- `heph init` → runs the invention pipeline on the string "init"
- `heph batch --input foo.txt` → Click error: `Error: No such option: --input`
- `heph lenses`, `heph workspace`, `heph scan` → same misrouting

**Suggested fix:**
```toml
[project.scripts]
heph = "hephaestus.cli.main:main"
```

---

### CRIT-02 · `NameError: name 'AMBER'` in `init_cmd` when directory already exists

**File:** `src/hephaestus/cli/main.py`, line ~530  
**Severity:** CRITICAL

```python
def init_cmd() -> None:
    ...
    if heph_dir.exists():
        console.print(f"  [{AMBER}]⚠[/] .hephaestus/ already exists in {cwd}")
        return
```

`AMBER` is never imported or defined in `main.py`. The `AMBER` constant lives in `hephaestus.cli.display` and is only imported inside specific functions in `repl.py`, not in `main.py`.

Running `heph init` on a directory that already has a `.hephaestus/` folder raises `NameError` and crashes.

**Suggested fix:**
```python
from hephaestus.cli.display import AMBER, GREEN  # add to top-level imports
```
Or inline the color string:
```python
console.print(f"  [yellow]⚠[/] .hephaestus/ already exists in {cwd}")
```

---

### CRIT-03 · `_coerce()` raises uncaught `ValueError` for bad env var types

**File:** `src/hephaestus/config/layered.py`, line ~112  
**Severity:** CRITICAL

```python
def _coerce(field_name: str, raw: str) -> Any:
    if field_name in _INT_FIELDS:
        return int(raw)          # <-- raises ValueError if raw="abc"
    if field_name in _BOOL_FIELDS:
        return raw.lower() in ("1", "true", "yes")
    return raw
```

If any int env var (`HEPHAESTUS_DEPTH`, `HEPHAESTUS_CANDIDATES`, `HEPHAESTUS_PANTHEON_MAX_ROUNDS`, `HEPHAESTUS_PANTHEON_MAX_SURVIVORS_TO_COUNCIL`) contains a non-integer value, `int(raw)` raises `ValueError` which propagates unhandled through `LayeredConfig.resolve()`, crashing startup.

**Suggested fix:**
```python
def _coerce(field_name: str, raw: str) -> Any:
    if field_name in _INT_FIELDS:
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid integer for %s: %r — using built-in default", field_name, raw)
            return None  # caller falls back to merged default
    if field_name in _BOOL_FIELDS:
        return raw.lower() in ("1", "true", "yes")
    return raw
```

And guard the assignment in `resolve()`:
```python
coerced = _coerce(field_name, raw)
if coerced is not None:
    merged[field_name] = coerced
    self._sources[field_name] = "<env>"
```

---

## HIGH

---

### HIGH-01 · Config load errors silently swallowed in `cli()` 

**File:** `src/hephaestus/cli/main.py`, lines ~197-211  
**Severity:** HIGH

```python
try:
    from hephaestus.config.layered import LayeredConfig
    layered = LayeredConfig()
    resolved = layered.resolve()
    ...
except Exception:
    pass  # Fall back to CLI defaults
```

A bare `except Exception: pass` swallows every possible failure — YAML parse errors, validation errors (from `ConfigValidationError`), import errors, permission errors. The user gets no feedback that their config was silently discarded.

**Suggested fix:**
```python
except ConfigValidationError as exc:
    print_warning(console, f"Config validation error: {exc}. Using CLI defaults.")
except Exception as exc:
    if verbose:
        print_warning(console, f"Could not load layered config: {exc}. Using CLI defaults.")
```

---

### HIGH-02 · `load_config()` silently falls back to defaults on any YAML error

**File:** `src/hephaestus/cli/config.py`, lines ~110-115  
**Severity:** HIGH

```python
try:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    ...
    cfg = HephaestusConfig(...)
except Exception:
    cfg = HephaestusConfig()  # silent fallback to defaults
_resolve_keys(cfg)
return cfg
```

If `~/.hephaestus/config.yaml` is malformed (even slightly), all user settings are silently dropped and defaults are used. The user has no way to know their config was ignored.

**Suggested fix:**
```python
except yaml.YAMLError as exc:
    import warnings
    warnings.warn(f"Malformed config at {CONFIG_PATH}: {exc}. Using defaults.")
    cfg = HephaestusConfig()
except Exception as exc:
    warnings.warn(f"Could not read config at {CONFIG_PATH}: {exc}. Using defaults.")
    cfg = HephaestusConfig()
```

---

### HIGH-03 · Hardcoded `depth=3` in `_bridge_report()` — loses actual pipeline depth

**File:** `src/hephaestus/cli/main.py`, line ~596  
**Severity:** HIGH

```python
return FmtReport(
    ...
    depth=3,                             # <-- hardcoded, always wrong
    wall_time_seconds=genesis_report.total_duration_seconds,
)
```

The `depth` value in every exported/saved report is always 3, regardless of the actual `--depth` argument used. Deep runs (`--depth 7`) produce reports claiming depth=3.

**Suggested fix:**
```python
# Pass depth into _bridge_report, or read it from genesis_report
depth=getattr(genesis_report, "depth", 3),
```
Or add `depth` to `_bridge_report()`'s signature and thread it from `_run_genesis()`.

---

### HIGH-04 · `"codex"` missing from `_VALID_CLI_MODELS` in `cli()` — config override silently ignored

**File:** `src/hephaestus/cli/main.py`, line ~188  
**Severity:** HIGH

```python
_VALID_CLI_MODELS = {"claude-max", "claude-cli", "opus", "gpt5", "both"}
...
if resolved.default_model in _VALID_CLI_MODELS:
    model = resolved.default_model
```

`"codex"` is a valid `--model` choice (it's in the `click.Choice` list) but is absent from `_VALID_CLI_MODELS`. If a user sets `default_model: codex` in their config, it is silently ignored and `model` stays at its CLI default (`"both"`).

**Suggested fix:**
```python
_VALID_CLI_MODELS = {"claude-max", "claude-cli", "codex", "opus", "gpt5", "both"}
```

---

### HIGH-05 · No max cap on `candidates` in `LayeredConfig._validate()`

**File:** `src/hephaestus/config/layered.py`, line ~147  
**Severity:** HIGH

```python
candidates = merged.get("candidates")
if candidates is not None:
    if not isinstance(candidates, int) or candidates < 1:
        raise ConfigValidationError(
            f"Invalid candidates: {candidates!r}. Must be positive integer."
        )
```

The upper bound check (max 20) present in `load_config()` and `--candidates` CLI option is missing here. Setting `HEPHAESTUS_CANDIDATES=999` or `candidates: 500` in a config file passes validation and gets used in the pipeline.

**Suggested fix:**
```python
if not isinstance(candidates, int) or not (1 <= candidates <= 20):
    raise ConfigValidationError(
        f"Invalid candidates: {candidates!r}. Must be integer 1–20."
    )
```

---

### HIGH-06 · `_build_adapter_for_analysis()` always tries Claude Max first, ignoring configured backend

**File:** `src/hephaestus/cli/repl.py`, lines ~780-810  
**Severity:** HIGH

```python
def _build_adapter_for_analysis(cfg: Any) -> Any:
    backend = cfg.backend

    if backend == "codex-cli":
        ...

    # Always try Claude Max first — it's free (subscription)
    try:
        from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter
        return ClaudeMaxAdapter(model=cfg.default_model or "claude-sonnet-4-6")
    except Exception:
        pass  # OAT token not available, fall back
    ...
```

For backends `api` and `openrouter`, the function unconditionally tries Claude Max first. A user configured with `backend: api` will silently get Claude Max calls (OAT auth) when analyzing a workspace — bypassing rate limits, billing, and model choices they configured. The `openrouter` backend is never served at all (falls through to Anthropic/OpenAI API keys).

**Suggested fix:** Respect `cfg.backend` ordering. Only fall back to Claude Max if explicitly configured or if no other option is found.

---

## MEDIUM

---

### MED-01 · `_deep_merge()` defined and exported but never actually used in config layering

**File:** `src/hephaestus/config/layered.py`, lines ~60-70, ~152  
**Severity:** MEDIUM

```python
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* ..."""
    ...

__all__ = ["LayeredConfig", "ConfigValidationError", "find_project_root", "_deep_merge"]
```

`_deep_merge` is defined and exported but the `_apply_yaml()` method does shallow key-by-key replacement (`merged[key] = value`), not deep merging. Nested config dict values (if any future config key uses dicts) would be fully replaced, not merged. This is misleading and the exported function is dead code.

**Suggested fix:** Either use `_deep_merge` inside `_apply_yaml()` for dict values, or remove it from the module and `__all__`.

---

### MED-02 · Inline `__import__` for `LensEngineState`/`PantheonState` in `_loaded_report()` is fragile

**File:** `src/hephaestus/cli/repl.py`, lines ~855-870  
**Severity:** MEDIUM

```python
lens_engine_state=(
    __import__("hephaestus.lenses.state", fromlist=["LensEngineState"])
    .LensEngineState.from_dict(lens_engine_payload)
    if isinstance(lens_engine_payload, dict)
    else None
),
pantheon_state=(
    __import__("hephaestus.pantheon.models", fromlist=["PantheonState"])
    .PantheonState.from_dict(pantheon_payload)
    if isinstance(pantheon_payload, dict)
    else None
),
```

These bare `__import__` calls are outside any try/except. If either module fails to import (e.g., missing dependency, syntax error), loading ANY saved invention crashes with an `ImportError`, even if the lens/pantheon data is irrelevant to what the user cares about.

**Suggested fix:**
```python
try:
    from hephaestus.lenses.state import LensEngineState
    lens_state = LensEngineState.from_dict(lens_engine_payload) if isinstance(lens_engine_payload, dict) else None
except Exception:
    lens_state = None
```

---

### MED-03 · `_handle_pipeline_update()` uses string `.name` comparison instead of enum

**File:** `src/hephaestus/cli/main.py`, line ~392  
**Severity:** MEDIUM

```python
elif update.stage.name == "FAILED":
    # Mark current stage as failed
    current = getattr(stage_progress, "_current_stage", 0)
    if current > 0:
        stage_progress.fail_stage(current, update.message[:80])
```

The other pipeline stage checks in this function all use proper enum comparisons (`update.stage == PipelineStage.FAILED`), but the FAILED branch uses the fragile `.name` string. If the enum is ever renamed, this check silently stops working. Also, `PipelineStage.FAILED` is already imported and used just 2 lines above.

**Suggested fix:**
```python
elif update.stage == PipelineStage.FAILED:
```

---

### MED-04 · `default_model` not validated in `load_config()` and `LayeredConfig`

**File:** `src/hephaestus/cli/config.py`, line ~120; `src/hephaestus/config/layered.py`  
**Severity:** MEDIUM

```python
cfg = HephaestusConfig(
    ...
    default_model=data.get("default_model", _DEFAULT_MODEL),   # no validation
    ...
)
```

Every other sensitive config field (`backend`, `divergence_intensity`, `output_mode`, `pantheon_resolution_mode`) is validated against an allowlist. `default_model` is accepted without any validation. A typo like `default_model: clauyde-opus` passes silently and causes a confusing runtime error later.

**Suggested fix:** Add `VALID_MODELS` to `cli/config.py` (or reuse the set from `repl.py`) and validate in both `load_config()` and `LayeredConfig._validate()`.

---

### MED-05 · REPL's `ALL_COMMANDS` list for readline completion is out-of-sync with `COMMANDS` dict

**File:** `src/hephaestus/cli/repl.py`, lines ~825-840  
**Severity:** MEDIUM

```python
ALL_COMMANDS = [
    "/help", "/status", "/quit", "/exit", "/clear",
    "/model", "/backend", "/usage", "/cost",
    "/refine", "/alternatives", "/deeper", "/domain",
    "/candidates", "/trace", "/export",
    "/context",
    "/save", "/load", "/history", "/compare",
    "/intensity", "/mode",
    "/todo", "/plan",
]
```

This hardcoded list does not include: `/read`, `/tree`, `/grep`, `/find`, `/edit`, `/invent`, `/ws`, `/workspace`. Tab completion for workspace commands will not work. Any new command added to `COMMANDS` must also be manually added here.

**Suggested fix:** Derive the list from the `CommandRegistry`:
```python
ALL_COMMANDS = _registry.completions("", mode="all")
```

---

### MED-06 · Test environment detection leaks into production config loading

**File:** `src/hephaestus/config/layered.py`, lines ~99-102  
**Severity:** MEDIUM

```python
if not (os.environ.get("PYTEST_CURRENT_TEST") and Path(self._user_config_dir).resolve() == Path(HEPHAESTUS_DIR).resolve()):
    self._apply_yaml(user_config, merged, config_fields, str(user_config))
```

Checking `PYTEST_CURRENT_TEST` in production code couples the config system to test infrastructure. If a user somehow has that env var set in their environment, their user config file is silently skipped.

**Suggested fix:** Use a dedicated test fixture that passes a custom `user_config_dir` to `LayeredConfig` (which it already supports via the `user_config_dir` constructor parameter). Remove the pytest env check entirely.

---

### MED-07 · `_cmd_export_v2()` imports `_bridge_report` from `main.py` (private symbol, cross-module coupling)

**File:** `src/hephaestus/cli/repl.py`, line ~959  
**Severity:** MEDIUM

```python
from hephaestus.cli.main import _bridge_report
```

`_bridge_report` is a module-private function (`_` prefix). Importing it across modules breaks encapsulation and creates a hidden dependency from `repl.py` to `main.py`. If `main.py` is refactored, this silent cross-module import breaks without any static analysis warning.

**Suggested fix:** Move `_bridge_report` to `output/formatter.py` as a public adapter function, or to a shared `cli/_utils.py` module.

---

## LOW

---

### LOW-01 · `heph batch` arg stripping is fragile — drops options before subcommand name

**File:** `src/hephaestus/cli/main.py`, lines ~625-640  
**Severity:** LOW

```python
def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # Strip 'batch'
        batch_cmd(standalone_mode=True)
        return
```

This only works if `batch` is exactly `sys.argv[1]`. If a user passes global options before the subcommand (`heph --verbose batch ...`), the detection fails and "batch" is passed to `cli()` as a problem argument.

**Suggested fix:** Use a proper Click group (`@click.group()`) for the CLI, or at least scan all of `sys.argv` for subcommand names rather than only checking position 1.

---

### LOW-02 · `--model both` in `--raw` mode silently uses only Anthropic adapter

**File:** `src/hephaestus/cli/main.py`, lines ~450-470  
**Severity:** LOW

```python
def _build_raw_adapter(model, depth, anthropic_key, openai_key):
    ...
    if model in ("opus", "both"):
        from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(...)   # OpenAI half of "both" is silently dropped
```

When `--raw --model both`, only the Anthropic adapter is constructed and returned. The OpenAI model is silently ignored. Users expecting both backends in raw mode get only one.

**Suggested fix:** Either document that `--raw` doesn't support the `both` preset, or error out: `if model == "both": raise click.UsageError("--raw does not support model 'both'. Choose a single backend.")`.

---

### LOW-03 · `"workspace"` alias in COMMANDS dict is effectively dead code

**File:** `src/hephaestus/cli/repl.py`, line ~885  
**Severity:** LOW

```python
COMMANDS: dict[str, Any] = {
    ...
    "ws": _cmd_ws,
    "workspace": _cmd_ws,   # <-- dead code
    ...
}
```

The REPL dispatches via the `CommandRegistry` (`_registry.parse_command(raw)`), which resolves `/workspace` to the command named `"ws"` (via `aliases=["workspace"]` defined in `commands.py`). The `COMMANDS["workspace"]` key is never reached by the dispatch path `handler = COMMANDS.get(cmd.name)` since `cmd.name` is always `"ws"`.

**Suggested fix:** Remove `"workspace": _cmd_ws` from `COMMANDS`.

---

### LOW-04 · Workspace validity not checked before context injection in `_run_pipeline()`

**File:** `src/hephaestus/cli/repl.py`, line ~1050  
**Severity:** LOW

```python
problem = _inject_workspace_context(problem, state)
```

If the workspace directory is deleted or unmounted after the REPL session starts, `_inject_workspace_context()` silently uses a stale `workspace_context` with potentially outdated file listings. No staleness check occurs before injection.

**Suggested fix:** Add a lightweight check (e.g., `workspace_root.exists()`) before injecting workspace context, and log a warning if the directory is gone.

---

### LOW-05 · `PERPLEXITY_API_KEY` not documented or validated anywhere in CLI path

**File:** `src/hephaestus/cli/config.py`, `src/hephaestus/config/layered.py`  
**Severity:** LOW

The `_ENV_MAP` in `layered.py` includes `HEPHAESTUS_PERPLEXITY_MODEL` but not `PERPLEXITY_API_KEY`. The `_resolve_keys()` in `config.py` only resolves `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `OPENROUTER_API_KEY`. There is no check or warning if `use_perplexity_research: true` but `PERPLEXITY_API_KEY` is unset — the failure surfaces later inside the pipeline as a generic error.

**Suggested fix:** Add a pre-flight check in `_run_genesis()` and `run_interactive()` similar to the existing Anthropic/OpenAI key checks:
```python
if use_research and not os.environ.get("PERPLEXITY_API_KEY"):
    print_warning(console, "PERPLEXITY_API_KEY not set. Perplexity research features will be disabled.")
    use_research = False
```

---

## INFO

---

### INFO-01 · No `.hephaestus/config.yaml` in repository workspace

**File:** `/home/ubuntu/.openclaw/workspace/hephaestus/` (project root)  
**Severity:** INFO

There is no `.hephaestus/config.yaml` in the project workspace. The `heph init` command would create one, but running from the repo root currently means `LayeredConfig` skips project-level config entirely (layer 3 is absent). This is expected for a fresh repo but worth noting for CI/CD environments.

---

### INFO-02 · `report_generator.py` referenced in audit scope but does not exist

**Severity:** INFO

The file `src/hephaestus/output/report_generator.py` was listed in the audit scope but does not exist in the repository. The output module consists of `formatter.py`, `proof.py`, and `prior_art.py`. Either this file was deleted, renamed, or planned but not yet implemented. No gap in functionality is apparent — `OutputFormatter` in `formatter.py` covers report generation.

---

### INFO-03 · `auto_save` and `theme` in config not plumbed to `LayeredConfig._validate()`

**File:** `src/hephaestus/config/layered.py`  
**Severity:** INFO

`auto_save` is a bool (validated by type coercion) and `theme` is a free string with no allowlist. If `theme` had valid options (currently only `"rich"` is referenced in code), a typo like `theme: rihc` would silently succeed. No action required unless themes are expanded.

---

### INFO-04 · `HephaestusConfig.to_dict()` omits `theme` key

**File:** `src/hephaestus/cli/config.py`, line ~73  
**Severity:** INFO

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "backend": self.backend,
        "default_model": self.default_model,
        ...
        # "theme" is missing
        ...
    }
```

`theme` is a field on `HephaestusConfig` but is not serialized in `to_dict()`. Running `save_config(cfg)` after changing the theme in a session would lose the user's theme preference silently on next load (it would revert to `"rich"`).

**Suggested fix:** Add `"theme": self.theme` to `to_dict()`.

---

## Summary Table

| ID | Severity | File | Issue |
|----|----------|------|-------|
| CRIT-01 | CRITICAL | pyproject.toml | Entry point `cli` instead of `main` — all subcommands unreachable |
| CRIT-02 | CRITICAL | cli/main.py | `NameError: AMBER` in `init_cmd` when dir exists |
| CRIT-03 | CRITICAL | config/layered.py | `_coerce()` raises unhandled `ValueError` on invalid int env vars |
| HIGH-01 | HIGH | cli/main.py | Bare `except Exception: pass` swallows all config errors |
| HIGH-02 | HIGH | cli/config.py | `load_config()` silently falls to defaults on any YAML error |
| HIGH-03 | HIGH | cli/main.py | `depth=3` hardcoded in `_bridge_report()` — depth never saved correctly |
| HIGH-04 | HIGH | cli/main.py | `"codex"` missing from `_VALID_CLI_MODELS` — config override silently ignored |
| HIGH-05 | HIGH | config/layered.py | No max cap on `candidates` — values > 20 accepted from env/config |
| HIGH-06 | HIGH | cli/repl.py | `_build_adapter_for_analysis()` ignores configured backend, always tries Claude Max |
| MED-01 | MEDIUM | config/layered.py | `_deep_merge()` exported but never used; config layers do shallow merge |
| MED-02 | MEDIUM | cli/repl.py | Bare `__import__` for lens/pantheon state in `_loaded_report()` — unprotected |
| MED-03 | MEDIUM | cli/main.py | `update.stage.name == "FAILED"` string check instead of enum comparison |
| MED-04 | MEDIUM | cli/config.py | `default_model` not validated against known model names |
| MED-05 | MEDIUM | cli/repl.py | `ALL_COMMANDS` for readline completion missing workspace commands |
| MED-06 | MEDIUM | config/layered.py | `PYTEST_CURRENT_TEST` check leaks test infra into production config loading |
| MED-07 | MEDIUM | cli/repl.py | `_bridge_report` imported from `main.py` (private symbol, cross-module coupling) |
| LOW-01 | LOW | cli/main.py | Subcommand detection only checks `sys.argv[1]` — fragile positional check |
| LOW-02 | LOW | cli/main.py | `--raw --model both` silently uses only Anthropic adapter |
| LOW-03 | LOW | cli/repl.py | `"workspace"` in `COMMANDS` dict is dead code; never reached by dispatcher |
| LOW-04 | LOW | cli/repl.py | No workspace staleness check before context injection in `_run_pipeline()` |
| LOW-05 | LOW | cli/config.py | `PERPLEXITY_API_KEY` not pre-flighted; unset key causes late, confusing error |
| INFO-01 | INFO | project root | No `.hephaestus/config.yaml` in repo — project config layer inactive |
| INFO-02 | INFO | output/ | `report_generator.py` referenced in audit scope but does not exist |
| INFO-03 | INFO | config/layered.py | `theme` field not validated against allowlist |
| INFO-04 | INFO | cli/config.py | `theme` missing from `HephaestusConfig.to_dict()` — lost on save/reload |

---

*Audit completed: 2026-04-03. Audited by subagent session `audit-config-pipeline`.*
