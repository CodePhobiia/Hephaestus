"""Workspace context — builds a rich context window from a codebase for the model."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hephaestus.workspace.scanner import WorkspaceScanner, WorkspaceSummary

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hephaestus.workspace.repo_dossier import RepoDossier


@dataclass
class WorkspaceContext:
    """Rich context derived from a workspace for injection into model prompts.

    Provides the model with enough information to understand the codebase
    without reading every file upfront.
    """

    summary: WorkspaceSummary
    repo_dossier: RepoDossier | None = None
    readme_content: str = ""
    config_contents: dict[str, str] = field(default_factory=dict)  # path -> content
    key_file_contents: dict[str, str] = field(default_factory=dict)  # path -> content
    budget_chars: int = 24_000

    @classmethod
    def from_directory(cls, root: Path | str, budget_chars: int = 24_000) -> WorkspaceContext:
        """Scan a directory and build workspace context."""
        root = Path(root).resolve()
        scanner = WorkspaceScanner(root)
        summary = scanner.scan()

        ctx = cls(summary=summary, repo_dossier=summary.repo_dossier, budget_chars=budget_chars)

        chars_used = len(summary.format_summary()) + len(summary.tree)

        if ctx.repo_dossier is not None:
            repo_text = ctx.repo_dossier.to_prompt_text(max_chars=min(7_000, budget_chars // 3))
            chars_used += len(repo_text)

        # Load README (most valuable context)
        if summary.readme_path:
            readme_path = root / summary.readme_path
            if readme_path.is_file():
                content = readme_path.read_text(encoding="utf-8", errors="replace")
                if chars_used + len(content) < budget_chars:
                    ctx.readme_content = content
                    chars_used += len(content)
                else:
                    # Truncate README to fit budget
                    available = budget_chars - chars_used - 100
                    if available > 500:
                        ctx.readme_content = content[:available] + "\n\n... [truncated]"
                        chars_used += available

        # Load key config files (small, high info density)
        for cfg_path in summary.config_files[:5]:
            full = root / cfg_path
            if full.is_file():
                try:
                    content = full.read_text(encoding="utf-8", errors="replace")
                    if len(content) < 2000 and chars_used + len(content) < budget_chars:
                        ctx.config_contents[cfg_path] = content
                        chars_used += len(content)
                except OSError:
                    continue

        # Load entry points (small, high value)
        for ep_path in summary.entry_points[:3]:
            full = root / ep_path
            if full.is_file():
                try:
                    content = full.read_text(encoding="utf-8", errors="replace")
                    if len(content) < 5000 and chars_used + len(content) < budget_chars:
                        ctx.key_file_contents[ep_path] = content
                        chars_used += len(content)
                except OSError:
                    continue

        return ctx

    def to_prompt_text(self) -> str:
        """Format the workspace context for injection into a model prompt."""
        sections: list[str] = []

        sections.append("=== WORKSPACE CONTEXT ===")
        sections.append(self.summary.format_summary())
        sections.append("")

        if self.summary.tree:
            sections.append("--- Directory Structure ---")
            sections.append(self.summary.tree)
            sections.append("")

        if self.repo_dossier:
            sections.append("--- Repo Dossier ---")
            sections.append(self.repo_dossier.to_prompt_text(max_chars=7_000))
            sections.append("")

        if self.summary.git:
            git = self.summary.git
            sections.append("--- Git Status ---")
            sections.append(f"Branch: {git.branch}")
            if git.head_sha:
                sections.append(f"HEAD: {git.head_sha[:12]}")
            if git.has_changes:
                sections.append(f"Dirty files: {', '.join(git.dirty_files[:10])}")
            if git.recent_commits:
                sections.append("Recent commits:")
                for commit in git.recent_commits[:5]:
                    sections.append(f"  {commit}")
            sections.append("")

        if self.readme_content:
            sections.append("--- README ---")
            sections.append(self.readme_content)
            sections.append("")

        if self.config_contents:
            sections.append("--- Config Files ---")
            for path, content in self.config_contents.items():
                sections.append(f"[{path}]")
                sections.append(content)
                sections.append("")

        if self.key_file_contents:
            sections.append("--- Key Files ---")
            for path, content in self.key_file_contents.items():
                sections.append(f"[{path}]")
                sections.append(content)
                sections.append("")

        sections.append("=== END WORKSPACE CONTEXT ===")
        return "\n".join(sections)


__all__ = ["WorkspaceContext"]
