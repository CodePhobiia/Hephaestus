"""Reporter handler — produces final output artifacts.

Reads vault state and renders markdown reports, summaries,
and briefing packs from vault content. The reporter creates
pages of type CONCEPT containing the generated reports.
All work happens on the task's workbook branch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus
from hephaestus.forgebase.domain.enums import PageType

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)


async def execute_reporter(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a reporter task: produce a summary report from vault content.

    Steps:
    1. Read all pages in the vault (concept pages and source cards)
    2. Read claims and their statuses
    3. Generate a markdown report summarizing the vault knowledge
    4. Persist the report as a page in the workbook

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        uow = forgebase.uow_factory()
        sections: list[str] = []
        concept_count = 0
        source_count = 0
        claim_count = 0

        async with uow:
            # Gather vault metadata
            vault = await uow.vaults.get(task.vault_id)
            vault_name = vault.name if vault else "Unknown Vault"

            # Count entities
            all_pages = await uow.pages.list_by_vault(task.vault_id)
            concept_titles: list[str] = []
            source_titles: list[str] = []

            for page in all_pages:
                head = await uow.pages.get_head_version(page.page_id)
                if head is None:
                    continue
                if page.page_type == PageType.CONCEPT:
                    concept_count += 1
                    concept_titles.append(head.title)
                elif page.page_type == PageType.SOURCE_CARD:
                    source_count += 1
                    source_titles.append(head.title)

            # Count claims
            all_claims = await uow.claims.list_by_vault(task.vault_id)
            claim_count = len(all_claims)

            # Count links
            all_links = await uow.links.list_by_vault(task.vault_id)
            link_count = len(all_links)

            await uow.rollback()

        # Build the report
        sections.append(f"# Knowledge Report: {vault_name}")
        sections.append("")
        sections.append(f"**Objective:** {task.objective}")
        sections.append("")
        sections.append("## Summary Statistics")
        sections.append("")
        sections.append(f"- **Concept pages:** {concept_count}")
        sections.append(f"- **Source cards:** {source_count}")
        sections.append(f"- **Claims:** {claim_count}")
        sections.append(f"- **Links:** {link_count}")
        sections.append("")

        if concept_titles:
            sections.append("## Concepts")
            sections.append("")
            for title in sorted(concept_titles):
                sections.append(f"- {title}")
            sections.append("")

        if source_titles:
            sections.append("## Sources")
            sections.append("")
            for title in sorted(source_titles):
                sections.append(f"- {title}")
            sections.append("")

        report_content = "\n".join(sections)

        # Persist report as a page
        page, _version = await forgebase.pages.create_page(
            vault_id=task.vault_id,
            page_key=f"reports/{task.task_id}",
            page_type=PageType.CONCEPT,
            title=f"Report: {task.objective[:60]}",
            content=report_content.encode("utf-8"),
            workbook_id=task.workbook_id,
            summary=f"Auto-generated report: {task.objective}",
        )
        task.artifacts_created.append(page.page_id)

        logger.info(
            "Reporter generated report with %d concepts, %d sources for vault=%s",
            concept_count,
            source_count,
            task.vault_id,
        )

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Reporter task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
