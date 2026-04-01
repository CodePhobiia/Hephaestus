# claw-code Features Relevant to Hephaestus

## Scope and confidence

This document compares the current Hephaestus codebase against `claw-code` as read from `/tmp/claw-code`.

Important caveat: `claw-code` has two different layers.

- The Rust workspace under `rust/` is the main active implementation.
- The Python tree under `src/` is mostly a parity and manifest surface. It is still useful because it exposes architecture intent, inventory snapshots, and compatibility ideas, but much of it is not the production runtime.
- `PARITY.md` explicitly says several advertised surfaces are incomplete or mirrored only. Wherever that matters, this document calls it out.

Hephaestus already has strong raw invention machinery:

- a staged invention pipeline in `src/hephaestus/core/genesis.py`
- a substantial REPL in `src/hephaestus/cli/repl.py`
- a prompt builder in `src/hephaestus/prompts/system_prompt.py`
- anti-memory in `src/hephaestus/memory/anti_memory.py`
- an early agent-chat loop in `src/hephaestus/cli/agent_chat.py`

The most valuable imports from `claw-code` are therefore not "basic chat features". They are the runtime, session, permission, context, and operator-experience layers around the model.

## 1. Layered project instruction discovery

- What it does in claw-code: `rust/crates/runtime/src/prompt.rs` searches for instruction files up the directory tree, including `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, and `.claude/instructions.md`. It deduplicates repeated content, enforces per-file and total-size limits, and exposes the discovered instruction set to the runtime.
- Why it matters for Hephaestus: Hephaestus currently builds a strong system prompt, but it has no equivalent project-local instruction stack. That means repository-specific norms, architecture notes, or operator policy have to be passed manually or lost between sessions.
- How we would integrate it into Hephaestus specifically: Add `src/hephaestus/prompts/context_loader.py` and teach `src/hephaestus/prompts/system_prompt.py` to merge built-in Hephaestus invention guidance with repository-local instructions such as `HEPHAESTUS.md`, `.hephaestus/instructions.md`, and `.hephaestus/local.md`. Surface discovered files in `/status` and `/context`.
- Priority: HIGH
- Effort: MEDIUM

## 2. Prompt assembly with an explicit dynamic boundary

- What it does in claw-code: `rust/crates/runtime/src/prompt.rs` separates the stable system prompt from dynamic runtime context using `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`, then appends discovered instructions, git context, runtime config, and other ephemeral state in a controlled order.
- Why it matters for Hephaestus: `src/hephaestus/prompts/system_prompt.py` already renders a static template and validates output settings, but it does not formally separate immutable core policy from volatile runtime context. That makes prompt growth harder to reason about and harder to compact safely.
- How we would integrate it into Hephaestus specifically: Split Hephaestus prompt construction into two layers: `core_prompt` for invention philosophy and `runtime_prompt` for session state, pinned context, current invention metadata, tool availability, and workspace instructions. Store the boundary marker so compaction and debugging can reconstruct exactly what changed during a turn.
- Priority: HIGH
- Effort: MEDIUM

## 3. Git-aware workspace context injection

- What it does in claw-code: `rust/crates/runtime/src/prompt.rs` injects git status and git diff context into the model prompt, and `rust/crates/rusty-claude-cli/src/main.rs` has operator-facing reporting around diffs.
- Why it matters for Hephaestus: Once Hephaestus is in interactive agent mode, the model needs lightweight awareness of the local code workspace and recent edits without rereading entire files every turn.
- How we would integrate it into Hephaestus specifically: Extend `src/hephaestus/cli/repl.py` and `src/hephaestus/cli/agent_chat.py` so the active prompt can include compact git state for the current workspace: branch, dirty files, and optionally staged or unstaged diffs under a token budget. This should be opt-in per mode because invention mode and coding mode need different amounts of repo awareness.
- Priority: MEDIUM
- Effort: MEDIUM

## 4. Budgeted context deduplication

- What it does in claw-code: `rust/crates/runtime/src/prompt.rs` hashes instruction content, drops duplicates, truncates oversized files, and respects total character ceilings before prompt assembly.
- Why it matters for Hephaestus: Hephaestus already deals with large context from invention traces, refinement history, anti-memory, and user-supplied documents. Without a budgeted merge step, useful signal gets crowded out by repeated or low-value context.
- How we would integrate it into Hephaestus specifically: Introduce a context-budgeting pass that runs before calls from both `src/hephaestus/core/genesis.py` and `src/hephaestus/cli/agent_chat.py`. Inputs should include pinned context, user-added context, prior inventions, anti-memory hits, workspace instructions, and optional repo state. Deduplicate exact repeats and then score by recency, pinning, and task relevance.
- Priority: HIGH
- Effort: MEDIUM

## 5. Structured session transcript model

- What it does in claw-code: `rust/crates/runtime/src/session.rs` defines a typed transcript model with roles like `System`, `User`, `Assistant`, and `Tool`, and block types like `Text`, `ToolUse`, and `ToolResult`. Sessions serialize cleanly to JSON and round-trip back into the runtime.
- Why it matters for Hephaestus: `src/hephaestus/cli/repl.py` stores session state, but the model transcript itself is not handled as a first-class typed object. That limits robust resume, export, replay, and compaction.
- How we would integrate it into Hephaestus specifically: Create `src/hephaestus/session/schema.py` with typed transcript records and block types. Migrate the current ad hoc conversation state in `src/hephaestus/cli/repl.py` and `src/hephaestus/cli/agent_chat.py` to read and write this shared schema. Use it as the canonical storage format for `/save`, `/load`, `/history`, and future resume commands.
- Priority: HIGH
- Effort: MEDIUM

## 6. Automatic context compaction with continuation summaries

- What it does in claw-code: `rust/crates/runtime/src/compact.rs` summarizes older conversation state into a continuation message that preserves recent user requests, pending work, key files, and current activity. It keeps the session running when token pressure grows instead of just losing history.
- Why it matters for Hephaestus: Hephaestus has long invention and refinement sessions by design. Interactive mode and agentic chat will hit context limits quickly if the system has no principled compaction strategy.
- How we would integrate it into Hephaestus specifically: Add `src/hephaestus/session/compact.py` and compact on thresholds in `src/hephaestus/cli/repl.py` and `src/hephaestus/cli/agent_chat.py`. The summary format should preserve Hephaestus-specific state: current invention, alternatives, selected refinement axis, anti-memory exclusions, pinned context, active tools, and outstanding user asks.
- Priority: HIGH
- Effort: LARGE

## 7. Explicit working-memory todo list

- What it does in claw-code: `rust/crates/tools/src/lib.rs` exposes `TodoWrite`, which persists a task list to `.clawd-todos.json`, enforces exactly zero or one `in_progress` items, and nudges the agent to verify work before declaring completion.
- Why it matters for Hephaestus: Hephaestus already has multi-stage invention logic, but its interactive coding/chat side does not have an explicit task memory for longer operational work. That makes multi-step agent sessions more brittle.
- How we would integrate it into Hephaestus specifically: Add a lightweight task ledger, ideally `src/hephaestus/session/todos.py`, and expose it in the REPL as `/plan`, `/todo`, or `/tasks`. This should be available only in interactive/agent modes, not in raw invention mode. The verification nudge is especially valuable when the agent transitions from idea generation to implementation.
- Priority: HIGH
- Effort: SMALL

## 8. Rich usage and cost accounting

- What it does in claw-code: `rust/crates/runtime/src/usage.rs` and `rust/crates/rusty-claude-cli/src/main.rs` maintain token usage, model pricing estimates, and human-readable cost summaries across turns and tools.
- Why it matters for Hephaestus: `src/hephaestus/core/genesis.py` already has cost structures and `src/hephaestus/cli/repl.py` already tracks token totals, but the reporting is still narrower than what a full agent runtime needs.
- How we would integrate it into Hephaestus specifically: Consolidate cost accounting behind a shared `UsageTracker` used by both genesis runs and interactive tool loops. Add per-mode, per-stage, and per-tool cost rollups to `/usage` and `/cost`, and persist them in saved sessions.
- Priority: MEDIUM
- Effort: SMALL

## 9. Reusable skill files as operator-facing procedural memory

- What it does in claw-code: `rust/crates/tools/src/lib.rs` includes a `Skill` tool that resolves `SKILL.md` content from configured skill directories and exposes reusable task-specific instructions to the model.
- Why it matters for Hephaestus: Hephaestus has domain-specific invention logic but no clean way to package recurring workflows such as "refine invention into MVP spec", "convert invention into experiment design", or "turn invention into code-generation brief".
- How we would integrate it into Hephaestus specifically: Add `.hephaestus/skills/` support and let the REPL or agent-chat load skills on demand. Examples: patent prior-art search skill, hardware feasibility skill, safety review skill, architecture review skill, and commercialization skill. This should complement, not replace, the core invention system prompt.
- Priority: MEDIUM
- Effort: MEDIUM

## 10. Generic conversation runtime over model client plus tool executor

- What it does in claw-code: `rust/crates/runtime/src/conversation.rs` defines `ConversationRuntime<C, T>` over an `ApiClient` and `ToolExecutor`, handling the tool loop, message flow, usage tracking, and permission checks in one reusable core.
- Why it matters for Hephaestus: `src/hephaestus/cli/agent_chat.py` currently contains a localized tool loop, and `src/hephaestus/core/genesis.py` contains a different generation path. The architecture does not yet have a shared runtime abstraction.
- How we would integrate it into Hephaestus specifically: Introduce `src/hephaestus/agent/runtime.py` with pluggable `ModelClient`, `ToolRegistry`, `PermissionPolicy`, and `SessionStore`. Then make `agent_chat.py` a thin adapter over that runtime. Longer term, some parts of interactive refinement could also use the same runtime.
- Priority: HIGH
- Effort: LARGE

## 11. Permission modes and per-tool escalation

- What it does in claw-code: `rust/crates/runtime/src/permissions.rs` defines permission policy and escalation behavior, and `rust/crates/rusty-claude-cli/src/main.rs` lets runs start in different permission modes with tool restrictions.
- Why it matters for Hephaestus: Hephaestus interactive mode currently has tools, but not a generalized permission model. As soon as it gains file-writing, shell, MCP, or network tools, permission policy becomes mandatory.
- How we would integrate it into Hephaestus specifically: Create `src/hephaestus/tools/permissions.py` with modes like `read_only`, `workspace_write`, and `full_access`. Wire it into `src/hephaestus/cli/agent_chat.py` and the REPL so tool calls are checked centrally instead of each tool deciding ad hoc.
- Priority: HIGH
- Effort: MEDIUM

## 12. Per-run allowed-tool filtering

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/main.rs` supports `allowedTools` filtering so the runtime can expose only a safe subset of tools for a session or invocation.
- Why it matters for Hephaestus: Different Hephaestus modes need different tool surfaces. Invention mode should not accidentally expose destructive coding tools; code mode might need them.
- How we would integrate it into Hephaestus specifically: Add tool profiles in `src/hephaestus/cli/config.py` and select them in `src/hephaestus/cli/repl.py` by mode. Example profiles: `invent`, `research`, `code_readonly`, `code_write`, `export_only`. Surface the active tool set in `/status`.
- Priority: HIGH
- Effort: SMALL

