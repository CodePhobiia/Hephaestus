"""Persistent repo dossier generation for repo-aware Hephaestus surfaces."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import tomllib
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
}

_DOC_FILENAMES = {
    "README.md",
    "README.rst",
    "README.txt",
    "CHANGELOG.md",
    "PRD.md",
    "FINAL_MERGE_NOTES.md",
}

_DOC_DIRS = {"docs", "doc", "design", "adr"}
_TEST_DIRS = {"tests", "test", "spec", "specs"}
_SKIP_CODE_ROOTS = _TEST_DIRS | _DOC_DIRS | {
    ".hephaestus",
    "vendor",
    "dist",
    "build",
    "coverage",
}
_MAKE_TARGETS = {"test", "lint", "format", "typecheck", "check", "build", "run", "dev"}
_VERSION_RE = re.compile(r"\s*[<>=!~].*$")


@dataclass(slots=True)
class RepoCommandHint:
    purpose: str
    command: str
    source: str


@dataclass(slots=True)
class RepoDependency:
    name: str
    ecosystem: str
    spec: str
    source: str


@dataclass(slots=True)
class RepoHotspot:
    path: str
    touches: int
    changed_lines: int


@dataclass(slots=True)
class RepoDependencyEdge:
    source: str
    target: str
    references: int


@dataclass(slots=True)
class RepoComponent:
    name: str
    root: str
    role: str
    file_count: int
    line_count: int
    key_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepoDossier:
    """Durable repo knowledge with structural and operational signals."""

    schema_version: int
    repo_name: str
    root: str
    generated_at: str
    fingerprint: str
    primary_language: str
    cache_path: str
    cache_state: str
    code_roots: list[str] = field(default_factory=list)
    test_roots: list[str] = field(default_factory=list)
    documentation_paths: list[str] = field(default_factory=list)
    key_artifacts: list[str] = field(default_factory=list)
    commands: list[RepoCommandHint] = field(default_factory=list)
    dependencies: list[RepoDependency] = field(default_factory=list)
    components: list[RepoComponent] = field(default_factory=list)
    dependency_edges: list[RepoDependencyEdge] = field(default_factory=list)
    hotspots: list[RepoHotspot] = field(default_factory=list)
    architecture_notes: list[str] = field(default_factory=list)

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def dominant_components(self) -> list[str]:
        return [component.name for component in self.components[:6]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RepoDossier:
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            repo_name=str(payload.get("repo_name", "")),
            root=str(payload.get("root", "")),
            generated_at=str(payload.get("generated_at", "")),
            fingerprint=str(payload.get("fingerprint", "")),
            primary_language=str(payload.get("primary_language", "unknown")),
            cache_path=str(payload.get("cache_path", "")),
            cache_state=str(payload.get("cache_state", "cached")),
            code_roots=list(payload.get("code_roots", []) or []),
            test_roots=list(payload.get("test_roots", []) or []),
            documentation_paths=list(payload.get("documentation_paths", []) or []),
            key_artifacts=list(payload.get("key_artifacts", []) or []),
            commands=[
                RepoCommandHint(**item) for item in payload.get("commands", []) or []
            ],
            dependencies=[
                RepoDependency(**item) for item in payload.get("dependencies", []) or []
            ],
            components=[
                RepoComponent(**item) for item in payload.get("components", []) or []
            ],
            dependency_edges=[
                RepoDependencyEdge(**item)
                for item in payload.get("dependency_edges", []) or []
            ],
            hotspots=[
                RepoHotspot(**item) for item in payload.get("hotspots", []) or []
            ],
            architecture_notes=list(payload.get("architecture_notes", []) or []),
        )

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.code_roots or self.test_roots:
            code_text = ", ".join(self.code_roots[:3]) or "n/a"
            test_text = ", ".join(self.test_roots[:3]) or "n/a"
            lines.append(f"Repo roots: code={code_text} | tests={test_text}")
        if self.components:
            names = ", ".join(self.dominant_components)
            extra = self.component_count - len(self.dominant_components)
            suffix = f" (+{extra} more)" if extra > 0 else ""
            lines.append(f"Subsystems: {names}{suffix}")
        if self.commands:
            lines.append(
                "Suggested commands: "
                + "; ".join(command.command for command in self.commands[:4])
            )
        return lines

    def format_status_text(self) -> str:
        lines = [
            f"[bold]Cache[/]  {self.cache_state} ({self.cache_path})",
            "[bold]Code Roots[/]  "
            + (", ".join(self.code_roots) if self.code_roots else "[dim]none[/]"),
            "[bold]Test Roots[/]  "
            + (", ".join(self.test_roots) if self.test_roots else "[dim]none[/]"),
        ]
        if self.components:
            component_text = ", ".join(self.dominant_components)
            extra = self.component_count - len(self.dominant_components)
            if extra > 0:
                component_text += f" (+{extra} more)"
            lines.append(f"[bold]Components[/]  {component_text}")
        if self.commands:
            lines.append(
                "[bold]Commands[/]  "
                + "; ".join(command.command for command in self.commands[:4])
            )
        if self.hotspots:
            lines.append(
                "[bold]Hotspots[/]  "
                + ", ".join(hotspot.path for hotspot in self.hotspots[:3])
            )
        return "\n".join(lines)

    def format_context_text(self) -> str:
        lines = [
            "[bold underline]Repo Dossier[/]",
            f"  cache: [cyan]{self.cache_state}[/] @ {self.cache_path}",
            f"  generated: [dim]{self.generated_at}[/]",
        ]

        lines.append("")
        lines.append("[bold underline]Architecture Notes[/]")
        if self.architecture_notes:
            for note in self.architecture_notes:
                lines.append(f"  - {note}")
        else:
            lines.append("  [dim]No architecture notes inferred.[/]")

        lines.append("")
        lines.append("[bold underline]Suggested Commands[/]")
        if self.commands:
            for command in self.commands:
                lines.append(
                    f"  [cyan]{command.purpose}[/]: {command.command} [dim]({command.source})[/]"
                )
        else:
            lines.append("  [dim]No commands inferred.[/]")

        lines.append("")
        lines.append("[bold underline]Subsystems[/]")
        if self.components:
            for component in self.components[:10]:
                line = (
                    f"  [cyan]{component.name}[/] "
                    f"({component.root}) files={component.file_count} lines={component.line_count}"
                )
                if component.test_files:
                    line += f" tests={len(component.test_files)}"
                if component.depends_on:
                    line += f" depends_on={', '.join(component.depends_on[:4])}"
                lines.append(line)
        else:
            lines.append("  [dim]No subsystems inferred.[/]")

        lines.append("")
        lines.append("[bold underline]Hotspots[/]")
        if self.hotspots:
            for hotspot in self.hotspots[:8]:
                lines.append(
                    f"  {hotspot.path} touches={hotspot.touches} "
                    f"changed_lines={hotspot.changed_lines}"
                )
        else:
            lines.append("  [dim]No git hotspots available.[/]")

        if self.documentation_paths:
            lines.append("")
            lines.append("[bold underline]Documentation[/]")
            for path in self.documentation_paths[:8]:
                lines.append(f"  {path}")

        return "\n".join(lines)

    def to_prompt_text(self, *, max_chars: int = 6000) -> str:
        parts = [
            "=== REPO DOSSIER ===",
            f"Repo: {self.repo_name}",
            f"Cache: {self.cache_state} ({self.cache_path})",
            f"Code roots: {', '.join(self.code_roots) if self.code_roots else 'n/a'}",
            f"Test roots: {', '.join(self.test_roots) if self.test_roots else 'n/a'}",
        ]

        if self.key_artifacts:
            parts.append("Key artifacts: " + ", ".join(self.key_artifacts[:8]))
        if self.architecture_notes:
            parts.append("Architecture notes:")
            parts.extend(f"- {note}" for note in self.architecture_notes[:6])
        if self.commands:
            parts.append("Suggested commands:")
            parts.extend(
                f"- {command.purpose}: {command.command} ({command.source})"
                for command in self.commands[:6]
            )
        if self.components:
            parts.append("Subsystem map:")
            for component in self.components[:10]:
                fragment = (
                    f"- {component.name} [{component.root}] "
                    f"{component.file_count} files / {component.line_count} lines"
                )
                if component.depends_on:
                    fragment += f" | depends on {', '.join(component.depends_on[:4])}"
                if component.test_files:
                    fragment += f" | tests {len(component.test_files)}"
                parts.append(fragment)
        if self.hotspots:
            parts.append("Git hotspots:")
            parts.extend(
                f"- {hotspot.path} "
                f"({hotspot.touches} touches, {hotspot.changed_lines} changed lines)"
                for hotspot in self.hotspots[:6]
            )
        parts.append("=== END REPO DOSSIER ===")

        return _trim_text("\n".join(parts), max_chars)

    def to_markdown(self) -> str:
        lines = [
            f"# Repo Dossier: {self.repo_name}",
            "",
            f"- Root: `{self.root}`",
            f"- Generated: `{self.generated_at}`",
            f"- Cache: `{self.cache_state}`",
            f"- Primary language: `{self.primary_language}`",
            "",
            "## Architecture Notes",
        ]
        if self.architecture_notes:
            lines.extend(f"- {note}" for note in self.architecture_notes)
        else:
            lines.append("- No architecture notes inferred.")

        lines.extend(["", "## Commands"])
        if self.commands:
            lines.extend(
                f"- `{command.purpose}`: `{command.command}` ({command.source})"
                for command in self.commands
            )
        else:
            lines.append("- No commands inferred.")

        lines.extend(["", "## Components"])
        if self.components:
            for component in self.components:
                line = (
                    f"- `{component.name}` at `{component.root}`: "
                    f"{component.file_count} files / {component.line_count} lines"
                )
                if component.depends_on:
                    line += f"; depends on {', '.join(component.depends_on)}"
                if component.test_files:
                    line += f"; tests {len(component.test_files)}"
                lines.append(line)
        else:
            lines.append("- No subsystems inferred.")

        lines.extend(["", "## Hotspots"])
        if self.hotspots:
            lines.extend(
                f"- `{hotspot.path}`: {hotspot.touches} touches / "
                f"{hotspot.changed_lines} changed lines"
                for hotspot in self.hotspots
            )
        else:
            lines.append("- No git hotspots available.")

        return "\n".join(lines) + "\n"


def build_repo_dossier(
    root: Path,
    *,
    files: Sequence[Any],
    primary_language: str,
    config_files: Sequence[str],
    entry_points: Sequence[str],
    persist: bool = True,
) -> RepoDossier:
    """Load a cached repo dossier when possible, otherwise rebuild it."""

    cache_json_path, cache_md_path = _cache_paths(root)
    fingerprint = _compute_fingerprint(root, files)
    cached = _load_cached_dossier(cache_json_path)
    if cached is not None and cached.fingerprint == fingerprint:
        cached.cache_state = "cached"
        cached.cache_path = str(cache_json_path)
        return cached

    code_roots = _detect_code_roots(root, files)
    test_roots = _detect_test_roots(files)
    documentation_paths = _detect_documentation_paths(files)
    key_artifacts = _detect_key_artifacts(config_files, documentation_paths, entry_points)
    commands = _detect_commands(root, config_files, entry_points, code_roots, test_roots)
    dependencies = _detect_dependencies(root, config_files)
    components, dependency_edges = _infer_components_and_edges(
        root,
        files,
        code_roots,
        test_roots,
        entry_points,
    )
    hotspots = _detect_hotspots(root)
    architecture_notes = _build_architecture_notes(
        code_roots=code_roots,
        test_roots=test_roots,
        components=components,
        dependency_edges=dependency_edges,
        hotspots=hotspots,
        key_artifacts=key_artifacts,
    )

    dossier = RepoDossier(
        schema_version=1,
        repo_name=root.name,
        root=str(root),
        generated_at=datetime.now(UTC).isoformat(),
        fingerprint=fingerprint,
        primary_language=primary_language,
        cache_path=str(cache_json_path),
        cache_state="fresh",
        code_roots=code_roots,
        test_roots=test_roots,
        documentation_paths=documentation_paths,
        key_artifacts=key_artifacts,
        commands=commands,
        dependencies=dependencies,
        components=components,
        dependency_edges=dependency_edges,
        hotspots=hotspots,
        architecture_notes=architecture_notes,
    )

    if persist:
        cache_json_path.parent.mkdir(parents=True, exist_ok=True)
        cache_json_path.write_text(
            json.dumps(dossier.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cache_md_path.write_text(dossier.to_markdown(), encoding="utf-8")

    return dossier


def _load_cached_dossier(cache_path: Path) -> RepoDossier | None:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return RepoDossier.from_dict(payload)
    except TypeError:
        return None


def _cache_paths(root: Path) -> tuple[Path, Path]:
    git_dir = _git_dir(root)
    cache_root = (
        git_dir / "hephaestus"
        if git_dir is not None
        else root / ".hephaestus" / "cache"
    )
    return cache_root / "repo_dossier.json", cache_root / "repo_dossier.md"


def _git_dir(root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None

    raw = result.stdout.strip()
    if result.returncode != 0 or not raw:
        return None

    git_dir = Path(raw)
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    return git_dir


def _compute_fingerprint(root: Path, files: Sequence[Any]) -> str:
    digest = hashlib.sha256()
    digest.update(str(root).encode("utf-8"))
    for item in sorted(files, key=lambda current: current.path):
        digest.update(item.path.encode("utf-8"))
        digest.update(str(item.size_bytes).encode("utf-8"))
        digest.update(str(getattr(item, "mtime_ns", 0)).encode("utf-8"))
    head_sha = _git_head_sha(root)
    if head_sha:
        digest.update(head_sha.encode("utf-8"))
    return digest.hexdigest()


def _git_head_sha(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _detect_code_roots(root: Path, files: Sequence[Any]) -> list[str]:
    counts: Counter[str] = Counter()
    top_level_code = False

    for item in files:
        if item.extension not in _CODE_EXTENSIONS:
            continue
        parts = Path(item.path).parts
        if len(parts) == 1:
            top_level_code = True
            continue
        top = parts[0]
        if top in _SKIP_CODE_ROOTS:
            continue
        if top == "src" and len(parts) >= 3:
            package_root = Path("src") / parts[1]
            if (root / package_root / "__init__.py").is_file():
                counts[str(package_root)] += 1
                continue
        counts[top] += 1

    roots = [path for path, _count in counts.most_common()]
    if top_level_code:
        roots.insert(0, ".")
    return roots


def _detect_test_roots(files: Sequence[Any]) -> list[str]:
    roots: list[str] = []
    seen: set[str] = set()
    for item in files:
        parts = Path(item.path).parts
        if not parts:
            continue
        top = parts[0]
        if top in _TEST_DIRS and top not in seen:
            roots.append(top)
            seen.add(top)
    return roots


def _detect_documentation_paths(files: Sequence[Any]) -> list[str]:
    docs: list[str] = []
    for item in files:
        path = item.path
        parts = Path(path).parts
        if path in _DOC_FILENAMES:
            docs.append(path)
            continue
        if parts and parts[0] in _DOC_DIRS:
            docs.append(path)
    return docs[:24]


def _detect_key_artifacts(
    config_files: Sequence[str],
    documentation_paths: Sequence[str],
    entry_points: Sequence[str],
) -> list[str]:
    artifacts: list[str] = []
    for item in list(documentation_paths[:6]) + list(config_files[:6]) + list(entry_points[:4]):
        if item not in artifacts:
            artifacts.append(item)
    return artifacts


def _detect_commands(
    root: Path,
    config_files: Sequence[str],
    entry_points: Sequence[str],
    code_roots: Sequence[str],
    test_roots: Sequence[str],
) -> list[RepoCommandHint]:
    commands: list[RepoCommandHint] = []
    seen_commands: set[str] = set()

    def add(purpose: str, command: str, source: str) -> None:
        if command in seen_commands:
            return
        seen_commands.add(command)
        commands.append(RepoCommandHint(purpose=purpose, command=command, source=source))

    makefile = root / "Makefile"
    if makefile.is_file():
        target_text = makefile.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"^([A-Za-z0-9_.-]+):", target_text, flags=re.MULTILINE):
            target = match.group(1)
            if target in _MAKE_TARGETS:
                add(target, f"make {target}", "Makefile")

    pyproject = root / "pyproject.toml"
    pyproject_data: dict[str, Any] = {}
    if pyproject.is_file():
        try:
            pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            pyproject_data = {}

    project = pyproject_data.get("project", {}) if isinstance(pyproject_data, dict) else {}
    optional_dependencies = (
        project.get("optional-dependencies", {})
        if isinstance(project, dict)
        else {}
    )
    scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
    dev_deps = (
        optional_dependencies.get("dev", [])
        if isinstance(optional_dependencies, dict)
        else []
    )
    project_deps = project.get("dependencies", []) if isinstance(project, dict) else []
    all_deps = [str(dep) for dep in list(project_deps) + list(dev_deps)]

    if pyproject.is_file():
        install_suffix = ".[dev]" if "dev" in optional_dependencies else "."
        add("install", f"pip install -e {install_suffix}", "pyproject.toml")
        add("build", "python -m build", "pyproject.toml")

    if test_roots or any("pytest" in dep for dep in all_deps) or "pytest.ini" in config_files:
        add("test", "pytest", "tests/ + pytest")
    if "tool" in pyproject_data and isinstance(pyproject_data["tool"], dict):
        tool_cfg = pyproject_data["tool"]
        if "ruff" in tool_cfg or any("ruff" in dep for dep in all_deps):
            add("lint", "ruff check .", "pyproject.toml")
        if any("mypy" in dep for dep in all_deps):
            target = code_roots[0] if code_roots else "src"
            add("typecheck", f"mypy {target}", "pyproject.toml")
    if scripts:
        script_name = next(iter(scripts))
        add("run", script_name, "project.scripts")

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for script_name in ("test", "lint", "build", "dev", "start"):
            script = (
                (data.get("scripts") or {}).get(script_name)
                if isinstance(data, dict)
                else None
            )
            if script:
                add(script_name, f"npm run {script_name}", "package.json")

    if not any(command.purpose == "run" for command in commands) and entry_points:
        first_entry = entry_points[0]
        if first_entry.endswith(".py"):
            add("run", f"python {first_entry}", "entry_points")

    return commands[:8]


def _detect_dependencies(root: Path, config_files: Sequence[str]) -> list[RepoDependency]:
    dependencies: list[RepoDependency] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, ecosystem: str, spec: str, source: str) -> None:
        key = (ecosystem, name)
        if key in seen:
            return
        seen.add(key)
        dependencies.append(
            RepoDependency(name=name, ecosystem=ecosystem, spec=spec, source=source)
        )

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        project = data.get("project", {}) if isinstance(data, dict) else {}
        for dep in project.get("dependencies", []) if isinstance(project, dict) else []:
            name = _normalize_dependency_name(str(dep))
            add(name, "python", str(dep), "pyproject.toml")
        optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
        if isinstance(optional, dict):
            for group, deps in optional.items():
                for dep in deps:
                    name = _normalize_dependency_name(str(dep))
                    add(name, "python", str(dep), f"pyproject.toml[{group}]")

    requirements = root / "requirements.txt"
    if requirements.is_file():
        for raw_line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            add(_normalize_dependency_name(line), "python", line, "requirements.txt")

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            for block_name in ("dependencies", "devDependencies"):
                block = data.get(block_name, {})
                if isinstance(block, dict):
                    for name, spec in block.items():
                        add(str(name), "node", str(spec), f"package.json:{block_name}")

    return dependencies[:24]


def _infer_components_and_edges(
    root: Path,
    files: Sequence[Any],
    code_roots: Sequence[str],
    test_roots: Sequence[str],
    entry_points: Sequence[str],
) -> tuple[list[RepoComponent], list[RepoDependencyEdge]]:
    code_by_root: dict[str, list[Any]] = {}
    for code_root in code_roots:
        code_by_root[code_root] = [
            item for item in files
            if item.extension in _CODE_EXTENSIONS and _under_root(item.path, code_root)
        ]

    component_members: dict[str, list[Any]] = defaultdict(list)
    component_roots: dict[str, str] = {}
    source_component_for_path: dict[str, str] = {}

    for code_root, members in code_by_root.items():
        root_path = Path(code_root)
        root_name = root_path.name if code_root != "." else root.name
        direct_file_count = 0

        for item in members:
            rel = Path(item.path)
            relative = rel if code_root == "." else rel.relative_to(root_path)
            if len(relative.parts) == 1:
                component_name = root_name
                direct_file_count += 1
            else:
                component_name = relative.parts[0]
            component_members[component_name].append(item)
            component_roots.setdefault(component_name, code_root)
            source_component_for_path[item.path] = component_name

        if direct_file_count == 0 and root_name in component_members and code_root != ".":
            component_members.pop(root_name, None)

    test_assignments = _map_tests_to_components(files, test_roots, component_members.keys())
    edge_counts = _infer_python_dependency_edges(
        root=root,
        files=files,
        code_roots=code_roots,
        source_component_for_path=source_component_for_path,
    )

    dependency_lookup: dict[str, list[str]] = defaultdict(list)
    dependency_edges: list[RepoDependencyEdge] = []
    for (source, target), references in sorted(
        edge_counts.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    ):
        dependency_edges.append(
            RepoDependencyEdge(source=source, target=target, references=references)
        )
        dependency_lookup[source].append(target)

    components: list[RepoComponent] = []
    for name, members in component_members.items():
        if not members:
            continue
        members.sort(key=lambda item: (-item.line_count, item.path))
        key_files = [item.path for item in members[:3]]
        for entry in entry_points:
            if any(item.path == entry for item in members) and entry not in key_files:
                key_files.insert(0, entry)
        components.append(
            RepoComponent(
                name=name,
                root=_component_root(name, members),
                role=_component_role(name, component_roots.get(name, "")),
                file_count=len(members),
                line_count=sum(item.line_count for item in members),
                key_files=key_files[:3],
                test_files=sorted(test_assignments.get(name, [])),
                depends_on=sorted(set(dependency_lookup.get(name, [])))[:6],
            )
        )

    components.sort(key=lambda component: (-component.line_count, component.name))
    return components, dependency_edges[:20]


def _map_tests_to_components(
    files: Sequence[Any],
    test_roots: Sequence[str],
    component_names: Iterable[str],
) -> dict[str, list[str]]:
    component_set = {name for name in component_names}
    assignments: dict[str, list[str]] = defaultdict(list)

    for item in files:
        path = Path(item.path)
        if not path.parts or path.parts[0] not in test_roots:
            continue
        candidate = None
        for part in path.parts[1:]:
            stem = part.removeprefix("test_").split(".")[0]
            if stem in component_set:
                candidate = stem
                break
        if candidate is None:
            stem = path.stem.removeprefix("test_")
            if stem in component_set:
                candidate = stem
        if candidate is not None:
            assignments[candidate].append(item.path)
    return assignments


def _infer_python_dependency_edges(
    *,
    root: Path,
    files: Sequence[Any],
    code_roots: Sequence[str],
    source_component_for_path: dict[str, str],
) -> Counter[tuple[str, str]]:
    package_roots = _python_package_roots(root, code_roots)
    module_to_component: dict[str, str] = {}
    module_name_for_path: dict[str, str] = {}

    for code_root, package_name in package_roots.items():
        base = Path(code_root)
        for item in files:
            if item.extension != ".py" or not _under_root(item.path, code_root):
                continue
            rel = Path(item.path).relative_to(base)
            module_name = _python_module_name(package_name, rel)
            module_name_for_path[item.path] = module_name
            module_to_component[module_name] = source_component_for_path.get(
                item.path,
                package_name,
            )

    edge_counts: Counter[tuple[str, str]] = Counter()
    for item in files:
        if item.extension != ".py":
            continue
        current_module = module_name_for_path.get(item.path)
        source_component = source_component_for_path.get(item.path)
        if not current_module or not source_component:
            continue

        full_path = root / item.path
        try:
            tree = ast.parse(full_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue

        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolve_import(current_module, node.level, node.module)
                if resolved:
                    imports.add(resolved)

        for imported in imports:
            target_component = _resolve_component_for_import(imported, module_to_component)
            if target_component and target_component != source_component:
                edge_counts[(source_component, target_component)] += 1

    return edge_counts


def _python_package_roots(root: Path, code_roots: Sequence[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for code_root in code_roots:
        if code_root == ".":
            continue
        candidate = root / code_root
        if (candidate / "__init__.py").is_file():
            mapping[code_root] = candidate.name
    return mapping


def _python_module_name(package_name: str, relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([package_name, *parts]) if parts else package_name


def _resolve_import(current_module: str, level: int, module: str | None) -> str | None:
    if level <= 0:
        return module

    current_parts = current_module.split(".")
    if level > len(current_parts):
        return None

    base_parts = current_parts[:-level]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(part for part in base_parts if part)


def _resolve_component_for_import(imported: str, module_to_component: dict[str, str]) -> str | None:
    parts = imported.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        target = module_to_component.get(candidate)
        if target is not None:
            return target
    return None


def _detect_hotspots(root: Path) -> list[RepoHotspot]:
    try:
        result = subprocess.run(
            ["git", "log", "--numstat", "--format=commit:%H", "-n", "200", "--", "."],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    touches: Counter[str] = Counter()
    changed_lines: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        if not line or line.startswith("commit:"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-":
            continue
        try:
            delta = int(added) + int(deleted)
        except ValueError:
            continue
        touches[path] += 1
        changed_lines[path] += delta

    hotspots = [
        RepoHotspot(path=path, touches=touch_count, changed_lines=changed_lines[path])
        for path, touch_count in touches.items()
    ]
    hotspots.sort(key=lambda item: (-item.touches, -item.changed_lines, item.path))
    return hotspots[:12]


def _build_architecture_notes(
    *,
    code_roots: Sequence[str],
    test_roots: Sequence[str],
    components: Sequence[RepoComponent],
    dependency_edges: Sequence[RepoDependencyEdge],
    hotspots: Sequence[RepoHotspot],
    key_artifacts: Sequence[str],
) -> list[str]:
    notes: list[str] = []
    if code_roots:
        code_text = ", ".join(code_roots[:3])
        notes.append(
            "Primary implementation lives under "
            f"{code_text}, with {len(components)} inferred subsystems."
        )
    if test_roots:
        covered = sum(1 for component in components if component.test_files)
        notes.append(
            f"Tests are anchored in {', '.join(test_roots[:3])} and map to {covered} subsystem(s)."
        )
    if dependency_edges:
        strongest = ", ".join(
            f"{edge.source}->{edge.target}"
            for edge in dependency_edges[:3]
        )
        notes.append(f"Strongest internal dependency edges are {strongest}.")
    if hotspots:
        notes.append(
            "Recent git churn concentrates in "
            + ", ".join(hotspot.path for hotspot in hotspots[:3])
            + "."
        )
    if key_artifacts:
        notes.append(
            "Key repo artifacts include "
            + ", ".join(key_artifacts[:5])
            + "."
        )
    return notes[:5]


def _normalize_dependency_name(spec: str) -> str:
    return _VERSION_RE.sub("", spec).strip()


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    trimmed = text[: max_chars - 16].rstrip()
    return trimmed + "\n... [truncated]"


def _under_root(path: str, root_name: str) -> bool:
    if root_name == ".":
        return "/" not in path
    return path == root_name or path.startswith(root_name + "/")


def _component_root(name: str, members: Sequence[Any]) -> str:
    if len(members) == 1:
        single = Path(members[0].path)
        return str(single.parent) if single.parent != Path(".") else name

    parent_sets = [
        [str(parent) for parent in Path(item.path).parents if str(parent) not in {"", "."}]
        for item in members
    ]
    common: set[str] | None = None
    for parents in parent_sets:
        current = set(parents)
        common = current if common is None else common & current
    if not common:
        return name
    return max(common, key=len)


def _component_role(name: str, root_name: str) -> str:
    lowered = name.lower()
    if lowered in {"cli", "web", "api", "server"} or root_name == "web":
        return "surface"
    if lowered in {"prompts", "config"}:
        return "configuration"
    return "subsystem"


__all__ = [
    "RepoCommandHint",
    "RepoComponent",
    "RepoDependency",
    "RepoDependencyEdge",
    "RepoDossier",
    "RepoHotspot",
    "build_repo_dossier",
]
