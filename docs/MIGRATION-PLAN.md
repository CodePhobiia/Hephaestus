# Migration Plan: Top 10 Recommended Imports

## Build Order (dependency-resolved)

### Phase 1 — Foundation (no interdependencies, fully parallel)
| # | Feature | Module | Effort | Deps |
|---|---------|--------|--------|------|
| 4 | Structured session schema + resume | `session/schema.py` | MEDIUM | None |
| 5 | Layered config precedence | `config/layered.py` | MEDIUM | None |
| 9 | Shared slash-command registry | `cli/commands.py` | MEDIUM | None |
| 7 | Todo working memory | `session/todos.py` | SMALL | None |
| 10 | Memory transparency surfaces | extend `/status`, `/context` | SMALL | None |

### Phase 2 — Core Runtime (depends on Phase 1)
| # | Feature | Module | Effort | Deps |
|---|---------|--------|--------|------|
| 2 | Instruction discovery + budgeted prompt assembly | `prompts/context_loader.py` | MEDIUM | Config (#5) |
| 3 | Conversation runtime + permissions | `agent/runtime.py`, `tools/permissions.py` | LARGE | Session (#4), Config (#5), Commands (#9) |
| 6 | Structured file/web tools + profiles | `tools/registry.py`, `tools/file_ops.py` | MEDIUM | Runtime (#3) |

### Phase 3 — Advanced (depends on Phase 2)
| # | Feature | Module | Effort | Deps |
|---|---------|--------|--------|------|
| 1 | Session compaction with continuation summaries | `session/compact.py` | LARGE | Session (#4), Runtime (#3) |
| 8 | MCP stdio integration | `tools/mcp/` | LARGE | Runtime (#3), Registry (#6) |

## Build→Audit→Fix Loop

After each phase:
1. Run full test suite (`pytest tests/ -q`)
2. Audit: read every new file, check for integration gaps
3. Fix: any test failures or missing wiring
4. Commit with descriptive message
5. Move to next phase

## Success Criteria
- All 593+ existing tests still pass
- Each new module has its own test file with ≥80% coverage of public API
- CLI `heph --help` shows new commands/modes
- REPL `/help` shows new slash commands
- No import errors, no circular deps
