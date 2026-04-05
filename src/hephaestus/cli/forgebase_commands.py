"""ForgeBase CLI and REPL command handlers.

Contains:
- Click subcommand group for ``heph vault ...`` and standalone commands
- Async handler functions for REPL slash commands (/vault, /ask, /fuse, etc.)
- Shared helper for lazy ForgeBase initialization

All handlers follow the existing REPL convention:
    async def handler(console: Console, state: SessionState, args: str) -> None
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from rich.console import Console

from hephaestus.cli.display import CYAN, GREEN, RED, DIM
from hephaestus.cli.forgebase_display import (
    render_compile_result,
    render_export_success,
    render_fusion_result,
    render_ingest_result,
    render_lint_report,
    render_vault_info,
    render_vault_list,
    render_workbook_list,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy ForgeBase initialization
# ---------------------------------------------------------------------------

async def _ensure_forgebase(state: Any) -> Any:
    """Initialize ForgeBase lazily on the session state if not already set.

    Stores the ForgeBase instance as ``state.forgebase``.
    Returns the instance.
    """
    fb = getattr(state, "forgebase", None)
    if fb is not None:
        return fb

    from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase

    # Determine database path: use ~/.hephaestus/forgebase.db by default
    data_dir = Path.home() / ".hephaestus"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(data_dir / "forgebase.db")

    config = ForgeBaseConfig(sqlite_path=db_path)
    fb = await create_forgebase(config)
    state.forgebase = fb
    return fb


# ---------------------------------------------------------------------------
# Vault entity counts helper
# ---------------------------------------------------------------------------

async def _vault_entity_counts(fb: Any, vault_id: Any) -> dict[str, int]:
    """Query entity counts for a vault using a read-only UoW."""
    counts: dict[str, int] = {
        "pages": 0,
        "claims": 0,
        "sources": 0,
        "links": 0,
        "workbooks": 0,
    }
    uow = fb.uow_factory()
    async with uow:
        try:
            pages = await uow.pages.list_by_vault(vault_id)
            counts["pages"] = len(pages)
        except Exception:
            pass
        try:
            sources = await uow.sources.list_by_vault(vault_id)
            counts["sources"] = len(sources)
        except Exception:
            pass
        try:
            claims = await uow.claims.list_by_vault(vault_id)
            counts["claims"] = len(claims)
        except Exception:
            pass
        try:
            links = await uow.links.list_by_vault(vault_id)
            counts["links"] = len(links)
        except Exception:
            pass
        try:
            workbooks = await uow.workbooks.list_by_vault(vault_id)
            counts["workbooks"] = len(workbooks)
        except Exception:
            pass
        await uow.rollback()
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# REPL slash-command handlers
# ═══════════════════════════════════════════════════════════════════════════
#
# All handlers: async def _cmd_X(console, state, args) -> None

async def _cmd_vault(console: Console, state: Any, args: str) -> None:
    """Handle /vault [create <name>|list|use <id>|info|compile|lint]."""
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    sub_args = parts[1].strip() if len(parts) > 1 else ""

    if not subcmd:
        # Show current vault context and usage
        current = getattr(state, "current_vault_id", None)
        if current:
            console.print(f"  [dim]Active vault:[/] [{CYAN}]{current}[/]")
        else:
            console.print("  [dim]No active vault. Use /vault create <name> or /vault use <id>.[/]")
        console.print(
            "  [dim]Subcommands:[/] create <name>, list, use <id>, info, compile, lint\n"
        )
        return

    if subcmd == "create":
        await _vault_create(console, state, sub_args)
    elif subcmd == "list":
        await _vault_list(console, state)
    elif subcmd == "use":
        await _vault_use(console, state, sub_args)
    elif subcmd == "info":
        await _vault_info(console, state)
    elif subcmd == "compile":
        await _vault_compile(console, state)
    elif subcmd == "lint":
        await _vault_lint(console, state)
    else:
        console.print(
            f"  [{RED}]Unknown vault subcommand: {subcmd}[/]\n"
            "  [dim]Available: create, list, use, info, compile, lint[/]\n"
        )


async def _vault_create(console: Console, state: Any, args: str) -> None:
    """Create a new vault."""
    parts = args.split("--description", 1)
    name = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else ""

    if not name:
        console.print(f"  [{RED}]Usage: /vault create <name> [--description TEXT][/]\n")
        return

    fb = await _ensure_forgebase(state)
    vault = await fb.vaults.create_vault(name, description=description)

    state.current_vault_id = vault.vault_id
    console.print(f"  [{GREEN}]Vault created[/]")
    console.print(f"  ID: [{CYAN}]{vault.vault_id}[/]")
    console.print(f"  Name: [{CYAN}]{vault.name}[/]")
    if description:
        console.print(f"  Description: {description}")
    console.print(f"  [dim]Vault is now the active context.[/]\n")


async def _vault_list(console: Console, state: Any) -> None:
    """List all vaults."""
    fb = await _ensure_forgebase(state)
    uow = fb.uow_factory()
    async with uow:
        vaults = await uow.vaults.list_all()
        await uow.rollback()
    render_vault_list(console, vaults)


async def _vault_use(console: Console, state: Any, vault_id_str: str) -> None:
    """Set the active vault context."""
    if not vault_id_str:
        console.print(f"  [{RED}]Usage: /vault use <vault_id>[/]\n")
        return

    from hephaestus.forgebase.domain.values import EntityId

    fb = await _ensure_forgebase(state)
    try:
        vid = EntityId(vault_id_str.strip())
    except Exception:
        console.print(f"  [{RED}]Invalid vault ID: {vault_id_str}[/]\n")
        return

    uow = fb.uow_factory()
    async with uow:
        vault = await uow.vaults.get(vid)
        await uow.rollback()

    if vault is None:
        console.print(f"  [{RED}]Vault not found: {vault_id_str}[/]\n")
        return

    state.current_vault_id = vid
    state.current_workbook_id = None  # Reset workbook when switching vault
    console.print(f"  [{GREEN}]Active vault set to [{CYAN}]{vault.name}[/] ({vid})[/]\n")


async def _vault_info(console: Console, state: Any) -> None:
    """Show detailed info about the current vault."""
    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)
    uow = fb.uow_factory()
    async with uow:
        vault = await uow.vaults.get(vault_id)
        await uow.rollback()

    if vault is None:
        console.print(f"  [{RED}]Vault no longer exists: {vault_id}[/]\n")
        state.current_vault_id = None
        return

    counts = await _vault_entity_counts(fb, vault_id)
    render_vault_info(
        console,
        vault,
        page_count=counts["pages"],
        claim_count=counts["claims"],
        source_count=counts["sources"],
        link_count=counts["links"],
        workbook_count=counts["workbooks"],
    )


async def _vault_compile(console: Console, state: Any) -> None:
    """Compile the current vault (Tier 2 vault synthesis)."""
    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)
    workbook_id = getattr(state, "current_workbook_id", None)

    console.print(f"  [dim]Compiling vault {vault_id}...[/]")
    try:
        manifest = await fb.vault_synthesizer.synthesize(
            vault_id, workbook_id=workbook_id
        )
        render_compile_result(console, manifest)
    except Exception as exc:
        console.print(f"  [{RED}]Compilation failed: {exc}[/]\n")


async def _vault_lint(console: Console, state: Any) -> None:
    """Lint the current vault."""
    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)
    workbook_id = getattr(state, "current_workbook_id", None)

    console.print(f"  [dim]Linting vault {vault_id}...[/]")
    try:
        report = await fb.lint_engine.run_lint(
            vault_id, workbook_id=workbook_id
        )
        render_lint_report(console, report)
    except Exception as exc:
        console.print(f"  [{RED}]Lint failed: {exc}[/]\n")


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------

async def _cmd_ask(console: Console, state: Any, args: str) -> None:
    """Handle /ask <query> -- query within current vault context."""
    query = args.strip()
    if not query:
        console.print(f"  [{RED}]Usage: /ask <query>[/]\n")
        return

    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)

    console.print(f"  [dim]Assembling context from vault {vault_id}...[/]")
    try:
        if fb.context_assembler is not None:
            baseline, context_pack, dossier = await fb.context_assembler.assemble_all(vault_id)

            # Format context summary
            console.print()
            if hasattr(baseline, "entries") and baseline.entries:
                console.print(f"  Prior art entries: [{CYAN}]{len(baseline.entries)}[/]")
            if hasattr(context_pack, "entries") and context_pack.entries:
                console.print(f"  Domain context entries: [{CYAN}]{len(context_pack.entries)}[/]")
            if hasattr(dossier, "entries") and dossier.entries:
                console.print(f"  Constraint dossier entries: [{CYAN}]{len(dossier.entries)}[/]")

            console.print()
            console.print(f"  [{CYAN}]Query:[/] {query}")
            console.print(
                f"  [dim]Context assembled. Pipe this into the invention pipeline "
                f"with: heph \"<problem>\" to use full ForgeBase context.[/]\n"
            )
        else:
            console.print(f"  [dim]No context assembler available.[/]\n")
    except Exception as exc:
        console.print(f"  [{RED}]Context assembly failed: {exc}[/]\n")


# ---------------------------------------------------------------------------
# /fuse
# ---------------------------------------------------------------------------

async def _cmd_fuse(console: Console, state: Any, args: str) -> None:
    """Handle /fuse <vault_ids...> [--problem TEXT] [--mode strict|exploratory]."""
    if not args.strip():
        console.print(f"  [{RED}]Usage: /fuse <vault_id1> <vault_id2> [--problem TEXT] [--mode strict|exploratory][/]\n")
        return

    from hephaestus.forgebase.contracts.fusion import FusionRequest
    from hephaestus.forgebase.domain.enums import FusionMode
    from hephaestus.forgebase.domain.values import EntityId

    # Parse arguments
    tokens = args.strip().split()
    vault_ids: list[EntityId] = []
    problem: str | None = None
    mode = FusionMode.STRICT
    i = 0
    while i < len(tokens):
        if tokens[i] == "--problem" and i + 1 < len(tokens):
            # Collect everything after --problem until next flag
            problem_parts = []
            i += 1
            while i < len(tokens) and not tokens[i].startswith("--"):
                problem_parts.append(tokens[i])
                i += 1
            problem = " ".join(problem_parts)
        elif tokens[i] == "--mode" and i + 1 < len(tokens):
            mode_str = tokens[i + 1].lower()
            if mode_str == "exploratory":
                mode = FusionMode.EXPLORATORY
            i += 2
        else:
            try:
                vault_ids.append(EntityId(tokens[i]))
            except Exception:
                console.print(f"  [{RED}]Invalid vault ID: {tokens[i]}[/]\n")
                return
            i += 1

    if len(vault_ids) < 2:
        console.print(f"  [{RED}]Fusion requires at least 2 vault IDs.[/]\n")
        return

    fb = await _ensure_forgebase(state)

    console.print(f"  [dim]Fusing {len(vault_ids)} vaults...[/]")
    try:
        request = FusionRequest(
            vault_ids=vault_ids,
            problem=problem,
            fusion_mode=mode,
        )
        result = await fb.fusion.fuse(request)
        render_fusion_result(console, result)
    except Exception as exc:
        console.print(f"  [{RED}]Fusion failed: {exc}[/]\n")


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------

async def _cmd_ingest(console: Console, state: Any, args: str) -> None:
    """Handle /ingest <path_or_url> -- ingest source into current vault."""
    path_or_url = args.strip()
    if not path_or_url:
        console.print(f"  [{RED}]Usage: /ingest <path_or_url>[/]\n")
        return

    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    from hephaestus.forgebase.domain.enums import SourceFormat

    fb = await _ensure_forgebase(state)

    # Detect format from path/URL
    fmt = SourceFormat.MARKDOWN
    title = path_or_url
    raw_content: bytes

    if path_or_url.startswith(("http://", "https://")):
        fmt = SourceFormat.URL
        title = path_or_url
        raw_content = path_or_url.encode("utf-8")
    else:
        p = Path(path_or_url).expanduser()
        if not p.exists():
            console.print(f"  [{RED}]File not found: {path_or_url}[/]\n")
            return

        title = p.name
        ext = p.suffix.lower()
        format_map = {
            ".pdf": SourceFormat.PDF,
            ".md": SourceFormat.MARKDOWN,
            ".csv": SourceFormat.CSV,
            ".json": SourceFormat.JSON,
        }
        fmt = format_map.get(ext, SourceFormat.MARKDOWN)
        raw_content = p.read_bytes()

    workbook_id = getattr(state, "current_workbook_id", None)

    console.print(f"  [dim]Ingesting {title}...[/]")
    try:
        source, version = await fb.ingest.ingest_source(
            vault_id=vault_id,
            raw_content=raw_content,
            format=fmt,
            title=title,
            origin_locator=path_or_url,
            workbook_id=workbook_id,
            idempotency_key=f"cli-ingest:{vault_id}:{path_or_url}",
        )
        render_ingest_result(console, source, version)
    except Exception as exc:
        console.print(f"  [{RED}]Ingestion failed: {exc}[/]\n")


# ---------------------------------------------------------------------------
# /lint (standalone, operates on current vault)
# ---------------------------------------------------------------------------

async def _cmd_lint(console: Console, state: Any, args: str) -> None:
    """Handle /lint -- lint current vault."""
    await _vault_lint(console, state)


# ---------------------------------------------------------------------------
# /compile (standalone, operates on current vault)
# ---------------------------------------------------------------------------

async def _cmd_compile(console: Console, state: Any, args: str) -> None:
    """Handle /compile -- compile current vault."""
    await _vault_compile(console, state)


# ---------------------------------------------------------------------------
# /workbook
# ---------------------------------------------------------------------------

async def _cmd_workbook(console: Console, state: Any, args: str) -> None:
    """Handle /workbook [open <name>|list|diff|merge|abandon]."""
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else ""
    sub_args = parts[1].strip() if len(parts) > 1 else ""

    if not subcmd:
        current = getattr(state, "current_workbook_id", None)
        if current:
            console.print(f"  [dim]Active workbook:[/] [{CYAN}]{current}[/]")
        else:
            console.print("  [dim]No active workbook.[/]")
        console.print(
            "  [dim]Subcommands:[/] open <name>, list, diff, merge, abandon\n"
        )
        return

    if subcmd == "open":
        await _workbook_open(console, state, sub_args)
    elif subcmd == "list":
        await _workbook_list(console, state)
    elif subcmd == "diff":
        await _workbook_diff(console, state)
    elif subcmd == "merge":
        await _workbook_merge(console, state)
    elif subcmd == "abandon":
        await _workbook_abandon(console, state)
    else:
        console.print(
            f"  [{RED}]Unknown workbook subcommand: {subcmd}[/]\n"
            "  [dim]Available: open, list, diff, merge, abandon[/]\n"
        )


async def _workbook_open(console: Console, state: Any, name: str) -> None:
    """Create and activate a new workbook."""
    if not name:
        console.print(f"  [{RED}]Usage: /workbook open <name>[/]\n")
        return

    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    from hephaestus.forgebase.domain.enums import BranchPurpose

    fb = await _ensure_forgebase(state)

    try:
        wb = await fb.branches.create_workbook(
            vault_id=vault_id,
            name=name,
            purpose=BranchPurpose.RESEARCH,
        )
        state.current_workbook_id = wb.workbook_id
        console.print(f"  [{GREEN}]Workbook created and activated[/]")
        console.print(f"  ID: [{CYAN}]{wb.workbook_id}[/]")
        console.print(f"  Name: [{CYAN}]{wb.name}[/]")
        console.print(f"  Base revision: [{DIM}]{wb.base_revision_id}[/]\n")
    except Exception as exc:
        console.print(f"  [{RED}]Failed to create workbook: {exc}[/]\n")


async def _workbook_list(console: Console, state: Any) -> None:
    """List workbooks in the current vault."""
    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)
    uow = fb.uow_factory()
    async with uow:
        workbooks = await uow.workbooks.list_by_vault(vault_id)
        await uow.rollback()
    render_workbook_list(console, workbooks)


async def _workbook_diff(console: Console, state: Any) -> None:
    """Show diff for the active workbook."""
    workbook_id = getattr(state, "current_workbook_id", None)
    if workbook_id is None:
        console.print("  [dim]No active workbook. Use /workbook open <name> first.[/]\n")
        return

    vault_id = getattr(state, "current_vault_id", None)
    fb = await _ensure_forgebase(state)

    # Read workbook metadata
    uow = fb.uow_factory()
    async with uow:
        wb = await uow.workbooks.get(workbook_id)
        if wb is None:
            console.print(f"  [{RED}]Workbook not found.[/]\n")
            await uow.rollback()
            return

        # Count branch-local entities
        page_heads = await uow.workbooks.list_page_heads(workbook_id)
        claim_heads = await uow.workbooks.list_claim_heads(workbook_id)
        source_heads = await uow.workbooks.list_source_heads(workbook_id)
        tombstones = await uow.workbooks.list_tombstones(workbook_id)
        await uow.rollback()

    console.print()
    console.print(f"  [{CYAN}]Workbook:[/] {wb.name} ({workbook_id})")
    console.print(f"  Base revision: [{DIM}]{wb.base_revision_id}[/]")
    console.print()
    console.print(f"  Modified pages:    [{CYAN}]{len(page_heads)}[/]")
    console.print(f"  Modified claims:   [{CYAN}]{len(claim_heads)}[/]")
    console.print(f"  Modified sources:  [{CYAN}]{len(source_heads)}[/]")
    console.print(f"  Deleted entities:  [{CYAN}]{len(tombstones)}[/]")
    console.print()


async def _workbook_merge(console: Console, state: Any) -> None:
    """Propose and execute merge for the active workbook."""
    workbook_id = getattr(state, "current_workbook_id", None)
    if workbook_id is None:
        console.print("  [dim]No active workbook. Use /workbook open <name> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)

    console.print(f"  [dim]Proposing merge for workbook {workbook_id}...[/]")
    try:
        proposal = await fb.merge.propose_merge(workbook_id)
        n_conflicts = len(getattr(proposal, "conflicts", []))

        if n_conflicts > 0:
            console.print(
                f"  [{RED}]Merge has {n_conflicts} conflict(s). "
                f"Resolve them before merging.[/]\n"
            )
            return

        # Execute merge
        await fb.merge.execute_merge(proposal.proposal_id)
        state.current_workbook_id = None
        console.print(f"  [{GREEN}]Merge executed successfully.[/]")
        console.print(f"  [dim]Workbook merged into canonical. Active workbook cleared.[/]\n")
    except Exception as exc:
        console.print(f"  [{RED}]Merge failed: {exc}[/]\n")


async def _workbook_abandon(console: Console, state: Any) -> None:
    """Abandon the active workbook."""
    workbook_id = getattr(state, "current_workbook_id", None)
    if workbook_id is None:
        console.print("  [dim]No active workbook. Use /workbook open <name> first.[/]\n")
        return

    fb = await _ensure_forgebase(state)

    try:
        await fb.branches.abandon_workbook(workbook_id)
        state.current_workbook_id = None
        console.print(f"  [{GREEN}]Workbook abandoned.[/]")
        console.print(f"  [dim]Active workbook cleared.[/]\n")
    except Exception as exc:
        console.print(f"  [{RED}]Abandon failed: {exc}[/]\n")


# ---------------------------------------------------------------------------
# /export (ForgeBase vault export)
# ---------------------------------------------------------------------------

async def _cmd_fb_export(console: Console, state: Any, args: str) -> None:
    """Handle /export [markdown|obsidian] -- export current vault."""
    vault_id = getattr(state, "current_vault_id", None)
    if vault_id is None:
        console.print("  [dim]No active vault. Use /vault use <id> first.[/]\n")
        return

    format_name = args.strip().lower() or "markdown"
    if format_name not in ("markdown", "obsidian"):
        console.print(f"  [{RED}]Supported formats: markdown, obsidian[/]\n")
        return

    fb = await _ensure_forgebase(state)

    # Read vault
    uow = fb.uow_factory()
    async with uow:
        vault = await uow.vaults.get(vault_id)
        if vault is None:
            console.print(f"  [{RED}]Vault not found.[/]\n")
            await uow.rollback()
            return

        pages_data = await uow.pages.list_by_vault(vault_id)
        page_versions = []
        for page in pages_data:
            pv = await uow.pages.get_head_version(page.page_id)
            if pv is not None:
                page_versions.append((page, pv))
        await uow.rollback()

    # Build export
    output_dir = Path.cwd() / f"forgebase-export-{vault.name}"
    output_dir.mkdir(parents=True, exist_ok=True)

    for page, pv in page_versions:
        page_key = getattr(page, "page_key", str(page.page_id))
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in page_key)
        filename = f"{safe_name}.md"
        content = getattr(pv, "content_markdown", "") or getattr(pv, "body", "") or f"# {pv.title}\n"
        (output_dir / filename).write_text(content, encoding="utf-8")

    render_export_success(console, str(output_dir), format_name)


# ═══════════════════════════════════════════════════════════════════════════
# Click CLI subcommands (standalone, dispatched from main.py)
# ═══════════════════════════════════════════════════════════════════════════

import click


def _cli_forgebase_factory() -> tuple[Any, Any]:
    """Create a ForgeBase config + factory coroutine for CLI commands.

    Returns (ForgeBaseConfig, create_forgebase) — both lazy-imported.
    """
    from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase

    data_dir = Path.home() / ".hephaestus"
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg = ForgeBaseConfig(sqlite_path=str(data_dir / "forgebase.db"))
    return cfg, create_forgebase


@click.group(
    name="vault",
    help="Manage ForgeBase knowledge vaults.",
    invoke_without_command=True,
)
@click.pass_context
def vault_cmd(ctx: click.Context) -> None:
    """Manage ForgeBase knowledge vaults."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@vault_cmd.command(name="create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Vault description.")
