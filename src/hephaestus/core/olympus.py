"""
Olympus — Stage 0 repo-awareness engine for Hephaestus.

Olympus doesn't scan-and-paste. It *explores*. When invoked, the Hephaestus
agent gets tools (read_file, list_directory, grep_search, search_files) and
walks the codebase itself — following imports, reading files it finds
interesting, building understanding organically. Then it writes OLYMPUS.md
from genuine comprehension.

OLYMPUS.md is the AGENTS.md / CLAUDE.md of Hephaestus. Every downstream
agent reads it before doing anything.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OLYMPUS_FILENAME = "OLYMPUS.md"
_CACHE_DIR = ".hephaestus"
_FINGERPRINT_FILE = "olympus_fingerprint.json"
_OLYMPUS_MAX_CHARS = 12_000


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OlympusContext:
    """The result of Stage 0 — repo-grounded problem context."""

    repo_name: str
    root: str
    problem: str
    generated_at: str
    fingerprint: str

    # The synthesized markdown
    olympus_md: str

    # Metadata
    components_mapped: int = 0
    relevant_files: list[str] = field(default_factory=list)
    constraints_from_code: list[str] = field(default_factory=list)
    architecture_summary: str = ""
    elapsed_seconds: float = 0.0
    tool_calls: int = 0
    exploration_rounds: int = 0

    def to_prompt_injection(self, max_chars: int = _OLYMPUS_MAX_CHARS) -> str:
        """Format for injection into any agent's system prompt."""
        header = "=== OLYMPUS — REPO CONTEXT ===\n"
        footer = "\n=== END OLYMPUS ===\n"
        budget = max_chars - len(header) - len(footer)
        body = self.olympus_md[:budget] if len(self.olympus_md) > budget else self.olympus_md
        return header + body + footer


# ---------------------------------------------------------------------------
# System prompt for the Olympus agent
# ---------------------------------------------------------------------------

_OLYMPUS_SYSTEM = """\
You are OLYMPUS, the repo-awareness engine for Hephaestus.

You have tools to explore this repository. USE THEM. Do not guess.
Read files. List directories. Search for patterns. Follow imports.
Build real understanding.

Your job: explore this codebase and produce OLYMPUS.md — a document that
maps the user's problem to the actual code. This document will be read by
every downstream agent (decomposers, searchers, translators, verifiers).

## How to explore

1. Start by listing the root directory to understand the project layout
2. Read README.md and any config files (pyproject.toml, etc.)
3. Identify the core source directories
4. Read the key files — entry points, main modules, the files that matter
5. Follow imports when you see something relevant to the problem
6. Search for patterns related to the problem (grep for keywords)
7. Build a mental map of how the codebase relates to the problem

## What to write

After exploring, output a markdown document with this structure:

# OLYMPUS — Repo Context for [repo name]

## Repo Overview
<2-4 sentences: what this codebase is and does>

## Problem ↔ Codebase Mapping
<Which components/files are directly relevant to the problem and why>

## Current Approach
<How the codebase currently handles the problem area — cite specific files, \
functions, classes, line numbers>

## Architectural Constraints
<What the code structure requires or forbids for any solution>

## Key Files to Study
<Ranked list of files an inventor must understand, with 1-line descriptions>

## Hotspots & Patterns
<What's interesting, what's complex, what's fragile>

## Assumptions a Novel Solution Must Navigate
<Code-level assumptions, API contracts, data flow constraints>

## Rules

- EVERY claim must reference actual files, functions, or patterns you read
- Do NOT make generic software observations
- Do NOT propose solutions — that's the invention engine's job
- Be specific to THIS repo and THIS problem
- If you're unsure about something, read the file instead of guessing
"""

