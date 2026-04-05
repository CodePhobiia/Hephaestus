"""
Tests for the Hephaestus Interactive REPL — Phases 1-4.

Tests cover:
  Phase 1: Core REPL commands (/help, /status, /quit, /model, /usage, /cost, /clear)
  Phase 2: Refinement & context (/refine, /alternatives, /trace, /context, /deeper)
  Phase 3: Persistence & history (/save, /load, /history, /compare, auto-save, session replay)
  Phase 4: Onboarding, tab completion, /export pdf
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from hephaestus.lenses.state import (
    LensBundleMember,
    LensBundleProof,
    LensEngineState,
    ResearchReferenceArtifact,
    ResearchReferenceState,
)

# ---------------------------------------------------------------------------
# Mock factories (reuse patterns from test_main.py)
# ---------------------------------------------------------------------------


def _make_problem_structure(problem: str = "test problem") -> MagicMock:
    s = MagicMock()
    s.original_problem = problem
    s.structure = "Abstract trust propagation"
    s.mathematical_shape = "Robust signal propagation"
    s.native_domain = "distributed_systems"
    s.constraints = ["no persistent identity"]
    s.confidence = 0.92
    s.cost_usd = 0.15
    return s


def _make_scored_candidate(source_domain: str = "Immune System") -> MagicMock:
    c = MagicMock()
    c.source_domain = source_domain
    c.source_solution = "T-cell memory"
    c.mechanism = "Clonal selection"
    c.structural_fidelity = 0.87
    c.domain_distance = 0.94
    c.combined_score = 0.91
    c.cost_usd = 0.05
    c.scoring_cost_usd = 0.02
    return c


def _make_translation(
    invention_name: str = "Immune Trust Protocol",
    source_domain: str = "Immune System",
) -> MagicMock:
    t = MagicMock()
    t.invention_name = invention_name
    t.source_domain = source_domain
    t.architecture = "Architecture description."
    t.mathematical_proof = "Proof statement."
    t.limitations = ["Breaks at high churn"]
    t.implementation_notes = "Use distributed graph."
    t.key_insight = "Trust propagates like immune memory."
    t.mapping = []
    t.cost_usd = 0.45
    t.source_candidate = _make_scored_candidate(source_domain)
    return t


def _make_adversarial_result(verdict: str = "NOVEL") -> MagicMock:
    adv = MagicMock()
    adv.attack_valid = False
    adv.fatal_flaws = []
    adv.structural_weaknesses = ["High churn"]
    adv.strongest_objection = "Breaks under load"
    adv.novelty_risk = 0.12
    adv.verdict = verdict
    return adv


def _make_verified_invention(
    name: str = "Immune Trust Protocol",
    source_domain: str = "Immune System",
    novelty_score: float = 0.91,
    verdict: str = "NOVEL",
) -> MagicMock:
    v = MagicMock()
    v.invention_name = name
    v.source_domain = source_domain
    v.novelty_score = novelty_score
    v.structural_validity = 0.88
    v.implementation_feasibility = 0.82
    v.feasibility_rating = "HIGH"
    v.adversarial_result = _make_adversarial_result(verdict)
    v.prior_art_status = "NO_PRIOR_ART_FOUND"
    v.prior_art_report = None
    v.validity_notes = "Valid mapping."
    v.recommended_next_steps = ["Build PoC"]
    v.verification_cost_usd = 0.15
    v.translation = _make_translation(name, source_domain)
    v.verdict = verdict
    v.is_viable = True
    return v


def _make_cost_breakdown() -> MagicMock:
    cb = MagicMock()
    cb.decomposition_cost = 0.15
    cb.search_cost = 0.12
    cb.scoring_cost = 0.05
    cb.translation_cost = 0.45
    cb.verification_cost = 0.15
    cb.total = 0.92
    cb.to_dict = lambda: {
        "decomposition": 0.15,
        "search": 0.12,
        "scoring": 0.05,
        "translation": 0.45,
        "verification": 0.15,
        "total": 0.92,
    }
    return cb


def _make_report(
    problem: str = "I need a trust system",
    name: str = "Immune Trust Protocol",
    source: str = "Immune System",
) -> MagicMock:
    report = MagicMock()
    report.problem = problem
    report.structure = _make_problem_structure(problem)
    report.total_cost_usd = 0.92
    report.total_duration_seconds = 47.3
    report.cost_breakdown = _make_cost_breakdown()
    report.model_config = {"decompose": "claude-sonnet-4-6", "search": "gpt-4o"}

    top = _make_verified_invention(name, source)
    report.top_invention = top
    alt = _make_verified_invention("Alt Invention", "Physics", 0.80)
    report.alternative_inventions = [alt]
    report.verified_inventions = [top, alt]
    report.all_candidates = [_make_scored_candidate()]
    report.scored_candidates = [_make_scored_candidate()]
    report.translations = [_make_translation()]

    report.to_dict.return_value = {
        "problem": problem,
        "top_invention": {"name": name, "source_domain": source, "novelty_score": 0.91},
        "alternatives": [],
        "cost_breakdown": {"total": 0.92},
        "total_duration_seconds": 47.3,
        "models": {},
        "native_domain": "distributed_systems",
        "mathematical_shape": "Robust signal propagation",
    }
    report.summary.return_value = f"⚒️  {name} (from {source}) | novelty=0.91"
    return report


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=3,
        active_bundle_id="bundle:adaptive:repl",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
            )
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:repl",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune"],
                status="active",
                proof_status="fallback",
                cohesion_score=0.61,
                proof_fingerprint="proof-repl",
                reference_generation=3,
                summary="Singleton fallback active.",
            )
        ],
        research=ResearchReferenceState(
            reference_generation=3,
            reference_signature="research-repl",
            artifacts=[
                ResearchReferenceArtifact(
                    artifact_name="baseline_dossier",
                    signature="artifact-repl",
                    citations=["https://example.com/repl"],
                    citation_count=1,
                )
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: Any) -> Any:
    from hephaestus.cli.config import HephaestusConfig

    defaults = {
        "backend": "api",
        "default_model": "claude-sonnet-4-6",
        "depth": 3,
        "candidates": 8,
        "auto_save": False,  # disable auto-save by default in tests
    }
    defaults.update(overrides)
    cfg = HephaestusConfig(**defaults)
    cfg.anthropic_api_key = "sk-ant-test"
    cfg.openai_api_key = "sk-test"
    return cfg


def _make_session(**overrides: Any) -> Any:
    from hephaestus.cli.repl import SessionState

    cfg = _make_config(**overrides)
    return SessionState(config=cfg)


def _console() -> Console:
    return Console(file=StringIO(), highlight=False, force_terminal=True, width=120)


def _get_output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[attr-defined]


def _make_workspace_context(tmp_path: Path) -> Any:
    from hephaestus.workspace.context import WorkspaceContext

    package = tmp_path / "src" / "demo"
    (package / "cli").mkdir(parents=True)
    (package / "core").mkdir(parents=True)
    (tmp_path / "tests" / "test_cli").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "__init__.py").write_text("", encoding="utf-8")
    (package / "core" / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli" / "main.py").write_text(
        "from demo.core.engine import run_engine\n\ndef main() -> str:\n    return run_engine()\n",
        encoding="utf-8",
    )
    (package / "core" / "engine.py").write_text(
        "def run_engine() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_cli" / "test_main.py").write_text(
        "from demo.cli.main import main\n\ndef test_main() -> None:\n    assert main() == 'ok'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "version = '0.1.0'\n"
        "dependencies = ['pytest>=8.0']\n"
        "scripts = { demo = 'demo.cli.main:main' }\n"
        "[project.optional-dependencies]\n"
        "dev = ['ruff>=0.5']\n",
        encoding="utf-8",
    )
    return WorkspaceContext.from_directory(tmp_path)


# ---------------------------------------------------------------------------
# Phase 1 & 2: Core commands
# ---------------------------------------------------------------------------


class TestCoreCommands:
    @pytest.mark.asyncio
    async def test_cmd_help(self) -> None:
        from hephaestus.cli.repl import _cmd_help

        console = _console()
        state = _make_session()
        await _cmd_help(console, state, "")
        output = _get_output(console)
        assert "/help" in output
        assert "/save" in output
        assert "/compare" in output
        assert "/export" in output

    @pytest.mark.asyncio
    async def test_cmd_status(self) -> None:
        from hephaestus.cli.repl import _cmd_status

        console = _console()
        state = _make_session()
        await _cmd_status(console, state, "")
        output = _get_output(console)
        assert "api" in output  # backend
        assert "claude-sonnet" in output  # model

    @pytest.mark.asyncio
    async def test_cmd_status_includes_lens_engine_summary(self) -> None:
        from hephaestus.cli.repl import _cmd_status
        from hephaestus.session.schema import Session

        console = _console()
        state = _make_session()
        state.session = Session()
        state.session.apply_lens_engine_state(_lens_engine_state(), op_id=1)
        await _cmd_status(console, state, "")
        output = _get_output(console)
        assert "Lens engine" in output
        assert "bundle:adaptive:repl" in output

    @pytest.mark.asyncio
    async def test_cmd_status_includes_repo_awareness(self, tmp_path: Path) -> None:
        from hephaestus.cli.repl import _cmd_status

        console = _console()
        state = _make_session()
        state.workspace_root = tmp_path
        state.workspace_context = _make_workspace_context(tmp_path)

        await _cmd_status(console, state, "")

        output = _get_output(console)
        assert "Repo awareness" in output
        assert "Repo Awareness" in output
        assert "Components" in output

    @pytest.mark.asyncio
    async def test_cmd_model_show(self) -> None:
        from hephaestus.cli.repl import _cmd_model

        console = _console()
        state = _make_session()
        await _cmd_model(console, state, "")
        assert "claude-sonnet" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_model_set(self) -> None:
        from hephaestus.cli.repl import _cmd_model

        console = _console()
        state = _make_session()
        await _cmd_model(console, state, "claude-opus-4-6")
        assert state.config.default_model == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_cmd_backend_show(self) -> None:
        from hephaestus.cli.repl import _cmd_backend

        console = _console()
        state = _make_session()
        await _cmd_backend(console, state, "")
        assert "api" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_backend_set_valid(self) -> None:
        from hephaestus.cli.repl import _cmd_backend

        console = _console()
        state = _make_session()
        await _cmd_backend(console, state, "claude-max")
        assert state.config.backend == "claude-max"

    @pytest.mark.asyncio
    async def test_cmd_backend_set_invalid(self) -> None:
        from hephaestus.cli.repl import _cmd_backend

        console = _console()
        state = _make_session()
        await _cmd_backend(console, state, "nonexistent")
        assert state.config.backend == "api"  # unchanged

    @pytest.mark.asyncio
    async def test_cmd_cost_no_report(self) -> None:
        from hephaestus.cli.repl import _cmd_cost

        console = _console()
        state = _make_session()
        await _cmd_cost(console, state, "")
        assert "No cost yet" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_clear(self) -> None:
        from hephaestus.cli.repl import _cmd_clear

        console = _console()
        state = _make_session()
        state.context_items = ["some context"]
        state.pinned = [0]
        await _cmd_clear(console, state, "")
        assert state.context_items == []
        assert state.pinned == []

    @pytest.mark.asyncio
    async def test_cmd_candidates_show(self) -> None:
        from hephaestus.cli.repl import _cmd_candidates

        console = _console()
        state = _make_session()
        await _cmd_candidates(console, state, "")
        assert "8" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_candidates_set(self) -> None:
        from hephaestus.cli.repl import _cmd_candidates

        console = _console()
        state = _make_session()
        await _cmd_candidates(console, state, "12")
        assert state.config.candidates == 12

    @pytest.mark.asyncio
    async def test_cmd_candidates_invalid(self) -> None:
        from hephaestus.cli.repl import _cmd_candidates

        console = _console()
        state = _make_session()
        await _cmd_candidates(console, state, "99")
        assert state.config.candidates == 8  # unchanged

    @pytest.mark.asyncio
    async def test_cmd_context_add(self) -> None:
        from hephaestus.cli.repl import _cmd_context

        console = _console()
        state = _make_session()
        await _cmd_context(console, state, "add must work offline")
        assert len(state.context_items) == 1
        assert "must work offline" in state.context_items[0]

    @pytest.mark.asyncio
    async def test_cmd_context_clear(self) -> None:
        from hephaestus.cli.repl import _cmd_context

        console = _console()
        state = _make_session()
        state.context_items = ["item1", "item2"]
        await _cmd_context(console, state, "clear")
        assert state.context_items == []

    @pytest.mark.asyncio
    async def test_cmd_context_show(self) -> None:
        from hephaestus.cli.repl import _cmd_context

        console = _console()
        state = _make_session()
        state.context_items = ["domain knowledge here"]
        await _cmd_context(console, state, "")
        assert "domain knowledge" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_context_includes_repo_dossier(self, tmp_path: Path) -> None:
        from hephaestus.cli.repl import _cmd_context

        console = _console()
        state = _make_session()
        state.workspace_root = tmp_path
        state.workspace_context = _make_workspace_context(tmp_path)

        await _cmd_context(console, state, "")

        output = _get_output(console)
        assert "Repo Dossier" in output
        assert "Suggested Commands" in output
        assert "Subsystems" in output


# ---------------------------------------------------------------------------
# Phase 2: Commands that need an invention
# ---------------------------------------------------------------------------


class TestInventionCommands:
    def _state_with_invention(self) -> Any:
        from hephaestus.cli.repl import InventionEntry

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="test problem", report=report)
        state.inventions.append(entry)
        state.current_idx = 0
        return state

    @pytest.mark.asyncio
    async def test_cmd_alternatives(self) -> None:
        from hephaestus.cli.repl import _cmd_alternatives

        console = _console()
        state = self._state_with_invention()
        await _cmd_alternatives(console, state, "")
        output = _get_output(console)
        assert "Alt Invention" in output

    @pytest.mark.asyncio
    async def test_cmd_alternatives_no_report(self) -> None:
        from hephaestus.cli.repl import _cmd_alternatives

        console = _console()
        state = _make_session()
        await _cmd_alternatives(console, state, "")
        assert "No current invention" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_trace(self) -> None:
        from hephaestus.cli.repl import _cmd_trace

        console = _console()
        state = self._state_with_invention()
        await _cmd_trace(console, state, "")
        # Should not raise — smoke test

    @pytest.mark.asyncio
    async def test_cmd_usage_with_invention(self) -> None:
        from hephaestus.cli.repl import _cmd_usage

        console = _console()
        state = self._state_with_invention()
        state.total_cost_usd = 0.92
        await _cmd_usage(console, state, "")
        assert "$0.92" in _get_output(console)


class TestWorkspaceCommands:
    @pytest.mark.asyncio
    async def test_cmd_ws_includes_repo_dossier_notes(self, tmp_path: Path) -> None:
        from hephaestus.cli.repl import _cmd_ws

        console = _console()
        state = _make_session()
        state.workspace_root = tmp_path
        state.workspace_context = _make_workspace_context(tmp_path)

        await _cmd_ws(console, state, "")

        output = _get_output(console)
        assert "Repo cache" in output
        assert "Components:" in output
        assert "Commands:" in output


# ---------------------------------------------------------------------------
# Phase 3: Persistence & History
# ---------------------------------------------------------------------------


class TestPersistence:
    def _state_with_invention(self, auto_save: bool = False) -> Any:
        from hephaestus.cli.repl import InventionEntry

        state = _make_session(auto_save=auto_save)
        report = _make_report()
        entry = InventionEntry(problem="test trust problem", report=report)
        state.inventions.append(entry)
        state.current_idx = 0
        return state

    @pytest.mark.asyncio
    async def test_cmd_save(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli.repl import _cmd_save

        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", tmp_path / "inventions")
        monkeypatch.setattr(config_mod, "SESSIONS_DIR", tmp_path / "sessions")
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)

        # Also patch in repl module
        from hephaestus.cli import repl as repl_mod

        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", tmp_path / "inventions")
        monkeypatch.setattr(repl_mod, "SESSIONS_DIR", tmp_path / "sessions")

        console = _console()
        state = self._state_with_invention()
        await _cmd_save(console, state, "my-test-save")

        output = _get_output(console)
        assert "Saved to" in output or "✓" in output

        # Check files were created
        json_files = list((tmp_path / "inventions").glob("*.json"))
        md_files = list((tmp_path / "inventions").glob("*.md"))
        assert len(json_files) >= 1
        assert len(md_files) >= 1

        # Validate JSON content
        data = json.loads(json_files[0].read_text())
        assert "top_invention" in data
        assert "_meta" in data
        assert data["_meta"]["problem"] == "test trust problem"

    @pytest.mark.asyncio
    async def test_cmd_save_no_invention(self) -> None:
        from hephaestus.cli.repl import _cmd_save

        console = _console()
        state = _make_session()
        await _cmd_save(console, state, "")
        assert "No current invention" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_load_not_found(self) -> None:
        from hephaestus.cli.repl import _cmd_load

        console = _console()
        state = _make_session()
        await _cmd_load(console, state, "nonexistent-12345")
        output = _get_output(console)
        assert "No saved invention" in output or "Error" in output

    @pytest.mark.asyncio
    async def test_cmd_load_no_args(self) -> None:
        from hephaestus.cli.repl import _cmd_load

        console = _console()
        state = _make_session()
        await _cmd_load(console, state, "")
        assert "Usage" in _get_output(console)

    @pytest.mark.asyncio
    async def test_cmd_load_json_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import _cmd_load

        inv_dir = tmp_path / "inventions"
        inv_dir.mkdir()
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        # Write a test invention file
        test_data = {
            "problem": "loaded problem",
            "top_invention": {
                "name": "Loaded Invention",
                "source_domain": "Biology",
                "novelty_score": 0.85,
            },
            "_meta": {
                "problem": "loaded problem",
                "timestamp": 1234567890.0,
                "refined": False,
                "slug": "loaded",
            },
        }
        test_file = inv_dir / "2026-03-31-loaded.json"
        test_file.write_text(json.dumps(test_data))

        console = _console()
        state = _make_session()
        await _cmd_load(console, state, "loaded")

        output = _get_output(console)
        assert "Loaded" in output
        assert "Loaded Invention" in output

    @pytest.mark.asyncio
    async def test_cmd_load_explicit_path_activates_invention(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import _cmd_load

        inv_dir = tmp_path / "inventions"
        inv_dir.mkdir()
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        test_data = {
            "problem": "loaded via path",
            "native_domain": "biology",
            "mathematical_shape": "feedback loop",
            "top_invention": {
                "name": "Path Load",
                "source_domain": "Biology",
                "novelty_score": 0.81,
            },
            "_meta": {
                "problem": "loaded via path",
                "timestamp": 1234567890.0,
                "refined": False,
                "slug": "path-load",
            },
        }
        test_file = inv_dir / "2026-03-31-path-load.json"
        test_file.write_text(json.dumps(test_data))

        console = _console()
        state = _make_session()
        await _cmd_load(console, state, str(test_file))

        assert state.current is not None
        assert state.current.problem == "loaded via path"
        assert state.current.report.top_invention.invention_name == "Path Load"

    def test_loaded_report_restores_lens_engine_state(self) -> None:
        from hephaestus.cli.repl import _loaded_report

        payload = {
            "problem": "loaded via helper",
            "native_domain": "biology",
            "mathematical_shape": "feedback loop",
            "top_invention": {
                "name": "Helper Load",
                "source_domain": "Biology",
                "novelty_score": 0.81,
            },
            "lens_engine": _lens_engine_state().to_dict(),
            "pantheon": {
                "mode": "pantheon",
                "consensus_achieved": True,
                "final_verdict": "NOVEL",
                "winning_candidate_id": "candidate-1:biology_immune",
            },
        }
        report = _loaded_report(payload, meta={"problem": "loaded via helper"})
        assert report.lens_engine_state is not None
        assert report.lens_engine_state.active_bundle_id == "bundle:adaptive:repl"
        assert report.lens_engine_state.research is not None
        assert report.pantheon_state is not None
        assert report.pantheon_state.consensus_achieved is True
        assert report.pantheon_state.final_verdict == "NOVEL"

    @pytest.mark.asyncio
    async def test_cmd_load_session_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import _cmd_load

        sess_dir = tmp_path / "sessions"
        sess_dir.mkdir()
        monkeypatch.setattr(config_mod, "SESSIONS_DIR", sess_dir)
        monkeypatch.setattr(repl_mod, "SESSIONS_DIR", sess_dir)
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", tmp_path / "inventions")
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", tmp_path / "inventions")

        # Write a session file
        session_data = {
            "backend": "claude-max",
            "model": "claude-opus-4-6",
            "depth": 5,
            "candidates": 10,
            "total_cost_usd": 1.23,
            "context_items": ["some context"],
            "inventions": [
                {
                    "problem": "session test",
                    "report": {"top_invention": {"name": "Session Inv"}},
                },
            ],
        }
        sess_file = sess_dir / "2026-03-31-test-session.json"
        sess_file.write_text(json.dumps(session_data))

        console = _console()
        state = _make_session()
        await _cmd_load(console, state, "test-session")

        output = _get_output(console)
        assert "session" in output.lower() or "1 inventions" in output
        assert len(state.inventions) == 1
        assert state.current_idx == 0
        assert state.current is not None
        assert state.current.report.top_invention.invention_name == "Session Inv"

    @pytest.mark.asyncio
    async def test_cmd_history_empty(self) -> None:
        from hephaestus.cli.repl import _cmd_history_v2

        console = _console()
        state = _make_session()
        await _cmd_history_v2(console, state, "")
        output = _get_output(console)
        assert "No inventions" in output or "History" in output

    @pytest.mark.asyncio
    async def test_cmd_history_with_inventions(self) -> None:
        from hephaestus.cli.repl import _cmd_history_v2

        console = _console()
        state = self._state_with_invention()
        await _cmd_history_v2(console, state, "")
        output = _get_output(console)
        assert "Immune Trust" in output

    @pytest.mark.asyncio
    async def test_cmd_history_search(self) -> None:
        from hephaestus.cli.repl import _cmd_history_v2

        console = _console()
        state = self._state_with_invention()
        await _cmd_history_v2(console, state, "trust")
        output = _get_output(console)
        assert "Immune Trust" in output

    @pytest.mark.asyncio
    async def test_cmd_history_search_no_match(self) -> None:
        from hephaestus.cli.repl import _cmd_history_v2

        console = _console()
        state = self._state_with_invention()
        await _cmd_history_v2(console, state, "zzzznotfound")
        assert "No inventions matching" in _get_output(console)


class TestCompare:
    @pytest.mark.asyncio
    async def test_compare_needs_two(self) -> None:
        from hephaestus.cli.repl import InventionEntry, _cmd_compare

        console = _console()
        state = _make_session()
        # Only one invention
        entry = InventionEntry(problem="p1", report=_make_report())
        state.inventions.append(entry)
        state.current_idx = 0
        await _cmd_compare(console, state, "")
        assert "Only 1 invention" in _get_output(console)

    @pytest.mark.asyncio
    async def test_compare_two_inventions(self) -> None:
        from hephaestus.cli.repl import InventionEntry, _cmd_compare

        console = _console()
        state = _make_session()

        r1 = _make_report("Problem A", "Invention A", "Domain A")
        r2 = _make_report("Problem B", "Invention B", "Domain B")
        state.inventions.append(InventionEntry(problem="Problem A", report=r1))
        state.inventions.append(InventionEntry(problem="Problem B", report=r2))
        state.current_idx = 1

        await _cmd_compare(console, state, "")
        output = _get_output(console)
        assert "Comparison" in output
        assert "Invention A" in output or "Problem A" in output
        assert "Invention B" in output or "Problem B" in output


class TestExportAndMenu:
    @pytest.mark.asyncio
    async def test_cmd_export_invalid_format(self) -> None:
        from hephaestus.cli.repl import InventionEntry, _cmd_export_v2

        console = _console()
        state = _make_session()
        state.inventions.append(InventionEntry(problem="test problem", report=_make_report()))
        state.current_idx = 0

        await _cmd_export_v2(console, state, "xlsx")

        output = _get_output(console)
        assert "Unknown export format" in output

    @pytest.mark.asyncio
    async def test_handle_menu_choice_chat(self) -> None:
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _handle_menu_choice

        console = _console()
        state = _make_session()
        state.inventions.append(InventionEntry(problem="test problem", report=_make_report()))
        state.current_idx = 0

        with patch.object(repl_mod, "_chat_about_invention", new=AsyncMock()) as mock_chat:
            handled = await _handle_menu_choice(console, state, "7")

        assert handled is True
        mock_chat.assert_awaited_once()

    def test_md_to_simple_html_wraps_lists(self) -> None:
        from hephaestus.cli.repl import _md_to_simple_html

        html = _md_to_simple_html("# Title\n- One\n- Two\nParagraph")

        assert "<ul>" in html
        assert "<li>One</li>" in html
        assert "</ul>" in html


class TestAutoSave:
    def test_auto_save_creates_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _auto_save_invention

        inv_dir = tmp_path / "inventions"
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        state = _make_session(auto_save=True)
        report = _make_report()
        entry = InventionEntry(problem="auto save test", report=report)
        state.inventions.append(entry)
        state.current_idx = 0

        path = _auto_save_invention(state)

        assert path is not None
        assert path.exists()
        assert path.suffix == ".json"

        # Markdown should also exist
        md_path = path.with_suffix(".md")
        assert md_path.exists()

        # Validate JSON
        data = json.loads(path.read_text())
        assert "_meta" in data
        assert data["_meta"]["problem"] == "auto save test"

        # Validate markdown
        md_content = md_path.read_text()
        assert "Immune Trust Protocol" in md_content

    def test_auto_save_unique_filenames(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _auto_save_invention

        inv_dir = tmp_path / "inventions"
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="same name test", report=report)
        state.inventions.append(entry)
        state.current_idx = 0

        p1 = _auto_save_invention(state)
        p2 = _auto_save_invention(state)

        assert p1 is not None and p2 is not None
        assert p1 != p2
        assert p1.exists() and p2.exists()


class TestSessionReplay:
    def test_save_session_replay(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _save_session_replay

        sess_dir = tmp_path / "sessions"
        monkeypatch.setattr(config_mod, "SESSIONS_DIR", sess_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", tmp_path / "inventions")
        monkeypatch.setattr(repl_mod, "SESSIONS_DIR", sess_dir)

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="session test", report=report)
        state.inventions.append(entry)
        state.total_cost_usd = 0.92
        state.context_items = ["extra context"]

        path = _save_session_replay(state)

        assert path is not None
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["total_cost_usd"] == 0.92
        assert len(data["inventions"]) == 1
        assert data["inventions"][0]["problem"] == "session test"
        assert data["context_items"] == ["extra context"]
        assert "backend" in data
        assert "model" in data


# ---------------------------------------------------------------------------
# Phase 4: Onboarding, Tab Completion, Export PDF
# ---------------------------------------------------------------------------


class TestOnboarding:
    def test_detect_backends(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import json

        from hephaestus.cli.config import _detect_claude_max

        # Test with a fake auth-profiles store containing an OAT token
        store_path = tmp_path / ".openclaw" / "agents" / "main" / "agent"
        store_path.mkdir(parents=True)
        store_file = store_path / "auth-profiles.json"
        store_file.write_text(
            json.dumps({"profiles": {"anthropic:default": {"token": "sk-ant-oat01-test"}}})
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert _detect_claude_max() is True

        # Test with no token
        store_file.write_text(json.dumps({"profiles": {}}))
        assert _detect_claude_max() is False

    def test_load_config_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli.config import load_config

        monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
        result = load_config()
        assert result is None

    def test_load_config_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli.config import HephaestusConfig, load_config, save_config

        config_path = tmp_path / "config.yaml"
        monkeypatch.setattr(config_mod, "CONFIG_PATH", config_path)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)

        cfg = HephaestusConfig(
            backend="openrouter",
            depth=5,
            divergence_intensity="MAXIMUM",
            output_mode="SYSTEM",
            use_branchgenome_v1=True,
        )
        save_config(cfg)

        loaded = load_config()
        assert loaded is not None
        assert loaded.backend == "openrouter"
        assert loaded.depth == 5
        assert loaded.divergence_intensity == "MAXIMUM"
        assert loaded.output_mode == "SYSTEM"
        assert loaded.use_branchgenome_v1 is True


class TestTabCompletion:
    def test_command_completer(self) -> None:
        from hephaestus.cli.repl import _CommandCompleter

        completer = _CommandCompleter(["/help", "/history", "/save", "/status"])

        # Completing "/h" should match /help and /history
        result0 = completer.complete("/h", 0)
        result1 = completer.complete("/h", 1)
        result2 = completer.complete("/h", 2)

        assert result0 in ("/help", "/history")
        assert result1 in ("/help", "/history")
        assert result2 is None

    def test_command_completer_exact(self) -> None:
        from hephaestus.cli.repl import _CommandCompleter

        completer = _CommandCompleter(["/help", "/history", "/save"])

        assert completer.complete("/s", 0) == "/save"
        assert completer.complete("/s", 1) is None

    def test_command_completer_no_slash(self) -> None:
        from hephaestus.cli.repl import _CommandCompleter

        completer = _CommandCompleter(["/help", "/save"])
        assert completer.complete("hello", 0) is None


class TestExportPdf:
    @pytest.mark.asyncio
    async def test_export_markdown(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _cmd_export_v2

        inv_dir = tmp_path / "inventions"
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="export test", report=report)
        state.inventions.append(entry)
        state.current_idx = 0

        console = _console()
        await _cmd_export_v2(console, state, "markdown")

        md_files = list(inv_dir.glob("*.md"))
        assert len(md_files) >= 1

    @pytest.mark.asyncio
    async def test_export_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _cmd_export_v2

        inv_dir = tmp_path / "inventions"
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="export test", report=report)
        state.inventions.append(entry)
        state.current_idx = 0

        console = _console()
        await _cmd_export_v2(console, state, "json")

        json_files = list(inv_dir.glob("*.json"))
        assert len(json_files) >= 1

    @pytest.mark.asyncio
    async def test_export_pdf_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PDF export falls back to markdown if weasyprint not installed."""
        from hephaestus.cli import config as config_mod
        from hephaestus.cli import repl as repl_mod
        from hephaestus.cli.repl import InventionEntry, _cmd_export_v2

        inv_dir = tmp_path / "inventions"
        monkeypatch.setattr(config_mod, "INVENTIONS_DIR", inv_dir)
        monkeypatch.setattr(config_mod, "HEPHAESTUS_DIR", tmp_path)
        monkeypatch.setattr(repl_mod, "INVENTIONS_DIR", inv_dir)

        state = _make_session()
        report = _make_report()
        entry = InventionEntry(problem="pdf test", report=report)
        state.inventions.append(entry)
        state.current_idx = 0

        console = _console()
        await _cmd_export_v2(console, state, "pdf")

        # Should have created either .pdf or .md fallback
        all_files = list(inv_dir.glob("*"))
        assert len(all_files) >= 1

    @pytest.mark.asyncio
    async def test_export_no_invention(self) -> None:
        from hephaestus.cli.repl import _cmd_export_v2

        console = _console()
        state = _make_session()
        await _cmd_export_v2(console, state, "markdown")
        assert "No current invention" in _get_output(console)

    def test_md_to_simple_html(self) -> None:
        from hephaestus.cli.repl import _md_to_simple_html

        md = "# Title\n\n## Section\n\n- item 1\n- item 2\n\nParagraph.\n\n```\ncode block\n```"
        html = _md_to_simple_html(md)
        assert "<h1>Title</h1>" in html
        assert "<h2>Section</h2>" in html
        assert "<li>item 1</li>" in html
        assert "<pre>" in html
        assert "code block" in html