def _cli_vault_create(name: str, description: str) -> None:
    """Create a new vault."""
    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            v = await fb.vaults.create_vault(name, description=description)
            click.echo(f"Vault created: {v.vault_id} ({v.name})")
        finally:
            await fb.close()

    asyncio.run(_run())


@vault_cmd.command(name="list")
def _cli_vault_list() -> None:
    """List all vaults."""
    from rich.console import Console as RichConsole

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            uow = fb.uow_factory()
            async with uow:
                vaults = await uow.vaults.list_all()
                await uow.rollback()
            console = RichConsole()
            render_vault_list(console, vaults)
        finally:
            await fb.close()

    asyncio.run(_run())


@vault_cmd.command(name="info")
@click.argument("vault_id")
def _cli_vault_info(vault_id: str) -> None:
    """Show vault details."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            vid = EntityId(vault_id)
            uow = fb.uow_factory()
            async with uow:
                v = await uow.vaults.get(vid)
                await uow.rollback()
            if v is None:
                click.echo(f"Vault not found: {vault_id}")
                return
            counts = await _vault_entity_counts(fb, vid)
            console = RichConsole()
            render_vault_info(console, v, **counts)
        finally:
            await fb.close()

    asyncio.run(_run())


@vault_cmd.command(name="compile")
@click.argument("vault_id")
def _cli_vault_compile(vault_id: str) -> None:
    """Compile a vault (run Tier 2 synthesis)."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            vid = EntityId(vault_id)
            manifest = await fb.vault_synthesizer.synthesize(vid)
            console = RichConsole()
            render_compile_result(console, manifest)
        finally:
            await fb.close()

    asyncio.run(_run())


