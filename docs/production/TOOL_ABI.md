# Tool ABI Contract

This ABI enforces how the agent accesses tools, MCP servers, and local OS commands. Any tool not complying with this standard is rejected at the registry layer.

## The ToolInvocation Model

All tool usage executes via `ToolInvocation`. Raw `kwargs` handling directly into function references is banned.

`ToolInvocation` manages:
* `tool_name`: Must match the registry exact name.
* `args`: Sanitized JSON dictionaries.
* `context`: Provides system environment constraints.
* `run_id`: Maps the tool run back to the durable Orchestrator run record.
* `timeout`: Enforces a maximum duration per tool execution.

## The ToolResult Model
Returns are normalized. Unhandled exceptions are caught and structured.
* `ok`: Boolean.
* `content`: The output schema or raw string.
* `error_code` & `error_detail`: Only populated if `ok=False`. Tracebacks are truncated to prevent context flooding.
* `metadata`: E.g., time elapsed, MCP server provenance.

## Async Enforcement
The async runtime assumes concurrency. Asynchronous tools (e.g. `web_search` and `web_fetch`) are executed natively via `await`. Tools executing `asyncio.run(...)` internally while inside a running event loop will cause strict runtime `RuntimeError` failure. The fallback wrapper evaluates whether a tool is a coroutine function and handles bridging appropriately.

## Permission Schema
Permissions do NOT use hardcoded list checks.
Every `ToolDefinition` must explicitly declare:
* `category`: (e.g. `web`, `local_fs`, `system`).
* `risk_level`: `safe`, `moderate`, `dangerous`.
* `requires_network`: Boolean.
* `requires_filesystem`: Boolean.
* `requires_write`: Boolean.

`permissions.py` evaluates these metadata properties. Unrecognized tools default implicitly to the highest risk band (`dangerous`) and explicitly fail-deny execution if unsupported.
