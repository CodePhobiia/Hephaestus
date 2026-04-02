"""Tests for workspace-aware invention."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hephaestus.workspace.inventor import (
    IdentifiedProblem,
    WorkspaceInvention,
    WorkspaceInventionReport,
    WorkspaceInventor,
    _parse_problems,
    _generate_impl_hint,
)


class TestIdentifiedProblem:
    def test_creation(self):
        p = IdentifiedProblem(
            problem="No retry logic on API calls",
            category="reliability",
            severity="high",
            context="The codebase makes HTTP calls without retries",
        )
        assert p.problem == "No retry logic on API calls"
        assert p.severity == "high"


class TestWorkspaceInvention:
    def test_success(self):
        inv = WorkspaceInvention(
            problem=IdentifiedProblem("test", "arch", "high", "ctx"),
            invention_name="Immune Retry",
            source_domain="biology",
            novelty_score=0.85,
        )
        assert inv.success

    def test_failure(self):
        inv = WorkspaceInvention(
            problem=IdentifiedProblem("test", "arch", "high", "ctx"),
            error="Pipeline failed",
        )
        assert not inv.success


class TestWorkspaceInventionReport:
    def test_creation(self):
        report = WorkspaceInventionReport(
            workspace_root="/tmp/test",
            problems_found=3,
            inventions_attempted=3,
            inventions_succeeded=2,
        )
        assert report.inventions_succeeded == 2


class TestParseProblem:
    def test_valid_json(self):
        text = '''Here are the problems:
[
  {"problem": "No caching layer", "category": "performance", "severity": "high", "context": "DB calls on every request"},
  {"problem": "No rate limiting", "category": "security", "severity": "medium", "context": "API is open"}
]'''
        problems = _parse_problems(text)
        assert len(problems) == 2
        assert problems[0].problem == "No caching layer"
        assert problems[0].category == "performance"

    def test_no_json(self):
        assert _parse_problems("no json here") == []

    def test_invalid_json(self):
        assert _parse_problems("[{invalid}]") == []

    def test_mixed_valid_invalid(self):
        text = '[{"problem": "valid"}, {"no_problem_key": true}]'
        problems = _parse_problems(text)
        assert len(problems) == 1

    def test_defaults(self):
        text = '[{"problem": "something"}]'
        problems = _parse_problems(text)
        assert problems[0].category == "architecture"
        assert problems[0].severity == "medium"


class TestGenerateImplHint:
    def test_returns_empty(self):
        hint = _generate_impl_hint("Use Redis caching", "slow queries", "myapp")
        assert hint == ""

    def test_empty_architecture(self):
        assert _generate_impl_hint("", "problem", "app") == ""


class TestWorkspaceInventor:
    def test_creation(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')\n")
        adapter = MagicMock()
        inventor = WorkspaceInventor(adapter, tmp_path)
        assert inventor.root == tmp_path
        assert inventor.max_inventions == 5

    def test_format_report(self, tmp_path: Path):
        adapter = MagicMock()
        inventor = WorkspaceInventor(adapter, tmp_path)

        report = WorkspaceInventionReport(
            workspace_root=str(tmp_path),
            problems_found=2,
            inventions_attempted=2,
            inventions_succeeded=1,
            research_dossier=type("Dossier", (), {
                "summary": "Comparable tools all use queue-backed workers.",
                "comparable_tools": ["Tool A"],
                "architecture_patterns": ["queue-backed workers"],
                "differentiation_opportunities": ["better grounding"],
                "implementation_risks": ["prompt drift"],
            })(),
            inventions=[
                WorkspaceInvention(
                    problem=IdentifiedProblem("Slow queries", "performance", "high", ""),
                    invention_name="Immune Cache",
                    source_domain="biology",
                    key_insight="Memory cells cache results",
                    architecture="Redis layer",
                    novelty_score=0.85,
                    verdict="NOVEL",
                ),
                WorkspaceInvention(
                    problem=IdentifiedProblem("No auth", "security", "high", ""),
                    error="Pipeline timeout",
                ),
            ],
        )

        md = inventor.format_report(report)
        assert "External Research Dossier" in md
        assert "Immune Cache" in md
        assert "biology" in md
        assert "Pipeline timeout" in md
