"""
Hephaestus configuration management and first-run onboarding.

Handles ``~/.hephaestus/config.yaml`` — model backend selection, default
parameters, and first-run setup wizard for interactive mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HEPHAESTUS_DIR = Path.home() / ".hephaestus"
CONFIG_PATH = HEPHAESTUS_DIR / "config.yaml"
INVENTIONS_DIR = HEPHAESTUS_DIR / "inventions"
SESSIONS_DIR = HEPHAESTUS_DIR / "sessions"

# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

VALID_BACKENDS = ("claude-max", "claude-cli", "api", "openrouter")
VALID_INTENSITIES = ("STANDARD", "AGGRESSIVE", "MAXIMUM")
VALID_OUTPUT_MODES = (
    "MECHANISM",
    "FRAMEWORK",
    "NARRATIVE",
    "SYSTEM",
    "PROTOCOL",
    "TAXONOMY",
    "INTERFACE",
)

# Import the single source-of-truth default model name
from hephaestus.core.cross_model import DEFAULT_MODEL as _DEFAULT_MODEL


@dataclass
class HephaestusConfig:
    """Runtime configuration loaded from ``~/.hephaestus/config.yaml``."""

    backend: str = "api"
    default_model: str = _DEFAULT_MODEL
    depth: int = 3
    candidates: int = 8
    auto_save: bool = True
    theme: str = "rich"
    divergence_intensity: str = "STANDARD"
    output_mode: str = "MECHANISM"

    # API keys (resolved from env at load time, never persisted)
    anthropic_api_key: str | None = field(default=None, repr=False)
    openai_api_key: str | None = field(default=None, repr=False)
    openrouter_api_key: str | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable dict (no secrets)."""
        return {
            "backend": self.backend,
            "default_model": self.default_model,
            "depth": self.depth,
            "candidates": self.candidates,
            "auto_save": self.auto_save,
            "theme": self.theme,
            "divergence_intensity": self.divergence_intensity,
            "output_mode": self.output_mode,
        }


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_config() -> HephaestusConfig | None:
    """Load config from disk.  Returns ``None`` if the file doesn't exist."""
    if not CONFIG_PATH.exists():
        return None
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        backend = data.get("backend", "api")
        if backend not in VALID_BACKENDS:
            backend = "api"
        depth = data.get("depth", 3)
        if not isinstance(depth, int) or not 1 <= depth <= 10:
            depth = 3
        candidates = data.get("candidates", 8)
        if not isinstance(candidates, int) or not 1 <= candidates <= 20:
            candidates = 8
        divergence_intensity = str(data.get("divergence_intensity", "STANDARD")).upper()
        if divergence_intensity not in VALID_INTENSITIES:
            divergence_intensity = "STANDARD"
        output_mode = str(data.get("output_mode", "MECHANISM")).upper()
        if output_mode not in VALID_OUTPUT_MODES:
            output_mode = "MECHANISM"
        cfg = HephaestusConfig(
            backend=backend,
            default_model=data.get("default_model", _DEFAULT_MODEL),
            depth=depth,
            candidates=candidates,
            auto_save=data.get("auto_save", True),
            theme=data.get("theme", "rich"),
            divergence_intensity=divergence_intensity,
            output_mode=output_mode,
        )
    except Exception:
        cfg = HephaestusConfig()
    _resolve_keys(cfg)
    return cfg