## 13. Sandbox abstraction instead of direct shell trust

- What it does in claw-code: `rust/crates/runtime/src/sandbox.rs` models sandbox configuration, detects runtime environment, and decides whether isolation is available or why it is not. `rust/crates/runtime/src/bash.rs` reports sandbox status with execution results.
- Why it matters for Hephaestus: If Hephaestus evolves into a serious coding agent, shell and filesystem operations need a clear isolation story rather than being treated as ordinary tools.
- How we would integrate it into Hephaestus specifically: Even if the first Hephaestus implementation remains local-only, add an abstraction layer for shell execution so permission mode, timeout policy, and sandbox status are explicit in returned tool results. That will make later containerized or remote execution much easier.
- Priority: MEDIUM
- Effort: LARGE

## 14. Structured file operations instead of free-form shell dependence

- What it does in claw-code: `rust/crates/runtime/src/file_ops.rs` provides first-class `read_file`, `write_file`, `edit_file`, `glob_search`, and `grep_search`. `rust/crates/tools/src/lib.rs` exposes these as named tools instead of forcing the model to reach for bash for every filesystem action.
- Why it matters for Hephaestus: The current `agent_chat.py` includes `read_file`, but the overall tool story is still sparse. Dedicated file tools are safer, easier to audit, and easier to permission-check than generic shell access.
- How we would integrate it into Hephaestus specifically: Build a real `src/hephaestus/tools/registry.py` and move file access, search, and edit operations there. The REPL should prefer structured tools first and reserve shell for cases that genuinely need it.
- Priority: HIGH
- Effort: MEDIUM

