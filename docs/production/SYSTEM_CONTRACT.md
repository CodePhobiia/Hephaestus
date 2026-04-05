# Hephaestus System Contract

## Core Principles

Hephaestus is an autonomous invention pipeline. This contract prevents architectural drift by defining immutable boundaries that all current and future implementations must respect.

### 1. The Principle of Durability
No critical path or state mutation is allowed to reside purely in-memory. If a user triggers an invention (via CLI, SDK, or Web), that request MUST enter the `RunStore` as a durable `RunRecord`. Wait states, stage transitions, and cancellations are managed persistently.

### 2. The Principle of Truth-in-Surface
Documentation, web UI bounds, schema limits, CLI arguments, and internal Python constants must not drift. If `depth=3` specifies 8 search candidates in the `DepthPolicyTable`, the documentation array and manifestation must precisely declare this. "Fake controls" and decorative parameters are forbidden.

### 3. The Principle of Failsafe Extensibility
Web Tools, Local Executables, and MCP integrations operate across a strict boundary via the canonical `ToolInvocation` ABI. The runtime assumes all tools are untrusted, fallible, and asynchronous. Async code executed within tool envelopes must safely await resolution without polluting the core loop.

### 4. The Principle of Pantheon Ledgering
AI deliberation cannot rely merely on text summaries or prompt strings to track state. Pantheon decisions (vetoes, modifications, approvals) must map accurately into an authoritative state ledger that verifies the objection ID and its causal resolution. 

### 5. The Principle of Modular Capabilities
While dependencies like `asyncpg` or the Anthropics SDK must be available for production modes, they are separated via extras or lazy imports such that the `hephaestus.core` libraries do not import-fail locally on missing 3rd party vendor binaries unless specifically engaged. 
