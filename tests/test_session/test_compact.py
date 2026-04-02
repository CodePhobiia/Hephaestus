"""Comprehensive tests for hephaestus.session.compact."""

from __future__ import annotations

import pytest

from hephaestus.lenses.state import (
    CompositeLens,
    FoldState,
    GuardDecision,
    LensBundleMember,
    LensBundleProof,
    LensEngineState,
    LensLineage,
    ResearchReferenceArtifact,
    ResearchReferenceState,
)
from hephaestus.session.schema import (
    EntryType,
    InventionSnapshot,
    Role,
    Session,
    SessionMeta,
    TranscriptEntry,
)
from hephaestus.session.compact import (
    CompactionConfig,
    CompactionSummary,
    build_continuation_summary,
    compact_session,
    format_compaction_report,
    should_compact,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(**kwargs) -> Session:
    meta = SessionMeta(id="test-id", name="test-session")
    return Session(meta=meta, **kwargs)


def _add_entries(session: Session, n: int, *, content: str = "msg") -> None:
    """Append *n* alternating user/assistant entries."""
    for i in range(n):
        role = Role.USER.value if i % 2 == 0 else Role.ASSISTANT.value
        session.append_entry(role, f"{content} {i}")


def _large_session(n: int = 120) -> Session:
    """Session with *n* entries — above the default threshold."""
    s = _make_session(
        active_tools=["grep", "read"],
        pinned_context=["focus on solar energy"],
    )
    _add_entries(s, n)
    s.add_invention(
        invention_name="Solar Widget",
        source_domain="biology",
        key_insight="photosynthesis",
        score=8.0,
    )
    return s


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=3,
        active_bundle_id="bundle:adaptive:compact",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
                matched_patterns=["allocation"],
            )
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:compact",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune"],
                status="active",
                proof_status="fallback",
                cohesion_score=0.64,
                proof_fingerprint="proof-compact",
                reference_generation=3,
                summary="Compact summary bundle.",
            )
        ],
        lineages=[
            LensLineage(
                lineage_id="lineage:biology_immune:g1",
                entity_id="biology_immune",
                fingerprint="lineage-compact",
                reference_generation=3,
            )
        ],
        fold_states=[
            FoldState(
                fold_id="fold:compact",
                bundle_id="bundle:adaptive:compact",
                status="singleton_fallback",
                reference_generation=3,
                active_lineage_ids=["lineage:biology_immune:g1"],
                summary="Fallback fold active.",
            )
        ],
        guards=[
            GuardDecision(
                guard_id="guard:compact",
                kind="singleton_fallback",
                status="triggered",
                target_id="bundle:adaptive:compact",
                summary="Singleton fallback active.",
            )
        ],
        composites=[
            CompositeLens(
                composite_id="composite:compact",
                component_lineage_ids=["lineage:biology_immune:g1"],
                component_lens_ids=["biology_immune"],
                derived_from_bundle_id="bundle:adaptive:compact",
                version=1,
                reference_generation=3,
                fingerprint="composite-compact",
            )
        ],
        research=ResearchReferenceState(
            reference_generation=3,
            reference_signature="research-compact",
            artifacts=[
                ResearchReferenceArtifact(
                    artifact_name="baseline_dossier",
                    signature="artifact-compact",
                    citations=["https://example.com/compact"],
                    citation_count=1,
                )
            ],
        ),
    )


# ---------------------------------------------------------------------------
# CompactionConfig
# ---------------------------------------------------------------------------


class TestCompactionConfig:
    def test_defaults(self):
        cfg = CompactionConfig()
        assert cfg.max_transcript_entries == 100
        assert cfg.max_transcript_chars == 80_000
        assert cfg.keep_last_n == 20
        assert cfg.preserve_inventions is True
        assert cfg.preserve_tool_results is False
        assert cfg.auto_compact_threshold == 0.8

    def test_custom_values(self):
        cfg = CompactionConfig(max_transcript_entries=50, keep_last_n=5)
        assert cfg.max_transcript_entries == 50
        assert cfg.keep_last_n == 5

    def test_invalid_keep_last_n(self):
        with pytest.raises(ValueError, match="keep_last_n"):
            CompactionConfig(keep_last_n=-1)

    def test_invalid_threshold(self):
        with pytest.raises(ValueError, match="auto_compact_threshold"):
            CompactionConfig(auto_compact_threshold=0.0)
        with pytest.raises(ValueError, match="auto_compact_threshold"):
            CompactionConfig(auto_compact_threshold=1.5)


# ---------------------------------------------------------------------------
# should_compact
# ---------------------------------------------------------------------------


