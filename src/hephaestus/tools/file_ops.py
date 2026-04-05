"""File operations for Hephaestus tools."""

from pathlib import Path

# Workspace boundary for path traversal protection
_workspace_root: Path | None = None

# Directories and patterns to skip during search/grep
_SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", "venv", ".hg", ".svn"})
_BINARY_EXTENSIONS = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)


def set_workspace_root(root: Path) -> None:
    """Set the workspace root for path traversal protection."""
    global _workspace_root
    _workspace_root = root.resolve()


def _resolve_safe_path(path: str, workspace_root_override: Path | None = None) -> Path:
    """Resolve path and verify it's within workspace (if set)."""
    resolved = Path(path).resolve()
    active_root = (
        workspace_root_override if workspace_root_override is not None else _workspace_root
    )
    if active_root is not None:
        try:
            resolved.relative_to(active_root)
        except ValueError as err:
            raise PermissionError(
                f"Path traversal blocked: {path} resolves outside workspace {active_root}"
            ) from err
    return resolved


def read_file(path: str, max_chars: int = 20_000) -> str:
    """Read a file with path traversal protection and size limit."""
    try:
        safe_path = _resolve_safe_path(path)
        if not safe_path.is_file():
            return f"Error: File not found ({path})"
        content = safe_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n... (truncated, {len(content)} total chars)"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"


def write_file(
    path: str, content: str, append: bool = False, workspace_root: Path | None = None
) -> str:
    """Write file with path traversal protection."""
    try:
        safe_path = _resolve_safe_path(path, workspace_root_override=workspace_root)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with safe_path.open(mode, encoding="utf-8") as f:
            f.write(content)
        verb = "Appended" if append else "Wrote"
        return f"{verb} {len(content)} chars to {path}"
    except PermissionError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error writing file: {exc}"


def list_directory(path: str, max_entries: int = 100) -> str:
    """List directory with path traversal protection."""
    try:
        safe_path = _resolve_safe_path(path)
        if not safe_path.is_dir():
            return f"Error: Not a directory: {path}"

        dirs = []
        files = []
        for child in safe_path.iterdir():
            if child.is_dir():
                dirs.append(f"{child.name}/")
            else:
                files.append(child.name)

        entries = sorted(dirs) + sorted(files)

        if len(entries) > max_entries:
            shown = entries[:max_entries]
            return "\n".join(shown) + f"\n... ({len(entries) - max_entries} more entries)"
        return "\n".join(entries) if entries else "Directory is empty"
    except Exception as exc:
        return f"Error listing directory: {exc}"


def search_files(pattern: str, directory: str, max_results: int = 50) -> str:
    """Find files matching a glob pattern under a directory.

    Parameters
    ----------
    pattern:
        Glob pattern to match (e.g. ``'*.py'``, ``'test_*.js'``).
    directory:
        Root directory to search in.
    max_results:
        Maximum number of file paths to return.

    Returns
    -------
    str
        Newline-separated list of matching file paths, or a message if none found.
    """
    try:
        safe_dir = _resolve_safe_path(directory)
    except Exception as exc:
        return f"Error: {exc}"

    if not safe_dir.is_dir():
        return f"Error: Not a directory: {directory}"

    results: list[str] = []
    try:
        for match in safe_dir.rglob(pattern):
            if any(part in _SKIP_DIRS for part in match.parts):
                continue
            if match.is_file():
                # Enforce boundary logic on symbolic link resolves
                try:
                    str(_resolve_safe_path(str(match)))
                except PermissionError:
                    continue
                results.append(str(match))
                if len(results) >= max_results:
                    break
    except OSError as exc:
        return f"Search error: {exc}"

    if not results:
        return f"No files matching '{pattern}' found in {directory}"
    header = f"Found {len(results)} file(s) matching '{pattern}':"
    return header + "\n" + "\n".join(results)


def grep_search(query: str, directory: str, max_results: int = 50) -> str:
    """Search file contents for a text query under a directory.

    Parameters
    ----------
    query:
        Text to search for (case-insensitive substring match).
    directory:
        Root directory to search in.
    max_results:
        Maximum number of matching lines to return.

    Returns
    -------
    str
        Formatted results with file path, line number, and matching line content.
    """
    try:
        safe_dir = _resolve_safe_path(directory)
    except Exception as exc:
        return f"Error: {exc}"

    if not safe_dir.is_dir():
        return f"Error: Not a directory: {directory}"

    query_lower = query.lower()
    results: list[str] = []

    for file_path in safe_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in file_path.parts):
            continue
        if file_path.suffix.lower() in _BINARY_EXTENSIONS:
            continue
        try:
            # Enforce boundary logic on symbolic link resolves
            _resolve_safe_path(str(file_path))
        except PermissionError:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_num, line in enumerate(text.splitlines(), 1):
            if query_lower in line.lower():
                preview = line.strip()
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                results.append(f"{file_path}:{line_num}: {preview}")
                if len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break

    if not results:
        return f"No matches for '{query}' found in {directory}"
    header = f"Found {len(results)} match(es) for '{query}':"
    return header + "\n" + "\n".join(results)
