"""Workspace scanner — builds a structural map of a codebase."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hephaestus.workspace.repo_dossier import RepoDossier

_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".hephaestus",
}

_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".cs",
    ".lua",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".proto",
    ".graphql",
}

_CONFIG_FILES = {
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "requirements.txt",
    "Pipfile",
    "go.mod",
    "Gemfile",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.ts",
    "jest.config.js",
}


@dataclass
class FileInfo:
    """Metadata about a single file."""

    path: str  # relative to workspace root
    extension: str
    size_bytes: int
    line_count: int
    mtime_ns: int = 0
    is_config: bool = False


@dataclass
class DirectoryInfo:
    """Metadata about a directory."""

    path: str
    file_count: int
    subdirs: list[str] = field(default_factory=list)


@dataclass
class GitInfo:
    """Git repository information."""

    branch: str = ""
    head_sha: str = ""
    has_changes: bool = False
    dirty_files: list[str] = field(default_factory=list)
    recent_commits: list[str] = field(default_factory=list)
    remote_url: str = ""


@dataclass
class WorkspaceSummary:
    """Complete summary of a workspace/codebase."""

    root: str
    total_files: int = 0
    total_lines: int = 0
    total_size_bytes: int = 0
    languages: dict[str, int] = field(default_factory=dict)  # ext -> file count
    language_lines: dict[str, int] = field(default_factory=dict)  # ext -> line count
    top_level_dirs: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)  # main.py, index.js, etc.
    readme_path: str = ""
    git: GitInfo | None = None
    tree: str = ""  # formatted directory tree
    files: list[FileInfo] = field(default_factory=list)
    repo_dossier: RepoDossier | None = None

    @property
    def primary_language(self) -> str:
        if not self.language_lines:
            return "unknown"
        return max(self.language_lines, key=self.language_lines.get)

    def format_summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Workspace: {self.root}",
            f"Files: {self.total_files} | Lines: {self.total_lines:,} | Size: {self.total_size_bytes // 1024:,} KB",
            f"Primary language: {self.primary_language}",
        ]
        if self.languages:
            lang_str = ", ".join(
                f"{ext}({n})" for ext, n in sorted(self.languages.items(), key=lambda x: -x[1])[:8]
            )
            lines.append(f"Languages: {lang_str}")
        if self.config_files:
            lines.append(f"Config files: {', '.join(self.config_files[:10])}")
        if self.entry_points:
            lines.append(f"Entry points: {', '.join(self.entry_points[:5])}")
        if self.git:
            lines.append(
                f"Git: {self.git.branch} {'(dirty)' if self.git.has_changes else '(clean)'}"
            )
        if self.repo_dossier:
            lines.extend(self.repo_dossier.summary_lines())
        return "\n".join(lines)


class WorkspaceScanner:
    """Scans a directory to build a WorkspaceSummary."""

    def __init__(
        self,
        root: Path | str,
        max_files: int = 5000,
        *,
        include_repo_dossier: bool = True,
        persist_repo_dossier: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.max_files = max_files
        self.include_repo_dossier = include_repo_dossier
        self.persist_repo_dossier = persist_repo_dossier

    def scan(self) -> WorkspaceSummary:
        """Perform full workspace scan."""
        summary = WorkspaceSummary(root=str(self.root))

        if not self.root.is_dir():
            return summary

        files: list[FileInfo] = []
        self._walk(self.root, files)
        summary.files = list(files)

        summary.total_files = len(files)
        summary.total_size_bytes = sum(f.size_bytes for f in files)
        summary.total_lines = sum(f.line_count for f in files)

        # Languages
        for f in files:
            if f.extension in _CODE_EXTENSIONS:
                summary.languages[f.extension] = summary.languages.get(f.extension, 0) + 1
                summary.language_lines[f.extension] = (
                    summary.language_lines.get(f.extension, 0) + f.line_count
                )

        # Config files
        summary.config_files = sorted(f.path for f in files if f.is_config)

        # Top-level dirs
        summary.top_level_dirs = sorted(
            d.name
            for d in self.root.iterdir()
            if d.is_dir() and d.name not in _IGNORE_DIRS and not d.name.startswith(".")
        )

        # Entry points
        entry_names = {
            "main.py",
            "app.py",
            "index.js",
            "index.ts",
            "main.rs",
            "main.go",
            "main.c",
            "server.py",
            "cli.py",
        }
        summary.entry_points = sorted(f.path for f in files if Path(f.path).name in entry_names)

        # README
        for name in ("README.md", "README.rst", "README.txt", "README"):
            if (self.root / name).is_file():
                summary.readme_path = name
                break

        # Git info
        summary.git = self._scan_git()

        if self.include_repo_dossier:
            try:
                from hephaestus.workspace.repo_dossier import build_repo_dossier

                summary.repo_dossier = build_repo_dossier(
                    self.root,
                    files=files,
                    primary_language=summary.primary_language,
                    config_files=summary.config_files,
                    entry_points=summary.entry_points,
                    persist=self.persist_repo_dossier,
                )
            except Exception as exc:
                logger.warning("Repo dossier build failed for %s: %s", self.root, exc)

        # Tree
        summary.tree = self._build_tree(max_depth=3, max_entries=50)

        return summary

    def _walk(self, directory: Path, files: list[FileInfo]) -> None:
        """Recursively walk the directory tree."""
        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name)
        except PermissionError:
            return

        for entry in entries:
            if len(files) >= self.max_files:
                return

            if entry.is_dir():
                if entry.name in _IGNORE_DIRS or entry.name.startswith("."):
                    continue
                self._walk(entry, files)
            elif entry.is_file():
                ext = entry.suffix.lower()
                if ext not in _CODE_EXTENSIONS and entry.name not in _CONFIG_FILES:
                    continue
                try:
                    size = entry.stat().st_size
                    mtime_ns = entry.stat().st_mtime_ns
                    if size > 1_000_000:  # skip files > 1MB
                        continue
                    line_count = entry.read_text(encoding="utf-8", errors="replace").count("\n")
                except (OSError, UnicodeDecodeError):
                    size = 0
                    line_count = 0
                    mtime_ns = 0

                rel = str(entry.relative_to(self.root))
                files.append(
                    FileInfo(
                        path=rel,
                        extension=ext,
                        size_bytes=size,
                        line_count=line_count,
                        mtime_ns=mtime_ns,
                        is_config=entry.name in _CONFIG_FILES,
                    )
                )

    def _scan_git(self) -> GitInfo | None:
        """Extract git information."""
        git_dir = self.root / ".git"
        if not git_dir.exists():
            return None

        info = GitInfo()
        try:
            info.branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=5,
            ).stdout.strip()
            info.head_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=5,
            ).stdout.strip()

            status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=5,
            ).stdout.strip()
            if status:
                info.has_changes = True
                info.dirty_files = [line[3:] for line in status.splitlines()[:20]]

            log = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=5,
            ).stdout.strip()
            if log:
                info.recent_commits = log.splitlines()

            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=5,
            ).stdout.strip()
            info.remote_url = remote

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        return info

    def _build_tree(self, max_depth: int = 3, max_entries: int = 50) -> str:
        """Build a formatted directory tree."""
        lines: list[str] = [self.root.name + "/"]
        self._tree_walk(self.root, "", 0, max_depth, max_entries, lines)
        return "\n".join(lines[:max_entries])

    def _tree_walk(
        self,
        directory: Path,
        prefix: str,
        depth: int,
        max_depth: int,
        max_entries: int,
        lines: list[str],
    ) -> None:
        if depth >= max_depth or len(lines) >= max_entries:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return

        visible = [e for e in entries if e.name not in _IGNORE_DIRS and not e.name.startswith(".")]
        for i, entry in enumerate(visible):
            if len(lines) >= max_entries:
                return
            connector = "└── " if i == len(visible) - 1 else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                extension = "    " if i == len(visible) - 1 else "│   "
                self._tree_walk(entry, prefix + extension, depth + 1, max_depth, max_entries, lines)


__all__ = ["WorkspaceScanner", "WorkspaceSummary", "FileInfo", "GitInfo"]
