=== WORKSPACE CONTEXT ===
Workspace: /home/ubuntu/.openclaw/workspace/claw-code
Files: 167 | Lines: 40,327 | Size: 1,335 KB
Primary language: .rs
Languages: .py(67), .rs(48), .json(32), .toml(10), .md(6), .sh(4)
Config files: rust/Cargo.toml, rust/crates/api/Cargo.toml, rust/crates/claw-cli/Cargo.toml, rust/crates/commands/Cargo.toml, rust/crates/compat-harness/Cargo.toml, rust/crates/lsp/Cargo.toml, rust/crates/plugins/Cargo.toml, rust/crates/runtime/Cargo.toml, rust/crates/server/Cargo.toml, rust/crates/tools/Cargo.toml
Entry points: rust/crates/claw-cli/src/main.rs, src/main.py
Repo roots: code=rust, src, src/assistant | tests=tests
Subsystems: crates, src, assistant, bootstrap, bridge, buddy (+26 more)
Suggested commands: pytest

--- Directory Structure ---
claw-code/
├── assets/
│   ├── omx/
│   │   ├── omx-readme-review-1.png
│   │   └── omx-readme-review-2.png
│   ├── clawd-hero.jpeg
│   ├── instructkr.png
│   ├── star-history.png
│   ├── tweet-screenshot.png
│   └── wsj-feature.png
├── rust/
│   ├── crates/
│   │   ├── api/
│   │   ├── claw-cli/
│   │   ├── commands/
│   │   ├── compat-harness/
│   │   ├── lsp/
│   │   ├── plugins/
│   │   ├── runtime/
│   │   ├── server/
│   │   └── tools/
│   ├── docs/
│   │   └── releases/
│   ├── CONTRIBUTING.md
│   ├── Cargo.lock
│   ├── Cargo.toml
│   └── README.md
├── src/
│   ├── assistant/
│   │   └── __init__.py
│   ├── bootstrap/
│   │   └── __init__.py
│   ├── bridge/
│   │   └── __init__.py
│   ├── buddy/
│   │   └── __init__.py
│   ├── cli/
│   │   └── __init__.py
│   ├── components/
│   │   └── __init__.py
│   ├── constants/
│   │   └── __init__.py
│   ├── coordinator/
│   │   └── __init__.py
│   ├── entrypoints/
│   │   └── __init__.py
│   ├── hooks/
│   │   └── __init__.py
│   ├── keybindings/
│   │   └── __init__.py

--- Repo Dossier ---
=== REPO DOSSIER ===
Repo: claw-code
Cache: cached (/home/ubuntu/.openclaw/workspace/.git/hephaestus/repo_dossier.json)
Code roots: rust, src, src/assistant, src/bootstrap, src/bridge, src/buddy, src/cli, src/components, src/constants, src/coordinator, src/entrypoints, src/hooks, src/keybindings, src/memdir, src/migrations, src/moreright, src/native_ts, src/outputStyles, src/plugins, src/reference_data, src/remote, src/schemas, src/screens, src/server, src/services, src/skills, src/state, src/types, src/upstreamproxy, src/utils, src/vim, src/voice
Test roots: tests
Key artifacts: README.md, rust/Cargo.toml, rust/crates/api/Cargo.toml, rust/crates/claw-cli/Cargo.toml, rust/crates/commands/Cargo.toml, rust/crates/compat-harness/Cargo.toml, rust/crates/lsp/Cargo.toml, rust/crates/claw-cli/src/main.rs
Architecture notes:
- Primary implementation lives under rust, src, src/assistant, with 32 inferred subsystems.
- Tests are anchored in tests and map to 0 subsystem(s).
- Key repo artifacts include README.md, rust/Cargo.toml, rust/crates/api/Cargo.toml, rust/crates/claw-cli/Cargo.toml, rust/crates/commands/Cargo.toml.
Suggested commands:
- test: pytest (tests/ + pytest)
Subsystem map:
- crates [rust/crates] 48 files / 34601 lines
- src [src] 36 files / 1673 lines
- assistant [src/assistant] 2 files / 32 lines
- bootstrap [src/bootstrap] 2 files / 32 lines
- bridge [src/bridge] 2 files / 32 lines
- buddy [src/buddy] 2 files / 32 lines
- cli [src/cli] 2 files / 32 lines
- components [src/components] 2 files / 32 lines
- constants [src/constants] 2 files / 32 lines
- coordinator [src/coordinator] 2 files / 32 lines
=== END REPO DOSSIER ===

