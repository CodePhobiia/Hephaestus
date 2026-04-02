"""Workspace mode — read, understand, and modify codebases."""

from hephaestus.workspace.scanner import WorkspaceScanner, WorkspaceSummary
from hephaestus.workspace.context import WorkspaceContext
from hephaestus.workspace.mode import WorkspaceMode
from hephaestus.workspace.inventor import WorkspaceInventor, WorkspaceInventionReport
from hephaestus.workspace.repo_dossier import RepoDossier, build_repo_dossier

__all__ = [
    "WorkspaceScanner", "WorkspaceSummary", "WorkspaceContext",
    "WorkspaceMode", "WorkspaceInventor", "WorkspaceInventionReport",
    "RepoDossier", "build_repo_dossier",
]
