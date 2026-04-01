"""Tests for invention history analytics."""

from __future__ import annotations

from pathlib import Path

import pytest

from hephaestus.analytics.history import (
    AnalyticsSummary,
    InventionHistory,
    InventionRecord,
    format_analytics,
)


def _make_record(**overrides) -> InventionRecord:
    defaults = dict(
        timestamp="2026-04-01T05:00:00Z",
        problem="Load balancer",
        invention_name="Immune Scheduler",
        source_domain="biology",
        novelty_score=0.85,
        domain_distance=0.80,
        structural_fidelity=0.75,
        verdict="NOVEL",
        cost_usd=1.20,
        duration_seconds=45.0,
        success=True,
    )
    defaults.update(overrides)
    return InventionRecord(**defaults)


class TestInventionRecord:
    def test_creation(self):
        r = _make_record()
        assert r.invention_name == "Immune Scheduler"
        assert r.success is True

    def test_failed_record(self):
        r = _make_record(success=False, verdict="FAILED")
        assert r.success is False


class TestInventionHistory:
    def test_record_and_load(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        h.record(_make_record())
        h.record(_make_record(invention_name="Ant Router", source_domain="ecology"))

        records = h.load()
        assert len(records) == 2
        assert records[0].invention_name == "Immune Scheduler"
        assert records[1].source_domain == "ecology"

    def test_empty_history(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        assert h.load() == []
        assert h.count == 0

    def test_count(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        h.record(_make_record())
        h.record(_make_record())
        h.record(_make_record())
        assert h.count == 3

    def test_clear(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        h.record(_make_record())
        h.clear()
        assert h.count == 0

    def test_malformed_line_skipped(self, tmp_path: Path):
        f = tmp_path / "history.jsonl"
        f.write_text('{"timestamp":"x","problem":"p","invention_name":"i","source_domain":"d","novelty_score":0.5,"domain_distance":0.5,"structural_fidelity":0.5,"verdict":"OK","cost_usd":0.1,"duration_seconds":1.0,"success":true}\n{bad json}\n')
        h = InventionHistory(f)
        records = h.load()
        assert len(records) == 1


class TestSummarize:
    def test_basic_summary(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        h.record(_make_record(cost_usd=1.0, novelty_score=0.8))
        h.record(_make_record(cost_usd=2.0, novelty_score=0.9, source_domain="ecology"))
        h.record(_make_record(cost_usd=0.5, success=False, novelty_score=0.0))

        s = h.summarize()
        assert s.total_runs == 3
        assert s.successful == 2
        assert s.failed == 1
        assert s.total_cost_usd == pytest.approx(3.5)
        assert s.success_rate == pytest.approx(2 / 3)

    def test_top_domains(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        for _ in range(3):
            h.record(_make_record(source_domain="biology"))
        h.record(_make_record(source_domain="physics"))

        s = h.summarize()
        assert s.top_domains[0] == ("biology", 3)

    def test_last_n(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        for i in range(10):
            h.record(_make_record(cost_usd=float(i)))

        s = h.summarize(last_n=3)
        assert s.total_runs == 3

    def test_empty_summary(self, tmp_path: Path):
        h = InventionHistory(tmp_path / "history.jsonl")
        s = h.summarize()
        assert s.total_runs == 0
        assert s.success_rate == 0.0


class TestFormatAnalytics:
    def test_basic_format(self):
        s = AnalyticsSummary(
            total_runs=10, successful=8, failed=2,
            success_rate=0.8, total_cost_usd=15.0,
            avg_cost_per_run=1.5, avg_novelty=0.82,
            avg_duration=40.0,
            top_domains=[("biology", 5), ("physics", 3)],
            top_verdicts={"NOVEL": 6, "QUESTIONABLE": 2},
        )
        text = format_analytics(s)
        assert "80%" in text
        assert "biology" in text
        assert "$15.00" in text