## 15. Distinct WebSearch and WebFetch tools

- What it does in claw-code: `rust/crates/tools/src/lib.rs` separates `WebSearch` from `WebFetch`. Search returns discovery results and basic metadata, while fetch normalizes a specific URL and returns extracted text suitable for model consumption.
- Why it matters for Hephaestus: The Hephaestus agentic-chat spec already includes `web_search`, but browsing work becomes much cleaner when discovery and document retrieval are separate operations with different budgets and safety rules.
- How we would integrate it into Hephaestus specifically: Split the current `web_search` concept in `docs/AGENTIC-CHAT-SPEC.md` and `src/hephaestus/cli/agent_chat.py` into `web_search` and `web_fetch`. Add source metadata, domain filters, and fetch-size controls. This will improve research mode, prior-art investigation, and competitor scans.
- Priority: HIGH
- Effort: MEDIUM

## 16. Structured output as a first-class tool/runtime mode

- What it does in claw-code: `rust/crates/tools/src/lib.rs` exposes `StructuredOutput`, and `rust/crates/rusty-claude-cli/src/main.rs` can run prompt mode while still producing a final structured object from the full tool loop.
- Why it matters for Hephaestus: Hephaestus already produces structured internal data in the genesis pipeline. Extending that discipline to interactive mode would make exports, downstream automation, and evaluation far more reliable.
- How we would integrate it into Hephaestus specifically: Add schema-driven output modes for common Hephaestus tasks: invention brief, experiment plan, implementation plan, market analysis, and design review. Use them in `/export`, API mode, and batch generation workflows.
- Priority: MEDIUM
- Effort: MEDIUM

## 17. Built-in code execution REPL tool

