# Phase 2 — Native Codex OAuth Integration Plan

## Research findings

### What OpenClaw actually does
- Treats Codex as a dedicated provider: `openai-codex`
- Uses OAuth credentials (`access`, `refresh`, `expires`, `accountId`)
- Refreshes via `@mariozechner/pi-ai/dist/utils/oauth/openai-codex.js`
- Provider base URL: `https://chatgpt.com/backend-api`
- Provider API type: `openai-codex-responses`
- Uses OpenClaw / pi-ai provider transport wrappers, not raw `requests.post`

### Key discovery
A direct bearer request from Python to `https://chatgpt.com/backend-api/responses` returns 403 HTML. So the transport contract is more complex than just a bearer token. The safe/real path is to use the same pi-ai provider stack OpenClaw uses.

## Execution strategy

### Phase 2A — Native bridge via OpenClaw/pi-ai provider stack
Goal: replace `codex exec` with a direct provider call using OAuth credentials and OpenClaw's provider transport.

1. Add a Node helper script (`scripts/codex_oauth_bridge.mjs`) that:
   - imports `@mariozechner/pi-ai`
   - imports `@mariozechner/pi-ai/oauth`
   - loads/refreshes Codex OAuth credentials from `~/.codex/auth.json`
   - constructs an `openai-codex-responses` model with baseUrl `https://chatgpt.com/backend-api`
   - performs direct generation through the provider stack
   - emits clean JSON to stdout

2. Add Python adapter `CodexOAuthAdapter` that:
   - calls the bridge script instead of `codex exec`
   - supports structured output
   - supports streaming (JSONL mode from bridge)
   - records usage/cost fields where available

3. Keep `CodexCliAdapter` as fallback if the bridge fails.

### Phase 2B — Harness parity
4. Add `generate_with_tools` support in `CodexOAuthAdapter`
5. Add native streaming chunks instead of fake post-hoc streaming
6. Add usage tracking parity (tokens if provider returns them, otherwise zeros)
7. Default `codex` preset to native OAuth adapter, fallback to CLI only on failure

## Why this plan
- Uses the same auth/refresh implementation OpenClaw uses
- Uses the same provider transport layer OpenClaw uses
- Avoids re-implementing hidden ChatGPT backend behavior in Python
- Gives us a genuinely native routed model path inside the Hephaestus harness