--- README ---
# Rewriting Project Claw Code

<p align="center">
  <strong>⭐ The fastest repo in history to surpass 50K stars, reaching the milestone in just 2 hours after publication ⭐</strong>
</p>

<p align="center">
  <a href="https://star-history.com/#instructkr/claw-code&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=instructkr/claw-code&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=instructkr/claw-code&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=instructkr/claw-code&type=Date" width="600" />
    </picture>
  </a>
</p>

<p align="center">
  <img src="assets/clawd-hero.jpeg" alt="Claw" width="300" />
</p>

<p align="center">
  <strong>Better Harness Tools, not merely storing the archive of leaked Claw Code</strong>
</p>

<p align="center">
  <a href="https://github.com/sponsors/instructkr"><img src="https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?logo=github&style=for-the-badge" alt="Sponsor on GitHub" /></a>
</p>

> [!IMPORTANT]
> **Rust port is now in progress** on the [`dev/rust`](https://github.com/instructkr/claw-code/tree/dev/rust) branch and is expected to be merged into main today. The Rust implementation aims to deliver a faster, memory-safe harness runtime. Stay tuned — this will be the definitive version of the project.

> If you find this work useful, consider [sponsoring @instructkr on GitHub](https://github.com/sponsors/instructkr) to support continued open-source harness engineering research.

---

## Rust Port

The Rust workspace under `rust/` is the current systems-language port of the project.

It currently includes:

- `crates/api-client` — API client with provider abstraction, OAuth, and streaming support
- `crates/runtime` — session state, compaction, MCP orchestration, prompt construction
- `crates/tools` — tool manifest definitions and execution framework
- `crates/commands` — slash commands, skills discovery, and config inspection
- `crates/plugins` — plugin model, hook pipeline, and bundled plugins
- `crates/compat-harness` — compatibility layer for upstream editor integration
- `crates/claw-cli` — interactive REPL, markdown rendering, and project bootstrap/init flows

Run the Rust build:

```bash
cd rust
cargo build --release
```

## Backstory

At 4 AM on March 31, 2026, I woke up to my phone blowing up with notifications. The Claw Code source had been exposed, and the entire dev community was in a frenzy. My girlfriend in Korea was genuinely worried I might face legal action from the original authors just for having the code on my machine — so I did what any engineer would do under pressure: I sat down, ported the core features to Python from scratch, and pushed it before the sun came up.

The whole thing was orchestrated end-to-end using [oh-my-codex (OmX)](https://github.com/Yeachan-Heo/oh-my-codex) by [@bellman_ych](https://x.com/bellman_ych) — a workflow layer built on top of OpenAI's Codex ([@OpenAIDevs](https://x.com/OpenAIDevs)). I used `$team` mode for parallel code review and `$ralph` mode for persistent execution loops with architect-level verification. The entire porting session — from reading the original harness structure to producing a working Python tree with tests — was driven through OmX orchestration.

The result is a clean-room Python rewrite that captures the architectural patterns of Claw Code's agent harness without copying any proprietary source. I'm now actively collaborating with [@bellman_ych](https://x.com/bellman_ych) — the creator of OmX himself — to push this further. The basic Python foundation is already in place and functional, but we're just getting started. **Stay tuned — a much more capable version is on the way.**

The Rust port was developed with both [oh-my-codex (OmX)](https://github.com/Yeachan-Heo/oh-my-codex) and [oh-my-opencode (OmO)](https://github.com/code-yeongyu/oh-my-openagent): OmX drove scaffolding, orchestration, and architecture direction, while OmO was used for later implementation acceleration and verification support.

https://github.com/instructkr/claw-code

![Tweet screenshot](assets/tweet-screenshot.png)

## The Creators Featured in Wall Street Journal For Avid Claw Code Fans

I've been deeply interested in **harness engineering** — studying how agent systems wire tools, orchestrate tasks, and manage runtime context. This isn't a sudden thing. The Wall Street Journal featured my work earlier this month, documenting how I've been one of the most active power users exploring these systems:

> AI startup worker Sigrid Jin, who attended the Seoul dinner, single-handedly used 25 billion of Claw Code tokens last year. At the time, usage limits were looser, allowing early enthusiasts to reach tens of billions of tokens at a very low cost.
>
> Despite his countless hours with Claw Code, Jin isn't faithful to any one AI lab. The tools available have different strengths and weaknesses, he said. Codex is better at reasoning, while Claw Code generates cleaner, more shareable code.
>
> Jin flew to San Francisco in February for Claw Code's first birthday party, where attendees waited in line to compare notes with Cherny. The crowd included a practicing cardiologist from Belgium who had built an app to help patients navigate care, and a California lawyer who made a tool for automating building permit approvals using Claw Code.
>
> "It was basically like a sharing party," Jin said. "There were lawyers, there were doctors, there were dentists. They did not have software engineering backgrounds."
>
> — *The Wall Street Journal*, March 21, 2026, [*"The Trillion Dollar Race to Automate Our Entire Lives"*](https://lnkd.in/gs9td3qd)

![WSJ Feature](assets/wsj-feature.png)

---

## Porting Status

The main source tree is now Python-first.

- `src/` contains the active Python porting workspace
- `tests/` verifies the current Python workspace
- the exposed snapshot is no longer part of the tracked repository state

The current Python workspace is not yet a complete one-to-one replacement for the original system, but the primary implementation surface is now Python.

## Why this rewrite exists

I originally studied the exposed codebase to understand its harness, tool wiring, and agent workflow. After spending more time with the legal and ethical questions—and after reading the essay linked below—I did not want the exposed snapshot itself to remain the main tracked source tree.

This repository now focuses on Python porting work instead.

## Repository Layout

```text
.
├── src/                                # Python porting workspace
│   ├── __init__.py
│   ├── commands.py
│   ├── main.py
│   ├── models.py
│   ├── port_manifest.py
│   ├── query_engine.py
│   ├── task.py
│   └── tools.py
├── rust/                               # Rust port (claw CLI)
│   ├── crates/api/                     # API client + streaming
│   ├── crates/runtime/                 # Session, tools, MCP, config
│   ├── crates/claw-cli/               # Interactive CLI binary
│   ├── crates/plugins/                 # Plugin system
│   ├── crates/commands/                # Slash commands
│   ├── crates/server/                  # HTTP/SSE server (axum)
│   ├── crates/lsp/                    # LSP client integration
│   └── crates/tools/                   # Tool specs
├── tests/                              # Python verification
├── assets/omx/                         # OmX workflow screenshots
├── 2026-03-09-is-legal-the-same-as-legitimate-ai-reimplementation-and-the-erosion-of-copyleft.md
└── README.md
```

## Python Workspace Overview

The new Python `src/` tree currently provides:

- **`port_manifest.py`** — summarizes the current Python workspace structure
- **`models.py`** — dataclasses for subsystems, modules, and backlog state
- **`commands.py`** — Python-side command port metadata
- **`tools.py`** — Python-side tool port metadata
- **`query_engine.py`** — renders a Python porting summary from the active workspace
- **`main.py`** — a CLI entrypoint for manifest and summary output

## Quickstart

Render the Python porting summary:

```bash
python3 -m src.main summary
```

Print the current Python workspace manifest:

```bash
python3 -m src.main manifest
```

List the current Python modules:

```bash
python3 -m src.main subsystems --limit 16
```

Run verification:

```bash
python3 -m unittest discover -s tests -

... [truncated]

=== END WORKSPACE CONTEXT ===