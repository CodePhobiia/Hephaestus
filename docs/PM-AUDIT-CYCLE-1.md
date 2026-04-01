# PM Audit — Cycle 1

## Product Assessment

Hephaestus is an invention engine that takes hard engineering problems, searches distant knowledge domains, and maps structural solutions back via a 5-stage pipeline (Decompose → Search → Score → Translate → Verify). It has a CLI, REPL, SDK, web UI stub, and now a full runtime/session/tools layer.

## What Works Well
- Core genesis pipeline is architecturally sound (5 stages, streaming, cost tracking)
- Rich terminal display with stage progress spinners
- 920 tests, clean imports, no circular deps
- Diverse lens library (51+ domains)
- Multiple backends (Anthropic, OpenAI, Claude Max/CLI, OpenRouter)
- V2 system prompt with divergence intensity and output modes
- New runtime layer (session, config, tools, permissions, MCP)

## Critical Gaps (Product-Blocking)

### 1. REPL doesn't use the new runtime layer
The REPL (1919 lines) still handles everything inline — it doesn't use the new session schema, command registry, layered config, or transparency surfaces. The new modules exist but aren't wired in.
**Impact**: Users don't benefit from any Phase 1-3 work until REPL integration.

### 2. No `heph init` command
There's no way to initialize a project with `.hephaestus/` directory, starter config, or instructions file.
**Impact**: Layered config and instruction discovery are dead features without this.

### 3. CLI doesn't load layered config
`main.py` uses hardcoded Click defaults instead of resolving from LayeredConfig.
**Impact**: Users can't configure defaults per-project.

### 4. No web_tools tests (mock httpx)
`tools/web_tools.py` exists but has no test file.
**Impact**: Untested code in a critical path.

### 5. REPL /status and /context don't show transparency data
Memory transparency module exists but isn't surfaced.
**Impact**: Users can't see what anti-memory or context is active.

## UX Improvements (High Impact)

### 6. Output quality — invention reports need richer formatting
The markdown output has basic sections but lacks:
- Implementation roadmap / next steps
- Confidence intervals on scores
- Visual score bars
- Collapsible details for long sections

### 7. REPL needs /init, /plan, /todo, /tools, /permissions commands
New modules exist but no slash commands expose them.

### 8. Agent mode needs the new ConversationRuntime
`agent_chat.py` has its own inline tool loop. Should use `agent/runtime.py`.

### 9. No integration test for the full pipeline
`tests/test_integration/` is empty.

### 10. .gitignore needs updating
`.venv/` and `__pycache__/` are being committed.

## Build Plan — Cycle 1

### Batch A (Wire-in — high impact, medium effort)
1. Wire LayeredConfig into CLI main.py
2. Wire CommandRegistry into REPL
3. Wire MemoryTransparency into REPL /status and /context
4. Wire Session schema into REPL (save/load/resume)
5. Add `heph init` command

### Batch B (Quality — medium impact, small effort)
6. Add web_tools tests
7. Add .gitignore
8. Add integration test (mock pipeline)
9. Wire TodoList into REPL (/plan, /todo)

### Batch C (Polish — high impact, medium effort)
10. Improve output formatter (score visualization, roadmap section)
11. Wire compaction into REPL (auto-compact on threshold)
12. Clean up REPL to use command registry for dispatch