- What it does in claw-code: `rust/crates/tools/src/lib.rs` includes `REPL`, which can run short snippets in languages like Python, JavaScript, and shell when supported by the environment.
- Why it matters for Hephaestus: Invention analysis often needs quick calculations, simulation snippets, text transforms, or JSON massaging. Right now Hephaestus has a calculator tool idea but not a general execution surface.
- How we would integrate it into Hephaestus specifically: Start small with a sandboxed Python evaluator for numeric reasoning and lightweight data processing, exposed only in interactive/agent mode. Keep it separate from full shell execution.
- Priority: MEDIUM
- Effort: MEDIUM

## 18. Notebook-aware editing

- What it does in claw-code: `rust/crates/tools/src/lib.rs` includes `NotebookEdit` for replacing, inserting, and deleting notebook cells by cell ID or relative position.
- Why it matters for Hephaestus: If Hephaestus is used for research-heavy workflows, notebook-native edits are much better than treating `.ipynb` as raw JSON.
- How we would integrate it into Hephaestus specifically: Add notebook support only if coding workflows become a core use case. Keep it as a separate optional tool package rather than mixing it into invention core logic.
- Priority: LOW
- Effort: MEDIUM

## 19. Shared slash-command registry

- What it does in claw-code: `rust/crates/commands/src/lib.rs` defines a central command registry for commands like `help`, `status`, `compact`, `model`, `permissions`, `clear`, `cost`, `resume`, `config`, `memory`, `init`, `diff`, `version`, `export`, and `session`.
- Why it matters for Hephaestus: `src/hephaestus/cli/repl.py` already supports many commands, but they are implemented directly in the REPL. A shared registry would make help text, parser behavior, validation, and future extensions more coherent.
- How we would integrate it into Hephaestus specifically: Refactor slash commands into `src/hephaestus/cli/commands.py` with structured metadata: name, aliases, args, mode availability, help, and handler. Then let both REPL and any future TUI/API surface reuse the same command definitions.
- Priority: HIGH
- Effort: MEDIUM

## 20. Resume-safe command subsets and persistent project sessions

- What it does in claw-code: `rust/crates/commands/src/lib.rs` distinguishes commands safe to use during resumed sessions, and `rust/crates/rusty-claude-cli/src/main.rs` persists sessions under `.claude/sessions/` with list/switch/resume support.
- Why it matters for Hephaestus: The interactive-mode spec talks about save/load, but project-local durable sessions are more ergonomic than manual named saves alone. Resume safety also matters once tools and long-lived sessions exist.
- How we would integrate it into Hephaestus specifically: Store session records under `.hephaestus/sessions/` in the workspace, with explicit session IDs and metadata. Add `/session list`, `/session switch`, and `/resume`. Mark commands that mutate model context or filesystem state so resume logic can gate them appropriately.
- Priority: HIGH
- Effort: MEDIUM

## 21. Rich streaming terminal renderer

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/render.rs` handles streaming markdown, headings, tables, code blocks, spinners, and tool result cards. `main.rs` uses it to keep the operator aware of what the model is doing.
- Why it matters for Hephaestus: The existing Rich display in `src/hephaestus/cli/display.py` is already good for invention stages, but agent mode will benefit from clearer tool-activity visualization, partial streaming, and session diagnostics.
- How we would integrate it into Hephaestus specifically: Extend the current Rich display layer to render tool invocations, permission prompts, fetched sources, compaction events, and session state changes. Keep invention-stage rendering distinct from tool-loop rendering so the UX does not collapse into generic chatbot output.
- Priority: MEDIUM
- Effort: MEDIUM

## 22. Better multiline input and command completion ergonomics

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/input.rs` provides slash-command completion, multiline input with `Shift+Enter` or `Ctrl+J`, and graceful handling of interrupts and EOF.
- Why it matters for Hephaestus: Long invention prompts, research briefs, and refinement instructions are common. Input friction directly hurts the value of interactive mode.
- How we would integrate it into Hephaestus specifically: Improve the prompt-toolkit setup in `src/hephaestus/cli/repl.py` to support multiline editing, command completion from the central registry, context-aware suggestions, and better interrupt recovery.
- Priority: MEDIUM
- Effort: SMALL

## 23. Project initialization command

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/init.rs` can bootstrap `.claude/`, add config files, create starter instructions, and adjust `.gitignore`.
- Why it matters for Hephaestus: Once workspace-local instructions, sessions, and skills exist, users need a clean way to set them up without manual file spelunking.
- How we would integrate it into Hephaestus specifically: Add `/init` or `hephaestus init` to create `.hephaestus/`, a starter instructions file, session directory, optional skill directory, and sensible ignore patterns. If the workspace is clearly a software repo, the initializer can propose coding-oriented defaults; otherwise it can propose invention/research defaults.
- Priority: MEDIUM
- Effort: SMALL

## 24. Config, memory, and diff reports as first-class operator surfaces

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/main.rs` includes commands and renderers for config reports, memory reports, and diff reports. It can show loaded config files, discovered instruction files, and change summaries.
- Why it matters for Hephaestus: Transparent state inspection reduces operator confusion, especially once the runtime starts layering workspace instructions, saved sessions, tools, and compaction.
- How we would integrate it into Hephaestus specifically: Extend `/status`, `/usage`, and `/context` in `src/hephaestus/cli/repl.py` to show loaded config layers, discovered instruction files, active tool profile, compaction state, and any current repo-diff summary when in coding mode.
- Priority: MEDIUM
- Effort: SMALL

