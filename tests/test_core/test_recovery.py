"""Tests for error recovery and checkpointing."""

from __future__ import annotations

from pathlib import Path

import pytest

from hephaestus.core.recovery import (
    PartialResult,
    PipelineCheckpoint,
    extract_partial_result,
    format_error_hint,
    load_checkpoint,
    save_checkpoint,
)


class TestPipelineCheckpoint:
    def test_creation(self):
        cp = PipelineCheckpoint(problem="test", stage_completed=3, stage_name="Score")
        assert cp.problem == "test"
        assert cp.timestamp  # auto-filled

    def test_is_complete(self):
        assert PipelineCheckpoint(problem="", stage_completed=5, stage_name="Verify").is_complete
        assert not PipelineCheckpoint(problem="", stage_completed=4, stage_name="Translate").is_complete

    def test_has_partial(self):
        assert PipelineCheckpoint(problem="", stage_completed=3, stage_name="Score").has_partial_results
        assert not PipelineCheckpoint(problem="", stage_completed=1, stage_name="Decompose").has_partial_results


class TestExtractPartialResult:
    def test_too_early_returns_none(self):
        cp = PipelineCheckpoint(problem="test", stage_completed=1, stage_name="Decompose")
        assert extract_partial_result(cp) is None

    def test_from_scored(self):
        cp = PipelineCheckpoint(
            problem="test", stage_completed=3, stage_name="Score",
            scored=["candidate1"], error="translation failed"
        )
        result = extract_partial_result(cp)
        assert result is not None
        assert result.best_candidate == "candidate1"
        assert "scoring" in result.reason.lower() or "translation" in result.reason.lower()

    def test_from_translations(self):
        cp = PipelineCheckpoint(
            problem="test", stage_completed=4, stage_name="Translate",
            translations=["trans1"], error="verify timeout"
        )
        result = extract_partial_result(cp)
        assert result.best_candidate == "trans1"

    def test_from_verified(self):
        cp = PipelineCheckpoint(
            problem="test", stage_completed=5, stage_name="Verify",
            verified=["inv1"], error="interrupted"
        )
        result = extract_partial_result(cp)
        assert result.best_candidate == "inv1"

    def test_no_data_returns_none(self):
        cp = PipelineCheckpoint(problem="test", stage_completed=3, stage_name="Score")
        assert extract_partial_result(cp) is None


class TestCheckpointPersistence:
    def test_save_and_load(self, tmp_path: Path):
        cp = PipelineCheckpoint(
            problem="Load balancer",
            stage_completed=3,
            stage_name="Score",
            cost_so_far=0.5,
            error="timeout",
        )
        path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, path)
        assert path.exists()

        loaded = load_checkpoint(path)
        assert loaded is not None
        assert loaded.problem == "Load balancer"
        assert loaded.stage_completed == 3
        assert loaded.cost_so_far == 0.5

    def test_load_missing_file(self, tmp_path: Path):
        assert load_checkpoint(tmp_path / "nope.json") is None

    def test_load_corrupt_file(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("not json")
        assert load_checkpoint(f) is None


class TestFormatErrorHint:
    def test_rate_limit(self):
        assert "wait" in format_error_hint("429 rate limit exceeded").lower()

    def test_timeout(self):
        assert "timed out" in format_error_hint("operation timed out", "Search").lower()

    def test_api_key(self):
        assert "api key" in format_error_hint("invalid API key").lower()

    def test_connection(self):
        assert "network" in format_error_hint("connection refused").lower()

    def test_no_candidates(self):
        hint = format_error_hint("no candidates found")
        assert "--domain" in hint

    def test_generic(self):
        hint = format_error_hint("something weird happened", "Translate")
        assert "Translate" in hint
