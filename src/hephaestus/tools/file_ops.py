"""File-system tools: read, write, list, search, grep."""

from __future__ import annotations

import fnmatch
from pathlib import Path


def read_file(path: str, max_chars: int = 20_000) -> str:
    """Read a file and return its contents (truncated to *max_chars*)."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: path does not exist: {p}"
    if p.is_dir():
        return f"Error: path is a directory, use list_directory instead: {p}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Error reading {p}: {exc}"
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
    return text


def write_file(path: str, content: str, workspace_root: str | Path | None = None) -> str:
    """Write *content* to *path*, validating it is within *workspace_root*."""
    p = Path(path).resolve()
    if workspace_root is not None:
        root = Path(workspace_root).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return f"Error: path {p} is outside workspace root {root}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"Error writing {p}: {exc}"
    return f"Wrote {len(content)} chars to {p}"


def list_directory(path: str, max_entries: int = 100) -> str:
    """List entries in a directory."""
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: path does not exist: {p}"
    if not p.is_dir():
        return f"Error: path is not a directory: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    except OSError as exc:
        return f"Error listing {p}: {exc}"
    lines: list[str] = []
    for entry in entries[:max_entries]:
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{entry.name}{suffix}")
    if len(entries) > max_entries:
        lines.append(f"... and {len(entries) - max_entries} more entries")
    return "\n".join(lines)


def search_files(pattern: str, directory: str, max_results: int = 50) -> str:
    """Find files matching a glob-like *pattern* under *directory*."""
    d = Path(directory).resolve()
    if not d.exists():
        return f"Error: directory does not exist: {d}"
    if not d.is_dir():
        return f"Error: not a directory: {d}"
    matches: list[str] = []
    try:
        for entry in d.rglob("*"):
            if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                matches.append(str(entry.relative_to(d)))
                if len(matches) >= max_results:
                    break
    except OSError as exc:
        return f"Error searching {d}: {exc}"
    if not matches:
        return f"No files matching '{pattern}' in {d}"
    result = "\n".join(sorted(matches))
    if len(matches) >= max_results:
        result += f"\n... [capped at {max_results} results]"
    return result


def grep_search(query: str, directory: str, max_results: int = 50) -> str:
    """Search file contents for *query* under *directory*."""
    d = Path(directory).resolve()
    if not d.exists():
        return f"Error: directory does not exist: {d}"
    if not d.is_dir():
        return f"Error: not a directory: {d}"
    hits: list[str] = []
    query_lower = query.lower()
    try:
        for entry in d.rglob("*"):
            if not entry.is_file():
                continue
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if query_lower in line.lower():
                    rel = entry.relative_to(d)
                    hits.append(f"{rel}:{lineno}: {line.rstrip()}")
                    if len(hits) >= max_results:
                        break
            if len(hits) >= max_results:
                break
    except OSError as exc:
        return f"Error searching {d}: {exc}"
    if not hits:
        return f"No matches for '{query}' in {d}"
    result = "\n".join(hits)
    if len(hits) >= max_results:
        result += f"\n... [capped at {max_results} results]"
    return result
