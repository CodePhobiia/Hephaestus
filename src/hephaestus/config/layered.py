"""
Layered configuration with precedence.

Sources (lowest to highest priority):
1. Built-in defaults (HephaestusConfig defaults)
2. User global: ~/.hephaestus/config.yaml
3. Project: .hephaestus/config.yaml (searched up directory tree)
4. Local override: .hephaestus/local.yaml (same dir as project config)
5. Environment variables: HEPHAESTUS_BACKEND, HEPHAESTUS_MODEL, etc.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml

from hephaestus.cli.config import (
    HEPHAESTUS_DIR,
    CONFIG_PATH,
    HephaestusConfig,
    VALID_BACKENDS,
    VALID_INTENSITIES,
    VALID_OUTPUT_MODES,
)

logger = logging.getLogger(__name__)

_ENV_MAP: dict[str, str] = {
    "HEPHAESTUS_BACKEND": "backend",
    "HEPHAESTUS_MODEL": "default_model",
    "HEPHAESTUS_DEPTH": "depth",
    "HEPHAESTUS_CANDIDATES": "candidates",
    "HEPHAESTUS_AUTO_SAVE": "auto_save",
    "HEPHAESTUS_THEME": "theme",
    "HEPHAESTUS_INTENSITY": "divergence_intensity",
    "HEPHAESTUS_OUTPUT_MODE": "output_mode",
}

_INT_FIELDS = {"depth", "candidates"}
_BOOL_FIELDS = {"auto_save"}

_VALIDATORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "backend": ("backend", VALID_BACKENDS),
    "divergence_intensity": ("divergence_intensity", VALID_INTENSITIES),
    "output_mode": ("output_mode", VALID_OUTPUT_MODES),
}


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""


class LayeredConfig:
    """Resolves configuration from multiple layered sources."""

    def __init__(self, start_dir: Path | None = None) -> None:
        self._start_dir = Path(start_dir) if start_dir else Path.cwd()
        self._sources: dict[str, str] = {}
        self._project_root: Path | None = None
        self._resolved: HephaestusConfig | None = None

    @staticmethod
    def find_project_root(start_dir: Path) -> Path | None:
        """Walk up from *start_dir* looking for a ``.hephaestus/`` directory."""
        current = start_dir.resolve()
        while True:
            candidate = current / ".hephaestus"
            if candidate.is_dir():
                return current
            parent = current.parent
            if parent == current:
                return None
            current = parent

    def resolve(self) -> HephaestusConfig:
        """Merge all layers and return the final config."""
        if self._resolved is not None:
            return self._resolved

        merged: dict[str, Any] = {}
        config_fields = {f.name for f in fields(HephaestusConfig)}

        # Layer 1: built-in defaults
        defaults = asdict(HephaestusConfig())
        for key, value in defaults.items():
            merged[key] = value
            self._sources[key] = "defaults"

        # Layer 2: user global
        self._apply_yaml(CONFIG_PATH, merged, config_fields, "user-global")

        # Layer 3 & 4: project + local
        self._project_root = self.find_project_root(self._start_dir)
        if self._project_root is not None:
            project_config = self._project_root / ".hephaestus" / "config.yaml"
            self._apply_yaml(project_config, merged, config_fields, f"project:{project_config}")

            local_config = self._project_root / ".hephaestus" / "local.yaml"
            self._apply_yaml(local_config, merged, config_fields, f"local:{local_config}")

        # Layer 5: environment variables
        for env_var, field_name in _ENV_MAP.items():
            raw = os.environ.get(env_var)
            if raw is not None and field_name in config_fields:
                merged[field_name] = _coerce(field_name, raw)
                self._sources[field_name] = f"env:{env_var}"

        # Validate
        self._validate(merged)

        self._resolved = HephaestusConfig(**{k: v for k, v in merged.items() if k in config_fields})
        return self._resolved

    def config_sources(self) -> dict[str, str]:
        """Return a mapping of field name → source label for the resolved config."""
        if self._resolved is None:
            self.resolve()
        return dict(self._sources)

    @property
    def project_root(self) -> Path | None:
        """The discovered project root, if any."""
        if self._resolved is None:
            self.resolve()
        return self._project_root

    def _apply_yaml(
        self,
        path: Path,
        merged: dict[str, Any],
        valid_fields: set[str],
        source_label: str,
    ) -> None:
        if not path.is_file():
            return
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as exc:
            logger.warning("Failed to read config %s: %s", path, exc)
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if key in valid_fields:
                merged[key] = value
                self._sources[key] = source_label

    @staticmethod
    def _validate(merged: dict[str, Any]) -> None:
        for field_name, (label, valid_values) in _VALIDATORS.items():
            value = merged.get(field_name)
            if value is not None and value not in valid_values:
                raise ConfigValidationError(
                    f"Invalid {label}: {value!r}. "
                    f"Must be one of: {', '.join(valid_values)}"
                )
        depth = merged.get("depth")
        if depth is not None:
            if not isinstance(depth, int) or depth < 1 or depth > 10:
                raise ConfigValidationError(
                    f"Invalid depth: {depth!r}. Must be integer 1-10."
                )
        candidates = merged.get("candidates")
        if candidates is not None:
            if not isinstance(candidates, int) or candidates < 1:
                raise ConfigValidationError(
                    f"Invalid candidates: {candidates!r}. Must be positive integer."
                )


def _coerce(field_name: str, raw: str) -> Any:
    """Coerce a string env var value to the appropriate type."""
    if field_name in _INT_FIELDS:
        return int(raw)
    if field_name in _BOOL_FIELDS:
        return raw.lower() in ("1", "true", "yes")
    return raw


__all__ = ["LayeredConfig", "ConfigValidationError"]
