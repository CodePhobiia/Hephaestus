"""Invention history analytics — tracks success rates, domain usage, and cost trends."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class InventionRecord:
    """A single invention run record for analytics."""

    timestamp: str
    problem: str
    invention_name: str
    source_domain: str
    novelty_score: float
    domain_distance: float
    structural_fidelity: float
    verdict: str
    cost_usd: float
    duration_seconds: float
    model: str = ""
    depth: int = 3
    success: bool = True


@dataclass
class AnalyticsSummary:
    """Aggregate analytics over invention history."""

    total_runs: int = 0
    successful: int = 0
    failed: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    avg_cost_per_run: float = 0.0
    avg_novelty: float = 0.0
    avg_duration: float = 0.0
    top_domains: list[tuple[str, int]] = field(default_factory=list)
    top_verdicts: dict[str, int] = field(default_factory=dict)
    cost_trend: list[float] = field(default_factory=list)  # last N costs


class InventionHistory:
    """Persistent invention history with analytics."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path.home() / ".hephaestus" / "history.jsonl"
        self._records: list[InventionRecord] | None = None

    def record(self, entry: InventionRecord) -> None:
        """Append a record to the history file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        # Invalidate cache
        self._records = None

    def load(self) -> list[InventionRecord]:
        """Load all records from the history file."""
        if self._records is not None:
            return self._records

        records: list[InventionRecord] = []
        if not self._path.is_file():
            self._records = records
            return records

        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(
                    InventionRecord(
                        **{
                            k: v
                            for k, v in data.items()
                            if k in InventionRecord.__dataclass_fields__
                        }
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed history line: %s", exc)

        self._records = records
        return records

    def summarize(self, last_n: int | None = None) -> AnalyticsSummary:
        """Compute analytics summary over history."""
        records = self.load()
        if last_n is not None:
            records = records[-last_n:]

        if not records:
            return AnalyticsSummary()

        successful = [r for r in records if r.success]
        failed = [r for r in records if not r.success]
        total_cost = sum(r.cost_usd for r in records)
        novelty_scores = [r.novelty_score for r in successful if r.novelty_score > 0]

        # Domain counts
        domain_counts: dict[str, int] = {}
        for r in successful:
            domain_counts[r.source_domain] = domain_counts.get(r.source_domain, 0) + 1
        top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Verdict counts
        verdict_counts: dict[str, int] = {}
        for r in successful:
            verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1

        return AnalyticsSummary(
            total_runs=len(records),
            successful=len(successful),
            failed=len(failed),
            success_rate=len(successful) / len(records),
            total_cost_usd=total_cost,
            avg_cost_per_run=total_cost / len(records),
            avg_novelty=sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0.0,
            avg_duration=sum(r.duration_seconds for r in records) / len(records),
            top_domains=top_domains,
            top_verdicts=verdict_counts,
            cost_trend=[r.cost_usd for r in records[-20:]],
        )

    def clear(self) -> None:
        """Clear all history."""
        if self._path.is_file():
            self._path.unlink()
        self._records = None

    @property
    def count(self) -> int:
        return len(self.load())


def format_analytics(summary: AnalyticsSummary) -> str:
    """Format analytics summary as a readable string."""
    lines = [
        f"Total runs: {summary.total_runs}",
        f"Success rate: {summary.success_rate:.0%} ({summary.successful}/{summary.total_runs})",
        f"Total cost: ${summary.total_cost_usd:.2f}",
        f"Avg cost/run: ${summary.avg_cost_per_run:.4f}",
        f"Avg novelty: {summary.avg_novelty:.2f}",
        f"Avg duration: {summary.avg_duration:.1f}s",
    ]
    if summary.top_domains:
        lines.append("Top domains:")
        for domain, count in summary.top_domains[:5]:
            lines.append(f"  {domain}: {count}")
    if summary.top_verdicts:
        lines.append("Verdicts:")
        for verdict, count in sorted(summary.top_verdicts.items()):
            lines.append(f"  {verdict}: {count}")
    return "\n".join(lines)


__all__ = ["InventionRecord", "AnalyticsSummary", "InventionHistory", "format_analytics"]
