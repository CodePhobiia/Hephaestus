"""Internal benchmark harness for pipeline quality and performance."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    benchmark_id: str = ""
    problem: str = ""
    mode: str = "standard"
    depth: int = 3
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    # Performance
    total_duration_seconds: float = 0.0
    stage_durations: dict[str, float] = field(default_factory=dict)

    # Cost
    total_cost_usd: float = 0.0
    total_tokens: int = 0

    # Quality
    novelty_score: float = 0.0
    structural_validity: float = 0.0
    feasibility_rating: str = ""
    quality_gate_passed: bool = False
    decorative_signal_count: int = 0

    # Stability
    parse_failures: int = 0
    retries: int = 0
    error: str | None = None

    # Pipeline metadata
    candidates_generated: int = 0
    candidates_surviving: int = 0
    pressure_rounds_used: int = 0
    pantheon_rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "problem": self.problem,
            "mode": self.mode,
            "depth": self.depth,
            "timestamp": self.timestamp,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "stage_durations": {k: round(v, 2) for k, v in self.stage_durations.items()},
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "novelty_score": round(self.novelty_score, 3),
            "structural_validity": round(self.structural_validity, 3),
            "feasibility_rating": self.feasibility_rating,
            "quality_gate_passed": self.quality_gate_passed,
            "decorative_signal_count": self.decorative_signal_count,
            "parse_failures": self.parse_failures,
            "retries": self.retries,
            "error": self.error,
            "candidates_generated": self.candidates_generated,
            "candidates_surviving": self.candidates_surviving,
            "pressure_rounds_used": self.pressure_rounds_used,
            "pantheon_rounds": self.pantheon_rounds,
        }


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report across multiple runs."""

    results: list[BenchmarkResult] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.error is None)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if r.error is not None)

    @property
    def avg_cost_usd(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.total_cost_usd for r in self.results) / len(self.results)

    @property
    def avg_duration_seconds(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.total_duration_seconds for r in self.results) / len(self.results)

    @property
    def avg_novelty(self) -> float:
        scored = [r for r in self.results if r.novelty_score > 0]
        if not scored:
            return 0.0
        return sum(r.novelty_score for r in scored) / len(scored)

    @property
    def quality_gate_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.quality_gate_passed) / len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_runs": len(self.results),
            "successes": self.success_count,
            "failures": self.failure_count,
            "avg_cost_usd": round(self.avg_cost_usd, 4),
            "avg_duration_seconds": round(self.avg_duration_seconds, 2),
            "avg_novelty": round(self.avg_novelty, 3),
            "quality_gate_pass_rate": round(self.quality_gate_pass_rate, 3),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# Hephaestus Benchmark Report",
            "",
            f"Generated: {self.generated_at}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total runs | {len(self.results)} |",
            f"| Successes | {self.success_count} |",
            f"| Failures | {self.failure_count} |",
            f"| Avg cost | ${self.avg_cost_usd:.4f} |",
            f"| Avg duration | {self.avg_duration_seconds:.1f}s |",
            f"| Avg novelty | {self.avg_novelty:.3f} |",
            f"| Quality gate pass rate | {self.quality_gate_pass_rate:.1%} |",
            "",
        ]

        if self.results:
            lines.append("## Results by Mode and Depth")
            lines.append("")

            by_mode: dict[str, list[BenchmarkResult]] = {}
            for r in self.results:
                key = f"{r.mode} (depth={r.depth})"
                by_mode.setdefault(key, []).append(r)

            for mode_key, runs in sorted(by_mode.items()):
                avg_cost = sum(r.total_cost_usd for r in runs) / len(runs)
                avg_dur = sum(r.total_duration_seconds for r in runs) / len(runs)
                avg_nov = sum(r.novelty_score for r in runs) / len(runs)
                lines.append(f"### {mode_key}")
                lines.append(f"- Runs: {len(runs)}")
                lines.append(f"- Avg cost: ${avg_cost:.4f}")
                lines.append(f"- Avg duration: {avg_dur:.1f}s")
                lines.append(f"- Avg novelty: {avg_nov:.3f}")
                lines.append("")

        return "\n".join(lines)


__all__ = [
    "BenchmarkReport",
    "BenchmarkResult",
]
