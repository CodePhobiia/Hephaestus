# UX Audit Round 2

Date: 2026-04-01

Scope:
- `src/hephaestus/cli/repl.py`
- `src/hephaestus/cli/main.py`
- `src/hephaestus/cli/display.py`
- `src/hephaestus/cli/config.py`
- `src/hephaestus/output/formatter.py`

## Summary

This round focused on the remaining user-facing rough edges in the CLI and REPL, especially for SSH-first usage where the terminal is the whole product surface. The work prioritized:

- making failures readable instead of leaking raw exception details
- fixing broken or misleading interactive flows
- tightening onboarding and command discoverability
- improving empty states and status clarity
- making saved and reloaded work feel first-class instead of partial

## Fixes Shipped

### 1. REPL prompt, onboarding, and discoverability

- Reworked the interactive help text to lead with quick-start guidance, menu usage, tab completion, and exit controls.
- Switched the REPL prompt to a compact `heph>` / `heph[slug]>` form that reads cleanly over SSH.
- Improved the first-run onboarding copy so it explains what backend selection means, where config is stored, and how to change it later.
- Added backend readiness hints to `/status`, `/backend`, and the REPL welcome block.
- Made `/usage` describe actual session telemetry instead of showing a misleading “token usage” table with mostly empty data.

### 2. Model/backend selection now behaves like the UI says it does

- Fixed the interactive session config builder so `/model` actually affects the next run.
- Fixed OpenRouter sessions so the REPL now passes `OPENROUTER_API_KEY` into the pipeline instead of silently behaving like plain API mode.
- Added support for preset model keywords (`opus`, `gpt5`, `both`) inside interactive mode.
- Added guardrails so switching between explicit Claude backends and preset model strategies does not leave the REPL in an invalid state.

### 3. Broken menu and command flows

- Fixed the numbered post-run menu so option `7` is now reachable from the REPL loop.
- Improved menu copy around “try different problem” and source-domain reruns.
- Added export format validation so bad values fail with a short correction instead of silently defaulting.
- Improved `/context`, `/alternatives`, `/compare`, and history empty states with concrete next actions.

### 4. Save/load and session restore

- `/load` now supports direct JSON file paths as advertised, not just fuzzy names.
- Loading a saved invention now activates it inside the current session instead of only printing a summary.
- Loading a session replay now restores the session inventions into usable REPL state, including the active invention pointer.
- Added clearer load success messages that tell the user what they can do next (`1`, `/history`, `/compare`, `/export`).
- Surfaced autosave more clearly by showing the saved snapshot name after a successful run.

### 5. Error handling and stack-trace suppression

- Wrapped CLI dispatch and streaming pipeline execution so unexpected exceptions become user-facing errors with hints instead of tracebacks.
- Hardened REPL command execution and problem runs to keep failures inside the terminal UX.
- Sanitized save/load/export failures into actionable messages about JSON validity, write permissions, credentials, or network issues.
- Removed duplicate exit summaries when leaving via `/quit`.

### 6. Display and formatter resilience

- Made invention display sections degrade gracefully when saved/reloaded reports only have partial data.
- Hardened adversarial verification, cost tables, traces, and quiet output against missing fields.
- Improved formatter fallbacks so exported Markdown/plain-text reports do not leak `None` or blank sections.
- Fixed the lightweight Markdown-to-HTML export path to emit valid `<ul>...</ul>` list markup for PDF exports.

## Tests Added/Extended

- `tests/test_cli/test_repl.py`
  - explicit-path `/load`
  - session replay restoration into active REPL state
  - invalid export format handling
  - menu option `7`
  - HTML list conversion for export
  - config persistence for `divergence_intensity` and `output_mode`

- `tests/test_cli/test_main.py`
  - unexpected pipeline exception handling without traceback leakage

## Verification

Run:

```bash
pytest
```
