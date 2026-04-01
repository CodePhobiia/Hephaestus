"""Tests for hephaestus.memory.transparency module."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from hephaestus.memory.transparency import (
    MemoryReport,
    build_memory_report,
    format_context_report,
    format_memory_report,
)


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins for SessionState / HephaestusConfig
# ---------------------------------------------------------------------------

def _make_session(**kwargs):
    """Return a SimpleNamespace mimicking SessionState with sensible defaults."""
    defaults = dict(
        context_items=[],
        pinned=[],
        config=SimpleNamespace(backend="api", default_model="claude-sonnet-4-20250514", depth=3, candidates=8),
        anti_memory_hits=[],
        loaded_instructions=[],
        compaction_summaries=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _sample_hits() -> list[dict]:
    return [
        {"pattern": "pheromone load balancer", "count": 3, "last_hit_time": 1_700_000_000.0},
        {"pattern": "swarm routing", "count": 1, "last_hit_time": 1_700_001_000.0},
    ]


# ---------------------------------------------------------------------------
# MemoryReport creation
# ---------------------------------------------------------------------------

class TestMemoryReportCreation:
    """Tests for MemoryReport dataclass construction."""

    def test_default_construction(self):
        report = MemoryReport()
        assert report.anti_memory_hits == []
        assert report.loaded_instructions == []
        assert report.pinned_context == []
        assert report.compaction_summaries == []
        assert report.active_config_sources == {}

    def test_construction_with_data(self):
        hits = _sample_hits()
        report = MemoryReport(
            anti_memory_hits=hits,
            loaded_instructions=["/etc/heph/rules.md"],
            pinned_context=["must tolerate node churn"],
            compaction_summaries=["Turn 1-5 compacted"],
            active_config_sources={"backend": "config.yaml"},
        )
        assert len(report.anti_memory_hits) == 2
        assert report.loaded_instructions == ["/etc/heph/rules.md"]
        assert report.pinned_context == ["must tolerate node churn"]
        assert report.compaction_summaries == ["Turn 1-5 compacted"]
        assert report.active_config_sources == {"backend": "config.yaml"}

    def test_total_anti_memory_hits_empty(self):
        report = MemoryReport()
        assert report.total_anti_memory_hits == 0

    def test_total_anti_memory_hits_populated(self):
        report = MemoryReport(anti_memory_hits=_sample_hits())
        assert report.total_anti_memory_hits == 4  # 3 + 1

    def test_has_activity_false_when_empty(self):
        report = MemoryReport()
        assert report.has_activity is False

    def test_has_activity_true_with_hits(self):
        report = MemoryReport(anti_memory_hits=_sample_hits())
        assert report.has_activity is True

    def test_has_activity_true_with_pinned_only(self):
        report = MemoryReport(pinned_context=["some context"])
        assert report.has_activity is True

    def test_has_activity_true_with_instructions_only(self):
        report = MemoryReport(loaded_instructions=["file.md"])
        assert report.has_activity is True

    def test_has_activity_true_with_compaction_only(self):
        report = MemoryReport(compaction_summaries=["compacted"])
        assert report.has_activity is True


# ---------------------------------------------------------------------------
# build_memory_report
# ---------------------------------------------------------------------------

class TestBuildMemoryReport:
    """Tests for build_memory_report with various session states."""

    def test_empty_session(self):
        session = _make_session()
        report = build_memory_report(session)
        assert report.anti_memory_hits == []
        assert report.pinned_context == []
        assert report.loaded_instructions == []
        assert report.compaction_summaries == []

    def test_session_with_context_items(self):
        session = _make_session(context_items=["offline", "low latency"])
        report = build_memory_report(session)
        assert report.pinned_context == ["offline", "low latency"]

    def test_session_with_anti_memory_hits(self):
        hits = _sample_hits()
        session = _make_session(anti_memory_hits=hits)
        report = build_memory_report(session)
        assert len(report.anti_memory_hits) == 2
        assert report.anti_memory_hits[0]["pattern"] == "pheromone load balancer"

    def test_session_with_compaction(self):
        session = _make_session(compaction_summaries=["Turns 1-3 summarized"])
        report = build_memory_report(session)
        assert report.compaction_summaries == ["Turns 1-3 summarized"]

    def test_session_with_loaded_instructions(self):
        session = _make_session(loaded_instructions=["rules.md", "constraints.yaml"])
        report = build_memory_report(session)
        assert report.loaded_instructions == ["rules.md", "constraints.yaml"]

    def test_config_sources_from_config_sources_attr(self):
        cfg = SimpleNamespace(config_sources={"backend": "env", "depth": "config.yaml"})
        session = _make_session(config=cfg)
        report = build_memory_report(session)
        assert report.active_config_sources == {"backend": "env", "depth": "config.yaml"}

    def test_config_sources_fallback_to_defaults(self):
        cfg = SimpleNamespace(backend="api", default_model="m", depth=3, candidates=8)
        session = _make_session(config=cfg)
        report = build_memory_report(session)
        assert "backend" in report.active_config_sources
        assert report.active_config_sources["backend"] == "defaults"

    def test_config_override(self):
        cfg = SimpleNamespace(config_sources={"backend": "override"})
        session = _make_session(config=SimpleNamespace())
        report = build_memory_report(session, config=cfg)
        assert report.active_config_sources == {"backend": "override"}

    def test_anti_memory_param_accepted(self):
        """anti_memory param is accepted without error (future use)."""
        session = _make_session()
        report = build_memory_report(session, anti_memory=object())
        assert isinstance(report, MemoryReport)

    def test_does_not_mutate_session(self):
        items = ["original"]
        session = _make_session(context_items=items)
        report = build_memory_report(session)
        report.pinned_context.append("added")
        assert session.context_items == ["original"]

    def test_missing_attrs_gracefully_handled(self):
        """A minimal namespace with no expected attrs still works."""
        session = SimpleNamespace()
        report = build_memory_report(session)
        assert report.pinned_context == []
        assert report.anti_memory_hits == []


# ---------------------------------------------------------------------------
# format_memory_report
# ---------------------------------------------------------------------------

class TestFormatMemoryReport:
    """Tests for the /status-oriented summary formatter."""

    def test_empty_report_contains_sections(self):
        report = MemoryReport()
        out = format_memory_report(report)
        assert "Anti-Memory" in out
        assert "Instructions" in out
        assert "Pinned Context" in out
        assert "Compaction" in out

    def test_empty_report_shows_dim_placeholders(self):
        report = MemoryReport()
        out = format_memory_report(report)
        assert "no patterns active" in out
        assert "none loaded" in out
        assert "not triggered" in out

    def test_populated_report_shows_counts(self):
        report = MemoryReport(
            anti_memory_hits=_sample_hits(),
            loaded_instructions=["a.md", "b.md"],
            pinned_context=["x", "y", "z"],
            compaction_summaries=["s1"],
        )
        out = format_memory_report(report)
        assert "2 pattern(s)" in out
        assert "4 total hit(s)" in out
        assert "2 file(s) loaded" in out
        assert "3 item(s)" in out
        assert "1 summary(ies)" in out

    def test_config_sources_shown(self):
        report = MemoryReport(active_config_sources={"backend": "env"})
        out = format_memory_report(report)
        assert "Config Sources" in out
        assert "env" in out

    def test_config_sources_hidden_when_empty(self):
        report = MemoryReport()
        out = format_memory_report(report)
        assert "Config Sources" not in out


# ---------------------------------------------------------------------------
# format_context_report
# ---------------------------------------------------------------------------

class TestFormatContextReport:
    """Tests for the /context-oriented detail formatter."""

    def test_empty_report_sections_present(self):
        report = MemoryReport()
        out = format_context_report(report)
        assert "Anti-Memory Exclusions" in out
        assert "Loaded Instructions" in out
        assert "Pinned Context" in out
        assert "Compaction History" in out

    def test_empty_report_shows_none_messages(self):
        report = MemoryReport()
        out = format_context_report(report)
        assert "No anti-memory patterns matched" in out
        assert "No instruction files loaded" in out
        assert "No context items pinned" in out
        assert "No compaction has occurred" in out

    def test_anti_memory_detail(self):
        report = MemoryReport(anti_memory_hits=_sample_hits())
        out = format_context_report(report)
        assert "pheromone load balancer" in out
        assert "swarm routing" in out
        assert "hits=3" in out
        assert "hits=1" in out

    def test_anti_memory_timestamp_formatted(self):
        report = MemoryReport(
            anti_memory_hits=[{"pattern": "x", "count": 1, "last_hit_time": 1_700_000_000.0}]
        )
        out = format_context_report(report)
        # Should show a UTC date string, not the raw epoch
        assert "2023-11-14" in out
        assert "UTC" in out

    def test_anti_memory_no_timestamp(self):
        report = MemoryReport(
            anti_memory_hits=[{"pattern": "x", "count": 1, "last_hit_time": None}]
        )
        out = format_context_report(report)
        assert "last=n/a" in out

    def test_pinned_context_numbered(self):
        report = MemoryReport(pinned_context=["alpha", "beta"])
        out = format_context_report(report)
        assert "1." in out
        assert "alpha" in out
        assert "2." in out
        assert "beta" in out

    def test_loaded_instructions_paths(self):
        report = MemoryReport(loaded_instructions=["/home/user/rules.md"])
        out = format_context_report(report)
        assert "/home/user/rules.md" in out

    def test_compaction_summaries_numbered(self):
        report = MemoryReport(compaction_summaries=["first", "second"])
        out = format_context_report(report)
        assert "1. first" in out
        assert "2. second" in out

    def test_config_sources_in_context(self):
        report = MemoryReport(active_config_sources={"backend": "env", "depth": "yaml"})
        out = format_context_report(report)
        assert "Active Config Sources" in out
        assert "backend" in out
        assert "depth" in out

    def test_config_sources_hidden_when_empty(self):
        report = MemoryReport()
        out = format_context_report(report)
        assert "Active Config Sources" not in out


# ---------------------------------------------------------------------------
# Integration-style: build then format
# ---------------------------------------------------------------------------

class TestBuildThenFormat:
    """Round-trip: build a report from session state and format it."""

    def test_full_round_trip(self):
        session = _make_session(
            context_items=["must be offline-capable"],
            anti_memory_hits=[
                {"pattern": "mesh network", "count": 2, "last_hit_time": time.time()},
            ],
            loaded_instructions=["safety.md"],
            compaction_summaries=["Turns 1-4 compacted"],
        )
        report = build_memory_report(session)

        status = format_memory_report(report)
        assert "1 pattern(s)" in status
        assert "1 file(s) loaded" in status

        ctx = format_context_report(report)
        assert "mesh network" in ctx
        assert "must be offline-capable" in ctx
        assert "safety.md" in ctx
        assert "Turns 1-4 compacted" in ctx

    def test_empty_round_trip(self):
        session = _make_session()
        report = build_memory_report(session)
        status = format_memory_report(report)
        ctx = format_context_report(report)
        assert "no patterns active" in status
        assert "No anti-memory patterns matched" in ctx