class TestShouldCompact:
    def test_under_threshold(self):
        s = _make_session()
        _add_entries(s, 10)
        assert should_compact(s) is False

    def test_at_entry_threshold(self):
        s = _make_session()
        _add_entries(s, 80)  # 80 == 100 * 0.8
        assert should_compact(s) is True

    def test_over_entry_threshold(self):
        s = _make_session()
        _add_entries(s, 100)
        assert should_compact(s) is True

    def test_under_entry_but_over_char_threshold(self):
        s = _make_session()
        # Few entries but lots of chars
        for i in range(10):
            s.append_entry(Role.USER.value, "x" * 10_000)
        # 10 entries * 10k chars = 100k > 80k * 0.8 = 64k
        cfg = CompactionConfig(max_transcript_chars=80_000)
        assert should_compact(s, cfg) is True

    def test_custom_threshold(self):
        s = _make_session()
        _add_entries(s, 50)
        cfg = CompactionConfig(max_transcript_entries=100, auto_compact_threshold=0.4)
        assert should_compact(s, cfg) is True

    def test_empty_session(self):
        s = _make_session()
        assert should_compact(s) is False


# ---------------------------------------------------------------------------
# build_continuation_summary
# ---------------------------------------------------------------------------


class TestBuildContinuationSummary:
    def test_includes_inventions(self):
        s = _large_session()
        s.inventions[0].pantheon_state = {"mode": "pantheon"}
        s.inventions[0].pantheon_final_verdict = "NOVEL"
        s.inventions[0].pantheon_consensus_achieved = True
        s.inventions[0].pantheon_rounds = 2
        entries = s.transcript[:50]
        summary = build_continuation_summary(entries, s)
        assert "Solar Widget" in summary
        assert "biology" in summary
        assert "8.0" in summary
        assert "pantheon" in summary.lower()

    def test_includes_user_requests(self):
        s = _make_session()
        s.append_entry(Role.USER.value, "find prior art")
        s.append_entry(Role.ASSISTANT.value, "searching...")
        summary = build_continuation_summary(s.transcript, s)
        assert "find prior art" in summary

    def test_includes_active_tools(self):
        s = _make_session(active_tools=["grep", "web_search"])
        _add_entries(s, 5)
        summary = build_continuation_summary(s.transcript, s)
        assert "grep" in summary
        assert "web_search" in summary

    def test_includes_pinned_context(self):
        s = _make_session(pinned_context=["focus on biomimicry"])
        _add_entries(s, 5)
        summary = build_continuation_summary(s.transcript, s)
        assert "biomimicry" in summary

    def test_includes_stats(self):
        s = _make_session()
        _add_entries(s, 10)
        summary = build_continuation_summary(s.transcript, s)
        assert "Compacted 10 entries" in summary

    def test_empty_entries(self):
        s = _make_session()
        summary = build_continuation_summary([], s)
        assert "Compacted 0 entries" in summary

    def test_has_header(self):
        s = _make_session()
        _add_entries(s, 3)
        summary = build_continuation_summary(s.transcript, s)
        assert summary.startswith("# Continuation Summary")

    def test_includes_lens_engine_state(self):
        s = _make_session()
        s.apply_lens_engine_state(_lens_engine_state(), op_id=2)
        _add_entries(s, 6)
        summary = build_continuation_summary(s.transcript, s)
        assert "Lens Engine State" in summary
        assert "bundle:adaptive:compact" in summary
        assert "composite:compact" in summary


# ---------------------------------------------------------------------------
# compact_session
# ---------------------------------------------------------------------------


