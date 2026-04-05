"""Tests for convergence tracking."""

from __future__ import annotations

from hephaestus.convergence.tracker import ConvergenceSignal, ConvergenceTracker


class TestConvergenceTracker:
    def test_empty_no_convergence(self):
        t = ConvergenceTracker()
        signal = t.check()
        assert not signal.is_converging

    def test_single_entry_no_convergence(self):
        t = ConvergenceTracker()
        t.add("Immune Scheduler", "biology", "T-cell memory", "Redis cache")
        assert not t.check().is_converging

    def test_diverse_entries_no_convergence(self):
        t = ConvergenceTracker()
        t.add("Immune Scheduler", "biology", "T-cell memory", "Redis layer")
        t.add("Volcanic Scaler", "geology", "Pressure dynamics", "Queue threshold")
        t.add("Music Router", "arts", "Counterpoint harmony", "Signal routing")
        assert not t.check().is_converging

    def test_similar_entries_converge(self):
        t = ConvergenceTracker()
        t.add("Immune Scheduler v1", "biology", "T-cell memory scheduling", "Redis immune layer")
        t.add(
            "Immune Scheduler v2",
            "biology",
            "T-cell memory scheduling patterns",
            "Redis immune memory layer",
        )
        t.add(
            "Immune Scheduler v3",
            "biology",
            "T-cell immune memory scheduling",
            "Redis immune cache layer",
        )
        signal = t.check()
        assert signal.is_converging
        assert signal.similarity_to_prior > 0.4
        assert "biology" in signal.ceiling_domain

    def test_recommendation_on_convergence(self):
        t = ConvergenceTracker()
        base = "Load balancing immune memory cells rapid recall pattern matching"
        t.add("X1", "biology", base, base)
        t.add("X2", "biology", base, base)
        t.add("X3", "biology", base + " extra", base)
        signal = t.check()
        assert signal.recommendation  # non-empty

    def test_count(self):
        t = ConvergenceTracker()
        assert t.count == 0
        t.add("A", "b", "c", "d")
        assert t.count == 1

    def test_clear(self):
        t = ConvergenceTracker()
        t.add("A", "b", "c", "d")
        t.clear()
        assert t.count == 0

    def test_window_size(self):
        t = ConvergenceTracker(window_size=2)
        # Add diverse entries that fall outside window
        t.add("X1", "biology", "immune memory", "redis")
        t.add("Y1", "physics", "quantum tunneling", "lattice")
        t.add("Z1", "arts", "counterpoint", "signal")
        # Only last 2 are compared — they're diverse
        assert not t.check().is_converging

    def test_custom_threshold(self):
        t = ConvergenceTracker(similarity_threshold=0.9)
        t.add("Similar alpha beta gamma delta", "d1", "x", "y")
        t.add("Similar alpha beta gamma epsilon", "d1", "x", "y")
        # With high threshold, moderate similarity doesn't trigger
        signal = t.check()
        assert signal.converged_count == 0


class TestConvergenceSignal:
    def test_dataclass(self):
        s = ConvergenceSignal(
            is_converging=True,
            similarity_to_prior=0.75,
            converged_count=3,
            ceiling_domain="biology",
            recommendation="Try harder",
        )
        assert s.is_converging
        assert s.ceiling_domain == "biology"