@vault_cmd.command(name="lint")
@click.argument("vault_id")
def _cli_vault_lint(vault_id: str) -> None:
    """Lint a vault for quality issues."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            vid = EntityId(vault_id)
            report = await fb.lint_engine.run_lint(vid)
            console = RichConsole()
            render_lint_report(console, report)
        finally:
            await fb.close()

    asyncio.run(_run())


@vault_cmd.command(name="ingest")
@click.argument("vault_id")
@click.argument("source_path")
@click.option("--format", "fmt", default=None, help="Source format override.")
def _cli_vault_ingest(vault_id: str, source_path: str, fmt: str | None) -> None:
    """Ingest a source into a vault."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.enums import SourceFormat
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        try:
            vid = EntityId(vault_id)

            if fmt:
                src_format = SourceFormat(fmt)
            elif source_path.startswith(("http://", "https://")):
                src_format = SourceFormat.URL
            else:
                ext = Path(source_path).suffix.lower()
                format_map = {
                    ".pdf": SourceFormat.PDF,
                    ".md": SourceFormat.MARKDOWN,
                    ".csv": SourceFormat.CSV,
                    ".json": SourceFormat.JSON,
                }
                src_format = format_map.get(ext, SourceFormat.MARKDOWN)

            if source_path.startswith(("http://", "https://")):
                raw = source_path.encode("utf-8")
                title = source_path
            else:
                p = Path(source_path).expanduser()
                if not p.exists():
                    click.echo(f"File not found: {source_path}")
                    return
                raw = p.read_bytes()
                title = p.name

            source, version = await fb.ingest.ingest_source(
                vault_id=vid,
                raw_content=raw,
                format=src_format,
                title=title,
                origin_locator=source_path,
                idempotency_key=f"cli-ingest:{vid}:{source_path}",
            )
            console = RichConsole()
            render_ingest_result(console, source, version)
        finally:
            await fb.close()

    asyncio.run(_run())