# ---------------------------------------------------------------------------
# Invention markdown generation
# ---------------------------------------------------------------------------


class TestInventionMarkdown:
    def test_invention_to_markdown(self) -> None:
        from hephaestus.cli.repl import InventionEntry, _invention_to_markdown

        report = _make_report()
        entry = InventionEntry(problem="md test problem", report=report)
        md = _invention_to_markdown(entry, report)

        assert "# Immune Trust Protocol" in md
        assert "**Problem:** md test problem" in md
        assert "Immune System" in md
        assert "0.91" in md
        assert "Trust propagates like immune memory" in md


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class TestSessionState:
    def test_add_invention(self) -> None:
        state = _make_session()
        report = _make_report()
        state.add_invention("test", report)

        assert len(state.inventions) == 1
        assert state.current_idx == 0
        assert state.current is not None
        assert state.current_report is report
        assert state.total_cost_usd == 0.92

    def test_current_none_when_empty(self) -> None:
        state = _make_session()
        assert state.current is None
        assert state.current_report is None

    def test_session_duration(self) -> None:
        state = _make_session()
        dur = state.session_duration
        assert dur >= 0

    def test_slug_generation(self) -> None:
        from hephaestus.cli.repl import InventionEntry

        entry = InventionEntry(problem="I need a load balancer for traffic", report=MagicMock())
        slug = entry.slug
        assert slug
        assert len(slug) <= 40
        # Should not contain special characters
        assert all(c.isalnum() or c == "-" for c in slug)


