"""Typed session transcript schema with JSON persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _now() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(_UTC).isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Transcript entry speaker role."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class EntryType(str, Enum):
    """Kind of transcript entry."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    INVENTION = "invention"
    REFINEMENT = "refinement"
    SUMMARY = "summary"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SessionMeta:
    """Metadata header for a session."""

    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    name: str = ""
    description: str = ""
    model: str = ""
    backend: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "backend": self.backend,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMeta:
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            model=data.get("model", ""),
            backend=data.get("backend", ""),
            tags=list(data.get("tags", [])),
        )


@dataclass
class TranscriptEntry:
    """Single turn in the session transcript."""

    role: str
    content: str
    timestamp: str = field(default_factory=_now)
    entry_type: str = EntryType.TEXT.value
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "entry_type": self.entry_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranscriptEntry:
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", _now()),
            entry_type=data.get("entry_type", EntryType.TEXT.value),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class InventionSnapshot:
    """Point-in-time snapshot of an invention produced during the session."""

    invention_name: str
    source_domain: str = ""
    architecture: str = ""
    key_insight: str = ""
    mapping_summary: str = ""
    score: float = 0.0
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invention_name": self.invention_name,
            "source_domain": self.source_domain,
            "architecture": self.architecture,
            "key_insight": self.key_insight,
            "mapping_summary": self.mapping_summary,
            "score": self.score,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InventionSnapshot:
        return cls(
            invention_name=data["invention_name"],
            source_domain=data.get("source_domain", ""),
            architecture=data.get("architecture", ""),
            key_insight=data.get("key_insight", ""),
            mapping_summary=data.get("mapping_summary", ""),
            score=float(data.get("score", 0.0)),
            timestamp=data.get("timestamp", _now()),
        )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """Full session transcript with typed persistence."""

    meta: SessionMeta = field(default_factory=SessionMeta)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    inventions: list[InventionSnapshot] = field(default_factory=list)
    pinned_context: list[str] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serialisable dictionary."""
        return {
            "meta": self.meta.to_dict(),
            "transcript": [e.to_dict() for e in self.transcript],
            "inventions": [i.to_dict() for i in self.inventions],
            "pinned_context": list(self.pinned_context),
            "active_tools": list(self.active_tools),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Reconstruct a *Session* from a serialised dictionary."""
        return cls(
            meta=SessionMeta.from_dict(data["meta"]),
            transcript=[
                TranscriptEntry.from_dict(e) for e in data.get("transcript", [])
            ],
            inventions=[
                InventionSnapshot.from_dict(i) for i in data.get("inventions", [])
            ],
            pinned_context=list(data.get("pinned_context", [])),
            active_tools=list(data.get("active_tools", [])),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> Session:
        """Deserialise from a JSON string.

        Raises
        ------
        json.JSONDecodeError
            If *text* is not valid JSON.
        KeyError
            If required fields are missing.
        """
        return cls.from_dict(json.loads(text))

    # -- file persistence ----------------------------------------------------

    def save(self, path: str | Path) -> Path:
        """Write the session to *path* as JSON, creating parent dirs."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        logger.debug("Session %s saved to %s", self.meta.id, p)
        return p

    @classmethod
    def load(cls, path: str | Path) -> Session:
        """Load a session from a JSON file.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        json.JSONDecodeError
            If the file is not valid JSON.
        """
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        return cls.from_json(text)

    @classmethod
    def resume(cls, path: str | Path) -> Session:
        """Load a session and stamp *updated_at*."""
        session = cls.load(path)
        session.meta.updated_at = _now()
        return session

    # -- transcript helpers --------------------------------------------------

    def append_entry(
        self,
        role: str,
        content: str,
        *,
        entry_type: str = EntryType.TEXT.value,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptEntry:
        """Create and append a transcript entry, returning it."""
        entry = TranscriptEntry(
            role=role,
            content=content,
            entry_type=entry_type,
            metadata=metadata or {},
        )
        self.transcript.append(entry)
        self.meta.updated_at = _now()
        return entry

    def add_invention(self, **kwargs: Any) -> InventionSnapshot:
        """Snapshot an invention and append it to the session."""
        snap = InventionSnapshot(**kwargs)
        self.inventions.append(snap)
        self.meta.updated_at = _now()
        return snap

    def compact_transcript(self, keep_last_n: int = 10) -> None:
        """Replace older entries with a single summary entry.

        Keeps the last *keep_last_n* entries intact.  All preceding entries
        are collapsed into one ``summary`` entry whose content lists the
        compacted entry count and role breakdown.
        """
        if len(self.transcript) <= keep_last_n:
            return

        old = self.transcript[: -keep_last_n]
        kept = self.transcript[-keep_last_n:]

        role_counts: dict[str, int] = {}
        for entry in old:
            role_counts[entry.role] = role_counts.get(entry.role, 0) + 1

        breakdown = ", ".join(f"{r}: {c}" for r, c in sorted(role_counts.items()))
        summary_content = (
            f"[Compacted {len(old)} earlier entries — {breakdown}]"
        )

        summary = TranscriptEntry(
            role=Role.SYSTEM.value,
            content=summary_content,
            entry_type=EntryType.SUMMARY.value,
            metadata={"compacted_count": len(old), "role_counts": role_counts},
        )

        self.transcript = [summary, *kept]
        self.meta.updated_at = _now()

    # -- directory scanning --------------------------------------------------

    @classmethod
    def list_sessions(cls, directory: str | Path) -> list[SessionMeta]:
        """Scan *directory* for ``*.json`` session files and return metadata.

        Files that fail to parse are silently skipped.
        """
        d = Path(directory)
        if not d.is_dir():
            return []

        results: list[SessionMeta] = []
        for fp in sorted(d.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                results.append(SessionMeta.from_dict(data["meta"]))
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.debug("Skipping unparseable session file: %s", fp)
        return results
