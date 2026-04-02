"""Lightweight rejection ledger for BranchGenome."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from hephaestus.branchgenome.models import BranchGenome

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DEFAULT_LEDGER_PATH = Path.home() / ".hephaestus" / "branchgenome-rejections.jsonl"
_STOPWORDS = {
    "about",
    "after",
    "against",
    "already",
    "also",
    "among",
    "because",
    "before",
    "being",
    "both",
    "build",
    "built",
    "candidate",
    "constraint",
    "could",
    "domain",
    "from",
    "into",
    "mechanism",
    "must",
    "problem",
    "should",
    "solution",
    "still",
    "that",
    "their",
    "them",
    "then",
    "these",
    "this",
    "through",
    "under",
    "using",
    "with",
}
_REJECTED_OUTCOMES = {"invalid", "decorative", "derivative", "baseline_overlap"}


def normalize_text(text: str) -> str:
    """Normalize a text fragment for branch fingerprinting."""
    tokens = [token for token in _TOKEN_RE.findall((text or "").lower()) if len(token) > 2]
    filtered = [token for token in tokens if token not in _STOPWORDS]
    return " ".join(filtered)


def fingerprint_tokens(text: str) -> set[str]:
    """Tokenize a normalized structural fingerprint."""
    return set(normalize_text(text).split())


def extract_structural_fingerprint(parts: Iterable[str]) -> str:
    """Build a normalized fingerprint from a collection of text fragments."""
    tokens: set[str] = set()
    for part in parts:
        tokens.update(fingerprint_tokens(part))
    return " ".join(sorted(tokens))


def fingerprint_branch(branch: BranchGenome) -> str:
    """Extract a fingerprint from the branch commitments, recoveries, and questions."""
    texts = [commitment.statement for commitment in branch.commitments]
    texts.extend(operator.summary() for operator in branch.recovery_operators)
    texts.extend(branch.open_questions)
    return extract_structural_fingerprint(texts)


def fingerprint_translation(translation: Any) -> str:
    """Extract a fingerprint from a translated invention."""
    parts = [
        str(getattr(translation, "key_insight", "") or ""),
        str(getattr(translation, "architecture", "") or ""),
        str(getattr(translation, "phase1_abstract_mechanism", "") or ""),
        str(getattr(translation, "future_option_preservation", "") or ""),
    ]
    parts.extend(getattr(translation, "recovery_commitments", []) or [])
    return extract_structural_fingerprint(parts)


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


class RejectionLedger:
    """Append-only JSONL ledger for accepted and rejected structural patterns."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_LEDGER_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._records = self._load_records()

    @property
    def path(self) -> Path:
        return self._path

    def overlap(self, fingerprint: str) -> float:
        """Return a rejection-weighted overlap score in ``[0.0, 1.0]``."""
        subject = set(fingerprint.split())
        if not subject:
            return 0.0

        best_rejected = 0.0
        best_accepted = 0.0
        for record in self._records:
            other = set(str(record.get("fingerprint", "")).split())
            similarity = _jaccard_similarity(subject, other)
            if str(record.get("outcome", "")) == "accepted":
                best_accepted = max(best_accepted, similarity)
            else:
                best_rejected = max(best_rejected, similarity)

        return max(0.0, min(1.0, best_rejected - 0.25 * best_accepted))

    def record(self, fingerprint: str, outcome: str, summary: str) -> None:
        """Append a ledger entry and keep it available for future overlap checks."""
        normalized_outcome = outcome.strip().lower()
        if normalized_outcome not in _REJECTED_OUTCOMES | {"accepted"}:
            normalized_outcome = "invalid"

        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint,
            "outcome": normalized_outcome,
            "summary": summary,
        }
        self._records.append(record)

        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception as exc:
            logger.warning("BranchGenome ledger write failed: %s", exc)

    def _load_records(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []

        records: list[dict[str, Any]] = []
        try:
            with self._path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        records.append(parsed)
        except Exception as exc:
            logger.warning("BranchGenome ledger load failed: %s", exc)
        return records
