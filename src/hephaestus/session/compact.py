"""Session compaction with continuation summaries.

Provides configurable transcript compaction that preserves key context
(inventions, pinned context, active tools, pending todos) in a structured
continuation summary, allowing sessions to stay within size limits without
losing critical state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from hephaestus.session.schema import (
    EntryType,
    Role,
    Session,
    TranscriptEntry,
)

__all__ = [
    "CompactionConfig",
    "CompactionSummary",
    "build_continuation_summary",
    "compact_session",
    "format_compaction_report",
    "should_compact",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _total_chars(entries: list[TranscriptEntry]) -> int:
    return sum(len(e.content) for e in entries)


# ---------------------------------------------------------------------------
# Config & result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CompactionConfig:
    """Knobs for session compaction behaviour."""

    max_transcript_entries: int = 100
    max_transcript_chars: int = 80_000
    keep_last_n: int = 20
    preserve_inventions: bool = True
    preserve_tool_results: bool = False
    auto_compact_threshold: float = 0.8

    def __post_init__(self) -> None:
        if self.keep_last_n < 0:
            raise ValueError("keep_last_n must be >= 0")
        if not 0 < self.auto_compact_threshold <= 1.0:
            raise ValueError("auto_compact_threshold must be in (0, 1]")


@dataclass
class CompactionSummary:
    """Metrics returned by :func:`compact_session`."""

    original_count: int
    compacted_count: int
    removed_entries: int
    summary_text: str
    preserved_inventions: int
    timestamp: str = field(default_factory=_now)
    chars_before: int = 0
    chars_after: int = 0


# ---------------------------------------------------------------------------
# Continuation summary builder
# ---------------------------------------------------------------------------


def build_continuation_summary(
    entries: list[TranscriptEntry],
    session: Session,
) -> str:
    """Build a rich continuation summary from compacted entries.

    The summary preserves enough context that subsequent turns can
    continue the conversation without re-reading the full history.
    """
    sections: list[str] = []

    # -- Invention status ----------------------------------------------------
    if session.inventions:
        inv_lines: list[str] = []
        for inv in session.inventions:
            line = f"  - {inv.invention_name}"
            if inv.source_domain:
                line += f" (source: {inv.source_domain})"
            if inv.score:
                line += f" [score: {inv.score}]"
            inv_lines.append(line)
        sections.append("## Inventions\n" + "\n".join(inv_lines))

    # -- Recent user requests ------------------------------------------------
    user_msgs: list[str] = []
    for entry in entries:
        if entry.role == Role.USER.value:
            text = entry.content.strip()
            if text:
                user_msgs.append(text)
    if user_msgs:
        # Keep the last few user messages for context
        recent = user_msgs[-5:]
        bullets = "\n".join(f"  - {m[:200]}" for m in recent)
        sections.append("## Recent User Requests\n" + bullets)

    # -- Key decisions -------------------------------------------------------
    decision_entries: list[str] = []
    for entry in entries:
        if entry.role == Role.ASSISTANT.value:
            text = entry.content.strip()
            if text:
                decision_entries.append(text)
    if decision_entries:
        recent = decision_entries[-5:]
        bullets = "\n".join(f"  - {d[:200]}" for d in recent)
        sections.append("## Key Decisions\n" + bullets)

    # -- Active tools --------------------------------------------------------
    if session.active_tools:
        tools_str = ", ".join(session.active_tools)
        sections.append(f"## Active Tools\n  {tools_str}")

    # -- Pinned context ------------------------------------------------------
    if session.pinned_context:
        ctx_bullets = "\n".join(f"  - {c}" for c in session.pinned_context)
        sections.append("## Pinned Context\n" + ctx_bullets)

    # -- Reference lots -----------------------------------------------------
    if getattr(session, "reference_lots", None):
        lot_lines: list[str] = []
        for lot in session.reference_lots[:12]:
            line = f"  - [{lot.kind}] {lot.subject_key}"
            if lot.floor:
                line += f" floor={lot.floor}"
            if lot.exact:
                line += f" exact={lot.exact}"
            if lot.realized:
                line += " [realized]"
            lot_lines.append(line)
        sections.append("## Operational Anchors (Reference Lots)\n" + "\n".join(lot_lines))

    # -- Lens engine state --------------------------------------------------
    lens_engine_state = getattr(session, "lens_engine_state", None)
    if lens_engine_state is not None:
        lens_lines: list[str] = [f"  - {lens_engine_state.summary()}"]
        active_bundle = getattr(lens_engine_state, "active_bundle", None)
        if active_bundle is not None:
            lens_lines.append(
                f"  - active bundle={active_bundle.bundle_id} "
                f"kind={active_bundle.bundle_kind} members={', '.join(active_bundle.member_ids)}"
            )
        active_composites = getattr(lens_engine_state, "active_composites", [])
        for composite in active_composites[:3]:
            lens_lines.append(
                f"  - composite={composite.composite_id} "
                f"version={composite.version} parents={', '.join(composite.component_lens_ids)}"
            )
        guards = getattr(lens_engine_state, "guards", [])
        for guard in guards[:4]:
            lens_lines.append(
                f"  - guard[{guard.kind}] {guard.status}: {guard.summary}"
            )
        invalidations = getattr(lens_engine_state, "pending_invalidations", [])
        for item in invalidations[:4]:
            lens_lines.append(
                f"  - invalidation[{item.target_kind}] {item.target_id}: {item.summary}"
            )
        recompositions = getattr(lens_engine_state, "recompositions", [])
        for item in recompositions[-3:]:
            lens_lines.append(
                f"  - recomposition {item.status}: {item.summary}"
            )
        sections.append("## Lens Engine State\n" + "\n".join(lens_lines))

    # -- Entry statistics ----------------------------------------------------
    role_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for entry in entries:
        role_counts[entry.role] = role_counts.get(entry.role, 0) + 1
        type_counts[entry.entry_type] = type_counts.get(entry.entry_type, 0) + 1

    stats_lines = [f"  Compacted {len(entries)} entries"]
    if role_counts:
        breakdown = ", ".join(f"{r}: {c}" for r, c in sorted(role_counts.items()))
        stats_lines.append(f"  Roles: {breakdown}")
    if type_counts:
        breakdown = ", ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
        stats_lines.append(f"  Types: {breakdown}")
    sections.append("## Compaction Stats\n" + "\n".join(stats_lines))

    header = "# Continuation Summary"
    return header + "\n\n" + "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_compact(
    session: Session,
    config: CompactionConfig | None = None,
) -> bool:
    """Return ``True`` if the session exceeds the auto-compact threshold."""
    cfg = config or CompactionConfig()

    entry_count = len(session.transcript)
    char_count = _total_chars(session.transcript)

    entry_limit = cfg.max_transcript_entries * cfg.auto_compact_threshold
    char_limit = cfg.max_transcript_chars * cfg.auto_compact_threshold

    return entry_count >= entry_limit or char_count >= char_limit


def compact_session(
    session: Session,
    config: CompactionConfig | None = None,
) -> CompactionSummary:
    """Compact a session transcript, preserving key context.

    Returns a :class:`CompactionSummary` with metrics.  If the session
    is below the compaction threshold a no-op summary is returned and
    the session is left untouched.
    """
    cfg = config or CompactionConfig()

    chars_before = _total_chars(session.transcript)
    original_count = len(session.transcript)

    if not should_compact(session, cfg):
        return CompactionSummary(
            original_count=original_count,
            compacted_count=original_count,
            removed_entries=0,
            summary_text="",
            preserved_inventions=0,
            chars_before=chars_before,
            chars_after=chars_before,
        )

    # ── Partition entries ──────────────────────────────────────────────
    keep_n = min(cfg.keep_last_n, len(session.transcript))
    if keep_n > 0:
        old_entries = session.transcript[:-keep_n]
        recent_entries = session.transcript[-keep_n:]
    else:
        old_entries = list(session.transcript)
        recent_entries = []

    # Pull out preserved invention entries from old
    preserved: list[TranscriptEntry] = []
    to_compact: list[TranscriptEntry] = []

    for entry in old_entries:
        if cfg.preserve_inventions and entry.entry_type == EntryType.INVENTION.value:
            preserved.append(entry)
        elif cfg.preserve_tool_results and entry.entry_type == EntryType.TOOL_RESULT.value:
            preserved.append(entry)
        else:
            to_compact.append(entry)

    if not to_compact:
        # Nothing to actually compact
        return CompactionSummary(
            original_count=original_count,
            compacted_count=original_count,
            removed_entries=0,
            summary_text="",
            preserved_inventions=len(preserved),
            chars_before=chars_before,
            chars_after=chars_before,
        )

    # ── Build summary ─────────────────────────────────────────────────
    summary_text = build_continuation_summary(to_compact, session)

    summary_entry = TranscriptEntry(
        role=Role.SYSTEM.value,
        content=summary_text,
        entry_type=EntryType.SUMMARY.value,
        metadata={
            "compacted_count": len(to_compact),
            "preserved_inventions": len(preserved),
        },
    )

    # ── Reassemble transcript ─────────────────────────────────────────
    session.transcript = [summary_entry] + preserved + recent_entries
    session.meta.updated_at = _now()

    chars_after = _total_chars(session.transcript)
    compacted_count = len(session.transcript)

    return CompactionSummary(
        original_count=original_count,
        compacted_count=compacted_count,
        removed_entries=len(to_compact),
        summary_text=summary_text,
        preserved_inventions=len(preserved),
        chars_before=chars_before,
        chars_after=chars_after,
    )


def format_compaction_report(summary: CompactionSummary) -> str:
    """Return a human-readable compaction report."""
    if summary.removed_entries == 0:
        return "No compaction needed."

    lines = [
        "=== Compaction Report ===",
        f"  Entries: {summary.original_count} -> {summary.compacted_count}"
        f" (removed {summary.removed_entries})",
        f"  Characters: {summary.chars_before} -> {summary.chars_after}",
        f"  Preserved invention entries: {summary.preserved_inventions}",
        f"  Timestamp: {summary.timestamp}",
        "=========================",
    ]
    return "\n".join(lines)
