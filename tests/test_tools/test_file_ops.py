"""Tests for file operation tools."""

import pytest

from hephaestus.tools.file_ops import (
    grep_search,
    list_directory,
    read_file,
    search_files,
    write_file,
)


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_read_existing(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        assert read_file(str(f)) == "hello world"

    def test_read_missing(self, tmp_path):
        result = read_file(str(tmp_path / "nope.txt"))
        assert "Error" in result

    def test_read_directory_gives_error(self, tmp_path):
        result = read_file(str(tmp_path))
        assert "directory" in result.lower()

    def test_truncation(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 500)
        result = read_file(str(f), max_chars=100)
        assert "truncated" in result
        assert len(result) < 500


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_write_new(self, tmp_path):
        target = tmp_path / "out.txt"
        result = write_file(str(target), "content")
        assert "Wrote" in result
        assert target.read_text() == "content"

    def test_write_creates_parents(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.txt"
        write_file(str(target), "nested")
        assert target.read_text() == "nested"

    def test_write_outside_workspace_denied(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"
        result = write_file(str(outside), "bad", workspace_root=workspace)
        assert "outside workspace" in result.lower()

    def test_write_inside_workspace_allowed(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        target = workspace / "ok.txt"
        result = write_file(str(target), "good", workspace_root=workspace)
        assert "Wrote" in result

    def test_write_no_workspace_always_ok(self, tmp_path):
        target = tmp_path / "any.txt"
        result = write_file(str(target), "data")
        assert "Wrote" in result


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------

class TestListDirectory:
    def test_lists_entries(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        result = list_directory(str(tmp_path))
        assert "sub/" in result
        assert "a.txt" in result

    def test_dirs_first(self, tmp_path):
        (tmp_path / "z_file.txt").write_text("")
        (tmp_path / "a_dir").mkdir()
        result = list_directory(str(tmp_path))
        lines = result.strip().split("\n")
        assert lines[0] == "a_dir/"

    def test_missing_dir(self, tmp_path):
        result = list_directory(str(tmp_path / "nope"))
        assert "Error" in result

    def test_max_entries(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("")
        result = list_directory(str(tmp_path), max_entries=3)
        assert "more entries" in result


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------

class TestSearchFiles:
    def test_finds_by_pattern(self, tmp_path):
        (tmp_path / "foo.py").write_text("")
        (tmp_path / "bar.txt").write_text("")
        result = search_files("*.py", str(tmp_path))
        assert "foo.py" in result
        assert "bar.txt" not in result

    def test_no_matches(self, tmp_path):
        (tmp_path / "foo.txt").write_text("")
        result = search_files("*.rs", str(tmp_path))
        assert "No files" in result

    def test_missing_dir(self, tmp_path):
        result = search_files("*", str(tmp_path / "nope"))
        assert "Error" in result


# ---------------------------------------------------------------------------
# grep_search
# ---------------------------------------------------------------------------

class TestGrepSearch:
    def test_finds_content(self, tmp_path):
        (tmp_path / "code.py").write_text("def hello():\n    pass\n")
        result = grep_search("hello", str(tmp_path))
        assert "code.py" in result
        assert "1:" in result  # line number

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "data.txt").write_text("Hello World\n")
        result = grep_search("hello", str(tmp_path))
        assert "data.txt" in result

    def test_no_matches(self, tmp_path):
        (tmp_path / "empty.txt").write_text("nothing here\n")
        result = grep_search("zzzzz", str(tmp_path))
        assert "No matches" in result

    def test_missing_dir(self, tmp_path):
        result = grep_search("x", str(tmp_path / "nope"))
        assert "Error" in result
