"""Explicit working-memory todo list for multi-step agent work.

A lightweight ledger that tracks tasks through their lifecycle
(pending → in_progress → completed/cancelled) with the constraint
that at most one item may be *in_progress* at any time.

Usage::

    todos = TodoList()
    item = todos.add("Search prior art for rotary engines")
    todos.start(item.id)
    todos.complete(item.id)
    todos.save("session_todos.json")
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "TodoItem",
    "TodoList",
]

# ── status constants ────────────────────────────────────────────────

PENDING = "pending"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
CANCELLED = "cancelled"

_VALID_STATUSES = {PENDING, IN_PROGRESS, COMPLETED, CANCELLED}
_TERMINAL_STATUSES = {COMPLETED, CANCELLED}

# ── status indicators for summary() ────────────────────────────────

_STATUS_INDICATOR = {
    PENDING: "[ ]",
    IN_PROGRESS: "[>]",
    COMPLETED: "[x]",
    CANCELLED: "[-]",
}


# ── data classes ────────────────────────────────────────────────────


@dataclass
class TodoItem:
    """A single tracked task."""

    id: str
    title: str
    status: str = PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""


@dataclass
class TodoList:
    """An ordered collection of :class:`TodoItem` instances.

    Enforces the invariant that **at most one** item may be
    ``in_progress`` at any given time.  Starting a new item
    automatically pauses (resets to ``pending``) the currently
    active one.
    """

    items: list[TodoItem] = field(default_factory=list)

    # ── private helpers ─────────────────────────────────────────────

    def _find(self, item_id: str) -> TodoItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise KeyError(f"No todo item with id {item_id!r}")

    def _touch(self, item: TodoItem) -> None:
        item.updated_at = datetime.now(UTC)

    # ── public API ──────────────────────────────────────────────────

    def add(self, title: str, notes: str = "") -> TodoItem:
        """Create a new *pending* item and append it to the list."""
        item = TodoItem(
            id=uuid.uuid4().hex[:12],
            title=title,
            notes=notes,
        )
        self.items.append(item)
        logger.debug("added todo %s: %s", item.id, title)
        return item

    def start(self, item_id: str) -> None:
        """Mark *item_id* as ``in_progress``.

        If another item is already active it is automatically set back
        to ``pending``.  Raises :exc:`ValueError` if the target item
        is in a terminal status (completed / cancelled).
        """
        item = self._find(item_id)
        if item.status in _TERMINAL_STATUSES:
            raise ValueError(f"Cannot start item {item_id!r} with status {item.status!r}")
        # auto-pause the current active item
        active = self.get_active()
        if active is not None and active.id != item_id:
            active.status = PENDING
            self._touch(active)
            logger.debug("auto-paused todo %s", active.id)

        item.status = IN_PROGRESS
        self._touch(item)
        logger.debug("started todo %s", item_id)

    def complete(self, item_id: str) -> None:
        """Mark *item_id* as ``completed``."""
        item = self._find(item_id)
        if item.status in _TERMINAL_STATUSES:
            raise ValueError(f"Cannot complete item {item_id!r} with status {item.status!r}")
        item.status = COMPLETED
        self._touch(item)
        logger.debug("completed todo %s", item_id)

    def cancel(self, item_id: str) -> None:
        """Mark *item_id* as ``cancelled``."""
        item = self._find(item_id)
        if item.status in _TERMINAL_STATUSES:
            raise ValueError(f"Cannot cancel item {item_id!r} with status {item.status!r}")
        item.status = CANCELLED
        self._touch(item)
        logger.debug("cancelled todo %s", item_id)

    def get_active(self) -> TodoItem | None:
        """Return the single ``in_progress`` item, or ``None``."""
        for item in self.items:
            if item.status == IN_PROGRESS:
                return item
        return None

    def get_pending(self) -> list[TodoItem]:
        """Return all ``pending`` items in insertion order."""
        return [i for i in self.items if i.status == PENDING]

    def summary(self) -> str:
        """Return a human-readable multi-line summary of all items."""
        if not self.items:
            return "No items."
        lines: list[str] = []
        for item in self.items:
            indicator = _STATUS_INDICATOR.get(item.status, "[ ]")
            line = f"{indicator} {item.title}"
            if item.notes:
                line += f"  ({item.notes})"
            lines.append(line)
        return "\n".join(lines)

    def clear_completed(self) -> int:
        """Remove all completed and cancelled items. Returns count removed."""
        before = len(self.items)
        self.items = [i for i in self.items if i.status not in _TERMINAL_STATUSES]
        removed = before - len(self.items)
        logger.debug("cleared %d completed/cancelled items", removed)
        return removed

    # ── serialization ───────────────────────────────────────────────

    def to_json(self) -> str:
        """Serialize the list to a JSON string."""
        raw = []
        for item in self.items:
            d = asdict(item)
            d["created_at"] = item.created_at.isoformat()
            d["updated_at"] = item.updated_at.isoformat()
            raw.append(d)
        return json.dumps(raw, indent=2)

    @classmethod
    def from_json(cls, data: str) -> TodoList:
        """Deserialize from a JSON string produced by :meth:`to_json`."""
        raw = json.loads(data)
        items: list[TodoItem] = []
        for d in raw:
            d["created_at"] = datetime.fromisoformat(d["created_at"])
            d["updated_at"] = datetime.fromisoformat(d["updated_at"])
            items.append(TodoItem(**d))
        return cls(items=items)

    def save(self, path: str | Path) -> None:
        """Persist the list to *path* as JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        logger.debug("saved %d items to %s", len(self.items), p)

    @classmethod
    def load(cls, path: str | Path) -> TodoList:
        """Load a list from a JSON file written by :meth:`save`."""
        p = Path(path)
        return cls.from_json(p.read_text(encoding="utf-8"))