# ---------------------------------------------------------------------------
# Command registry completeness
# ---------------------------------------------------------------------------


class TestCommandRegistry:
    def test_all_commands_registered(self) -> None:
        from hephaestus.cli.repl import COMMANDS

        required = [
            "help",
            "status",
            "history",
            "model",
            "backend",
            "usage",
            "cost",
            "clear",
            "quit",
            "exit",
            "alternatives",
            "trace",
            "export",
            "candidates",
            "refine",
            "domain",
            "deeper",
            "context",
            "save",
            "load",
            "compare",
        ]
        for cmd in required:
            assert cmd in COMMANDS, f"/{cmd} not registered"

    def test_all_command_list_for_tab_completion(self) -> None:
        from hephaestus.cli.repl import ALL_COMMANDS

        assert "/save" in ALL_COMMANDS
        assert "/load" in ALL_COMMANDS
        assert "/compare" in ALL_COMMANDS
        assert "/help" in ALL_COMMANDS
        assert "/export" in ALL_COMMANDS


# ---------------------------------------------------------------------------
# REPL loop integration (light smoke test)
# ---------------------------------------------------------------------------


class TestReplLoop:
    @pytest.mark.asyncio
    async def test_quit_command(self) -> None:
        """Sending /quit should raise SystemExit."""
        from hephaestus.cli.repl import _cmd_quit

        console = _console()
        state = _make_session()
        with pytest.raises(SystemExit):
            await _cmd_quit(console, state, "")

    @pytest.mark.asyncio
    async def test_menu_choice_1(self) -> None:
        """Menu choice 1 shows full report."""
        from hephaestus.cli.repl import InventionEntry, _handle_menu_choice

        console = _console()
        state = _make_session()
        report = _make_report()
        state.inventions.append(InventionEntry(problem="test", report=report))
        state.current_idx = 0

        handled = await _handle_menu_choice(console, state, "1")
        assert handled is True

    @pytest.mark.asyncio
    async def test_menu_choice_4_resets(self) -> None:
        """Menu choice 4 resets for new problem."""
        from hephaestus.cli.repl import InventionEntry, _handle_menu_choice

        console = _console()
        state = _make_session()
        state.context_items = ["old context"]
        report = _make_report()
        state.inventions.append(InventionEntry(problem="test", report=report))
        state.current_idx = 0

        handled = await _handle_menu_choice(console, state, "4")
        assert handled is True
        assert state.current_idx == -1
        assert state.context_items == []

    @pytest.mark.asyncio
    async def test_menu_choice_7_launches_agent_chat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import hephaestus.cli.repl as repl_module
        from hephaestus.cli.repl import InventionEntry, _handle_menu_choice

        called = {"chat": False}

        async def _fake_chat(console: Console, state: Any) -> None:
            called["chat"] = True

        monkeypatch.setattr(repl_module, "_chat_about_invention", _fake_chat)

        console = _console()
        state = _make_session()
        report = _make_report()
        state.inventions.append(InventionEntry(problem="test", report=report))
        state.current_idx = 0

        handled = await _handle_menu_choice(console, state, "7")
        assert handled is True
        assert called["chat"] is True

    @pytest.mark.asyncio
    async def test_unknown_menu_not_handled(self) -> None:
        from hephaestus.cli.repl import _handle_menu_choice

        console = _console()
        state = _make_session()
        handled = await _handle_menu_choice(console, state, "9")
        assert handled is False