_OLYMPUS_USER = """\
PROBLEM STATEMENT:
{problem}

Explore this repository and produce OLYMPUS.md. Start by listing the \
root directory, then read key files, then search for patterns related \
to the problem. Take your time — deep understanding matters more than speed.
"""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def build_olympus(
    problem: str,
    root: Path,
    adapter: Any,
    *,
    force_rebuild: bool = False,
    persist: bool = True,
    max_tool_rounds: int = 25,
    thinking_budget: int = 16_000,
) -> OlympusContext | None:
    """Build the Stage 0 Olympus context by having the agent explore the repo.

    Parameters
    ----------
    problem:
        The user's problem statement.
    root:
        Path to the repo root.
    adapter:
        LLM adapter (must support ``generate_with_tools``).
    force_rebuild:
        Skip cache and always regenerate.
    persist:
        Write OLYMPUS.md to disk.
    max_tool_rounds:
        Max exploration rounds for the agent.
    thinking_budget:
        Extended thinking token budget.

    Returns
    -------
    OlympusContext or None if not in a repo or generation fails.
    """
    t_start = time.monotonic()

    # ── Step 1: Detect repo ──────────────────────────────────────────────
    if not _is_repo(root):
        logger.info("Olympus: not a repo at %s, skipping", root)
        return None

    # ── Step 2: Check cache ──────────────────────────────────────────────
    fingerprint = _compute_fingerprint(problem, root)
    cache_dir = root / _CACHE_DIR
    olympus_path = cache_dir / OLYMPUS_FILENAME
    fingerprint_path = cache_dir / _FINGERPRINT_FILE

    if not force_rebuild and olympus_path.is_file() and fingerprint_path.is_file():
        try:
            cached_fp = json.loads(fingerprint_path.read_text(encoding="utf-8"))
            if cached_fp.get("fingerprint") == fingerprint:
                logger.info("Olympus: cache hit, loading existing OLYMPUS.md")
                olympus_md = olympus_path.read_text(encoding="utf-8")
                return OlympusContext(
                    repo_name=root.name,
                    root=str(root),
                    problem=problem,
                    generated_at=cached_fp.get("generated_at", ""),
                    fingerprint=fingerprint,
                    olympus_md=olympus_md,
                    elapsed_seconds=0.0,
                )
        except (OSError, json.JSONDecodeError, KeyError):
            pass  # Cache miss, rebuild

    # ── Step 3: Agentic exploration ──────────────────────────────────────
    from hephaestus.deepforge.agentic import RepoToolExecutor, AGENTIC_TOOLS
    from hephaestus.deepforge.adapters.base import ModelCapability

    executor = RepoToolExecutor(root)
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in AGENTIC_TOOLS
    ]

    user_prompt = _OLYMPUS_USER.format(problem=problem)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt},
    ]

    # Extended thinking if supported
    extra_kwargs: dict[str, Any] = {}
    if hasattr(adapter, "config") and adapter.config.supports(ModelCapability.EXTENDED_THINKING):
        extra_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }
        logger.info("Olympus: extended thinking enabled | budget=%d", thinking_budget)

    total_tool_calls = 0
    rounds = 0
    olympus_md = ""

    logger.info("Olympus: starting agentic exploration of %s", root.name)

    for round_idx in range(max_tool_rounds):
        rounds = round_idx + 1

        # On the last 2 rounds, nudge the model to wrap up
        round_tools = tools
        if round_idx >= max_tool_rounds - 2:
            # Remove tools to force the model to produce text output
            round_tools = []
            if round_idx == max_tool_rounds - 2:
                messages.append({
                    "role": "user",
                    "content": (
                        "You've explored enough. Now write the OLYMPUS.md document "
                        "based on everything you've read. Output the full markdown."
                    ),
                })
                logger.info("Olympus: nudging agent to write output (round %d/%d)", rounds, max_tool_rounds)

        try:
            gen = await adapter.generate_with_tools(
                messages,
                system=_OLYMPUS_SYSTEM,
                tools=round_tools,
                max_tokens=32_000,
                temperature=1.0,
                **extra_kwargs,
            )
        except Exception as exc:
            logger.warning("Olympus: API call failed on round %d: %s", rounds, exc)
            break

        # No tool calls → agent is done exploring, has produced output
        if not gen.tool_calls:
            olympus_md = gen.text
            logger.info("Olympus: exploration complete | round=%d tool_calls=%d", rounds, total_tool_calls)
            break

        # Append assistant message
        messages.append({"role": "assistant", "content": gen.content_blocks})

        # Execute tool calls
        tool_results: list[dict[str, Any]] = []
        for tc in gen.tool_calls:
            total_tool_calls += 1
            result_text = executor.execute(tc.name, tc.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_text[:15000],  # Cap individual results
            })
            logger.debug("Olympus tool: %s(%s) → %d chars", tc.name, tc.input.get("path", tc.input.get("query", "")), len(result_text))

        messages.append({"role": "user", "content": tool_results})

        # Capture partial text
        if gen.text:
            olympus_md = gen.text
    else:
        logger.warning("Olympus: hit max exploration rounds (%d)", max_tool_rounds)

    if not olympus_md or len(olympus_md.strip()) < 100:
        logger.warning("Olympus: agent produced empty or trivial output after %d rounds", rounds)
        return None

    elapsed = time.monotonic() - t_start

    # ── Step 4: Persist ──────────────────────────────────────────────────
    if persist:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            olympus_path.write_text(olympus_md, encoding="utf-8")
            fingerprint_path.write_text(
                json.dumps({
                    "fingerprint": fingerprint,
                    "problem": problem[:200],
                    "generated_at": _now_iso(),
                    "elapsed_seconds": round(elapsed, 2),
                    "tool_calls": total_tool_calls,
                    "exploration_rounds": rounds,
                }, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "Olympus: wrote %s (%d chars, %d tool calls, %d rounds, %.1fs)",
                olympus_path, len(olympus_md), total_tool_calls, rounds, elapsed,
            )
        except OSError as exc:
            logger.warning("Olympus: failed to persist: %s", exc)

    return OlympusContext(
        repo_name=root.name,
        root=str(root),
        problem=problem,
        generated_at=_now_iso(),
        fingerprint=fingerprint,
        olympus_md=olympus_md,
        tool_calls=total_tool_calls,
        exploration_rounds=rounds,
        elapsed_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_repo(root: Path) -> bool:
    """Check if root is a git repo or has a recognizable project structure."""
    if (root / ".git").exists():
        return True
    for marker in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml"):
        if (root / marker).exists():
            return True
    return False


def _compute_fingerprint(problem: str, root: Path) -> str:
    """Fingerprint = hash(problem + git HEAD). Changes when either changes."""
    import subprocess

    digest = hashlib.sha256()
    digest.update(problem.encode("utf-8"))

    # Use git HEAD as repo state signal
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0:
            digest.update(result.stdout.strip().encode("utf-8"))
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    return digest.hexdigest()[:24]


def _now_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


__all__ = [
    "OlympusContext",
    "OLYMPUS_FILENAME",
    "build_olympus",
]
