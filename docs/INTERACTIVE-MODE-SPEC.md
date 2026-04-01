# Hephaestus Interactive Mode — Specification

## Overview

Transform Hephaestus from a one-shot CLI into a persistent interactive invention session. The user enters a REPL where they can describe problems, refine inventions, explore alternatives, and iterate — all within a single running session that maintains context.

## Launch

```bash
heph                              # Launches interactive mode (default)
heph -i                           # Explicit interactive flag
heph "problem"                    # One-shot mode (existing behavior, preserved)
heph --model claude-max -i        # Interactive with model selection
```

**Rule:** If no problem string is provided as an argument, launch interactive mode. If a problem string is given, run one-shot (backward compatible).

---

## Onboarding (First Run)

On first launch, detect if `~/.hephaestus/config.yaml` exists. If not:

```
⚒️  HEPHAESTUS — The Invention Engine
   First time? Let's get you set up.

   Model backend:
   [1] Claude Max (subscription, $0/run)  ← recommended if you have Claude Max/Pro
   [2] Claude CLI (uses `claude` binary, slower)
   [3] API keys (Anthropic + OpenAI, pay-per-use)
   [4] OpenRouter (single key, pay-per-use)

   > 1

   ✓ Claude Max detected (OAT token found)
   ✓ Config saved to ~/.hephaestus/config.yaml

   Type your problem, or /help for commands.

⚒️ >
```

Config file (`~/.hephaestus/config.yaml`):
```yaml
backend: claude-max          # claude-max | claude-cli | api | openrouter
default_model: claude-sonnet-4-6
depth: 3                     # anti-training pressure rounds
candidates: 8                # search candidates
auto_save: true              # save inventions to ~/.hephaestus/inventions/
theme: rich                  # rich | plain | json
```

---

## REPL Interface

### Prompt
```
⚒️ >                          # Ready for input
⚒️ [spam-detector] >          # Inside an active invention session
⚒️ [spam-detector/refine] >   # In refinement sub-mode
```

### Core Flow

```
⚒️ > I need a spam detection system that identifies novel techniques without retraining

  ⏳ Stage 1/5 Decompose...  [7.2s]
  ⏳ Stage 2/5 Search...     [16.1s]  Found 8 candidates
  ⏳ Stage 3/5 Score...      [12.4s]  Top: Fracture Mechanics (0.847)
  ⏳ Stage 4/5 Translate...  [45.2s]  3 inventions built
  ⏳ Stage 5/5 Verify...     [28.0s]  Novelty: 0.72

  ⚒️ Adversarial Stress Intensity Factor
  Source: Fracture Mechanics (Linear Elastic)
  Novelty: 0.72 | Feasibility: HIGH | Cost: $0.00 | Time: 109s

  [1] View full report          [4] Try different problem
  [2] Explore alternatives      [5] Export (markdown/json/pdf)
  [3] Refine this invention     [6] Go deeper on source domain

⚒️ [spam-detector] >
```

### Refinement Mode

```
⚒️ [spam-detector] > /refine

  What would you like to change?
  - Add constraints ("must work offline", "latency < 10ms")
  - Shift domain ("try biology instead of physics")
  - Narrow scope ("focus on email only, not SMS")
  - Challenge weakness ("the adversarial flaw about frozen embeddings")

⚒️ [spam-detector/refine] > focus on the adversarial robustness weakness — 
  how do we handle an intelligent adversary that reads the structural drawings?

  ⏳ Re-running Stage 4 with refinement constraint...
  ...
```

---

## Commands

All commands prefixed with `/`. Anything without `/` is treated as a problem description or natural language input.

### Session Management
| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | Current session info: model, backend, tokens used, inventions generated |
| `/history` | List all inventions in this session |
| `/save [name]` | Save current invention to disk |
| `/load <name>` | Load a previous invention session |
| `/clear` | Clear current context, start fresh |
| `/quit` or `/exit` | Exit interactive mode |

### Model & Backend
| Command | Description |
|---------|-------------|
| `/model` | Show current model |
| `/model <name>` | Switch model (e.g., `/model claude-opus-4-6`) |
| `/backend` | Show current backend |
| `/backend <name>` | Switch backend (claude-max, claude-cli, api, openrouter) |
| `/usage` | Token usage breakdown for this session |
| `/cost` | Running cost for this session |

### Invention Controls
| Command | Description |
|---------|-------------|
| `/refine` | Enter refinement mode for current invention |
| `/alternatives` | Show alternative inventions from last run |
| `/deeper <n>` | Re-run with more depth (anti-training pressure rounds) |
| `/domain <hint>` | Re-run with a domain hint (e.g., `/domain biology`) |
| `/candidates <n>` | Change number of search candidates |
| `/trace` | Show full reasoning trace of last invention |
| `/export [format]` | Export last invention (markdown, json, text, pdf) |
| `/compare` | Side-by-side comparison of inventions in session |