class TestWorkspaceAwarePipeline:
    @pytest.mark.asyncio
    async def test_run_pipeline_injects_workspace_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import hephaestus.cli.main as main_module
        import hephaestus.cli.repl as repl_module
        import hephaestus.core.genesis as genesis_module

        captured: dict[str, str] = {}

        class _FakeGenesis:
            def __init__(self, config: Any) -> None:
                self.config = config

            async def invent_stream(self, problem: str):
                captured["problem"] = problem
                yield SimpleNamespace(
                    stage=genesis_module.PipelineStage.COMPLETE,
                    message="done",
                    data=_make_report(problem=problem),
                )

        monkeypatch.setattr(
            repl_module, "_build_genesis_config_from_session", lambda state: object()
        )
        monkeypatch.setattr(genesis_module, "Genesis", _FakeGenesis)
        monkeypatch.setattr(
            main_module, "_handle_pipeline_update", lambda update, stage_progress: None
        )
        monkeypatch.setattr(repl_module, "_display_invention_result", lambda console, state: None)

        console = _console()
        state = _make_session(auto_save=False)
        state.workspace_root = Path("/tmp/example-repo")
        state.workspace_context = SimpleNamespace(
            to_prompt_text=lambda: (
                "=== WORKSPACE CONTEXT ===\nrepo summary here\n=== END WORKSPACE CONTEXT ==="
            )
        )

        await repl_module._run_pipeline(console, state, "reinvent this system")

        assert "problem" in captured
        assert captured["problem"].startswith("reinvent this system")
        assert "=== WORKSPACE CONTEXT ===" in captured["problem"]
        assert "repo summary here" in captured["problem"]

    def test_inject_workspace_context_avoids_duplication(self) -> None:
        from hephaestus.cli.repl import _inject_workspace_context

        state = _make_session(auto_save=False)
        state.workspace_context = SimpleNamespace(
            to_prompt_text=lambda: (
                "=== WORKSPACE CONTEXT ===\nrepo summary here\n=== END WORKSPACE CONTEXT ==="
            )
        )
        problem = "reinvent this system\n\n=== WORKSPACE CONTEXT ===\nrepo summary here\n=== END WORKSPACE CONTEXT ==="

        assert _inject_workspace_context(problem, state) == problem
