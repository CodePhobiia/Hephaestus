"""File operations for Hephaestus tools."""
from pathlib import Path

# Workspace boundary for path traversal protection
_workspace_root: Path | None = None

def set_workspace_root(root: Path) -> None:
    """Set the workspace root for path traversal protection."""
    global _workspace_root
    _workspace_root = root.resolve()

def _resolve_safe_path(path: str) -> Path:
    """Resolve path and verify it's within workspace (if set)."""
    resolved = Path(path).resolve()
    if _workspace_root is not None and not str(resolved).startswith(str(_workspace_root)):
        raise PermissionError(
            f"Path traversal blocked: {path} resolves outside workspace { _workspace_root}"
        )
    return resolved


def read_file(path: str, max_chars: int = 20_000) -> str:
    """Read a file with path traversal protection and size limit."""
    safe_path = _resolve_safe_path(path)
    if not safe_path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    content = safe_path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_chars:
        return content[:max_chars] + f"\n... (truncated, {len(content)} total chars)"
    return content


def write_file(path: str, content: str, append: bool = False) -> str:
    """Write file with path traversal protection."""
    safe_path = _resolve_safe_path(path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    safe_path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {path}"


def list_directory(path: str) -> list[str]:
    """List directory with path traversal protection."""
    safe_path = _resolve_safe_path(path)
    if not safe_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    return sorted(str(child) for child in safe_path.iterdir())