### Context & Memory
| Command | Description |
|---------|-------------|
| `/context` | Show what's in the current context window |
| `/context add <text>` | Add domain knowledge or constraints to context |
| `/context clear` | Clear added context |
| `/pin <invention>` | Pin an invention for cross-reference in future runs |

---

## `/status` Output

```
⚒️ Session Status
┌─────────────────────┬────────────────────────────────┐
│ Backend             │ claude-max (OAT subscription)   │
│ Model               │ claude-sonnet-4-6               │
│ Session duration    │ 12m 34s                         │
│ Inventions          │ 3 generated, 1 refined          │
│ Tokens (session)    │ 47,231 in / 18,442 out          │
│ Cost (session)      │ $0.00 (subscription)            │
│ Depth               │ 3 (default)                     │
│ Search candidates   │ 8 (default)                     │
│ Context additions   │ 2 items pinned                  │
│ Auto-save           │ ON → ~/.hephaestus/inventions/  │
└─────────────────────┴────────────────────────────────┘
```

---

## `/usage` Output

```
⚒️ Token Usage (This Session)
┌──────────────┬─────────┬──────────┬──────────┐
│ Stage        │ Calls   │ Input    │ Output   │
├──────────────┼─────────┼──────────┼──────────┤
│ Decompose    │ 3       │ 4,210    │ 1,890    │
│ Search       │ 24      │ 19,440   │ 7,200    │
│ Score        │ 3       │ 8,100    │ 2,400    │
│ Translate    │ 6       │ 12,300   │ 5,800    │
│ Verify       │ 3       │ 3,181    │ 1,152    │
│ Refine       │ 1       │ 2,100    │ 890      │
├──────────────┼─────────┼──────────┼──────────┤
│ TOTAL        │ 40      │ 49,331   │ 19,332   │
│ Cost         │         │          │ $0.00    │
└──────────────┴─────────┴──────────┴──────────┘
```

---

## Session Persistence

Inventions auto-saved to `~/.hephaestus/inventions/`:

```
~/.hephaestus/
├── config.yaml
├── inventions/
│   ├── 2026-03-31-spam-detector.json
│   ├── 2026-03-31-spam-detector.md
│   ├── 2026-03-31-load-balancer.json
│   └── ...
├── sessions/
│   └── 2026-03-31-session.json    # Full session replay
└── cache/
    └── embeddings/                 # Cached sentence-transformer embeddings
```

Session JSON contains full conversation + all invention reports, so you can `/load` and continue from where you left off.

---

## Implementation Plan

### Phase 1: Core REPL (MVP)
- [ ] REPL loop with Rich console
- [ ] Problem input → pipeline → result display
- [ ] `/help`, `/status`, `/quit` commands
- [ ] `/model`, `/usage`, `/cost` commands
- [ ] Numbered menu after invention (view, alternatives, export)
- [ ] Auto-detection of backend from existing config

### Phase 2: Refinement & Context
- [ ] `/refine` mode — re-run translation with constraints
- [ ] `/domain` hints — bias search toward specific fields
- [ ] `/deeper` — increase anti-training pressure
- [ ] `/context add` — inject domain knowledge
- [ ] `/pin` — cross-reference previous inventions

### Phase 3: Persistence & History
- [ ] Auto-save inventions to disk
- [ ] `/save`, `/load` commands
- [ ] Session replay from JSON
- [ ] `/history` with search
- [ ] `/compare` side-by-side

### Phase 4: Onboarding & Polish
- [ ] First-run setup wizard
- [ ] Config file management
- [ ] `/export pdf` (via markdown → weasyprint)
- [ ] Tab completion for commands
- [ ] Streaming stage progress with spinners

### Estimated Build Time
- Phase 1: ~2-3 hours (core REPL + commands)
- Phase 2: ~2 hours (refinement engine)
- Phase 3: ~1-2 hours (file I/O + serialization)
- Phase 4: ~1 hour (onboarding + polish)

Total: ~6-8 hours for full interactive mode.

---

## Open Questions

1. **Multi-model runs?** Should `/refine` be able to use a different model than the initial run? (e.g., Opus for refinement, Sonnet for search)
2. **Collaborative mode?** Multiple users sharing a session via WebSocket?
3. **Plugin system?** Custom lens libraries loadable at runtime?
4. **Web UI?** The existing `web/` directory has a FastAPI skeleton — should interactive mode also power a browser interface?
