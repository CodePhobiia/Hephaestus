"""
Layered instruction discovery and budgeted prompt assembly.

Discovers ``HEPHAESTUS.md``, ``.hephaestus/instructions.md``, and
``.hephaestus/local.md`` files walking up the directory tree, plus the
user-global ``~/.hephaestus/instructions.md``.  All discovered content is
merged within a configurable character budget and appended after the core
system prompt behind a dynamic boundary marker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from hephaestus.prompts.system_prompt import build_system_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DYNAMIC_BOUNDARY: str = "--- DYNAMIC CONTEXT BOUNDARY ---"

_PROJECT_INSTRUCTION_NAMES: tuple[str, ...] = (
    "HEPHAESTUS.md",
    ".hephaestus/instructions.md",
    ".hephaestus/local.md",
)

_USER_GLOBAL_INSTRUCTION: Path = Path.home() / ".hephaestus" / "instructions.md"

_DEFAULT_PER_FILE_LIMIT: int = 8000
_DEFAULT_TOTAL_LIMIT: int = 24000

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InstructionFile:
    """A single discovered instruction file."""

    path: str
    content: str
    source: str  # 'project' | 'user' | 'builtin'
    size: int


@dataclass
class ContextBudget:
    """Character budget for the assembled context."""

    max_total_chars: int = 32000
    max_per_source: int = 8000
    reserved_for_prompt: int = 4000


@dataclass
class BudgetedContext:
    """Result of budget-aware context assembly."""

    instruction_text: str
    anti_memory_text: str
    pinned_context_text: str
    workspace_summary: str
    total_chars: int
    sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Instruction discovery
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY = {"builtin": 0, "user": 1, "project": 2}


def discover_instructions(
    start_dir: Path | None = None,
    *,
    per_file_limit: int = _DEFAULT_PER_FILE_LIMIT,
    total_limit: int = _DEFAULT_TOTAL_LIMIT,
) -> list[InstructionFile]:
    """Walk up from *start_dir* collecting instruction files.

    Returns a list sorted by priority (builtin < user < project).
    Files are deduplicated by SHA-256 content hash.
    """
    start = Path(start_dir).resolve() if start_dir else Path.cwd()
    found: list[InstructionFile] = []
    seen_hashes: set[str] = set()

    # Walk up the directory tree for project-level instructions.
    current = start
    while True:
        for name in _PROJECT_INSTRUCTION_NAMES:
            candidate = current / name
            if candidate.is_file():
                _maybe_add(candidate, "project", per_file_limit, found, seen_hashes)
        parent = current.parent
        if parent == current:
            break
        current = parent

    # User-global instructions
    if _USER_GLOBAL_INSTRUCTION.is_file():
        _maybe_add(_USER_GLOBAL_INSTRUCTION, "user", per_file_limit, found, seen_hashes)

    # Sort by priority
    found.sort(key=lambda f: _SOURCE_PRIORITY.get(f.source, 0))

    # Enforce total limit
    total = 0
    result: list[InstructionFile] = []
    for inst in found:
        if total + inst.size > total_limit:
            remaining = total_limit - total
            if remaining > 0:
                truncated = inst.content[:remaining]
                result.append(
                    InstructionFile(
                        path=inst.path,
                        content=truncated,
                        source=inst.source,
                        size=len(truncated),
                    )
                )
            break
        result.append(inst)
        total += inst.size

    return result


def _maybe_add(
    path: Path,
    source: str,
    per_file_limit: int,
    out: list[InstructionFile],
    seen: set[str],
) -> None:
    """Read *path*, dedup by hash, truncate to *per_file_limit*, append."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return

    digest = hashlib.sha256(raw.encode()).hexdigest()
    if digest in seen:
        return
    seen.add(digest)

    content = raw[:per_file_limit]
    out.append(
        InstructionFile(
            path=str(path),
            content=content,
            source=source,
            size=len(content),
        )
    )


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def assemble_context(
    instructions: list[InstructionFile] | None = None,
    anti_memory_hits: list[str] | None = None,
    pinned_context: list[str] | None = None,
    workspace_summary: str = "",
    budget: ContextBudget | None = None,
) -> BudgetedContext:
    """Merge all context sources within *budget*.

    Priority when truncating (first to lose → last):
    1. instruction text
    2. pinned context
    3. workspace summary
    4. anti-memory text (last to lose)
    """
    budget = budget or ContextBudget()
    available = budget.max_total_chars - budget.reserved_for_prompt
    if available < 0:
        available = 0

    sources: list[str] = []

    # --- anti-memory (highest priority — allocated first) -----------------
    anti_parts = _dedup_strings(anti_memory_hits or [])
    anti_text = "\n".join(anti_parts)
    anti_text = anti_text[: budget.max_per_source]
    if anti_text:
        sources.append("anti_memory")

    # --- workspace summary ------------------------------------------------
    ws = workspace_summary[: budget.max_per_source]
    if ws:
        sources.append("workspace")

    # --- pinned context ---------------------------------------------------
    pinned_parts = _dedup_strings(pinned_context or [])
    pinned_text = "\n".join(pinned_parts)
    pinned_text = pinned_text[: budget.max_per_source]
    if pinned_text:
        sources.append("pinned")

    # --- instruction text (lowest priority) -------------------------------
    inst_parts: list[str] = []
    for inst in instructions or []:
        inst_parts.append(inst.content)
        if inst.source not in sources:
            sources.append(inst.source)
    inst_text = "\n\n".join(_dedup_strings(inst_parts))
    inst_text = inst_text[: budget.max_per_source]

    # --- fit within total budget ------------------------------------------
    # Order of shedding: instructions → pinned → workspace → anti-memory
    sections = [
        ("instruction", inst_text),
        ("pinned", pinned_text),
        ("workspace", ws),
        ("anti_memory", anti_text),
    ]

    total = sum(len(s) for _, s in sections)
    if total > available:
        excess = total - available
        trimmed: list[tuple[str, str]] = []
        for label, text in sections:
            if excess > 0 and text:
                cut = min(excess, len(text))
                text = text[: len(text) - cut]
                excess -= cut
            trimmed.append((label, text))
        sections = trimmed

    final_inst = _section_text(sections, "instruction")
    final_pinned = _section_text(sections, "pinned")
    final_ws = _section_text(sections, "workspace")
    final_anti = _section_text(sections, "anti_memory")

    total_chars = len(final_inst) + len(final_anti) + len(final_pinned) + len(final_ws)

    return BudgetedContext(
        instruction_text=final_inst,
        anti_memory_text=final_anti,
        pinned_context_text=final_pinned,
        workspace_summary=final_ws,
        total_chars=total_chars,
        sources=sources,
    )


