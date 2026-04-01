"""Tests for session.todos — working-memory todo list."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from hephaestus.session.todos import (
    CANCELLED,
    COMPLETED,
    IN_PROGRESS,
    PENDING,
    TodoItem,
    TodoList,
)


# ── helpers ─────────────────────────────────────────────────────────


def _make_list(*titles: str) -> TodoList:
    """Build a TodoList pre-populated with pending items."""
    tl = TodoList()
    for t in titles:
        tl.add(t)
    return tl


# ── TodoItem basics ─────────────────────────────────────────────────


class TestTodoItem:
    def test_defaults(self) -> None:
        item = TodoItem(id="abc", title="Do thing")
        assert item.status == PENDING
        assert item.notes == ""
        assert isinstance(item.created_at, datetime)
        assert item.created_at.tzinfo is not None

    def test_custom_notes(self) -> None:
        item = TodoItem(id="xyz", title="Task", notes="extra context")
        assert item.notes == "extra context"


# ── add ─────────────────────────────────────────────────────────────


class TestAdd:
    def test_add_returns_pending_item(self) -> None:
        tl = TodoList()
        item = tl.add("First task")
        assert item.status == PENDING
        assert item.title == "First task"
        assert len(tl.items) == 1

    def test_add_with_notes(self) -> None:
        tl = TodoList()
        item = tl.add("Task", notes="some note")
        assert item.notes == "some note"

    def test_add_generates_unique_ids(self) -> None:
        tl = TodoList()
        ids = {tl.add(f"task-{i}").id for i in range(20)}
        assert len(ids) == 20

    def test_add_preserves_order(self) -> None:
        tl = _make_list("a", "b", "c")
        assert [i.title for i in tl.items] == ["a", "b", "c"]


# ── start / in_progress constraint ─────────────────────────────────


class TestStart:
    def test_start_marks_in_progress(self) -> None:
        tl = _make_list("task")
        tl.start(tl.items[0].id)
        assert tl.items[0].status == IN_PROGRESS

    def test_single_active_constraint(self) -> None:
        tl = _make_list("a", "b")
        tl.start(tl.items[0].id)
        tl.start(tl.items[1].id)
        # first auto-paused, second is active
        assert tl.items[0].status == PENDING
        assert tl.items[1].status == IN_PROGRESS

    def test_start_same_item_twice_is_idempotent(self) -> None:
        tl = _make_list("a")
        tl.start(tl.items[0].id)
        tl.start(tl.items[0].id)  # no error
        assert tl.items[0].status == IN_PROGRESS

    def test_start_completed_raises(self) -> None:
        tl = _make_list("a")
        tl.start(tl.items[0].id)
        tl.complete(tl.items[0].id)
        with pytest.raises(ValueError, match="Cannot start"):
            tl.start(tl.items[0].id)

    def test_start_cancelled_raises(self) -> None:
        tl = _make_list("a")
        tl.cancel(tl.items[0].id)
        with pytest.raises(ValueError, match="Cannot start"):
            tl.start(tl.items[0].id)

    def test_start_nonexistent_raises(self) -> None:
        tl = TodoList()
        with pytest.raises(KeyError):
            tl.start("does-not-exist")


# ── complete ────────────────────────────────────────────────────────


class TestComplete:
    def test_complete_from_in_progress(self) -> None:
        tl = _make_list("a")
        tl.start(tl.items[0].id)
        tl.complete(tl.items[0].id)
        assert tl.items[0].status == COMPLETED

    def test_complete_from_pending(self) -> None:
        tl = _make_list("a")
        tl.complete(tl.items[0].id)
        assert tl.items[0].status == COMPLETED

    def test_complete_already_completed_raises(self) -> None:
        tl = _make_list("a")
        tl.complete(tl.items[0].id)
        with pytest.raises(ValueError, match="Cannot complete"):
            tl.complete(tl.items[0].id)

    def test_complete_nonexistent_raises(self) -> None:
        tl = TodoList()
        with pytest.raises(KeyError):
            tl.complete("nope")


# ── cancel ──────────────────────────────────────────────────────────


class TestCancel:
    def test_cancel_pending(self) -> None:
        tl = _make_list("a")
        tl.cancel(tl.items[0].id)
        assert tl.items[0].status == CANCELLED

    def test_cancel_in_progress(self) -> None:
        tl = _make_list("a")
        tl.start(tl.items[0].id)
        tl.cancel(tl.items[0].id)
        assert tl.items[0].status == CANCELLED

    def test_cancel_already_cancelled_raises(self) -> None:
        tl = _make_list("a")
        tl.cancel(tl.items[0].id)
        with pytest.raises(ValueError, match="Cannot cancel"):
            tl.cancel(tl.items[0].id)


# ── get_active / get_pending ────────────────────────────────────────


class TestQueries:
    def test_get_active_none_when_empty(self) -> None:
        assert TodoList().get_active() is None

    def test_get_active_returns_in_progress(self) -> None:
        tl = _make_list("a", "b")
        tl.start(tl.items[1].id)
        assert tl.get_active() is tl.items[1]

    def test_get_pending(self) -> None:
        tl = _make_list("a", "b", "c")
        tl.start(tl.items[0].id)
        tl.complete(tl.items[0].id)
        pending = tl.get_pending()
        assert len(pending) == 2
        assert all(i.status == PENDING for i in pending)

    def test_get_pending_empty_list(self) -> None:
        assert TodoList().get_pending() == []


# ── summary ─────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_empty(self) -> None:
        assert TodoList().summary() == "No items."

    def test_summary_indicators(self) -> None:
        tl = _make_list("pending", "active", "done", "nope")
        tl.start(tl.items[1].id)
        tl.complete(tl.items[2].id)
        tl.cancel(tl.items[3].id)
        s = tl.summary()
        assert "[ ] pending" in s
        assert "[>] active" in s
        assert "[x] done" in s
        assert "[-] nope" in s

    def test_summary_includes_notes(self) -> None:
        tl = TodoList()
        tl.add("task", notes="see doc")
        assert "(see doc)" in tl.summary()


# ── clear_completed ─────────────────────────────────────────────────


class TestClearCompleted:
    def test_removes_completed_and_cancelled(self) -> None:
        tl = _make_list("a", "b", "c", "d")
        tl.complete(tl.items[0].id)
        tl.cancel(tl.items[1].id)
        removed = tl.clear_completed()
        assert removed == 2
        assert len(tl.items) == 2
        assert all(i.status == PENDING for i in tl.items)

    def test_clear_on_empty_list(self) -> None:
        assert TodoList().clear_completed() == 0


# ── serialization ───────────────────────────────────────────────────


class TestSerialization:
    def test_json_round_trip(self) -> None:
        tl = _make_list("a", "b")
        tl.start(tl.items[0].id)
        tl.complete(tl.items[0].id)
        tl.items[1].notes = "important"

        restored = TodoList.from_json(tl.to_json())
        assert len(restored.items) == 2
        assert restored.items[0].status == COMPLETED
        assert restored.items[1].notes == "important"
        assert restored.items[0].created_at == tl.items[0].created_at

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        tl = _make_list("x", "y")
        tl.start(tl.items[0].id)
        fpath = tmp_path / "todos.json"
        tl.save(fpath)
        loaded = TodoList.load(fpath)
        assert len(loaded.items) == 2
        assert loaded.items[0].status == IN_PROGRESS
        assert loaded.items[0].id == tl.items[0].id

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        tl = _make_list("z")
        fpath = tmp_path / "nested" / "deep" / "todos.json"
        tl.save(fpath)
        assert fpath.exists()
        loaded = TodoList.load(fpath)
        assert loaded.items[0].title == "z"

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TodoList.load(tmp_path / "nope.json")


# ── updated_at tracking ────────────────────────────────────────────


class TestTimestamps:
    def test_updated_at_changes_on_start(self) -> None:
        tl = _make_list("a")
        original = tl.items[0].updated_at
        tl.start(tl.items[0].id)
        assert tl.items[0].updated_at >= original
