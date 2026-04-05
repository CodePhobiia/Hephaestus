"""Tests for the ForgeBase CLI/REPL commands.

Tests cover:
- REPL slash commands (/vault, /ask, /fuse, /ingest, /workbook, /fb-lint, /fb-compile, /fb-export)
- Display rendering functions
- Command registry integration
- Click CLI commands via CliRunner
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from hephaestus.cli.commands import default_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _console() -> Console:
    return Console(file=StringIO(), highlight=False, force_terminal=True, width=120)


def _get_output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[attr-defined]


def _make_state(**overrides: Any) -> SimpleNamespace:
    """Create a minimal state namespace mimicking SessionState + ForgeBase fields."""
    defaults = dict(
        forgebase=None,
        current_vault_id=None,
        current_workbook_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_vault(
    vault_id: str = "vlt_00000000000000000000000001",
    name: str = "Test Vault",
    description: str = "A test vault",
) -> SimpleNamespace:
    return SimpleNamespace(
        vault_id=vault_id,
        name=name,
        description=description,
        head_revision_id="rev_00000000000000000000000001",
        created_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
        config={},
    )


def _make_lint_report() -> SimpleNamespace:
    return SimpleNamespace(
        report_id="rpt_00000000000000000000000001",
        vault_id="vlt_00000000000000000000000001",
        workbook_id=None,
        job_id="job_00000000000000000000000001",
        finding_count=5,
        findings_by_category={"unsupported_claim": 3, "orphaned_page": 2},
        findings_by_severity={"warning": 3, "info": 2},
        debt_score=12.5,
        debt_policy_version="1.0.0",
        raw_counts={},
        created_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
    )


def _make_workbook(
    workbook_id: str = "wb_00000000000000000000000001",
    name: str = "Research Branch",
) -> SimpleNamespace:
    return SimpleNamespace(
        workbook_id=workbook_id,
        vault_id="vlt_00000000000000000000000001",
        name=name,
        purpose=SimpleNamespace(value="research"),
        status=SimpleNamespace(value="open"),
        base_revision_id="rev_00000000000000000000000001",
        created_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
        created_by=SimpleNamespace(actor_type="system", actor_id="test"),
        created_by_run=None,
    )


def _make_fusion_result() -> SimpleNamespace:
    bridge = SimpleNamespace(
        bridge_concept="Metabolic Regulation",
        left_structure="enzyme_cascade",
        right_structure="control_loop",
        confidence=0.87,
    )
    transfer = SimpleNamespace(
        mechanism="Feedback inhibition",
        rationale="Both systems use negative feedback to maintain homeostasis.",
        confidence=0.79,
        caveats=["Scale mismatch"],
    )
    pair_result = SimpleNamespace(
        left_vault_id="vlt_00000000000000000000000001",
        right_vault_id="vlt_00000000000000000000000002",
        candidates_generated=12,
        maps_produced=[bridge],
        transfers_produced=[transfer],
    )
    return SimpleNamespace(
        fusion_id="fus_00000000000000000000000001",
        request=SimpleNamespace(
            vault_ids=["vlt_00000000000000000000000001", "vlt_00000000000000000000000002"]
        ),
        bridge_concepts=[bridge],
        transfer_opportunities=[transfer],
        pair_results=[pair_result],
        fused_baseline=SimpleNamespace(entries=[]),
        fused_context=SimpleNamespace(entries=[]),
        fused_dossier=SimpleNamespace(entries=[]),
        fusion_manifest=SimpleNamespace(),
        created_at=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Mock ForgeBase factory
# ---------------------------------------------------------------------------


def _mock_forgebase(vaults: list | None = None) -> MagicMock:
    """Create a mock ForgeBase with standard service stubs."""
    fb = MagicMock()

    # vault service
    vault_svc = AsyncMock()
    vault_svc.create_vault = AsyncMock(return_value=_make_vault())
    fb.vaults = vault_svc

    # UoW factory with mock repos
    mock_uow = AsyncMock()
    mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
    mock_uow.__aexit__ = AsyncMock(return_value=False)
    mock_uow.vaults = AsyncMock()
    mock_uow.vaults.list_all = AsyncMock(return_value=vaults or [])
    mock_uow.vaults.get = AsyncMock(return_value=_make_vault() if vaults else None)
    mock_uow.pages = AsyncMock()
    mock_uow.pages.list_by_vault = AsyncMock(return_value=[])
    mock_uow.claims = AsyncMock()
    mock_uow.claims.list_by_vault = AsyncMock(return_value=[])
    mock_uow.sources = AsyncMock()
    mock_uow.sources.list_by_vault = AsyncMock(return_value=[])
    mock_uow.links = AsyncMock()
    mock_uow.links.list_by_vault = AsyncMock(return_value=[])
    mock_uow.workbooks = AsyncMock()
    mock_uow.workbooks.list_by_vault = AsyncMock(return_value=[])
    mock_uow.workbooks.get = AsyncMock(return_value=_make_workbook())
    mock_uow.workbooks.list_page_heads = AsyncMock(return_value=[])
    mock_uow.workbooks.list_claim_heads = AsyncMock(return_value=[])
    mock_uow.workbooks.list_source_heads = AsyncMock(return_value=[])
    mock_uow.workbooks.list_tombstones = AsyncMock(return_value=[])
    mock_uow.rollback = AsyncMock()
    fb.uow_factory = MagicMock(return_value=mock_uow)

    # Lint engine
    fb.lint_engine = AsyncMock()
    fb.lint_engine.run_lint = AsyncMock(return_value=_make_lint_report())

    # Vault synthesizer
    fb.vault_synthesizer = AsyncMock()
    fb.vault_synthesizer.synthesize = AsyncMock(
        return_value=SimpleNamespace(pages_created=3, claims_created=10, open_questions=[])
    )

    # Branch service
    fb.branches = AsyncMock()
    fb.branches.create_workbook = AsyncMock(return_value=_make_workbook())
    fb.branches.abandon_workbook = AsyncMock()

    # Merge service
    fb.merge = AsyncMock()

    # Ingest service
    fb.ingest = AsyncMock()
    fb.ingest.ingest_source = AsyncMock(
        return_value=(
            SimpleNamespace(
                source_id="src_00000000000000000000000001", format=SimpleNamespace(value="markdown")
            ),
            SimpleNamespace(
                title="test.md",
                trust_tier=SimpleNamespace(value="standard"),
            ),
        )
    )

    # Context assembler
    fb.context_assembler = AsyncMock()
    fb.context_assembler.assemble_all = AsyncMock(
        return_value=(
            SimpleNamespace(entries=[]),
            SimpleNamespace(entries=[]),
            SimpleNamespace(entries=[]),
        )
    )

    # Fusion
    fb.fusion = AsyncMock()
    fb.fusion.fuse = AsyncMock(return_value=_make_fusion_result())

    fb.close = AsyncMock()

    return fb


# ═══════════════════════════════════════════════════════════════════════════
# Display rendering tests
# ═══════════════════════════════════════════════════════════════════════════


class TestForgeBaseDisplay:
    def test_render_vault_info(self) -> None:
        from hephaestus.cli.forgebase_display import render_vault_info

        console = _console()
        vault = _make_vault()
        render_vault_info(console, vault, page_count=5, claim_count=12, source_count=3)
        output = _get_output(console)
        assert "Test Vault" in output
        assert "vlt_00000000000000000000000001" in output
        assert "5" in output  # pages
        assert "12" in output  # claims

    def test_render_vault_list_empty(self) -> None:
        from hephaestus.cli.forgebase_display import render_vault_list

        console = _console()
        render_vault_list(console, [])
        output = _get_output(console)
        assert "No vaults found" in output

    def test_render_vault_list_with_entries(self) -> None:
        from hephaestus.cli.forgebase_display import render_vault_list

        console = _console()
        vaults = [
            _make_vault(),
            _make_vault(vault_id="vlt_00000000000000000000000002", name="Other"),
        ]
        render_vault_list(console, vaults)
        output = _get_output(console)
        assert "Test Vault" in output
        assert "Other" in output

    def test_render_lint_report(self) -> None:
        from hephaestus.cli.forgebase_display import render_lint_report

        console = _console()
        report = _make_lint_report()
        render_lint_report(console, report)
        output = _get_output(console)
        assert "5" in output  # finding count
        assert "12.5" in output  # debt score
        assert "unsupported_claim" in output

    def test_render_fusion_result(self) -> None:
        from hephaestus.cli.forgebase_display import render_fusion_result

        console = _console()
        result = _make_fusion_result()
        render_fusion_result(console, result)
        output = _get_output(console)
        assert "Metabolic Regulation" in output
        assert "Feedback inhibition" in output
        assert "0.87" in output

    def test_render_compile_result_tier2(self) -> None:
        from hephaestus.cli.forgebase_display import render_compile_result

        console = _console()
        manifest = SimpleNamespace(pages_created=4, claims_created=15, open_questions=["Q1"])
        render_compile_result(console, manifest)
        output = _get_output(console)
        assert "synthesis complete" in output.lower()
        assert "4" in output

    def test_render_workbook_list_empty(self) -> None:
        from hephaestus.cli.forgebase_display import render_workbook_list

        console = _console()
        render_workbook_list(console, [])
        output = _get_output(console)
        assert "No workbooks" in output

    def test_render_workbook_list_with_entries(self) -> None:
        from hephaestus.cli.forgebase_display import render_workbook_list

        console = _console()
        render_workbook_list(console, [_make_workbook()])
        output = _get_output(console)
        assert "Research Branch" in output

    def test_render_ingest_result(self) -> None:
        from hephaestus.cli.forgebase_display import render_ingest_result

        console = _console()
        source = SimpleNamespace(
            source_id="src_00000000000000000000000001",
            format=SimpleNamespace(value="markdown"),
        )
        version = SimpleNamespace(
            title="paper.md",
            trust_tier=SimpleNamespace(value="standard"),
        )
        render_ingest_result(console, source, version)
        output = _get_output(console)
        assert "Source ingested" in output
        assert "paper.md" in output

    def test_render_export_success(self) -> None:
        from hephaestus.cli.forgebase_display import render_export_success

        console = _console()
        render_export_success(console, "/tmp/export", "markdown")
        output = _get_output(console)
        assert "Exported" in output
        assert "markdown" in output


# ═══════════════════════════════════════════════════════════════════════════
# REPL handler tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVaultCommand:
    @pytest.mark.asyncio
    async def test_vault_no_args_shows_usage(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "")
        output = _get_output(console)
        assert "create" in output.lower()
        assert "list" in output.lower()

    @pytest.mark.asyncio
    async def test_vault_create(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb)

        await _cmd_vault(console, state, "create MyVault --description Test desc")
        output = _get_output(console)
        assert "Vault created" in output
        assert state.current_vault_id is not None

    @pytest.mark.asyncio
    async def test_vault_create_no_name(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "create")
        output = _get_output(console)
        assert "Usage" in output

    @pytest.mark.asyncio
    async def test_vault_list(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        fb = _mock_forgebase(vaults=[_make_vault()])
        state = _make_state(forgebase=fb)

        await _cmd_vault(console, state, "list")
        output = _get_output(console)
        assert "Test Vault" in output

    @pytest.mark.asyncio
    async def test_vault_list_empty(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        fb = _mock_forgebase(vaults=[])
        state = _make_state(forgebase=fb)

        await _cmd_vault(console, state, "list")
        output = _get_output(console)
        assert "No vaults" in output

    @pytest.mark.asyncio
    async def test_vault_info_no_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "info")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_vault_info_with_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        fb = _mock_forgebase(vaults=[_make_vault()])
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")

        await _cmd_vault(console, state, "info")
        output = _get_output(console)
        assert "Test Vault" in output

    @pytest.mark.asyncio
    async def test_vault_lint_no_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "lint")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_vault_lint_with_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")

        await _cmd_vault(console, state, "lint")
        output = _get_output(console)
        assert "5" in output  # finding count

    @pytest.mark.asyncio
    async def test_vault_compile_no_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "compile")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_vault_unknown_subcmd(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "nosuch")
        output = _get_output(console)
        assert "Unknown vault subcommand" in output

    @pytest.mark.asyncio
    async def test_vault_use_no_id(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_vault

        console = _console()
        state = _make_state()
        await _cmd_vault(console, state, "use")
        output = _get_output(console)
        assert "Usage" in output


class TestAskCommand:
    @pytest.mark.asyncio
    async def test_ask_no_query(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ask

        console = _console()
        state = _make_state()
        await _cmd_ask(console, state, "")
        output = _get_output(console)
        assert "Usage" in output

    @pytest.mark.asyncio
    async def test_ask_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ask

        console = _console()
        state = _make_state()
        await _cmd_ask(console, state, "What is entropy?")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_ask_with_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ask

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")

        await _cmd_ask(console, state, "What is entropy?")
        output = _get_output(console)
        assert "What is entropy?" in output


class TestFuseCommand:
    @pytest.mark.asyncio
    async def test_fuse_no_args(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_fuse

        console = _console()
        state = _make_state()
        await _cmd_fuse(console, state, "")
        output = _get_output(console)
        assert "Usage" in output

    @pytest.mark.asyncio
    async def test_fuse_one_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_fuse

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb)
        await _cmd_fuse(console, state, "vlt_00000000000000000000000001")
        output = _get_output(console)
        assert "at least 2" in output

    @pytest.mark.asyncio
    async def test_fuse_two_vaults(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_fuse

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb)
        await _cmd_fuse(
            console, state, "vlt_00000000000000000000000001 vlt_00000000000000000000000002"
        )
        output = _get_output(console)
        assert "Fusion complete" in output or "Metabolic" in output


class TestIngestCommand:
    @pytest.mark.asyncio
    async def test_ingest_no_args(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ingest

        console = _console()
        state = _make_state()
        await _cmd_ingest(console, state, "")
        output = _get_output(console)
        assert "Usage" in output

    @pytest.mark.asyncio
    async def test_ingest_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ingest

        console = _console()
        state = _make_state()
        await _cmd_ingest(console, state, "/some/path.md")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_ingest_file_not_found(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ingest

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")
        await _cmd_ingest(console, state, "/nonexistent/file.md")
        output = _get_output(console)
        assert "not found" in output.lower()

    @pytest.mark.asyncio
    async def test_ingest_url(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ingest

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")
        await _cmd_ingest(console, state, "https://example.com/paper.pdf")
        output = _get_output(console)
        assert "Source ingested" in output

    @pytest.mark.asyncio
    async def test_ingest_local_file(self, tmp_path: Path) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_ingest

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\nSome content.", encoding="utf-8")

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")
        await _cmd_ingest(console, state, str(test_file))
        output = _get_output(console)
        assert "Source ingested" in output


class TestWorkbookCommand:
    @pytest.mark.asyncio
    async def test_workbook_no_args(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        state = _make_state()
        await _cmd_workbook(console, state, "")
        output = _get_output(console)
        assert "No active workbook" in output

    @pytest.mark.asyncio
    async def test_workbook_open_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        state = _make_state()
        await _cmd_workbook(console, state, "open Research")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_workbook_open(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")
        await _cmd_workbook(console, state, "open Research")
        output = _get_output(console)
        assert "Workbook created" in output
        assert state.current_workbook_id is not None

    @pytest.mark.asyncio
    async def test_workbook_list_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        state = _make_state()
        await _cmd_workbook(console, state, "list")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_workbook_list(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        fb = _mock_forgebase()
        state = _make_state(forgebase=fb, current_vault_id="vlt_00000000000000000000000001")
        await _cmd_workbook(console, state, "list")
        output = _get_output(console)
        # Either shows workbooks or "No workbooks" -- depends on mock
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_workbook_abandon_no_active(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        state = _make_state()
        await _cmd_workbook(console, state, "abandon")
        output = _get_output(console)
        assert "No active workbook" in output

    @pytest.mark.asyncio
    async def test_workbook_unknown_subcmd(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_workbook

        console = _console()
        state = _make_state()
        await _cmd_workbook(console, state, "nosuch")
        output = _get_output(console)
        assert "Unknown workbook subcommand" in output


class TestFbLintCompileExport:
    @pytest.mark.asyncio
    async def test_lint_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_lint

        console = _console()
        state = _make_state()
        await _cmd_lint(console, state, "")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_compile_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_compile

        console = _console()
        state = _make_state()
        await _cmd_compile(console, state, "")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_fb_export_no_vault(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_fb_export

        console = _console()
        state = _make_state()
        await _cmd_fb_export(console, state, "")
        output = _get_output(console)
        assert "No active vault" in output

    @pytest.mark.asyncio
    async def test_fb_export_invalid_format(self) -> None:
        from hephaestus.cli.forgebase_commands import _cmd_fb_export

        console = _console()
        state = _make_state(current_vault_id="vlt_00000000000000000000000001")
        await _cmd_fb_export(console, state, "pdf")
        output = _get_output(console)
        assert "Supported formats" in output


# ═══════════════════════════════════════════════════════════════════════════
# Command registry tests
# ═══════════════════════════════════════════════════════════════════════════

EXPECTED_FORGEBASE_COMMANDS = {
    "vault",
    "ask",
    "fuse",
    "ingest",
    "fb-lint",
    "fb-compile",
    "workbook",
    "fb-export",
}


class TestForgeBaseRegistry:
    def test_all_forgebase_commands_registered(self) -> None:
        reg = default_registry()
        for name in EXPECTED_FORGEBASE_COMMANDS:
            assert reg.get(name) is not None, f"Missing ForgeBase command: {name}"

    def test_vault_alias(self) -> None:
        reg = default_registry()
        cmd = reg.get("v")
        assert cmd is not None
        assert cmd.name == "vault"

    def test_workbook_alias(self) -> None:
        reg = default_registry()
        cmd = reg.get("wb")
        assert cmd is not None
        assert cmd.name == "workbook"

    def test_forgebase_category(self) -> None:
        reg = default_registry()
        fb_cmds = reg.list_commands(category="forgebase")
        names = {c.name for c in fb_cmds}
        assert names == EXPECTED_FORGEBASE_COMMANDS

    def test_ask_requires_args(self) -> None:
        reg = default_registry()
        cmd = reg.get("ask")
        assert cmd is not None
        assert cmd.args_required is True

    def test_fuse_requires_args(self) -> None:
        reg = default_registry()
        cmd = reg.get("fuse")
        assert cmd is not None
        assert cmd.args_required is True

    def test_vault_completions(self) -> None:
        reg = default_registry()
        comps = reg.completions("/va")
        assert "/vault" in comps

    def test_format_help_includes_forgebase(self) -> None:
        reg = default_registry()
        text = reg.format_help()
        assert "Forgebase" in text

    def test_handler_names_populated(self) -> None:
        reg = default_registry()
        for name in EXPECTED_FORGEBASE_COMMANDS:
            cmd = reg.get(name)
            assert cmd.handler_name, f"{name} missing handler_name"


# ═══════════════════════════════════════════════════════════════════════════
# REPL COMMANDS dict wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestReplCommandsWiring:
    def test_forgebase_handlers_wired(self) -> None:
        from hephaestus.cli.repl import COMMANDS

        for name in (
            "vault",
            "ask",
            "fuse",
            "ingest",
            "fb-lint",
            "fb-compile",
            "workbook",
            "fb-export",
        ):
            assert COMMANDS.get(name) is not None, f"COMMANDS[{name!r}] not wired"
            assert callable(COMMANDS[name]), f"COMMANDS[{name!r}] is not callable"

    def test_alias_handlers_wired(self) -> None:
        from hephaestus.cli.repl import COMMANDS

        assert COMMANDS.get("v") is not None
        assert COMMANDS.get("wb") is not None


# ═══════════════════════════════════════════════════════════════════════════
# SessionState ForgeBase fields
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionStateForgeBaseFields:
    def test_forgebase_fields_exist(self) -> None:
        from hephaestus.cli.config import HephaestusConfig
        from hephaestus.cli.repl import SessionState

        cfg = HephaestusConfig(backend="api", default_model="opus", depth=3, candidates=8)
        state = SessionState(config=cfg)

        assert state.forgebase is None
        assert state.current_vault_id is None
        assert state.current_workbook_id is None

    def test_forgebase_fields_settable(self) -> None:
        from hephaestus.cli.config import HephaestusConfig
        from hephaestus.cli.repl import SessionState

        cfg = HephaestusConfig(backend="api", default_model="opus", depth=3, candidates=8)
        state = SessionState(config=cfg)

        state.forgebase = "mock_fb"
        state.current_vault_id = "vlt_123"
        state.current_workbook_id = "wb_456"

        assert state.forgebase == "mock_fb"
        assert state.current_vault_id == "vlt_123"
        assert state.current_workbook_id == "wb_456"