## 25. Layered configuration precedence

- What it does in claw-code: `rust/crates/runtime/src/config.rs` loads config from multiple locations with clear precedence, including user-global, project, and local override files. It extracts typed settings such as model, permission mode, sandbox settings, MCP servers, and OAuth.
- Why it matters for Hephaestus: `src/hephaestus/cli/config.py` already manages a user config and onboarding flow, but it lacks a strong layered project-local override model.
- How we would integrate it into Hephaestus specifically: Add config layering for `~/.hephaestus/config.yaml`, project `.hephaestus/config.yaml`, and `.hephaestus/local.yaml`. Project config should control default model/backend, mode defaults, active tool profile, web policy, workspace instructions policy, and session behavior.
- Priority: HIGH
- Effort: MEDIUM

## 26. MCP stdio integration

- What it does in claw-code: `rust/crates/runtime/src/mcp_stdio.rs` manages stdio MCP servers, initializes them, discovers tools, and calls them via JSON-RPC. `rust/crates/runtime/src/mcp_client.rs` defines transport/bootstrap types, and `rust/crates/runtime/src/mcp.rs` normalizes tool naming and server signatures.
- Why it matters for Hephaestus: MCP is the cleanest path to extensible tools without baking every integration into the core repo. Hephaestus could gain research, design, issue-tracking, or internal-company tools with much less bespoke code.
- How we would integrate it into Hephaestus specifically: Add optional MCP support to the tool registry. Start with stdio-only servers and a conservative allowlist in config. Tool names should be namespaced by server. Show connected servers and discovered tools in `/tools` or `/status`.
- Priority: HIGH
- Effort: LARGE

## 27. MCP server identity normalization and config hygiene

- What it does in claw-code: `rust/crates/runtime/src/mcp.rs` normalizes names, derives stable identifiers, and handles signature-like metadata so MCP tools remain traceable even when transport details differ.
- Why it matters for Hephaestus: Once multiple external tool providers exist, sloppy naming becomes a debugging and auditing problem very quickly.
- How we would integrate it into Hephaestus specifically: Adopt stable names like `server_name.tool_name`, persist server identity in session metadata, and include source server information in tool results and exports. This makes tool provenance visible in long research sessions.
- Priority: MEDIUM
- Effort: SMALL

## 28. OAuth and startup auth-source resolution

- What it does in claw-code: `rust/crates/runtime/src/oauth.rs` handles PKCE and credential storage, while `rust/crates/api/src/client.rs` can resolve whether auth comes from env vars, stored OAuth, or refreshed tokens.
- Why it matters for Hephaestus: Hephaestus currently supports multiple backends, but auth handling can become messy when local CLI backends, direct APIs, and future remote/MCP services coexist.
- How we would integrate it into Hephaestus specifically: Centralize backend credential resolution in `src/hephaestus/cli/config.py` or a new `src/hephaestus/auth/` module. Make `/status` show which auth source is active for each backend. This is especially useful if Hephaestus expands beyond Anthropic/OpenRouter-style flows.
- Priority: MEDIUM
- Effort: MEDIUM

## 29. Resilient API client with retries and streaming support

- What it does in claw-code: `rust/crates/api/src/client.rs`, `rust/crates/api/src/error.rs`, and `rust/crates/api/src/sse.rs` provide retryable vs non-retryable error classification, streaming event parsing, and startup auth resolution.
- Why it matters for Hephaestus: Long invention generations and agentic tool loops are vulnerable to transient failures. A stronger client layer reduces flaky sessions and odd partial-state bugs.
- How we would integrate it into Hephaestus specifically: Audit existing backend adapters and normalize retry, timeout, and streaming behavior. Preserve partial turn state in sessions so transient failures do not force complete restarts. This is especially important for multi-stage genesis runs with expensive context.
- Priority: HIGH
- Effort: MEDIUM

## 30. Agent tool with persisted sub-agent artifacts

- What it does in claw-code: `rust/crates/tools/src/lib.rs` includes an `Agent` tool that can create agent work products and persist output artifacts in `.clawd-agents`. Snapshot inventories in `src/reference_data/tools_snapshot.json` and `src/reference_data/commands_snapshot.json` also show broader agent-oriented surfaces.
- Why it matters for Hephaestus: Hephaestus has multiple conceptual phases already. Some research or implementation tasks could benefit from bounded specialist agents instead of one monolithic loop.
- How we would integrate it into Hephaestus specifically: Do not start with open-ended swarms. Start with one bounded sub-agent pattern for clearly isolated tasks, such as prior-art search, literature extraction, or implementation-plan drafting. Persist their outputs under `.hephaestus/agents/` and make them reviewable before incorporation.
- Priority: MEDIUM
- Effort: LARGE

