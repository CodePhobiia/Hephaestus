# Changelog

All notable changes to Hephaestus are documented in this file.

## [Unreleased]

### Added — Core Pipeline
- 5-stage genesis pipeline: Decompose → Search → Score → Translate → Verify
- Cross-domain structural transfer with 160+ cognitive lenses
- DeepForge anti-training pressure system
- Adversarial novelty verification (cross-model)
- Prior art search (Semantic Scholar, patent databases)
- Novelty proof generation with formal statements
- V2 system prompt with divergence intensity and output modes
- Load-bearing domain check (heuristic + critique harness)
- Candidate diversity scoring with negative correlation penalty
- Solution shape detection (novelty module)
- Convergence tracking across sessions
- Error recovery with partial results and checkpoints
- Parallel execution with semaphore-based concurrency
- Retry logic with exponential backoff for API calls
- Input validation with injection detection

### Added — CLI
- `heph` command with rich terminal output
- `heph init` — initialize project configuration
- `heph batch` — process multiple problems from a file
- `heph lenses` — lens library statistics and validation
- `--intensity` flag (STANDARD, AGGRESSIVE, MAXIMUM)
- `--output-mode` flag (MECHANISM, FRAMEWORK, NARRATIVE, SYSTEM, PROTOCOL, TAXONOMY, INTERFACE)
- `--trace` flag for full reasoning trace
- `--raw` flag for direct DeepForge access
- `--quiet` flag for minimal output
- Score visualization with unicode/ASCII bars
- Confidence analysis in output
- Implementation roadmap generation

### Added — Interactive REPL
- Full interactive mode with 22+ slash commands
- Session recording with typed transcript schema
- Working-memory todo list (/todo, /plan)
- Auto-compaction with continuation summaries
- Command registry with tab completion
- Memory/context transparency (/status, /context)
- Refinement, domain hinting, deeper search
- Invention save/load/compare/export
- Agent chat mode with tool-using sessions

### Added — Runtime & Infrastructure
- Layered configuration (defaults < user < project < local < env)
- Session management with typed schema and persistence
- Tool registry with 5 built-in profiles
- Permission system (READ_ONLY, WORKSPACE_WRITE, FULL_ACCESS)
- MCP stdio integration (JSON-RPC 2.0 client + multi-server manager)
- File operations (read, write, list, search, grep)
- Web tools (search, fetch)
- Conversation runtime with pluggable adapters
- Instruction discovery and budgeted prompt assembly
- Dynamic context boundary markers

### Added — Output & Export
- Markdown, JSON, and plain text output formats
- Publication-ready markdown export with configurable sections
- Score bars, confidence tables, implementation roadmaps
- Prior art and novelty proof rendering
- Alternative inventions display

### Added — Analytics
- Invention history with JSONL persistence
- Analytics summary (success rates, domain usage, cost trends)
- Failure logging

### Added — SDK
- Python SDK client (sync)
- Async SDK client with invent() and invent_stream()

### Added — Quality
- 160+ domain lenses across 15+ knowledge families
- Lens validation and statistics
- 1100+ tests with comprehensive coverage
- .gitignore, CI-ready project structure