def _dedup_strings(items: list[str]) -> list[str]:
    """Remove exact duplicate strings while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _section_text(sections: list[tuple[str, str]], label: str) -> str:
    for lbl, text in sections:
        if lbl == label:
            return text
    return ""


# ---------------------------------------------------------------------------
# Full prompt builder
# ---------------------------------------------------------------------------


def build_full_prompt(
    user_prompt: str,
    context: BudgetedContext,
    **system_prompt_kwargs: str,
) -> str:
    """Build the complete prompt: system prompt + boundary + context sections.

    Parameters
    ----------
    user_prompt:
        The user's invention / creative prompt.
    context:
        A :class:`BudgetedContext` from :func:`assemble_context`.
    **system_prompt_kwargs:
        Extra keyword arguments forwarded to
        :func:`~hephaestus.prompts.system_prompt.build_system_prompt`.
    """
    core = build_system_prompt(user_prompt=user_prompt, **system_prompt_kwargs)

    parts: list[str] = [core, "", DYNAMIC_BOUNDARY]

    if context.instruction_text:
        parts.append("")
        parts.append("## Project Instructions")
        parts.append(context.instruction_text)

    if context.anti_memory_text:
        parts.append("")
        parts.append("## Anti-Memory Zone")
        parts.append(context.anti_memory_text)

    if context.pinned_context_text:
        parts.append("")
        parts.append("## Pinned Context")
        parts.append(context.pinned_context_text)

    if context.workspace_summary:
        parts.append("")
        parts.append("## Workspace Summary")
        parts.append(context.workspace_summary)

    return "\n".join(parts)


__all__ = [
    "InstructionFile",
    "ContextBudget",
    "BudgetedContext",
    "DYNAMIC_BOUNDARY",
    "discover_instructions",
    "assemble_context",
    "build_full_prompt",
]
