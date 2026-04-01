"""Tests for batch invention mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from hephaestus.cli.batch import BatchConfig, BatchResult, BatchResultEntry, parse_problems


class TestParseProblems:
    def test_basic(self, tmp_path: Path):
        f = tmp_path / "problems.txt"
        f.write_text("Problem one\nProblem two\nProblem three\n")
        problems = parse_problems(f)
        assert len(problems) == 3
        assert problems[0] == "Problem one"

    def test_skips_blanks(self, tmp_path: Path):
        f = tmp_path / "problems.txt"
        f.write_text("A\n\n\nB\n")
        assert len(parse_problems(f)) == 2

    def test_skips_comments(self, tmp_path: Path):
        f = tmp_path / "problems.txt"
        f.write_text("# This is a comment\nReal problem\n# Another comment\n")
        problems = parse_problems(f)
        assert len(problems) == 1
        assert problems[0] == "Real problem"

    def test_strips_whitespace(self, tmp_path: Path):
        f = tmp_path / "problems.txt"
        f.write_text("  padded  \n")
        assert parse_problems(f) == ["padded"]

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_problems(tmp_path / "nope.txt")

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert parse_problems(f) == []


class TestBatchConfig:
    def test_defaults(self, tmp_path: Path):
        cfg = BatchConfig(input_file=tmp_path / "in.txt", output_dir=tmp_path / "out")
        assert cfg.format == "markdown"
        assert cfg.depth == 3
        assert cfg.model == "both"
        assert cfg.max_concurrent == 1


class TestBatchResult:
    def test_success_rate_all_succeed(self):
        r = BatchResult(total=5, succeeded=5, failed=0)
        assert r.success_rate == 1.0

    def test_success_rate_partial(self):
        r = BatchResult(total=4, succeeded=3, failed=1)
        assert r.success_rate == 0.75

    def test_success_rate_empty(self):
        r = BatchResult()
        assert r.success_rate == 0.0

    def test_entries(self):
        entry = BatchResultEntry(index=1, problem="test", status="success", invention_name="X")
        r = BatchResult(total=1, succeeded=1, results=[entry])
        assert r.results[0].invention_name == "X"