## 31. Tool discovery and deferred tool loading

- What it does in claw-code: `rust/crates/tools/src/lib.rs` includes `ToolSearch`, and the Python parity layer in `src/tool_pool.py` and `src/reference_data/tools_snapshot.json` treats tool inventory as a searchable pool rather than a hard-coded fixed list.
- Why it matters for Hephaestus: As the tool surface grows, the model should not always see every possible tool. Discoverability helps keep prompts smaller and tool choice sharper.
- How we would integrate it into Hephaestus specifically: Add a registry that can load core tools eagerly and optional integrations lazily. In long sessions, the model can search for available capabilities before loading them. This matters more once MCP and skills are introduced.
- Priority: MEDIUM
- Effort: MEDIUM

## 32. Hooks and event surfaces

- What it does in claw-code: This is mostly a snapshot-only feature. `src/reference_data/subsystems/hooks.json` and command snapshots indicate a hooks system around notifications, tool permissions, and lifecycle events, but `PARITY.md` makes clear that not all of it is active in the Rust runtime.
- Why it matters for Hephaestus: Hephaestus has clearly defined stages and will likely benefit from internal events such as "stage started", "stage finished", "tool called", "compaction triggered", and "session resumed".
- How we would integrate it into Hephaestus specifically: Add an internal event bus first, not a public plugin hook API. Emit events from `src/hephaestus/core/genesis.py`, `src/hephaestus/cli/repl.py`, and the future agent runtime for logging, metrics, UI updates, and optional policy modules.
- Priority: MEDIUM
- Effort: MEDIUM

## 33. Plugin surface and external capability packaging

- What it does in claw-code: This is partly active and partly aspirational. The runtime has MCP-related infrastructure, while `src/reference_data/subsystems/plugins.json` and command snapshots expose a broader plugin concept. `PARITY.md` indicates plugin parity is incomplete.
- Why it matters for Hephaestus: Hephaestus will eventually outgrow a single baked-in tool set if it wants to support research, engineering, commercialization, and design workflows without bloating the core repo.
- How we would integrate it into Hephaestus specifically: Do not build a full plugin marketplace yet. First support three extension classes: built-in tools, MCP servers, and local skill bundles. If that stabilizes, then define a real plugin manifest later.
- Priority: LOW
- Effort: LARGE

## 34. Task and team orchestration surfaces

- What it does in claw-code: Snapshot manifests in `src/reference_data/commands_snapshot.json` and `src/reference_data/tools_snapshot.json` expose commands and tools for `tasks`, `team`, and multi-agent behaviors, but the active Rust runtime only has a more modest `Agent` tool and supporting runtime pieces.
- Why it matters for Hephaestus: There is value in task decomposition, but uncontrolled orchestration would cut against Hephaestus's deliberate invention style and add major operational complexity.
- How we would integrate it into Hephaestus specifically: Import the bounded-task mindset, not the full orchestration surface. Use explicit task objects and optional specialist agents only where the decomposition is obvious and reviewable.
- Priority: LOW
- Effort: LARGE

## 35. Semantic and LSP-oriented tooling

- What it does in claw-code: This is snapshot-only. Tool manifests in `src/reference_data/tools_snapshot.json` include LSP-oriented capabilities even though they are not part of the active minimal Rust tool set.
- Why it matters for Hephaestus: If Hephaestus becomes a serious coding assistant, semantic code search and symbol-aware edits will outperform plain grep and file scanning.
- How we would integrate it into Hephaestus specifically: Keep it out of invention core. If coding mode matures, add LSP-backed read-only tools first: symbol lookup, reference search, and diagnostics. Only later consider semantic edits.
- Priority: LOW
- Effort: LARGE

## 36. Compatibility manifests and runtime introspection

- What it does in claw-code: The Python parity layer in `src/commands.py`, `src/tools.py`, `src/port_manifest.py`, `src/query_engine.py`, `src/runtime.py`, and `rust/crates/compat-harness/src/lib.rs` treats command and tool inventories as introspectable data. `src/reference_data/commands_snapshot.json` and `src/reference_data/tools_snapshot.json` are machine-readable snapshots of the runtime surface.
- Why it matters for Hephaestus: A tool-rich system becomes easier to test, document, and explain if commands and tools can be enumerated automatically rather than maintained manually in help text and docs.
- How we would integrate it into Hephaestus specifically: Generate a manifest from the command registry and tool registry for `/help`, docs generation, UI introspection, and regression tests. This is more valuable than porting the compatibility harness itself.
- Priority: MEDIUM
- Effort: SMALL

## 37. Remote transport and environment bootstrap

