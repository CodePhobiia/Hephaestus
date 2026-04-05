# ForgeBase Sub-project 5b: CLI/REPL Surface — Design Spec

## Goal
Make ForgeBase operable from the command line — vault management, knowledge queries, fusion, linting, and workbook workflows as CLI commands and REPL slash commands.

## What Gets Built

### CLI Commands (Click)
- `heph vault create <name>` — create vault
- `heph vault list` — list vaults with health scores
- `heph vault info <vault_id>` — vault summary (pages, claims, sources, health)
- `heph vault ingest <vault_id> <path>` — ingest a file/URL into vault
- `heph vault compile <vault_id>` — run Tier 1 + Tier 2 compilation
- `heph vault lint <vault_id>` — run lint, display health report
- `heph ask <query> --vault <vault_id>` — query vault knowledge (returns relevant claims/pages)
- `heph fuse <vault_id1> <vault_id2> [--problem "..."]` — cross-vault fusion
- `heph invent --vault <vault_id> <problem>` — vault-aware invention run
- `heph export <vault_id> --format obsidian|markdown` — export vault pages

### REPL Slash Commands
- `/vault [create|list|use|info]` — vault lifecycle in REPL
- `/ask <query>` — query current vault context
- `/fuse <vault_ids...> [--problem "..."]` — fusion in REPL
- `/lint` — lint current vault
- `/compile` — compile current vault
- `/health` — show vault health/debt score
- `/workbook [create|list|diff|merge]` — workbook management
- `/export [format]` — export current vault

### Display Rendering
- VaultSummary → Rich table (name, pages, claims, health score, last compiled)
- LintReport → Rich panel (debt score bar, findings by category/severity)
- FusionResult → Rich panel (bridge concepts, transfers, fused pack summaries)
- WorkbookDiff → Rich table (added/modified/deleted entities)

## Architecture
- New Click group `vault` under main CLI
- New REPL command handlers registered via existing CommandRegistry
- Display functions using Rich (already a dependency)
- All commands delegate to existing ForgeBase services — no new business logic
- Session state extended with optional `active_vault_id`

## Module Organization
```
src/hephaestus/
  cli/
    vault_commands.py    # CREATE — Click commands for vault ops
    forgebase_display.py # CREATE — Rich rendering for vault/lint/fusion output
  forgebase/
    cli_helpers.py       # CREATE — bridge between CLI and ForgeBase services
```

## Implementation Tasks
1. CLI vault commands (create, list, info, ingest, compile, lint)
2. CLI ask + fuse + invent --vault commands
3. CLI export command
4. REPL slash commands (/vault, /ask, /fuse, /lint, /compile, /health, /workbook, /export)
5. Rich display renderers (VaultSummary, LintReport, FusionResult, WorkbookDiff)
6. Session state extension (active_vault_id)
7. Tests + e2e CLI workflow test
