"""
Persistent failure logging for rejected inventions.

Records are stored as append-only JSON Lines under ``~/.hephaestus/failures/``.
The module is intentionally light-weight: file-backed, scan-based queries, and
best-effort integration points for Genesis or future analytics jobs.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from hephaestus.core.verifier import VerifiedInvention

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_DEFAULT_LOG_DIR = Path.home() / ".hephaestus" / "failures"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    """Convert supported timestamp inputs to timezone-aware UTC datetimes."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _serialize_timestamp(value: datetime | str | None) -> str:
    """Serialize a timestamp to ISO-8601 in UTC."""
    parsed = _coerce_datetime(value) or _utc_now()
    return parsed.isoformat()


def _normalize_text(text: str) -> str:
    """Lowercase text and collapse it into alphanumeric tokens."""
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _normalized_tokens(text: str) -> set[str]:
    """Tokenize normalized text and drop very short tokens."""
    return {token for token in _normalize_text(text).split() if len(token) > 2}


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    """Deduplicate strings while preserving their original order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def detect_baseline_overlaps(
    invention_text: str,
    baselines: Sequence[str] | None = None,
) -> list[str]:
    """
    Detect textual overlap between an invention and burn-off baselines.

    Overlap is intentionally heuristic. A baseline counts as overlapping if its
    normalized form appears as a substring of the invention text or if at least
    60% of the baseline's informative tokens appear in the invention text.
    """
    if not baselines:
        return []

    normalized_invention = _normalize_text(invention_text)
    invention_tokens = _normalized_tokens(invention_text)
    overlaps: list[str] = []

    for baseline in baselines:
        normalized_baseline = _normalize_text(baseline)
        if not normalized_baseline:
            continue
        if normalized_baseline in normalized_invention:
            overlaps.append(baseline)
            continue

        baseline_tokens = _normalized_tokens(baseline)
        if len(baseline_tokens) < 3:
            continue

        overlap_ratio = len(baseline_tokens & invention_tokens) / len(baseline_tokens)
        if overlap_ratio >= 0.6:
            overlaps.append(baseline)

    return _dedupe_keep_order(overlaps)


def infer_rejection_reasons(
    invention: VerifiedInvention,
    baseline_overlaps: Sequence[str] | None = None,
) -> list[str]:
    """
    Convert verifier output into stable rejection reason codes.

    The codes are meant for analytics and querying, while the detailed critique
    is preserved separately on the record.
    """
    reasons: list[str] = []
    verdict = invention.verdict.upper()
    feasibility = invention.feasibility_rating.upper()

    if invention.adversarial_result.fatal_flaws:
        reasons.append("fatal_flaws")
    if verdict == "INVALID":
        reasons.append("verdict_invalid")
    elif verdict == "DERIVATIVE":
        reasons.append("verdict_derivative")
    elif verdict == "QUESTIONABLE":
        reasons.append("verdict_questionable")

    if feasibility == "LOW":
        reasons.append("low_feasibility")
    elif feasibility == "THEORETICAL":
        reasons.append("theoretical_feasibility")

    if baseline_overlaps:
        reasons.append("baseline_overlap")

    return _dedupe_keep_order(reasons)


@dataclass(slots=True)
class VerifierCritique:
    """Structured subset of the verifier's critical output."""

    verdict: str
    strongest_objection: str = ""
    fatal_flaws: list[str] = field(default_factory=list)
    structural_weaknesses: list[str] = field(default_factory=list)
    validity_notes: str = ""
    feasibility_notes: str = ""
    novelty_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert the critique to a JSON-serializable dictionary."""
        return {
            "verdict": self.verdict,
            "strongest_objection": self.strongest_objection,
            "fatal_flaws": list(self.fatal_flaws),
            "structural_weaknesses": list(self.structural_weaknesses),
            "validity_notes": self.validity_notes,
            "feasibility_notes": self.feasibility_notes,
            "novelty_notes": self.novelty_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifierCritique:
        """Create a critique from serialized data."""
        return cls(
            verdict=str(data.get("verdict", "")),
            strongest_objection=str(data.get("strongest_objection", "")),
            fatal_flaws=list(data.get("fatal_flaws", [])),
            structural_weaknesses=list(data.get("structural_weaknesses", [])),
            validity_notes=str(data.get("validity_notes", "")),
            feasibility_notes=str(data.get("feasibility_notes", "")),
            novelty_notes=str(data.get("novelty_notes", "")),
        )


@dataclass(slots=True)
class FailureRecord:
    """Single persisted rejected-invention record."""

    invention_name: str
    source_domain: str
    target_domain: str
    rejection_reasons: list[str]
    verifier_critique: VerifierCritique
    record_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: _serialize_timestamp(None))
    problem: str = ""
    key_insight: str = ""
    architecture: str = ""
    limitations: list[str] = field(default_factory=list)
    baseline_overlaps: list[str] = field(default_factory=list)
    novelty_score: float | None = None
    structural_validity: float | None = None
    implementation_feasibility: float | None = None
    feasibility_rating: str = ""
    prior_art_status: str = ""

    @property
    def domain_pair(self) -> tuple[str, str]:
        """Return the source/target domain pair."""
        return (self.source_domain, self.target_domain)

    @property
    def timestamp_dt(self) -> datetime:
        """Timestamp as a timezone-aware UTC datetime."""
        return _coerce_datetime(self.timestamp) or _utc_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a JSON-serializable dictionary."""
        return {
            "schema_version": _SCHEMA_VERSION,
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "problem": self.problem,
            "invention_name": self.invention_name,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "domain_pair": {
                "source_domain": self.source_domain,
                "target_domain": self.target_domain,
            },
            "rejection_reasons": list(self.rejection_reasons),
            "baseline_overlaps": list(self.baseline_overlaps),
            "key_insight": self.key_insight,
            "architecture": self.architecture,
            "limitations": list(self.limitations),
            "novelty_score": self.novelty_score,
            "structural_validity": self.structural_validity,
            "implementation_feasibility": self.implementation_feasibility,
            "feasibility_rating": self.feasibility_rating,
            "prior_art_status": self.prior_art_status,
            "verifier_critique": self.verifier_critique.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailureRecord:
        """Create a record from serialized data."""
        domain_pair = data.get("domain_pair", {})
        source_domain = str(data.get("source_domain") or domain_pair.get("source_domain", ""))
        target_domain = str(data.get("target_domain") or domain_pair.get("target_domain", ""))
        return cls(
            record_id=str(data.get("record_id", uuid4().hex)),
            timestamp=_serialize_timestamp(data.get("timestamp")),
            problem=str(data.get("problem", "")),
            invention_name=str(data.get("invention_name", "")),
            source_domain=source_domain,
            target_domain=target_domain,
            rejection_reasons=list(data.get("rejection_reasons", [])),
            baseline_overlaps=list(data.get("baseline_overlaps", [])),
            key_insight=str(data.get("key_insight", "")),
            architecture=str(data.get("architecture", "")),
            limitations=list(data.get("limitations", [])),
            novelty_score=data.get("novelty_score"),
            structural_validity=data.get("structural_validity"),
            implementation_feasibility=data.get("implementation_feasibility"),
            feasibility_rating=str(data.get("feasibility_rating", "")),
            prior_art_status=str(data.get("prior_art_status", "")),
            verifier_critique=VerifierCritique.from_dict(dict(data.get("verifier_critique", {}))),
        )

    @classmethod
    def from_verified_invention(
        cls,
        invention: VerifiedInvention,
        target_domain: str,
        *,
        problem: str = "",
        baselines: Sequence[str] | None = None,
        timestamp: datetime | str | None = None,
    ) -> FailureRecord:
        """Create a failure record from a verifier output object."""
        translation = invention.translation
        invention_text = "\n".join(
            [
                invention.invention_name,
                translation.key_insight,
                translation.architecture,
                *translation.limitations,
            ]
        )
        baseline_overlaps = detect_baseline_overlaps(
            invention_text=invention_text,
            baselines=baselines,
        )
        rejection_reasons = infer_rejection_reasons(invention, baseline_overlaps)

        critique = VerifierCritique(
            verdict=invention.verdict,
            strongest_objection=invention.adversarial_result.strongest_objection,
            fatal_flaws=list(invention.adversarial_result.fatal_flaws),
            structural_weaknesses=list(invention.adversarial_result.structural_weaknesses),
            validity_notes=invention.validity_notes,
            feasibility_notes=invention.feasibility_notes,
            novelty_notes=invention.novelty_notes,
        )

        return cls(
            timestamp=_serialize_timestamp(timestamp),
            problem=problem,
            invention_name=invention.invention_name,
            source_domain=invention.source_domain,
            target_domain=target_domain,
            rejection_reasons=rejection_reasons,
            verifier_critique=critique,
            baseline_overlaps=baseline_overlaps,
            key_insight=translation.key_insight,
            architecture=translation.architecture,
            limitations=list(translation.limitations),
            novelty_score=invention.novelty_score,
            structural_validity=invention.structural_validity,
            implementation_feasibility=invention.implementation_feasibility,
            feasibility_rating=invention.feasibility_rating,
            prior_art_status=invention.prior_art_status,
        )


class FailureLog:
    """Append-only file-backed failure log."""

    def __init__(self, log_dir: str | Path | None = None) -> None:
        self._log_dir = Path(log_dir) if log_dir is not None else _DEFAULT_LOG_DIR

    @property
    def log_dir(self) -> Path:
        """Directory containing the failure log partitions."""
        return self._log_dir

    def append(self, record: FailureRecord) -> Path:
        """Append a single failure record and return the file used."""
        paths = self.append_many([record])
        return paths[0]

    def append_many(self, records: Sequence[FailureRecord]) -> list[Path]:
        """Append multiple failure records, grouped by UTC day."""
        if not records:
            return []

        self._log_dir.mkdir(parents=True, exist_ok=True)
        lines_by_path: dict[Path, list[str]] = {}
        for record in records:
            path = self._path_for(record.timestamp_dt)
            serialized = json.dumps(record.to_dict(), sort_keys=True)
            lines_by_path.setdefault(path, []).append(serialized)

        for path, lines in lines_by_path.items():
            with path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line)
                    handle.write("\n")

        return list(lines_by_path)

    def append_rejected_inventions(
        self,
        inventions: Sequence[VerifiedInvention],
        target_domain: str,
        *,
        problem: str = "",
        baselines: Sequence[str] | None = None,
        timestamp: datetime | str | None = None,
    ) -> list[FailureRecord]:
        """
        Persist only inventions that classify as rejected.

        Rejection is derived from verifier verdicts, fatal flaws, feasibility,
        and any detected baseline overlap.
        """
        rejected_records: list[FailureRecord] = []
        for invention in inventions:
            record = FailureRecord.from_verified_invention(
                invention=invention,
                target_domain=target_domain,
                problem=problem,
                baselines=baselines,
                timestamp=timestamp,
            )
            if record.rejection_reasons:
                rejected_records.append(record)

        self.append_many(rejected_records)
        return rejected_records

    def query(
        self,
        *,
        source_domain: str | None = None,
        target_domain: str | None = None,
        domain_pair: tuple[str, str] | None = None,
        rejection_reason: str | None = None,
        verdict: str | None = None,
        baseline_overlap: str | None = None,
        invention_name: str | None = None,
        since: datetime | str | None = None,
        until: datetime | str | None = None,
        limit: int | None = None,
    ) -> list[FailureRecord]:
        """Query persisted failure records using simple scan filters."""
        if limit is not None and limit <= 0:
            return []

        if domain_pair is not None:
            source_domain, target_domain = domain_pair

        since_dt = _coerce_datetime(since)
        until_dt = _coerce_datetime(until)
        verdict_filter = verdict.upper() if verdict is not None else None

        matches: list[FailureRecord] = []
        for record in self._iter_records():
            if source_domain and record.source_domain != source_domain:
                continue
            if target_domain and record.target_domain != target_domain:
                continue
            if rejection_reason and rejection_reason not in record.rejection_reasons:
                continue
            if verdict_filter and record.verifier_critique.verdict.upper() != verdict_filter:
                continue
            if baseline_overlap and baseline_overlap not in record.baseline_overlaps:
                continue
            if invention_name and record.invention_name != invention_name:
                continue
            if since_dt and record.timestamp_dt < since_dt:
                continue
            if until_dt and record.timestamp_dt > until_dt:
                continue
            matches.append(record)

        matches.sort(key=lambda record: record.timestamp_dt, reverse=True)
        if limit is None:
            return matches
        return matches[:limit]

    def _iter_records(self) -> Iterable[FailureRecord]:
        """Yield all readable records from all partitions."""
        if not self._log_dir.exists():
            return []

        yielded: list[FailureRecord] = []
        for path in sorted(self._log_dir.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                        yielded.append(FailureRecord.from_dict(data))
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        logger.warning(
                            "Skipping malformed failure record in %s:%d: %s",
                            path,
                            line_number,
                            exc,
                        )
        return yielded

    def _path_for(self, timestamp: datetime) -> Path:
        """Return the partition file for a UTC timestamp."""
        utc_timestamp = timestamp.astimezone(UTC)
        return self._log_dir / f"{utc_timestamp.date().isoformat()}.jsonl"


__all__ = [
    "FailureLog",
    "FailureRecord",
    "VerifierCritique",
    "detect_baseline_overlaps",
    "infer_rejection_reasons",
]