# ── heph ask ─────────────────────────────────────────────────────────
@click.command(name="ask", help="Query within a vault's knowledge context.")
@click.argument("query")
@click.option("--vault", "vault_id", required=True, help="Vault ID to query.")
@click.option(
    "--scope",
    default="single",
    type=click.Choice(["single", "fused"], case_sensitive=False),
    help="Query scope.",
)
def ask_cmd(query: str, vault_id: str, scope: str) -> None:
    """Query within a vault's knowledge context."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        console = RichConsole()
        try:
            vid = EntityId(vault_id)
            if fb.context_assembler is not None:
                baseline, ctx_pack, dossier = await fb.context_assembler.assemble_all(vid)
                console.print(f"\n  [{GREEN}]Context assembled[/] for vault [{CYAN}]{vault_id}[/]")
                if hasattr(baseline, "entries") and baseline.entries:
                    console.print(f"  Prior art entries: [{CYAN}]{len(baseline.entries)}[/]")
                if hasattr(ctx_pack, "entries") and ctx_pack.entries:
                    console.print(f"  Domain context entries: [{CYAN}]{len(ctx_pack.entries)}[/]")
                console.print(f"\n  [{CYAN}]Query:[/] {query}")
                console.print(
                    f"  [dim]Use this context with the full pipeline via: "
                    f"heph \"<problem>\"[/]\n"
                )
            else:
                console.print("  [dim]No context assembler available.[/]\n")
        finally:
            await fb.close()

    asyncio.run(_run())


# ── heph fuse ────────────────────────────────────────────────────────
@click.command(name="fuse", help="Cross-vault fusion between two or more vaults.")
@click.argument("vault_ids", nargs=-1, required=True)
@click.option("--problem", default=None, help="Problem statement for guided fusion.")
@click.option(
    "--mode",
    default="strict",
    type=click.Choice(["strict", "exploratory"], case_sensitive=False),
    help="Fusion mode.",
)
def fuse_cmd(vault_ids: tuple[str, ...], problem: str | None, mode: str) -> None:
    """Cross-vault fusion between two or more vaults."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.contracts.fusion import FusionRequest
    from hephaestus.forgebase.domain.enums import FusionMode
    from hephaestus.forgebase.domain.values import EntityId

    if len(vault_ids) < 2:
        click.echo("Fusion requires at least 2 vault IDs.")
        return

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        console = RichConsole()
        try:
            vids = [EntityId(v) for v in vault_ids]
            fm = FusionMode.EXPLORATORY if mode == "exploratory" else FusionMode.STRICT
            request = FusionRequest(
                vault_ids=vids,
                problem=problem,
                fusion_mode=fm,
            )
            result = await fb.fusion.fuse(request)
            render_fusion_result(console, result)
        finally:
            await fb.close()

    asyncio.run(_run())


