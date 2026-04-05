"""Tests for persistent repo dossier generation."""

from __future__ import annotations

from pathlib import Path

from hephaestus.workspace.repo_dossier import build_repo_dossier
from hephaestus.workspace.scanner import WorkspaceScanner


def _make_repo_workspace(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "demo"
    (package / "cli").mkdir(parents=True)
    (package / "core").mkdir(parents=True)
    (package / "utils").mkdir(parents=True)
    (tmp_path / "tests" / "test_cli").mkdir(parents=True)
    (tmp_path / "tests" / "test_core").mkdir(parents=True)
    (tmp_path / "docs").mkdir()

    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "__init__.py").write_text("", encoding="utf-8")
    (package / "core" / "__init__.py").write_text("", encoding="utf-8")
    (package / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "main.py").write_text(
        "from demo.core.engine import run_engine\n"
        "from demo.utils.formatting import format_message\n\n"
        "def main() -> str:\n"
        "    return format_message(run_engine())\n",
        encoding="utf-8",
    )
    (package / "core" / "engine.py").write_text(
        "from demo.utils.formatting import format_message\n\n"
        "def run_engine() -> str:\n"
        "    return format_message('ok')\n",
        encoding="utf-8",
    )
    (package / "utils" / "formatting.py").write_text(
        "def format_message(value: str) -> str:\n    return f'[{value}]'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_cli" / "test_main.py").write_text(
        "from demo.cli.main import main\n\ndef test_main() -> None:\n    assert main() == '[ok]'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_core" / "test_engine.py").write_text(
        "from demo.core.engine import run_engine\n\n"
        "def test_engine() -> None:\n"
        "    assert run_engine() == '[ok]'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    (tmp_path / "docs" / "architecture.md").write_text(
        "# Architecture\n\nThe CLI calls the core engine.\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(
        "test:\n\tpytest\n\nlint:\n\truff check .\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "version = '0.1.0'\n"
        "dependencies = ['click>=8.1', 'pytest>=8.0']\n"
        "scripts = { demo = 'demo.cli.main:main' }\n"
        "[project.optional-dependencies]\n"
        "dev = ['ruff>=0.5', 'mypy>=1.10']\n"
        "[tool.ruff]\n"
        "line-length = 100\n",
        encoding="utf-8",
    )

    return tmp_path


class TestRepoDossier:
    def test_build_detects_components_commands_and_artifacts(self, tmp_path: Path) -> None:
        repo = _make_repo_workspace(tmp_path)
        summary = WorkspaceScanner(repo, include_repo_dossier=False).scan()

        dossier = build_repo_dossier(
            repo,
            files=summary.files,
            primary_language=summary.primary_language,
            config_files=summary.config_files,
            entry_points=summary.entry_points,
        )

        assert dossier.cache_state == "fresh"
        assert dossier.code_roots == ["src/demo"]
        assert dossier.test_roots == ["tests"]
        assert "README.md" in dossier.documentation_paths
        assert "docs/architecture.md" in dossier.documentation_paths
        assert {component.name for component in dossier.components} >= {"cli", "core", "utils"}
        assert any(
            edge.source == "cli" and edge.target == "core" for edge in dossier.dependency_edges
        )
        assert any(command.command == "make test" for command in dossier.commands)
        assert any(command.command == "pytest" for command in dossier.commands)
        assert any(command.command == "ruff check ." for command in dossier.commands)
        assert any(command.command == "demo" for command in dossier.commands)
        assert any(dep.name == "click" for dep in dossier.dependencies)
        assert dossier.architecture_notes
        assert Path(dossier.cache_path).is_file()
        assert Path(dossier.cache_path).with_suffix(".md").is_file()

    def test_build_reuses_cache_when_fingerprint_matches(self, tmp_path: Path) -> None:
        repo = _make_repo_workspace(tmp_path)
        summary = WorkspaceScanner(repo, include_repo_dossier=False).scan()

        first = build_repo_dossier(
            repo,
            files=summary.files,
            primary_language=summary.primary_language,
            config_files=summary.config_files,
            entry_points=summary.entry_points,
        )
        second = build_repo_dossier(
            repo,
            files=summary.files,
            primary_language=summary.primary_language,
            config_files=summary.config_files,
            entry_points=summary.entry_points,
        )

        assert first.fingerprint == second.fingerprint
        assert second.cache_state == "cached"

    def test_prompt_text_surfaces_subsystems_and_commands(self, tmp_path: Path) -> None:
        repo = _make_repo_workspace(tmp_path)
        summary = WorkspaceScanner(repo).scan()
        dossier = summary.repo_dossier

        assert dossier is not None
        prompt_text = dossier.to_prompt_text(max_chars=4_000)

        assert "REPO DOSSIER" in prompt_text
        assert "Subsystem map" in prompt_text
        assert "cli" in prompt_text
        assert "pytest" in prompt_text
