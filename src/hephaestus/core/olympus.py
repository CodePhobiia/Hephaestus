"""
Olympus — Stage 0 repo-awareness engine for Hephaestus.

When Hephaestus is invoked from within a repository, Olympus automatically
builds a rich context map that connects the problem statement to the actual
codebase.  The result is persisted as ``.hephaestus/OLYMPUS.md`` and injected
into every downstream agent (decomposer, Pantheon council, translators, verifiers).

This is what turns Hephaestus from a "fancy brainstormer" into a repo-grounded
invention engine.
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

# Max chars for key file content sampling
_KEY_FILE_SAMPLE_CHARS = 4_000
# Max total chars for all sampled files
_TOTAL_SAMPLE_BUDGET = 30_000
# Max chars for the final OLYMPUS.md
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

    def to_prompt_injection(self, max_chars: int = _OLYMPUS_MAX_CHARS) -> str:
        """Format for injection into any agent's system prompt."""
        header = "=== OLYMPUS — REPO CONTEXT ===\n"
        footer = "\n=== END OLYMPUS ===\n"
        budget = max_chars - len(header) - len(footer)
        body = self.olympus_md[:budget] if len(self.olympus_md) > budget else self.olympus_md
        return header + body + footer


# ---------------------------------------------------------------------------
# Prompt for the LLM synthesis step
# ---------------------------------------------------------------------------

_OLYMPUS_SYSTEM_PROMPT = """\
You are OLYMPUS, the repo-awareness engine for Hephaestus (an AI invention system).

Your job: given a repo dossier (structure, components, dependencies, hotspots) \
and the user's problem statement, produce a concise OLYMPUS.md that connects the \
problem to the codebase.

You must:
1. Identify which components/files/modules are DIRECTLY relevant to the problem
2. Summarize what the codebase currently does about this problem (existing approach)
3. Identify architectural constraints the code imposes on any solution
4. Note what has already been tried (from git history/hotspots if visible)
5. Flag any code-level assumptions that a novel solution must respect or break

You must NOT:
- Propose solutions (that's the invention engine's job)
- Be generic — every statement must reference specific files, modules, or patterns
- Exceed the output budget (aim for 2000-4000 words)

Output format: Markdown. Use headers, bullet points, code references with backticks.

Structure your output as:
# OLYMPUS — Repo Context for Hephaestus

## Repo Overview
<1-3 sentences: what this codebase is>

## Problem ↔ Codebase Mapping
<Which components/files are relevant and why>

## Current Approach
<How the codebase currently handles this problem area>

## Architectural Constraints
<What the code structure requires/forbids for any solution>

## Key Files to Study
<Ranked list of files an inventor must understand, with 1-line descriptions>

## Hotspots & History
<What's been changing recently, what's been tried>

## Assumptions a Novel Solution Must Navigate
<Code-level assumptions, API contracts, data flow constraints>
"""

