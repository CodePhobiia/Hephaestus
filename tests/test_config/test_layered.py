"""Tests for hephaestus.config.layered — layered configuration with precedence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from hephaestus.cli.config import HephaestusConfig
from hephaestus.config.layered import (
    ConfigValidationError,
    LayeredConfig,
    _deep_merge,
    find_project_root,
)

# ── Helpers ───────────────────────────────────────────────────────────────


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def _make_lc(
    tmp_path: Path,
    *,
    user: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    local: dict[str, Any] | None = None,
) -> LayeredConfig:
    """Build a LayeredConfig with optional per-layer YAML under tmp_path."""
    user_dir = tmp_path / "user_home" / ".hephaestus"
    user_dir.mkdir(parents=True, exist_ok=True)
    if user:
        _write_yaml(user_dir / "config.yaml", user)

    proj_dir = tmp_path / "project"
    if project is not None or local is not None:
        heph = proj_dir / ".hephaestus"
        heph.mkdir(parents=True, exist_ok=True)
        if project:
            _write_yaml(heph / "config.yaml", project)
        if local:
            _write_yaml(heph / "local.yaml", local)
    else:
        proj_dir.mkdir(parents=True, exist_ok=True)

    return LayeredConfig(start_dir=proj_dir, user_config_dir=user_dir)


# ── find_project_root ─────────────────────────────────────────────────────


class TestFindProjectRoot:
    def test_finds_root_in_current_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".hephaestus").mkdir()
        assert find_project_root(tmp_path) == tmp_path

    def test_finds_root_in_ancestor(self, tmp_path: Path) -> None:
        (tmp_path / ".hephaestus").mkdir()
        child = tmp_path / "a" / "b" / "c"
        child.mkdir(parents=True)
        assert find_project_root(child) == tmp_path

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        child = tmp_path / "no_config"
        child.mkdir()
        assert find_project_root(child) is None


# ── Defaults ──────────────────────────────────────────────────────────────


class TestDefaults:
    def test_defaults_only(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path)
        cfg = lc.resolve()
        assert cfg.backend == "api"
        assert cfg.depth == 3
        assert cfg.candidates == 8
        assert cfg.auto_save is True
        assert cfg.theme == "rich"
        assert cfg.divergence_intensity == "STANDARD"
        assert cfg.output_mode == "MECHANISM"
        assert cfg.use_perplexity_research is True
        assert cfg.perplexity_model == "sonar-pro"
        assert cfg.use_branchgenome_v1 is False
        assert cfg.use_adaptive_lens_engine is True
        assert cfg.allow_lens_bundle_fallback is True
        assert cfg.enable_derived_lens_composites is True
        assert cfg.use_pantheon_mode is False
        assert cfg.pantheon_max_rounds == 4
        assert cfg.pantheon_require_unanimity is True
        assert cfg.pantheon_allow_fail_closed is True
        assert cfg.pantheon_resolution_mode == "TASK_SENSITIVE"
        assert cfg.pantheon_max_survivors_to_council == 2
        assert cfg.pantheon_athena_model is None
        assert cfg.pantheon_hermes_model is None
        assert cfg.pantheon_apollo_model is None

    def test_sources_all_builtin(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path)
        sources = lc.config_sources()
        assert sources["backend"] == "<builtin>"
        assert sources["depth"] == "<builtin>"

    def test_resolve_returns_hephaestus_config(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path)
        assert isinstance(lc.resolve(), HephaestusConfig)


# ── User global config ────────────────────────────────────────────────────


class TestUserConfig:
    def test_user_overrides_defaults(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"backend": "openrouter", "depth": 5})
        cfg = lc.resolve()
        assert cfg.backend == "openrouter"
        assert cfg.depth == 5
        assert cfg.candidates == 8  # untouched default

    def test_user_source_tracked(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"theme": "plain"})
        sources = lc.config_sources()
        user_yaml = str(tmp_path / "user_home" / ".hephaestus" / "config.yaml")
        assert sources["theme"] == user_yaml
        assert sources["backend"] == "<builtin>"


# ── Project config ────────────────────────────────────────────────────────


class TestProjectConfig:
    def test_project_overrides_user(self, tmp_path: Path) -> None:
        lc = _make_lc(
            tmp_path,
            user={"backend": "openrouter", "depth": 7},
            project={"backend": "claude-cli"},
        )
        cfg = lc.resolve()
        assert cfg.backend == "claude-cli"  # project wins
        assert cfg.depth == 7  # user still applies

    def test_project_source_tracked(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, project={"candidates": 12})
        sources = lc.config_sources()
        proj_yaml = str(tmp_path / "project" / ".hephaestus" / "config.yaml")
        assert sources["candidates"] == proj_yaml


# ── Local override ────────────────────────────────────────────────────────


class TestLocalOverride:
    def test_local_overrides_project(self, tmp_path: Path) -> None:
        lc = _make_lc(
            tmp_path,
            project={"depth": 5, "backend": "claude-cli"},
            local={"depth": 9},
        )
        cfg = lc.resolve()
        assert cfg.depth == 9  # local wins
        assert cfg.backend == "claude-cli"  # project still applies

    def test_local_source_tracked(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, project={"depth": 5}, local={"depth": 9})
        sources = lc.config_sources()
        local_yaml = str(tmp_path / "project" / ".hephaestus" / "local.yaml")
        assert sources["depth"] == local_yaml


# ── Environment variables ─────────────────────────────────────────────────


class TestEnvVars:
    def test_env_overrides_all_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEPHAESTUS_BACKEND", "api")
        lc = _make_lc(
            tmp_path,
            user={"backend": "openrouter"},
            project={"backend": "claude-cli"},
        )
        assert lc.resolve().backend == "api"

    def test_env_source_tracked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEPHAESTUS_DEPTH", "7")
        lc = _make_lc(tmp_path)
        assert lc.config_sources()["depth"] == "<env>"

    def test_env_bool_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEPHAESTUS_AUTO_SAVE", "false")
        lc = _make_lc(tmp_path)
        assert lc.resolve().auto_save is False

    def test_env_int_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEPHAESTUS_CANDIDATES", "15")
        lc = _make_lc(tmp_path)
        assert lc.resolve().candidates == 15

    def test_env_research_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEPHAESTUS_USE_PERPLEXITY_RESEARCH", "false")
        monkeypatch.setenv("HEPHAESTUS_PERPLEXITY_MODEL", "sonar-deep-research")
        lc = _make_lc(tmp_path)
        cfg = lc.resolve()
        assert cfg.use_perplexity_research is False
        assert cfg.perplexity_model == "sonar-deep-research"

    def test_env_branchgenome_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HEPHAESTUS_USE_BRANCHGENOME_V1", "true")
        lc = _make_lc(tmp_path)
        assert lc.resolve().use_branchgenome_v1 is True

    def test_env_adaptive_lens_flags_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HEPHAESTUS_USE_ADAPTIVE_LENS_ENGINE", "false")
        monkeypatch.setenv("HEPHAESTUS_ALLOW_LENS_BUNDLE_FALLBACK", "false")
        monkeypatch.setenv("HEPHAESTUS_ENABLE_DERIVED_LENS_COMPOSITES", "false")
        lc = _make_lc(tmp_path)
        cfg = lc.resolve()
        assert cfg.use_adaptive_lens_engine is False
        assert cfg.allow_lens_bundle_fallback is False
        assert cfg.enable_derived_lens_composites is False

    def test_env_pantheon_flags_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HEPHAESTUS_USE_PANTHEON_MODE", "true")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_MAX_ROUNDS", "6")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_REQUIRE_UNANIMITY", "false")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_ALLOW_FAIL_CLOSED", "false")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_RESOLUTION_MODE", "STRICT")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_MAX_SURVIVORS_TO_COUNCIL", "3")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_ATHENA_MODEL", "gpt-4o")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_HERMES_MODEL", "claude-opus-4-5")
        monkeypatch.setenv("HEPHAESTUS_PANTHEON_APOLLO_MODEL", "gpt-4o-mini")
        lc = _make_lc(tmp_path)
        cfg = lc.resolve()
        assert cfg.use_pantheon_mode is True
        assert cfg.pantheon_max_rounds == 6
        assert cfg.pantheon_require_unanimity is False
        assert cfg.pantheon_allow_fail_closed is False
        assert cfg.pantheon_resolution_mode == "STRICT"
        assert cfg.pantheon_max_survivors_to_council == 3
        assert cfg.pantheon_athena_model == "gpt-4o"
        assert cfg.pantheon_hermes_model == "claude-opus-4-5"
        assert cfg.pantheon_apollo_model == "gpt-4o-mini"


# ── Full precedence ──────────────────────────────────────────────────────


class TestPrecedence:
    def test_full_stack(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """env > local > project > user > defaults."""
        monkeypatch.setenv("HEPHAESTUS_THEME", "rich")
        lc = _make_lc(
            tmp_path,
            user={"backend": "openrouter", "depth": 2, "candidates": 4, "theme": "plain"},
            project={"depth": 6, "candidates": 10, "theme": "minimal"},
            local={"candidates": 14, "theme": "custom"},
        )
        cfg = lc.resolve()
        assert cfg.backend == "openrouter"  # user
        assert cfg.depth == 6  # project
        assert cfg.candidates == 14  # local
        assert cfg.theme == "rich"  # env


# ── Validation ────────────────────────────────────────────────────────────


class TestValidation:
    def test_invalid_backend(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"backend": "nonexistent"})
        with pytest.raises(ConfigValidationError, match="Invalid backend"):
            lc.resolve()

    def test_invalid_depth_too_high(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"depth": 99})
        with pytest.raises(ConfigValidationError, match="Invalid depth"):
            lc.resolve()

    def test_invalid_candidates_zero(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"candidates": 0})
        with pytest.raises(ConfigValidationError, match="Invalid candidates"):
            lc.resolve()

    def test_invalid_divergence_intensity(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"divergence_intensity": "MEGA"})
        with pytest.raises(ConfigValidationError, match="Invalid divergence_intensity"):
            lc.resolve()

    def test_invalid_output_mode(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"output_mode": "YOLO"})
        with pytest.raises(ConfigValidationError, match="Invalid output_mode"):
            lc.resolve()


# ── Deep merge ────────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_nested_dicts_merged(self) -> None:
        base = {"a": {"x": 1, "y": 2}, "b": 10}
        over = {"a": {"y": 99, "z": 3}, "c": 20}
        result = _deep_merge(base, over)
        assert result == {"a": {"x": 1, "y": 99, "z": 3}, "b": 10, "c": 20}

    def test_scalar_override(self) -> None:
        assert _deep_merge({"k": 1}, {"k": 2}) == {"k": 2}

    def test_no_mutation(self) -> None:
        base = {"a": {"x": 1}}
        over = {"a": {"x": 2}}
        _deep_merge(base, over)
        assert base == {"a": {"x": 1}}


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user_home" / ".hephaestus"
        user_dir.mkdir(parents=True)
        (user_dir / "config.yaml").write_text("", encoding="utf-8")
        proj = tmp_path / "project"
        proj.mkdir()
        lc = LayeredConfig(start_dir=proj, user_config_dir=user_dir)
        assert lc.resolve().backend == "api"

    def test_yaml_with_non_dict(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user_home" / ".hephaestus"
        user_dir.mkdir(parents=True)
        (user_dir / "config.yaml").write_text("- a\n- b\n", encoding="utf-8")
        proj = tmp_path / "project"
        proj.mkdir()
        lc = LayeredConfig(start_dir=proj, user_config_dir=user_dir)
        assert lc.resolve().backend == "api"

    def test_unknown_fields_ignored(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, user={"backend": "api", "unknown_field": 42})
        cfg = lc.resolve()
        assert cfg.backend == "api"

    def test_resolve_caches(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path)
        first = lc.resolve()
        second = lc.resolve()
        assert first is second

    def test_project_root_property(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path, project={"depth": 5})
        assert lc.project_root == tmp_path / "project"

    def test_no_project_root(self, tmp_path: Path) -> None:
        lc = _make_lc(tmp_path)
        assert lc.project_root is None
