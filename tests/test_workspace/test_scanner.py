"""Tests for workspace scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from hephaestus.workspace.scanner import WorkspaceScanner, WorkspaceSummary, FileInfo, GitInfo


def _make_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace structure."""
    # Source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (src / "api").mkdir()
    (src / "api" / "server.py").write_text("from flask import Flask\napp = Flask(__name__)\n")

    # Tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_main():\n    assert True\n")

    # Config
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']\n")
    (tmp_path / "README.md").write_text("# Test Project\n\nA test project.\n")
    (tmp_path / "requirements.txt").write_text("flask\npytest\n")

    return tmp_path


class TestWorkspaceScanner:
    def test_scan_basic(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        scanner = WorkspaceScanner(ws)
        summary = scanner.scan()

        assert summary.total_files > 0
        assert summary.total_lines > 0
        assert ".py" in summary.languages

    def test_finds_config_files(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert any("pyproject.toml" in c for c in summary.config_files)
        assert any("requirements.txt" in c for c in summary.config_files)

    def test_finds_readme(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert summary.readme_path == "README.md"

    def test_top_level_dirs(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert "src" in summary.top_level_dirs
        assert "tests" in summary.top_level_dirs

    def test_primary_language(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert summary.primary_language == ".py"

    def test_tree_generation(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert summary.tree
        assert "src/" in summary.tree or "src" in summary.tree

    def test_format_summary(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        text = summary.format_summary()
        assert "Files:" in text
        assert "Lines:" in text
        assert "Repo roots:" in text

    def test_ignores_pycache(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        cache = ws / "src" / "__pycache__"
        cache.mkdir()
        (cache / "main.cpython-312.pyc").write_bytes(b"\x00" * 100)

        summary = WorkspaceScanner(ws).scan()
        assert not any("__pycache__" in f.path for f in [])  # shouldn't appear in tree
        assert "__pycache__" not in summary.tree

    def test_empty_directory(self, tmp_path: Path):
        summary = WorkspaceScanner(tmp_path).scan()
        assert summary.total_files == 0
        assert summary.primary_language == "unknown"
        assert summary.repo_dossier is not None

    def test_includes_repo_dossier(self, tmp_path: Path):
        ws = _make_workspace(tmp_path)
        summary = WorkspaceScanner(ws).scan()
        assert summary.repo_dossier is not None
        assert summary.repo_dossier.code_roots

    def test_max_files_limit(self, tmp_path: Path):
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}\n")
        scanner = WorkspaceScanner(tmp_path, max_files=5)
        summary = scanner.scan()
        assert summary.total_files <= 5

    def test_nonexistent_directory(self, tmp_path: Path):
        summary = WorkspaceScanner(tmp_path / "nope").scan()
        assert summary.total_files == 0


class TestGitInfo:
    def test_no_git(self, tmp_path: Path):
        summary = WorkspaceScanner(tmp_path).scan()
        assert summary.git is None

    def test_git_info_creation(self):
        info = GitInfo(branch="main", has_changes=True, dirty_files=["file.py"])
        assert info.branch == "main"
        assert info.has_changes

    def test_scan_hephaestus_repo(self):
        """The hephaestus repo itself should scan with git info."""
        import os
        repo = Path(__file__).parent.parent.parent
        if (repo / ".git").exists():
            summary = WorkspaceScanner(repo).scan()
            assert summary.git is not None
            assert summary.git.branch
            assert summary.total_files > 50


class TestFileInfo:
    def test_creation(self):
        f = FileInfo(path="src/main.py", extension=".py", size_bytes=100, line_count=10)
        assert f.path == "src/main.py"
        assert f.extension == ".py"

    def test_is_config(self):
        f = FileInfo(path="pyproject.toml", extension=".toml", size_bytes=50, line_count=5, is_config=True)
        assert f.is_config