class TestCompactSession:
    def test_noop_small_session(self):
        s = _make_session()
        _add_entries(s, 5)
        result = compact_session(s)
        assert result.removed_entries == 0
        assert result.compacted_count == 5
        assert len(s.transcript) == 5

    def test_compact_large_session(self):
        s = _large_session(120)
        result = compact_session(s)
        assert result.removed_entries > 0
        assert result.original_count == 120
        assert result.compacted_count < 120
        # Summary entry should be first
        assert s.transcript[0].entry_type == EntryType.SUMMARY.value

    def test_invention_preservation(self):
        s = _make_session()
        # Add entries including invention entries
        for i in range(100):
            if i == 30:
                s.append_entry(
                    Role.ASSISTANT.value,
                    "Invented the BioLens",
                    entry_type=EntryType.INVENTION.value,
                )
            elif i == 60:
                s.append_entry(
                    Role.ASSISTANT.value,
                    "Refined the BioLens",
                    entry_type=EntryType.INVENTION.value,
                )
            else:
                role = Role.USER.value if i % 2 == 0 else Role.ASSISTANT.value
                s.append_entry(role, f"msg {i}")

        cfg = CompactionConfig(max_transcript_entries=100, keep_last_n=20)
        result = compact_session(s, cfg)
        # Both invention entries from the old region should be preserved
        assert result.preserved_inventions == 2
        inv_entries = [
            e for e in s.transcript if e.entry_type == EntryType.INVENTION.value
        ]
        assert len(inv_entries) == 2

    def test_invention_preservation_disabled(self):
        s = _make_session()
        for i in range(100):
            if i == 30:
                s.append_entry(
                    Role.ASSISTANT.value,
                    "Invented X",
                    entry_type=EntryType.INVENTION.value,
                )
            else:
                s.append_entry(Role.USER.value, f"msg {i}")

        cfg = CompactionConfig(
            max_transcript_entries=100,
            keep_last_n=20,
            preserve_inventions=False,
        )
        result = compact_session(s, cfg)
        assert result.preserved_inventions == 0

    def test_tool_result_preservation(self):
        s = _make_session()
        for i in range(100):
            if i == 40:
                s.append_entry(
                    Role.TOOL.value,
                    "tool output",
                    entry_type=EntryType.TOOL_RESULT.value,
                )
            else:
                s.append_entry(Role.USER.value, f"msg {i}")

        cfg = CompactionConfig(
            max_transcript_entries=100,
            keep_last_n=20,
            preserve_tool_results=True,
        )
        result = compact_session(s, cfg)
        tool_entries = [
            e for e in s.transcript if e.entry_type == EntryType.TOOL_RESULT.value
        ]
        assert len(tool_entries) == 1

    def test_summary_text_in_result(self):
        s = _large_session()
        result = compact_session(s)
        assert "Continuation Summary" in result.summary_text

    def test_compaction_metrics(self):
        s = _make_session()
        _add_entries(s, 100)
        cfg = CompactionConfig(max_transcript_entries=100, keep_last_n=10)
        result = compact_session(s, cfg)
        assert result.original_count == 100
        assert result.chars_before > 0
        assert result.chars_after > 0
        assert result.chars_after < result.chars_before
        assert result.compacted_count == 11  # 1 summary + 10 kept

    def test_multiple_compactions(self):
        """Compact an already-compacted session."""
        s = _make_session()
        _add_entries(s, 120)
        cfg = CompactionConfig(max_transcript_entries=50, keep_last_n=10)

        result1 = compact_session(s, cfg)
        assert result1.removed_entries > 0
        count_after_first = len(s.transcript)

        # Add more entries to trigger a second compaction
        _add_entries(s, 50, content="new")
        result2 = compact_session(s, cfg)
        assert result2.removed_entries > 0
        assert result2.original_count == count_after_first + 50
        # The transcript should have a summary as its first entry
        assert s.transcript[0].entry_type == EntryType.SUMMARY.value

    def test_empty_session(self):
        s = _make_session()
        result = compact_session(s)
        assert result.removed_entries == 0
        assert result.original_count == 0
        assert len(s.transcript) == 0

    def test_session_only_inventions(self):
        """Session with only invention entries — nothing to compact."""
        s = _make_session()
        for i in range(5):
            s.append_entry(
                Role.ASSISTANT.value,
                f"invention {i}",
                entry_type=EntryType.INVENTION.value,
            )
        # 5 entries — below threshold
        result = compact_session(s)
        assert result.removed_entries == 0
        assert len(s.transcript) == 5

    def test_keep_last_n_zero(self):
        """All entries can be compacted (no recent kept)."""
        s = _make_session()
        _add_entries(s, 100)
        cfg = CompactionConfig(max_transcript_entries=100, keep_last_n=0)
        result = compact_session(s, cfg)
        assert result.removed_entries == 100
        # Only the summary entry remains
        assert len(s.transcript) == 1
        assert s.transcript[0].entry_type == EntryType.SUMMARY.value

    def test_keep_last_n_exceeds_transcript(self):
        s = _make_session()
        _add_entries(s, 90)
        # keep_last_n > transcript length: everything is recent
        cfg = CompactionConfig(
            max_transcript_entries=100,
            keep_last_n=200,
        )
        result = compact_session(s, cfg)
        # should_compact triggers (90 >= 80), but old_entries is empty
        assert result.removed_entries == 0

    def test_updates_meta_timestamp(self):
        s = _make_session()
        _add_entries(s, 100)
        old_ts = s.meta.updated_at
        compact_session(s)
        assert s.meta.updated_at >= old_ts

    def test_summary_entry_metadata(self):
        s = _large_session()
        compact_session(s)
        summary = s.transcript[0]
        assert "compacted_count" in summary.metadata
        assert "preserved_inventions" in summary.metadata

    def test_recent_entries_preserved_in_order(self):
        s = _make_session()
        _add_entries(s, 100)
        cfg = CompactionConfig(max_transcript_entries=100, keep_last_n=5)
        compact_session(s, cfg)
        recent = s.transcript[-5:]
        expected = [f"msg {i}" for i in range(95, 100)]
        actual = [e.content for e in recent]
        assert actual == expected


# ---------------------------------------------------------------------------
# format_compaction_report
# ---------------------------------------------------------------------------


class TestFormatCompactionReport:
    def test_no_compaction(self):
        summary = CompactionSummary(
            original_count=10,
            compacted_count=10,
            removed_entries=0,
            summary_text="",
            preserved_inventions=0,
        )
        report = format_compaction_report(summary)
        assert report == "No compaction needed."

    def test_with_compaction(self):
        summary = CompactionSummary(
            original_count=100,
            compacted_count=21,
            removed_entries=80,
            summary_text="...",
            preserved_inventions=2,
            chars_before=50000,
            chars_after=10000,
        )
        report = format_compaction_report(summary)
        assert "100 -> 21" in report
        assert "removed 80" in report
        assert "50000 -> 10000" in report
        assert "Preserved invention entries: 2" in report
        assert "Compaction Report" in report
