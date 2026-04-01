"""Tests for the layered configuration system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hephaestus.config.layered import ConfigValidationError, LayeredConfig


class TestFindProjectRoot:
    def test_finds_root_in_current_dir(self, tmp_path: Path):
        (tmp_path / ".hephaestus").mkdir()
        assert LayeredConfig.find_project_root(tmp_path) == tmp_path

    def test_finds_root_in_parent(self, tmp_path: Path):
        (tmp_path / ".hephaestus").mkdir()
        child = tmp_path / "deep" / "nested"
        child.mkdir(parents=True)
        assert LayeredConfig.find_project_root(child) == tmp_path

    def test_returns_none_when_absent(self, tmp_path: Path):
        assert LayeredConfig.find_project_root(tmp_path) is None


class TestDefaults:
    def test_resolve_returns_defaults_without_any_files(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "nonexistent.yaml")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 3
        assert cfg.divergence_intensity == "STANDARD"
        assert cfg.output_mode == "MECHANISM"

    def test_all_sources_are_defaults(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "nonexistent.yaml")
        lc = LayeredConfig(start_dir=tmp_path)
        lc.resolve()
        sources = lc.config_sources()
        assert all(v == "defaults" for v in sources.values())


class TestUserGlobalConfig:
    def test_user_config_overrides_defaults(self, tmp_path: Path, monkeypatch):
        user_cfg = tmp_path / "user_config.yaml"
        user_cfg.write_text(yaml.dump({"depth": 7, "backend": "openrouter"}))
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", user_cfg)

        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 7
        assert cfg.backend == "openrouter"
        sources = lc.config_sources()
        assert sources["depth"] == "user-global"
        assert sources["backend"] == "user-global"
        # Unset fields still come from defaults
        assert sources["theme"] == "defaults"


class TestProjectConfig:
    def test_project_config_overrides_user(self, tmp_path: Path, monkeypatch):
        # User config
        user_cfg = tmp_path / "user_config.yaml"
        user_cfg.write_text(yaml.dump({"depth": 7, "backend": "openrouter"}))
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", user_cfg)

        # Project config
        proj = tmp_path / "myproject"
        proj.mkdir()
        heph_dir = proj / ".hephaestus"
        heph_dir.mkdir()
        (heph_dir / "config.yaml").write_text(yaml.dump({"depth": 5}))

        lc = LayeredConfig(start_dir=proj)
        cfg = lc.resolve()
        assert cfg.depth == 5  # project wins
        assert cfg.backend == "openrouter"  # user still applies
        assert lc.project_root == proj

    def test_local_overrides_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")

        heph_dir = tmp_path / ".hephaestus"
        heph_dir.mkdir()
        (heph_dir / "config.yaml").write_text(yaml.dump({"depth": 5}))
        (heph_dir / "local.yaml").write_text(yaml.dump({"depth": 2}))

        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 2
        sources = lc.config_sources()
        assert "local:" in sources["depth"]


class TestEnvironmentVariables:
    def test_env_overrides_all_file_sources(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        heph_dir = tmp_path / ".hephaestus"
        heph_dir.mkdir()
        (heph_dir / "config.yaml").write_text(yaml.dump({"depth": 5}))

        monkeypatch.setenv("HEPHAESTUS_DEPTH", "9")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 9
        assert lc.config_sources()["depth"] == "env:HEPHAESTUS_DEPTH"

    def test_env_backend(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_BACKEND", "claude-max")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.backend == "claude-max"

    def test_env_bool_coercion(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_AUTO_SAVE", "false")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.auto_save is False

    def test_env_intensity(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_INTENSITY", "MAXIMUM")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.divergence_intensity == "MAXIMUM"


class TestPrecedenceChain:
    def test_full_precedence_chain(self, tmp_path: Path, monkeypatch):
        """env > local > project > user > defaults"""
        user_cfg = tmp_path / "user_config.yaml"
        user_cfg.write_text(yaml.dump({
            "depth": 2,
            "backend": "openrouter",
            "theme": "minimal",
            "divergence_intensity": "AGGRESSIVE",
        }))
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", user_cfg)

        proj = tmp_path / "proj"
        proj.mkdir()
        heph_dir = proj / ".hephaestus"
        heph_dir.mkdir()
        (heph_dir / "config.yaml").write_text(yaml.dump({
            "depth": 4,
            "backend": "claude-cli",
            "divergence_intensity": "MAXIMUM",
        }))
        (heph_dir / "local.yaml").write_text(yaml.dump({
            "depth": 6,
            "backend": "claude-max",
        }))

        monkeypatch.setenv("HEPHAESTUS_DEPTH", "8")

        lc = LayeredConfig(start_dir=proj)
        cfg = lc.resolve()
        assert cfg.depth == 8  # env wins
        assert cfg.backend == "claude-max"  # local wins (no env override)
        assert cfg.divergence_intensity == "MAXIMUM"  # project wins (no local/env)
        assert cfg.theme == "minimal"  # user wins (nothing above overrides)
        assert cfg.auto_save is True  # default (nothing overrides)


class TestValidation:
    def test_invalid_backend_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_BACKEND", "invalid-backend")
        lc = LayeredConfig(start_dir=tmp_path)
        with pytest.raises(ConfigValidationError, match="Invalid backend"):
            lc.resolve()

    def test_invalid_intensity_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_INTENSITY", "TURBO")
        lc = LayeredConfig(start_dir=tmp_path)
        with pytest.raises(ConfigValidationError, match="Invalid divergence_intensity"):
            lc.resolve()

    def test_invalid_depth_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_DEPTH", "99")
        lc = LayeredConfig(start_dir=tmp_path)
        with pytest.raises(ConfigValidationError, match="Invalid depth"):
            lc.resolve()

    def test_invalid_output_mode_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        monkeypatch.setenv("HEPHAESTUS_OUTPUT_MODE", "HAIKU")
        lc = LayeredConfig(start_dir=tmp_path)
        with pytest.raises(ConfigValidationError, match="Invalid output_mode"):
            lc.resolve()


class TestEdgeCases:
    def test_resolve_caches(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        lc = LayeredConfig(start_dir=tmp_path)
        cfg1 = lc.resolve()
        cfg2 = lc.resolve()
        assert cfg1 is cfg2

    def test_malformed_yaml_is_ignored(self, tmp_path: Path, monkeypatch):
        bad_file = tmp_path / "bad_config.yaml"
        bad_file.write_text(":::not yaml:::")
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", bad_file)
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 3  # fell back to defaults

    def test_yaml_with_non_dict_is_ignored(self, tmp_path: Path, monkeypatch):
        bad_file = tmp_path / "list_config.yaml"
        bad_file.write_text(yaml.dump([1, 2, 3]))
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", bad_file)
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 3

    def test_unknown_keys_in_yaml_are_ignored(self, tmp_path: Path, monkeypatch):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"depth": 5, "unknown_key": "hello"}))
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", cfg_file)
        lc = LayeredConfig(start_dir=tmp_path)
        cfg = lc.resolve()
        assert cfg.depth == 5

    def test_project_root_property(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("hephaestus.config.layered.CONFIG_PATH", tmp_path / "none.yaml")
        (tmp_path / ".hephaestus").mkdir()
        lc = LayeredConfig(start_dir=tmp_path)
        # project_root triggers resolve
        assert lc.project_root == tmp_path
