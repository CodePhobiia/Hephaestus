"""Workspace mode — read, understand, and modify codebases."""

from hephaestus.workspace.context import WorkspaceContext
from hephaestus.workspace.inventor import WorkspaceInventionReport, WorkspaceInventor
from hephaestus.workspace.mode import WorkspaceMode
from hephaestus.workspace.repo_dossier import RepoDossier, build_repo_dossier
from hephaestus.workspace.scanner import WorkspaceScanner, WorkspaceSummary

__all__ = [
    "WorkspaceScanner",
    "WorkspaceSummary",
    "WorkspaceContext",
    "WorkspaceMode",
    "WorkspaceInventor",
    "WorkspaceInventionReport",
    "RepoDossier",
    "build_repo_dossier",
]