- What it does in claw-code: `rust/crates/runtime/src/remote.rs`, `rust/crates/runtime/src/mcp_client.rs`, and parts of the Python parity layer such as `src/remote_runtime.py` describe remote session environments and transport bootstrap strategies.
- Why it matters for Hephaestus: This is not immediately necessary, but if Hephaestus ever runs as a hosted or distributed agent rather than a purely local CLI, a transport boundary will matter.
- How we would integrate it into Hephaestus specifically: Treat this as future-proofing only. Keep the internal runtime interface transport-agnostic so local CLI and future remote orchestration could share core logic. Do not build remote transport now.
- Priority: LOW
- Effort: LARGE

## 38. Direct mode separation between prompt mode and REPL mode

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/main.rs` cleanly separates single-shot prompt mode, REPL mode, resume mode, login/logout, init, and metadata-oriented commands, but still routes prompt mode through the same underlying runtime.
- Why it matters for Hephaestus: Hephaestus currently centers the REPL and staged pipeline. A cleaner distinction between batch generation, interactive refinement, and agentic workspace mode would reduce feature entanglement.
- How we would integrate it into Hephaestus specifically: Keep `genesis` as the batch invention engine, use the REPL for interactive invention refinement, and introduce a clearer `agent` or `workspace` mode for tool-using work. All three should share session and prompt infrastructure where possible.
- Priority: MEDIUM
- Effort: MEDIUM

## 39. Memory reporting as a transparency feature

- What it does in claw-code: `rust/crates/rusty-claude-cli/src/main.rs` can render a memory report showing discovered instruction sources and memory-like context inputs rather than hiding them.
- Why it matters for Hephaestus: `src/hephaestus/memory/anti_memory.py` is unusual and important. Users will trust it more if they can see what anti-memory items were retrieved and how they affected generation.
- How we would integrate it into Hephaestus specifically: Expand `/context` and `/status` to show anti-memory hits, loaded instruction files, pinned context, and any compaction summaries currently in effect. That will make Hephaestus feel like a controlled instrument rather than an opaque chatbot.
- Priority: HIGH
- Effort: SMALL

## 40. Clear separation between core runtime and CLI presentation

- What it does in claw-code: The runtime crates (`runtime`, `api`, `tools`, `commands`) are cleanly separated from the terminal app crate (`rusty-claude-cli`). The Python parity layer mirrors the same idea by keeping query/runtime abstractions separate from CLI wrappers.
- Why it matters for Hephaestus: Some Hephaestus code still mixes session logic, command handling, and rendering in the REPL layer. That is manageable today but will get painful as modes multiply.
- How we would integrate it into Hephaestus specifically: Push more logic out of `src/hephaestus/cli/repl.py` into reusable modules: `session`, `commands`, `agent runtime`, `tools`, and `display`. Keep the REPL thin and mode-specific.
- Priority: HIGH
- Effort: MEDIUM

## Not Worth Porting

These are parts of `claw-code` that are specific to its parity mission, branding, or implementation strategy and should not be copied directly into Hephaestus.

### 1. The Python parity runtime as product architecture

- What it is in claw-code: Files like `src/runtime.py`, `src/query_engine.py`, `src/commands.py`, `src/tools.py`, `src/port_manifest.py`, and related modules provide a mirrored or compatibility-oriented surface over command and tool inventories.
- Why it is not worth porting: Hephaestus does not need a mirror of another product. The useful idea is runtime introspection, not the parity scaffolding itself.

### 2. Compatibility harness aimed at upstream parity

- What it is in claw-code: `rust/crates/compat-harness/src/lib.rs` extracts manifests and bootstrap plans from another source tree.
- Why it is not worth porting: Hephaestus should not spend complexity on mirroring an upstream command universe. If you want manifests, generate them from Hephaestus itself.

### 3. Claude-specific branding and file naming

- What it is in claw-code: `CLAUDE.md`, `.claude/`, `.claude.json`, and other naming choices are built around the source product's identity.
- Why it is not worth porting: The pattern is useful; the branding is not. Hephaestus should use its own naming and mental model.

### 4. Duplicate or transitional CLI entrypoints

- What it is in claw-code: There are older or smaller paths such as `rust/crates/rusty-claude-cli/src/app.rs` and `src/args.rs` alongside the main runtime flow in `main.rs`.
- Why it is not worth porting: Hephaestus should not inherit transitional structure. Keep one primary CLI path.

### 5. PowerShell parity on day one

- What it is in claw-code: `rust/crates/tools/src/lib.rs` exposes a `PowerShell` tool for Windows parity.
- Why it is not worth porting: Hephaestus should focus on one clean shell/tool execution model first. Add Windows-specific shell parity only when there is real demand.

### 6. Remote transport layers before local runtime maturity

- What it is in claw-code: `rust/crates/runtime/src/remote.rs` and related parity files show transport abstraction and remote session plumbing.
- Why it is not worth porting: Hephaestus is not blocked on remote execution today. Building it now would distract from higher-value local runtime architecture.

### 7. Broad plugin marketplace ambitions before MCP and skills stabilize

- What it is in claw-code: Snapshot files such as `src/reference_data/subsystems/plugins.json` and command manifests suggest a larger plugin surface, but `PARITY.md` shows it is not a finished active system.
- Why it is not worth porting: Hephaestus should stabilize built-in tools, skills, and MCP before inventing a broader plugin ecosystem.

### 8. Open-ended task/team/multi-agent surface area

- What it is in claw-code: Snapshot manifests advertise team and task orchestration beyond the actively implemented runtime.
- Why it is not worth porting: Hephaestus needs bounded specialist agents at most, not a large autonomous orchestration layer. The latter would dilute product focus and raise verification costs sharply.

### 9. Exact on-disk artifact conventions

- What it is in claw-code: Files and directories like `.clawd-todos.json` and `.clawd-agents`.
- Why it is not worth porting: The pattern is useful; the exact storage scheme is not. Hephaestus should define its own session and artifact layout.

### 10. Voice, teleport, and other snapshot-only novelty surfaces

- What it is in claw-code: Snapshot manifests expose commands such as `voice` and `teleport` that are not central to the active runtime examined here.
- Why it is not worth porting: They do not address Hephaestus's actual bottlenecks in invention, session management, or tool safety.

## Top 10 recommended imports for Hephaestus

### 1. Session compaction with continuation summaries

- Why this ranks first: Hephaestus is built for long, information-dense sessions. Without compaction, interactive and agentic mode will degrade fast under token pressure.
- Main claw-code sources: `rust/crates/runtime/src/compact.rs`, `rust/crates/runtime/src/session.rs`

### 2. Layered instruction discovery plus budgeted prompt assembly

- Why this ranks second: This is the cleanest way to let Hephaestus adapt to the local workspace without bloating the core system prompt.
- Main claw-code sources: `rust/crates/runtime/src/prompt.rs`

### 3. Shared conversation runtime with pluggable tools and permissions

- Why this ranks third: It is the architectural move that prevents agent mode from becoming a pile of one-off handlers in `agent_chat.py`.
- Main claw-code sources: `rust/crates/runtime/src/conversation.rs`, `rust/crates/runtime/src/permissions.rs`

### 4. Structured session schema and project-local resume

- Why this ranks fourth: Hephaestus already has save/load concepts; formalizing them into durable project sessions unlocks resume, export, and compaction.
- Main claw-code sources: `rust/crates/runtime/src/session.rs`, `rust/crates/rusty-claude-cli/src/main.rs`

### 5. Layered config precedence

- Why this ranks fifth: Workspace-local behavior matters for invention, research, and coding tasks. User-global config alone is too blunt.
- Main claw-code sources: `rust/crates/runtime/src/config.rs`

### 6. Structured file and web tools with allowed-tool profiles

- Why this ranks sixth: Safer and more controllable tools are a prerequisite for growing Hephaestus beyond read-only chat.
- Main claw-code sources: `rust/crates/runtime/src/file_ops.rs`, `rust/crates/tools/src/lib.rs`, `rust/crates/rusty-claude-cli/src/main.rs`

### 7. Explicit todo-based working memory

- Why this ranks seventh: It is a small implementation with high leverage for multi-step agent work and verification discipline.
- Main claw-code sources: `rust/crates/tools/src/lib.rs`

### 8. MCP stdio integration

- Why this ranks eighth: This is the best medium-term path to extensibility without overgrowing the core repository.
- Main claw-code sources: `rust/crates/runtime/src/mcp_stdio.rs`, `rust/crates/runtime/src/mcp_client.rs`, `rust/crates/runtime/src/mcp.rs`

### 9. Shared slash-command registry and better operator ergonomics

- Why this ranks ninth: Hephaestus already has a strong REPL. Centralizing commands and improving input/rendering will make future growth manageable.
- Main claw-code sources: `rust/crates/commands/src/lib.rs`, `rust/crates/rusty-claude-cli/src/input.rs`, `rust/crates/rusty-claude-cli/src/render.rs`

### 10. Memory transparency surfaces

- Why this ranks tenth: Hephaestus has an unusual differentiator in anti-memory. Showing the operator what memory and instructions are active will materially improve trust and debuggability.
- Main claw-code sources: `rust/crates/rusty-claude-cli/src/main.rs`, `rust/crates/runtime/src/prompt.rs`

## Bottom line

The best `claw-code` imports for Hephaestus are mostly runtime discipline layers, not flashy end-user features:

- prompt and context loading
- session persistence and compaction
- tool permissions and tool profiles
- structured tool/runtime abstraction
- project-local config and sessions
- operator transparency around memory, context, and cost

The lowest-value imports are parity scaffolding, unfinished plugin ambitions, and snapshot-only novelty surfaces. Hephaestus should borrow the architecture patterns, keep its own product identity, and stay centered on invention quality.
