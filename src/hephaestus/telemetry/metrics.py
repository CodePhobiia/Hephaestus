"""Prometheus-compatible metrics collector."""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Counter:
    """Thread-safe counter metric."""

    name: str
    help_text: str
    values: dict[tuple[str, ...], float] = field(default_factory=lambda: defaultdict(float))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self.lock:
            self.values[key] += value


@dataclass
class _Histogram:
    """Simple histogram with fixed buckets."""

    name: str
    help_text: str
    buckets: tuple[float, ...] = (
        0.01,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
        300.0,
    )
    counts: dict[tuple[str, ...], list[int]] = field(default_factory=dict)
    sums: dict[tuple[str, ...], float] = field(default_factory=lambda: defaultdict(float))
    totals: dict[tuple[str, ...], int] = field(default_factory=lambda: defaultdict(int))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self.lock:
            if key not in self.counts:
                self.counts[key] = [0] * len(self.buckets)
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self.counts[key][i] += 1
            self.sums[key] += value
            self.totals[key] += 1


@dataclass
class _Gauge:
    """Thread-safe gauge metric."""

    name: str
    help_text: str
    values: dict[tuple[str, ...], float] = field(default_factory=lambda: defaultdict(float))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self.lock:
            self.values[key] = value

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self.lock:
            self.values[key] += value


class MetricsCollector:
    """In-process metrics collector with Prometheus text format export."""

    def __init__(self) -> None:
        self._counters: dict[str, _Counter] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all default Hephaestus metrics."""
        # Counters
        self.counter("heph_runs_total", "Total pipeline runs by mode, depth, status")
        self.counter("heph_tokens_total", "Total tokens used by provider")
        self.counter("heph_cost_usd_total", "Total cost in USD by provider and run type")
        self.counter("heph_parse_failures_total", "Total JSON parse failures")
        self.counter("heph_pantheon_reforge_total", "Total Pantheon reforge operations")
        self.counter("heph_tool_denials_total", "Total tool permission denials")
        self.counter("heph_provider_calls_total", "Total provider API calls")
        self.counter("heph_mcp_calls_total", "Total MCP tool calls")
        self.counter("heph_research_calls_total", "Total research API calls")
        self.counter("heph_cancellations_total", "Total run cancellations")

        # Histograms
        self.histogram("heph_stage_duration_seconds", "Pipeline stage duration")
        self.histogram("heph_provider_latency_seconds", "Provider API call latency")
        self.histogram(
            "heph_run_duration_seconds",
            "Total run duration",
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 900),
        )

        # Gauges
        self.gauge("heph_active_runs", "Currently active runs")
        self.gauge("heph_queued_runs", "Currently queued runs")
        self.gauge("heph_spend_usd_current_hour", "Spend in current hour window")

    def counter(self, name: str, help_text: str = "") -> _Counter:
        if name not in self._counters:
            self._counters[name] = _Counter(name=name, help_text=help_text)
        return self._counters[name]

    def histogram(
        self, name: str, help_text: str = "", buckets: tuple[float, ...] | None = None
    ) -> _Histogram:
        if name not in self._histograms:
            h = _Histogram(name=name, help_text=help_text)
            if buckets:
                h.buckets = buckets
            self._histograms[name] = h
        return self._histograms[name]

    def gauge(self, name: str, help_text: str = "") -> _Gauge:
        if name not in self._gauges:
            self._gauges[name] = _Gauge(name=name, help_text=help_text)
        return self._gauges[name]

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment a counter."""
        c = self._counters.get(name)
        if c:
            c.inc(labels, value)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Observe a histogram value."""
        h = self._histograms.get(name)
        if h:
            h.observe(value, labels)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge value."""
        g = self._gauges.get(name)
        if g:
            g.set(value, labels)

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        for c in self._counters.values():
            lines.append(f"# HELP {c.name} {c.help_text}")
            lines.append(f"# TYPE {c.name} counter")
            with c.lock:
                for label_key, val in c.values.items():
                    label_str = self._format_labels(label_key)
                    lines.append(f"{c.name}{label_str} {val}")

        for h in self._histograms.values():
            lines.append(f"# HELP {h.name} {h.help_text}")
            lines.append(f"# TYPE {h.name} histogram")
            with h.lock:
                for label_key in h.counts:
                    label_str = self._format_labels(label_key)
                    for i, bound in enumerate(h.buckets):
                        cumulative = sum(h.counts[label_key][: i + 1])
                        le_label = self._format_labels(label_key, extra={"le": str(bound)})
                        lines.append(f"{h.name}_bucket{le_label} {cumulative}")
                    inf_label = self._format_labels(label_key, extra={"le": "+Inf"})
                    lines.append(f"{h.name}_bucket{inf_label} {h.totals[label_key]}")
                    lines.append(f"{h.name}_sum{label_str} {h.sums[label_key]}")
                    lines.append(f"{h.name}_count{label_str} {h.totals[label_key]}")

        for g in self._gauges.values():
            lines.append(f"# HELP {g.name} {g.help_text}")
            lines.append(f"# TYPE {g.name} gauge")
            with g.lock:
                for label_key, val in g.values.items():
                    label_str = self._format_labels(label_key)
                    lines.append(f"{g.name}{label_str} {val}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_labels(label_key: tuple[str, ...], *, extra: dict[str, str] | None = None) -> str:
        all_labels = dict(label_key)
        if extra:
            all_labels.update(extra)
        if not all_labels:
            return ""
        pairs = ",".join(f'{k}="{v}"' for k, v in sorted(all_labels.items()))
        return "{" + pairs + "}"


# Global singleton
_global_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = MetricsCollector()
    return _global_metrics


__all__ = [
    "MetricsCollector",
    "get_metrics",
]