# ── heph export (forgebase vault export) ─────────────────────────────
@click.command(
    name="fb-export",
    help="Export a vault's pages to markdown or Obsidian format.",
)
@click.argument("vault_id")
@click.option(
    "--format",
    "fmt",
    default="markdown",
    type=click.Choice(["markdown", "obsidian"], case_sensitive=False),
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Output directory.")
def fb_export_cmd(vault_id: str, fmt: str, output: str | None) -> None:
    """Export a vault's pages to markdown or Obsidian format."""
    from rich.console import Console as RichConsole
    from hephaestus.forgebase.domain.values import EntityId

    cfg, create_fb = _cli_forgebase_factory()

    async def _run() -> None:
        fb = await create_fb(cfg)
        console = RichConsole()
        try:
            vid = EntityId(vault_id)
            uow = fb.uow_factory()
            async with uow:
                vault = await uow.vaults.get(vid)
                if vault is None:
                    click.echo(f"Vault not found: {vault_id}")
                    await uow.rollback()
                    return
                pages_data = await uow.pages.list_by_vault(vid)
                page_versions = []
                for page in pages_data:
                    pv = await uow.pages.get_head_version(page.page_id)
                    if pv is not None:
                        page_versions.append((page, pv))
                await uow.rollback()

            out_dir = Path(output) if output else Path.cwd() / f"forgebase-export-{vault.name}"
            out_dir.mkdir(parents=True, exist_ok=True)

            for page, pv in page_versions:
                page_key = getattr(page, "page_key", str(page.page_id))
                safe_name = "".join(
                    c if c.isalnum() or c in "-_ " else "_" for c in page_key
                )
                filename = f"{safe_name}.md"
                content = (
                    getattr(pv, "content_markdown", "")
                    or getattr(pv, "body", "")
                    or f"# {pv.title}\n"
                )
                (out_dir / filename).write_text(content, encoding="utf-8")

            render_export_success(console, str(out_dir), fmt)
        finally:
            await fb.close()

    asyncio.run(_run())
