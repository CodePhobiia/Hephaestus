"""Tests for workspace mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from hephaestus.workspace.mode import WorkspaceConfig, WorkspaceMode, _edit_file


class TestWorkspaceConfig:
    def test_defaults(self, tmp_path: Path):
        cfg = WorkspaceConfig(root=tmp_path)
        assert cfg.context_budget == 24_000
        assert cfg.auto_scan is True


class TestWorkspaceModeCreation:
    def test_create(self, tmp_path: Path):
        # Create a minimal workspace
        (tmp_path / "main.py").write_text("print('hello')\n")
        (tmp_path / "README.md").write_text("# Test\n")

        adapter = MagicMock()
        adapter.model = "test-model"

        mode = WorkspaceMode.create(root=tmp_path, adapter=adapter)
        assert mode.config.root == tmp_path
        assert "test-model" in mode.runtime.session.meta.model

    def test_get_summary(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')\n")
        adapter = MagicMock()
        adapter.model = "test"
        mode = WorkspaceMode.create(root=tmp_path, adapter=adapter)
        summary = mode.get_summary()
        assert "Files:" in summary

    def test_get_tree(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')\n")
        adapter = MagicMock()
        adapter.model = "test"
        mode = WorkspaceMode.create(root=tmp_path, adapter=adapter)
        tree = mode.get_tree()
        assert tree  # non-empty

    def test_rescan(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')\n")
        adapter = MagicMock()
        adapter.model = "test"
        mode = WorkspaceMode.create(root=tmp_path, adapter=adapter)
        assert mode.context.summary.total_files == 1

        # Add a file
        (tmp_path / "utils.py").write_text("x = 1\n")
        mode.rescan()
        assert mode.context.summary.total_files == 2


class TestEditFile:
    def test_basic_edit(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 1\n")
        result = _edit_file(tmp_path, "test.py", "return 1", "return 42")
        assert "Edited" in result
        assert f.read_text() == "def foo():\n    return 42\n"

    def test_outside_workspace(self, tmp_path: Path):
        result = _edit_file(tmp_path, "/etc/passwd", "x", "y")
        assert "outside" in result.lower()

    def test_file_not_found(self, tmp_path: Path):
        result = _edit_file(tmp_path, "nope.py", "x", "y")
        assert "not found" in result.lower()

    def test_old_text_not_found(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("hello world\n")
        result = _edit_file(tmp_path, "test.py", "nonexistent", "replacement")
        assert "not found" in result.lower()

    def test_ambiguous_match(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\nx = 1\n")
        result = _edit_file(tmp_path, "test.py", "x = 1", "x = 2")
        assert "appears 2 times" in result
