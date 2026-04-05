"""Tests for workspace context."""

from __future__ import annotations

from pathlib import Path

from hephaestus.workspace.context import WorkspaceContext


def _make_workspace(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']\n")
    (tmp_path / "README.md").write_text("# My Project\n\nThis is a test project.\n")
    return tmp_path


class TestWorkspaceContext:
    def test_from_directory(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        ctx = WorkspaceContext.from_directory(ws)
        assert ctx.summary.total_files > 0
        assert ctx.repo_dossier is not None
        assert ctx.readme_content
        assert "My Project" in ctx.readme_content

    def test_loads_config_files(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        ctx = WorkspaceContext.from_directory(ws)
        assert any("pyproject.toml" in k for k in ctx.config_contents)

    def test_to_prompt_text(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        ctx = WorkspaceContext.from_directory(ws)
        text = ctx.to_prompt_text()
        assert "WORKSPACE CONTEXT" in text
        assert "REPO DOSSIER" in text
        assert "README" in text
        assert "My Project" in text

    def test_budget_limits(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        # Write a large README
        (ws / "README.md").write_text("# Big\n\n" + "x " * 50000)
        ctx = WorkspaceContext.from_directory(ws, budget_chars=1000)
        assert len(ctx.readme_content) < 1500  # truncated

    def test_empty_directory(self, tmp_path: Path):
        ctx = WorkspaceContext.from_directory(tmp_path)
        assert ctx.summary.total_files == 0
        assert ctx.readme_content == ""
        text = ctx.to_prompt_text()
        assert "WORKSPACE CONTEXT" in text

    def test_loads_entry_points(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        ctx = WorkspaceContext.from_directory(ws)
        # main.py is in src/, should be in key_files
        assert any("main.py" in k for k in ctx.key_file_contents)
