"""Tests for hephaestus.prompts.context_loader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hephaestus.prompts.context_loader import (
    DYNAMIC_BOUNDARY,
    BudgetedContext,
    ContextBudget,
    InstructionFile,
    assemble_context,
    build_full_prompt,
    discover_instructions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# discover_instructions
# ---------------------------------------------------------------------------


class TestDiscoverInstructions:
    """Tests for discover_instructions()."""

    def test_finds_hephaestus_md(self, tmp_path: Path) -> None:
        _write(tmp_path / "HEPHAESTUS.md", "project instructions")
        result = discover_instructions(tmp_path)
        assert len(result) == 1
        assert result[0].content == "project instructions"
        assert result[0].source == "project"

    def test_finds_dotdir_instructions(self, tmp_path: Path) -> None:
        _write(tmp_path / ".hephaestus" / "instructions.md", "dot instructions")
        result = discover_instructions(tmp_path)
        assert len(result) == 1
        assert result[0].content == "dot instructions"

    def test_finds_local_md(self, tmp_path: Path) -> None:
        _write(tmp_path / ".hephaestus" / "local.md", "local overrides")
        result = discover_instructions(tmp_path)
        assert len(result) == 1
        assert result[0].content == "local overrides"

    def test_walks_up_directory_tree(self, tmp_path: Path) -> None:
        _write(tmp_path / "HEPHAESTUS.md", "root")
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        result = discover_instructions(child)
        assert any(i.content == "root" for i in result)

    def test_dedup_by_content_hash(self, tmp_path: Path) -> None:
        """Two files with identical content should produce only one entry."""
        _write(tmp_path / "HEPHAESTUS.md", "same content")
        _write(tmp_path / ".hephaestus" / "instructions.md", "same content")
        result = discover_instructions(tmp_path)
        assert len(result) == 1

    def test_different_content_not_deduped(self, tmp_path: Path) -> None:
        _write(tmp_path / "HEPHAESTUS.md", "alpha")
        _write(tmp_path / ".hephaestus" / "instructions.md", "beta")
        result = discover_instructions(tmp_path)
        assert len(result) == 2

    def test_per_file_limit(self, tmp_path: Path) -> None:
        _write(tmp_path / "HEPHAESTUS.md", "x" * 20000)
        result = discover_instructions(tmp_path, per_file_limit=100)
        assert result[0].size == 100
        assert result[0].content == "x" * 100

    def test_total_limit(self, tmp_path: Path) -> None:
        _write(tmp_path / "HEPHAESTUS.md", "A" * 500)
        _write(tmp_path / ".hephaestus" / "instructions.md", "B" * 500)
        result = discover_instructions(tmp_path, per_file_limit=500, total_limit=700)
        total = sum(i.size for i in result)
        assert total <= 700

    def test_user_global_instruction(self, tmp_path: Path) -> None:
        user_path = tmp_path / "fake_home" / ".hephaestus" / "instructions.md"
        _write(user_path, "global user instruction")
        with patch(
            "hephaestus.prompts.context_loader._USER_GLOBAL_INSTRUCTION",
            user_path,
        ):
            result = discover_instructions(tmp_path)
        assert any(i.source == "user" for i in result)
        assert any(i.content == "global user instruction" for i in result)

    def test_sorted_by_priority(self, tmp_path: Path) -> None:
        """builtin < user < project ordering."""
        _write(tmp_path / "HEPHAESTUS.md", "project file")
        user_path = tmp_path / "fake_home" / ".hephaestus" / "instructions.md"
        _write(user_path, "user file")
        with patch(
            "hephaestus.prompts.context_loader._USER_GLOBAL_INSTRUCTION",
            user_path,
        ):
            result = discover_instructions(tmp_path)
        sources = [i.source for i in result]
        assert sources == sorted(sources, key=lambda s: {"builtin": 0, "user": 1, "project": 2}[s])

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = discover_instructions(tmp_path)
        assert result == []

    def test_nonexistent_file_skipped(self, tmp_path: Path) -> None:
        """No crash when instruction files don't exist."""
        result = discover_instructions(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# assemble_context
# ---------------------------------------------------------------------------


class TestAssembleContext:
    """Tests for assemble_context()."""

    def test_empty_context(self) -> None:
        ctx = assemble_context()
        assert ctx.total_chars == 0
        assert ctx.instruction_text == ""
        assert ctx.anti_memory_text == ""
        assert ctx.sources == []

    def test_instruction_text_included(self) -> None:
        inst = InstructionFile(path="/a", content="hello", source="project", size=5)
        ctx = assemble_context(instructions=[inst])
        assert "hello" in ctx.instruction_text
        assert "project" in ctx.sources

    def test_anti_memory_included(self) -> None:
        ctx = assemble_context(anti_memory_hits=["avoid X", "avoid Y"])
        assert "avoid X" in ctx.anti_memory_text
        assert "avoid Y" in ctx.anti_memory_text
        assert "anti_memory" in ctx.sources

    def test_pinned_context_included(self) -> None:
        ctx = assemble_context(pinned_context=["pin1", "pin2"])
        assert "pin1" in ctx.pinned_context_text
        assert "pinned" in ctx.sources

    def test_workspace_summary_included(self) -> None:
        ctx = assemble_context(workspace_summary="my workspace")
        assert ctx.workspace_summary == "my workspace"
        assert "workspace" in ctx.sources

    def test_dedup_anti_memory(self) -> None:
        ctx = assemble_context(anti_memory_hits=["dup", "dup", "unique"])
        assert ctx.anti_memory_text.count("dup") == 1

    def test_budget_truncation(self) -> None:
        big_inst = InstructionFile(path="/a", content="I" * 5000, source="project", size=5000)
        budget = ContextBudget(max_total_chars=1000, max_per_source=800, reserved_for_prompt=100)
        ctx = assemble_context(
            instructions=[big_inst],
            anti_memory_hits=["A" * 500],
            budget=budget,
        )
        assert ctx.total_chars <= 900  # max_total - reserved

    def test_anti_memory_preserved_over_instructions(self) -> None:
        """Anti-memory should be the last to lose content — instructions shed first."""
        big_inst = InstructionFile(path="/a", content="I" * 3000, source="project", size=3000)
        budget = ContextBudget(max_total_chars=1000, max_per_source=3000, reserved_for_prompt=100)
        ctx = assemble_context(
            instructions=[big_inst],
            anti_memory_hits=["AM" * 100],
            budget=budget,
        )
        # Instructions should be truncated; anti-memory should be fully preserved
        assert len(ctx.instruction_text) < 3000  # instructions were cut
        assert ctx.anti_memory_text == "AM" * 100  # anti-memory untouched

    def test_total_chars_accurate(self) -> None:
        ctx = assemble_context(
            anti_memory_hits=["abc"],
            workspace_summary="xyz",
        )
        expected = len(ctx.instruction_text) + len(ctx.anti_memory_text) + len(ctx.pinned_context_text) + len(ctx.workspace_summary)
        assert ctx.total_chars == expected


# ---------------------------------------------------------------------------
# build_full_prompt
# ---------------------------------------------------------------------------


class TestBuildFullPrompt:
    """Tests for build_full_prompt()."""

    def test_contains_boundary(self) -> None:
        ctx = BudgetedContext(
            instruction_text="", anti_memory_text="", pinned_context_text="",
            workspace_summary="", total_chars=0, sources=[],
        )
        prompt = build_full_prompt("invent something", ctx)
        assert DYNAMIC_BOUNDARY in prompt

    def test_includes_instruction_section(self) -> None:
        ctx = BudgetedContext(
            instruction_text="my instructions", anti_memory_text="",
            pinned_context_text="", workspace_summary="",
            total_chars=15, sources=["project"],
        )
        prompt = build_full_prompt("invent something", ctx)
        assert "## Project Instructions" in prompt
        assert "my instructions" in prompt

    def test_includes_anti_memory_section(self) -> None:
        ctx = BudgetedContext(
            instruction_text="", anti_memory_text="avoid this",
            pinned_context_text="", workspace_summary="",
            total_chars=10, sources=["anti_memory"],
        )
        prompt = build_full_prompt("invent something", ctx)
        assert "## Anti-Memory Zone" in prompt
        assert "avoid this" in prompt

    def test_empty_context_still_has_boundary(self) -> None:
        ctx = BudgetedContext(
            instruction_text="", anti_memory_text="", pinned_context_text="",
            workspace_summary="", total_chars=0, sources=[],
        )
        prompt = build_full_prompt("invent something", ctx)
        assert DYNAMIC_BOUNDARY in prompt
        assert "## Project Instructions" not in prompt

    def test_all_sections_present(self) -> None:
        ctx = BudgetedContext(
            instruction_text="inst", anti_memory_text="anti",
            pinned_context_text="pinned", workspace_summary="ws",
            total_chars=100, sources=[],
        )
        prompt = build_full_prompt("invent something", ctx)
        assert "## Project Instructions" in prompt
        assert "## Anti-Memory Zone" in prompt
        assert "## Pinned Context" in prompt
        assert "## Workspace Summary" in prompt

    def test_kwargs_forwarded(self) -> None:
        ctx = BudgetedContext(
            instruction_text="", anti_memory_text="", pinned_context_text="",
            workspace_summary="", total_chars=0, sources=[],
        )
        # Should not raise — divergence_intensity is forwarded to build_system_prompt
        prompt = build_full_prompt(
            "invent something", ctx, divergence_intensity="AGGRESSIVE",
        )
        assert isinstance(prompt, str)