_OLYMPUS_USER_PROMPT = """\
PROBLEM STATEMENT:
{problem}

REPO DOSSIER:
{dossier}

KEY FILE SAMPLES:
{file_samples}

Produce the OLYMPUS.md. Be specific to THIS repo and THIS problem. \
Every claim must reference actual files, modules, or patterns from the dossier/samples.
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
) -> OlympusContext | None:
    """Build the Stage 0 Olympus context for a repo + problem.

    Parameters
    ----------
    problem:
        The user's problem statement.
    root:
        Path to the repo root.
    adapter:
        LLM adapter (must support ``generate`` or ``forge``).
    force_rebuild:
        Skip cache and always regenerate.
    persist:
        Write OLYMPUS.md to disk.

    Returns
    -------
    OlympusContext or None if not in a repo or generation fails.
    """
    t_start = time.monotonic()

    # ── Step 1: Detect repo ──────────────────────────────────────────────
    if not _is_repo(root):
        logger.info("Olympus: not a repo at %s, skipping", root)
        return None

    # ── Step 2: Build repo dossier ───────────────────────────────────────
    try:
        from hephaestus.workspace.context import WorkspaceContext

        ws_context = WorkspaceContext.from_directory(root, budget_chars=_TOTAL_SAMPLE_BUDGET)
        dossier = ws_context.repo_dossier
    except Exception as exc:
        logger.warning("Olympus: workspace scan failed: %s", exc)
        return None

    if dossier is None:
        logger.warning("Olympus: no repo dossier produced for %s", root)
        return None

    # ── Step 3: Check cache ──────────────────────────────────────────────
    fingerprint = _compute_olympus_fingerprint(problem, dossier.fingerprint)
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
                    repo_name=dossier.repo_name,
                    root=str(root),
                    problem=problem,
                    generated_at=cached_fp.get("generated_at", ""),
                    fingerprint=fingerprint,
                    olympus_md=olympus_md,
                    components_mapped=dossier.component_count,
                    relevant_files=dossier.key_artifacts[:10],
                    elapsed_seconds=0.0,
                )
        except (OSError, json.JSONDecodeError, KeyError):
            pass  # Cache miss, rebuild

    # ── Step 4: Sample key files ─────────────────────────────────────────
    file_samples = _sample_key_files(root, dossier, ws_context, budget=_TOTAL_SAMPLE_BUDGET)

    # ── Step 5: LLM synthesis ────────────────────────────────────────────
    dossier_text = dossier.to_prompt_text(max_chars=8_000)
    user_prompt = _OLYMPUS_USER_PROMPT.format(
        problem=problem,
        dossier=dossier_text,
        file_samples=file_samples,
    )

    logger.info("Olympus: synthesizing repo context via LLM (%d chars input)", len(user_prompt))

    try:
        olympus_md = await _call_adapter(adapter, _OLYMPUS_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        logger.error("Olympus: LLM synthesis failed: %s", exc)
        return None

    if not olympus_md or len(olympus_md.strip()) < 100:
        logger.warning("Olympus: LLM returned empty or trivial output")
        return None

    elapsed = time.monotonic() - t_start

    # ── Step 6: Persist ──────────────────────────────────────────────────
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
                }, indent=2),
                encoding="utf-8",
            )
            logger.info("Olympus: wrote %s (%d chars)", olympus_path, len(olympus_md))
        except OSError as exc:
            logger.warning("Olympus: failed to persist: %s", exc)

    # ── Build result ─────────────────────────────────────────────────────
    return OlympusContext(
        repo_name=dossier.repo_name,
        root=str(root),
        problem=problem,
        generated_at=_now_iso(),
        fingerprint=fingerprint,
        olympus_md=olympus_md,
        components_mapped=dossier.component_count,
        relevant_files=dossier.key_artifacts[:10],
        elapsed_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_repo(root: Path) -> bool:
    """Check if root is a git repo or has a recognizable project structure."""
    if (root / ".git").exists():
        return True
    # Also detect non-git project roots
    for marker in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml"):
        if (root / marker).exists():
            return True
    return False


def _compute_olympus_fingerprint(problem: str, repo_fingerprint: str) -> str:
    """Fingerprint = hash(problem + repo state). Changes when either changes."""
    digest = hashlib.sha256()
    digest.update(problem.encode("utf-8"))
    digest.update(repo_fingerprint.encode("utf-8"))
    return digest.hexdigest()[:24]


def _sample_key_files(
    root: Path,
    dossier: Any,
    ws_context: Any,
    *,
    budget: int = _TOTAL_SAMPLE_BUDGET,
) -> str:
    """Sample the most important files from the repo for LLM context.

    Prioritizes:
    1. Key files from dossier components (sorted by line count)
    2. Entry points
    3. Hotspot files
    """
    sampled: list[str] = []
    chars_used = 0
    seen_paths: set[str] = set()

    # Gather candidate paths in priority order
    candidate_paths: list[str] = []

    # From components — key files first
    if dossier.components:
        for component in dossier.components:
            for kf in component.key_files:
                if kf not in seen_paths:
                    candidate_paths.append(kf)
                    seen_paths.add(kf)

    # Key artifacts
    for artifact in dossier.key_artifacts:
        if artifact not in seen_paths and artifact.endswith((".py", ".rs", ".ts", ".go", ".js")):
            candidate_paths.append(artifact)
            seen_paths.add(artifact)

    # Hotspots
    for hotspot in dossier.hotspots:
        if hotspot.path not in seen_paths and _is_code_file(hotspot.path):
            candidate_paths.append(hotspot.path)
            seen_paths.add(hotspot.path)

    # Sample files up to budget
    for rel_path in candidate_paths:
        if chars_used >= budget:
            break
        full_path = root / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Truncate individual files
        if len(content) > _KEY_FILE_SAMPLE_CHARS:
            content = content[:_KEY_FILE_SAMPLE_CHARS] + "\n... [truncated]"

        remaining = budget - chars_used
        if len(content) > remaining:
            content = content[:remaining] + "\n... [truncated]"

        sampled.append(f"--- {rel_path} ---\n{content}\n")
        chars_used += len(content) + len(rel_path) + 10

    if not sampled:
        return "(No code files sampled — non-code repo or scan failed)"

    return "\n".join(sampled)


def _is_code_file(path: str) -> bool:
    """Check if a path looks like a code file."""
    code_exts = {
        ".py", ".rs", ".go", ".ts", ".tsx", ".js", ".jsx",
        ".java", ".kt", ".scala", ".c", ".cpp", ".h", ".hpp",
        ".rb", ".php", ".swift", ".cs",
    }
    return Path(path).suffix.lower() in code_exts


async def _call_adapter(adapter: Any, system: str, user: str) -> str:
    """Call the LLM adapter to generate Olympus content.

    Supports multiple adapter interfaces:
    - forge(prompt, system=...) — DeepForgeHarness
    - generate(prompt, system_prompt=...) — raw adapters
    """
    # Try forge first (harness interface)
    if hasattr(adapter, "forge"):
        result = await adapter.forge(user, system=system)
        if isinstance(result, str):
            return result
        # Some harnesses return objects with .text
        return getattr(result, "text", str(result))

    # Try generate (raw adapter interface)
    if hasattr(adapter, "generate"):
        result = await adapter.generate(user, system_prompt=system)
        if isinstance(result, str):
            return result
        return getattr(result, "text", str(result))

    # Try __call__ as last resort
    if callable(adapter):
        result = await adapter(user, system=system)
        if isinstance(result, str):
            return result
        return str(result)

    raise TypeError(f"Olympus: adapter {type(adapter).__name__} has no generate/forge method")


def _now_iso() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


__all__ = [
    "OlympusContext",
    "OLYMPUS_FILENAME",
    "build_olympus",
]