def save_config(cfg: HephaestusConfig) -> None:
    """Persist config to ``~/.hephaestus/config.yaml``."""
    HEPHAESTUS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        yaml.dump(cfg.to_dict(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _resolve_keys(cfg: HephaestusConfig) -> None:
    """Populate API key fields from the environment."""
    cfg.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    cfg.openai_api_key = os.environ.get("OPENAI_API_KEY")
    cfg.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")


def ensure_dirs() -> None:
    """Create the ``~/.hephaestus`` directory tree if needed."""
    for d in (HEPHAESTUS_DIR, INVENTIONS_DIR, SESSIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------


def _detect_claude_max() -> bool:
    """Return True if an OAT token is present in OpenClaw's auth-profiles store."""
    try:
        import json
        from pathlib import Path
        store_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        if not store_path.exists():
            return False
        store = json.loads(store_path.read_text())
        token = store.get("profiles", {}).get("anthropic:default", {}).get("token", "")
        return token.startswith("sk-ant-oat")
    except Exception:
        return False


def _detect_claude_cli() -> bool:
    """Return True if the ``claude`` binary is on PATH."""
    import shutil
    return shutil.which("claude") is not None


def run_onboarding(console: Console) -> HephaestusConfig:
    """
    Interactive first-run setup wizard.

    Asks the user to choose a backend, validates availability, saves config,
    and returns the resulting ``HephaestusConfig``.
    """
    console.print()

    # Detect available backends
    has_claude_max = _detect_claude_max()
    has_claude_cli = _detect_claude_cli()
    has_api = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))

    # Auto-recommend the best detected backend
    recommended = None
    if has_claude_max:
        recommended = "1"
    elif has_api:
        recommended = "3"
    elif has_claude_cli:
        recommended = "2"
    elif has_openrouter:
        recommended = "4"

    banner = Text()
    banner.append("  Welcome to Hephaestus interactive mode.\n", style="dim")
    banner.append("  Pick the backend this shell should use for invention runs.\n", style="dim")
    banner.append("  You can change it later with /backend or by editing ", style="dim")
    banner.append(str(CONFIG_PATH), style="bold cyan")
    banner.append(".\n\n", style="dim")

    banner.append("  [1] Claude Max", style="bold cyan")
    banner.append("  — Uses your Claude subscription (no per-run cost)", style="dim")
    if has_claude_max:
        banner.append("  <-- detected", style="bold green")
    if recommended == "1":
        banner.append("  (recommended)", style="bold green")
    banner.append("\n")

    banner.append("  [2] Claude CLI", style="bold cyan")
    banner.append("  — Runs via the `claude` command-line tool", style="dim")
    if has_claude_cli:
        banner.append("  <-- detected", style="bold green")
    if recommended == "2":
        banner.append("  (recommended)", style="bold green")
    banner.append("\n")

    banner.append("  [3] API keys", style="bold cyan")
    banner.append("   — Direct API access (Anthropic + OpenAI, pay-per-use)", style="dim")
    if has_api:
        banner.append("  <-- keys found", style="bold green")
    if recommended == "3":
        banner.append("  (recommended)", style="bold green")
    banner.append("\n")

    banner.append("  [4] OpenRouter", style="bold cyan")
    banner.append(" — Single API key, routes to many models", style="dim")
    if has_openrouter:
        banner.append("  <-- key found", style="bold green")
    if recommended == "4":
        banner.append("  (recommended)", style="bold green")
    banner.append("\n")

    console.print(
        Panel(
            banner,
            title="[bold yellow]First-Time Setup[/]",
            border_style="yellow",
            padding=(0, 1),
        )
    )

    backend_map = {"1": "claude-max", "2": "claude-cli", "3": "api", "4": "openrouter"}
    rec_hint = f" [dim](Enter for {recommended})[/]" if recommended else ""

    while True:
        try:
            choice = console.input(f"  [bold yellow]Choose 1-4{rec_hint}>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            fallback = recommended or "3"
            console.print(f"\n  [dim]Setup interrupted. Using option {fallback} for now.[/]")
            choice = recommended or "3"
            break
        if not choice and recommended:
            choice = recommended
            break
        if choice in backend_map:
            break
        console.print("  [red]Please enter 1, 2, 3, or 4.[/]")

    backend = backend_map.get(choice, "api")
    cfg = HephaestusConfig(backend=backend)
    _resolve_keys(cfg)

    # Validate the chosen backend
    ok = True
    if backend == "claude-max" and not _detect_claude_max():
        console.print(
            "  [yellow]Warning:[/] Claude Max login was not detected in "
            "[cyan]~/.openclaw/agents/main/agent/auth-profiles.json[/]."
        )
        ok = False
    elif backend == "claude-cli" and not _detect_claude_cli():
        console.print("  [yellow]Warning:[/] `claude` binary not found on PATH.")
        ok = False
    elif backend == "api":
        if not cfg.anthropic_api_key and not cfg.openai_api_key:
            console.print("  [yellow]Warning:[/] No API keys found. Set ANTHROPIC_API_KEY / OPENAI_API_KEY.")
            ok = False
    elif backend == "openrouter":
        if not cfg.openrouter_api_key:
            console.print("  [yellow]Warning:[/] No OPENROUTER_API_KEY found.")
            ok = False

    ensure_dirs()
    save_config(cfg)

    if ok:
        console.print(f"  [bold green]\u2713[/] Backend set to [cyan]{backend}[/]")
        console.print("  [dim]Next time, interactive mode will reuse this choice automatically.[/]")
    else:
        console.print("  [dim]The config was saved, but this backend still needs setup before it can run requests.[/]")
    console.print(f"  [bold green]\u2713[/] Config saved to [cyan]{CONFIG_PATH}[/]")
    console.print()

    return cfg
