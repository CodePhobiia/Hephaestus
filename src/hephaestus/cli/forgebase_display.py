"""Rich display rendering for ForgeBase CLI/REPL commands.

Provides structured Rich output for:
- Vault info panels (name, health score, page/claim/source counts)
- Lint report tables (category, severity, count, debt score)
- Fusion result display (bridge concepts, transfer opportunities, confidence bars)
- Compile progress feedback
- Workbook diff display
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hephaestus.cli.display import AMBER, CYAN, CYAN_BOLD, DIM, GOLD, GREEN, RED

# ---------------------------------------------------------------------------
# Vault info
# ---------------------------------------------------------------------------


def render_vault_info(
    console: Console,
    vault: Any,
    *,
    page_count: int = 0,
    claim_count: int = 0,
    source_count: int = 0,
    link_count: int = 0,
    workbook_count: int = 0,
) -> None:
    """Render a vault info panel with entity counts."""
    table = Table(box=box.ROUNDED, border_style="yellow", show_header=False, padding=(0, 2))
    table.add_column("Key", style=DIM, no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Vault ID", f"[{CYAN}]{vault.vault_id}[/]")
    table.add_row("Name", f"[{CYAN_BOLD}]{vault.name}[/]")
    table.add_row("Description", vault.description or "[dim]none[/]")
    table.add_row("Head Revision", f"[{DIM}]{vault.head_revision_id}[/]")
    table.add_row(
        "Created",
        vault.created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(vault.created_at, datetime) else str(vault.created_at),
    )
    table.add_section()
    table.add_row("Pages", f"[{CYAN}]{page_count}[/]")
    table.add_row("Claims", f"[{CYAN}]{claim_count}[/]")
    table.add_row("Sources", f"[{CYAN}]{source_count}[/]")
    table.add_row("Links", f"[{CYAN}]{link_count}[/]")
    table.add_row("Workbooks", f"[{CYAN}]{workbook_count}[/]")

    console.print()
    console.print(Panel(table, title=f"[bold yellow]Vault: {vault.name}[/]", border_style="yellow"))
    console.print()


def render_vault_list(console: Console, vaults: list[Any]) -> None:
    """Render a table listing all vaults."""
    if not vaults:
        console.print("  [dim]No vaults found. Use /vault create <name> to create one.[/]\n")
        return

    table = Table(
        title="ForgeBase Vaults",
        box=box.SIMPLE_HEAD,
        border_style="yellow",
        padding=(0, 2),
    )
    table.add_column("ID", style=DIM, no_wrap=True, max_width=30)
    table.add_column("Name", style=CYAN_BOLD)
    table.add_column("Description", style="white", max_width=40)
    table.add_column("Created", style=DIM)

    for v in vaults:
        created = (
            v.created_at.strftime("%Y-%m-%d %H:%M")
            if isinstance(v.created_at, datetime)
            else str(v.created_at)
        )
        table.add_row(
            str(v.vault_id),
            v.name,
            v.description or "-",
            created,
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Lint report
# ---------------------------------------------------------------------------


def render_lint_report(console: Console, report: Any) -> None:
    """Render a lint report with findings breakdown."""
    console.print()

    # Summary line
    debt_color = GREEN if report.debt_score < 10 else (AMBER if report.debt_score < 50 else RED)
    console.print(
        f"  Lint complete: [{CYAN}]{report.finding_count}[/] findings, "
        f"debt score [{debt_color}]{report.debt_score:.1f}[/]"
    )

    # By category
    if report.findings_by_category:
        cat_table = Table(
            title="Findings by Category",
            box=box.SIMPLE_HEAD,
            border_style="yellow",
            padding=(0, 2),
        )
        cat_table.add_column("Category", style=AMBER)
        cat_table.add_column("Count", justify="right", style="white")

        for cat, count in sorted(report.findings_by_category.items()):
            cat_table.add_row(cat, str(count))

        console.print()
        console.print(cat_table)

    # By severity
    if report.findings_by_severity:
        sev_table = Table(
            title="Findings by Severity",
            box=box.SIMPLE_HEAD,
            border_style="yellow",
            padding=(0, 2),
        )
        sev_table.add_column("Severity", style=AMBER)
        sev_table.add_column("Count", justify="right", style="white")

        severity_order = ["critical", "error", "warning", "info"]
        for sev in severity_order:
            if sev in report.findings_by_severity:
                color = RED if sev in ("critical", "error") else (AMBER if sev == "warning" else DIM)
                sev_table.add_row(f"[{color}]{sev}[/]", str(report.findings_by_severity[sev]))

        # Add any remaining severities not in the predefined order
        for sev, count in sorted(report.findings_by_severity.items()):
            if sev not in severity_order:
                sev_table.add_row(sev, str(count))

        console.print()
        console.print(sev_table)

    console.print()


# ---------------------------------------------------------------------------
# Fusion result
# ---------------------------------------------------------------------------


def render_fusion_result(console: Console, result: Any) -> None:
    """Render a fusion result with bridge concepts and transfer opportunities."""
    console.print()

    # Header
    n_vaults = len(result.request.vault_ids)
    n_bridges = len(result.bridge_concepts)
    n_transfers = len(result.transfer_opportunities)
    console.print(
        f"  Fusion complete: [{CYAN}]{n_vaults}[/] vaults, "
        f"[{CYAN}]{n_bridges}[/] bridge concepts, "
        f"[{CYAN}]{n_transfers}[/] transfer opportunities"
    )

    # Bridge concepts table
    if result.bridge_concepts:
        bridge_table = Table(
            title="Bridge Concepts",
            box=box.SIMPLE_HEAD,
            border_style="yellow",
            padding=(0, 2),
        )
        bridge_table.add_column("Bridge", style=CYAN_BOLD, max_width=30)
        bridge_table.add_column("Left Structure", style="white", max_width=25)
        bridge_table.add_column("Right Structure", style="white", max_width=25)
        bridge_table.add_column("Confidence", justify="right", style=AMBER)

        for m in result.bridge_concepts[:10]:
            conf = f"{m.confidence:.2f}" if hasattr(m, "confidence") else "-"
            bridge_table.add_row(
                getattr(m, "bridge_concept", "?"),
                getattr(m, "left_structure", "?"),
                getattr(m, "right_structure", "?"),
                conf,
            )

        console.print()
        console.print(bridge_table)

    # Transfer opportunities table
    if result.transfer_opportunities:
        xfer_table = Table(
            title="Transfer Opportunities",
            box=box.SIMPLE_HEAD,
            border_style="yellow",
            padding=(0, 2),
        )
        xfer_table.add_column("Mechanism", style=CYAN_BOLD, max_width=30)
        xfer_table.add_column("Rationale", style="white", max_width=40)
        xfer_table.add_column("Confidence", justify="right", style=AMBER)
        xfer_table.add_column("Caveats", justify="right", style=DIM)

        for t in result.transfer_opportunities[:10]:
            conf = f"{t.confidence:.2f}" if hasattr(t, "confidence") else "-"
            n_caveats = len(t.caveats) if hasattr(t, "caveats") else 0
            xfer_table.add_row(
                getattr(t, "mechanism", "?"),
                getattr(t, "rationale", "?"),
                conf,
                str(n_caveats),
            )

        console.print()
        console.print(xfer_table)

    # Pair results summary
    if result.pair_results:
        pair_table = Table(
            title="Pair Results",
            box=box.SIMPLE_HEAD,
            border_style="yellow",
            padding=(0, 2),
        )
        pair_table.add_column("Left Vault", style=DIM, max_width=20)
        pair_table.add_column("Right Vault", style=DIM, max_width=20)
        pair_table.add_column("Candidates", justify="right", style="white")
        pair_table.add_column("Maps", justify="right", style=CYAN)
        pair_table.add_column("Transfers", justify="right", style=GREEN)

        for pr in result.pair_results:
            pair_table.add_row(
                str(pr.left_vault_id),
                str(pr.right_vault_id),
                str(pr.candidates_generated),
                str(len(pr.maps_produced)),
                str(len(pr.transfers_produced)),
            )

        console.print()
        console.print(pair_table)

    console.print()


# ---------------------------------------------------------------------------
# Compile progress
# ---------------------------------------------------------------------------


def render_compile_result(console: Console, manifest: Any) -> None:
    """Render compilation result summary."""
    console.print()

    if hasattr(manifest, "source_id"):
        # SourceCompileManifest (Tier 1)
        console.print(f"  [{GREEN}]Compilation complete[/] (source: {manifest.source_id})")
        if hasattr(manifest, "claim_count"):
            console.print(f"  Claims extracted: [{CYAN}]{manifest.claim_count}[/]")
        if hasattr(manifest, "concept_count"):
            console.print(f"  Concepts found: [{CYAN}]{manifest.concept_count}[/]")
    else:
        # VaultSynthesisManifest (Tier 2)
        console.print(f"  [{GREEN}]Vault synthesis complete[/]")
        if hasattr(manifest, "pages_created"):
            console.print(f"  Pages created: [{CYAN}]{manifest.pages_created}[/]")
        if hasattr(manifest, "claims_created"):
            console.print(f"  Claims synthesized: [{CYAN}]{manifest.claims_created}[/]")
        if hasattr(manifest, "open_questions"):
            console.print(f"  Open questions: [{CYAN}]{len(manifest.open_questions)}[/]")

    console.print()


# ---------------------------------------------------------------------------
# Workbook display
# ---------------------------------------------------------------------------


def render_workbook_list(console: Console, workbooks: list[Any]) -> None:
    """Render a table listing workbooks (branches)."""
    if not workbooks:
        console.print("  [dim]No workbooks in this vault.[/]\n")
        return

    table = Table(
        title="Workbooks",
        box=box.SIMPLE_HEAD,
        border_style="yellow",
        padding=(0, 2),
    )
    table.add_column("ID", style=DIM, no_wrap=True, max_width=30)
    table.add_column("Name", style=CYAN_BOLD)
    table.add_column("Purpose", style="white")
    table.add_column("Status", style=AMBER)
    table.add_column("Created", style=DIM)

    for wb in workbooks:
        status_color = GREEN if str(wb.status) == "open" or str(getattr(wb.status, "value", wb.status)) == "open" else DIM
        status_val = getattr(wb.status, "value", str(wb.status))
        purpose_val = getattr(wb.purpose, "value", str(wb.purpose))
        created = (
            wb.created_at.strftime("%Y-%m-%d %H:%M")
            if isinstance(wb.created_at, datetime)
            else str(wb.created_at)
        )
        table.add_row(
            str(wb.workbook_id),
            wb.name,
            purpose_val,
            f"[{status_color}]{status_val}[/]",
            created,
        )

    console.print()
    console.print(table)
    console.print()


def render_ingest_result(
    console: Console,
    source: Any,
    version: Any,
) -> None:
    """Render source ingestion result."""
    console.print()
    console.print(f"  [{GREEN}]Source ingested[/]")
    console.print(f"  Source ID: [{CYAN}]{source.source_id}[/]")
    console.print(f"  Title: [{CYAN}]{version.title or '(untitled)'}[/]")
    console.print(f"  Format: [{CYAN}]{getattr(source.format, 'value', source.format)}[/]")
    console.print(f"  Trust tier: [{CYAN}]{getattr(version.trust_tier, 'value', version.trust_tier)}[/]")
    console.print()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def render_export_success(console: Console, path: str, format_name: str) -> None:
    """Render export success message."""
    console.print(f"  [{GREEN}]Exported[/] vault as [{CYAN}]{format_name}[/] to [{CYAN}]{path}[/]\n")
