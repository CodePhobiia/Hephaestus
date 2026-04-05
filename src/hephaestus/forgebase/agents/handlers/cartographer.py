"""Cartographer handler — builds links, indexes, and concept maps.

Creates RELATED_CONCEPT links, backlinks, and source indexes
by querying existing pages and finding relationships between them.
All work happens on the task's workbook branch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus
from hephaestus.forgebase.domain.enums import LinkKind, PageType
from hephaestus.forgebase.domain.values import EntityId

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)


async def execute_cartographer(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a cartographer task: build links and indexes.

    Steps:
    1. Read all pages in the vault (concept pages and source cards)
    2. For each pair of concept pages without a RELATED_CONCEPT link, create one
    3. Create a source index page listing all sources
    4. Create backlinks from concept pages to their sources

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        uow = forgebase.uow_factory()
        concept_pages: list[tuple[EntityId, str]] = []  # (page_id, page_key)
        source_pages: list[tuple[EntityId, str]] = []
        existing_link_pairs: set[tuple[str, str]] = set()

        async with uow:
            # Gather concept pages and source cards
            all_pages = await uow.pages.list_by_vault(task.vault_id)
            for page in all_pages:
                head = await uow.pages.get_head_version(page.page_id)
                if head is None:
                    continue
                if page.page_type == PageType.CONCEPT:
                    concept_pages.append((page.page_id, page.page_key))
                elif page.page_type == PageType.SOURCE_CARD:
                    source_pages.append((page.page_id, page.page_key))

            # Gather existing RELATED_CONCEPT links to avoid duplicates
            all_links = await uow.links.list_by_vault(task.vault_id)
            for link in all_links:
                if link.kind == LinkKind.RELATED_CONCEPT:
                    head = await uow.links.get_head_version(link.link_id)
                    if head is not None:
                        pair = (str(head.source_entity), str(head.target_entity))
                        existing_link_pairs.add(pair)
                        # Also add reverse
                        existing_link_pairs.add((pair[1], pair[0]))

            await uow.rollback()

        # Create RELATED_CONCEPT links between concept pages
        links_created = 0
        for i, (page_a_id, _key_a) in enumerate(concept_pages):
            for page_b_id, _key_b in concept_pages[i + 1 :]:
                pair = (str(page_a_id), str(page_b_id))
                if pair in existing_link_pairs:
                    continue

                link, _version = await forgebase.links.create_link(
                    vault_id=task.vault_id,
                    kind=LinkKind.RELATED_CONCEPT,
                    source_entity=page_a_id,
                    target_entity=page_b_id,
                    label="related_concept",
                    weight=0.5,
                    workbook_id=task.workbook_id,
                )
                task.artifacts_created.append(link.link_id)
                links_created += 1

        # Create source index page if there are source cards
        if source_pages:
            index_lines = ["# Source Index", ""]
            for _page_id, page_key in sorted(source_pages, key=lambda x: x[1]):
                index_lines.append(f"- [{page_key}]({page_key})")
            index_lines.append("")

            page, _version = await forgebase.pages.create_page(
                vault_id=task.vault_id,
                page_key="indexes/source-index",
                page_type=PageType.SOURCE_INDEX,
                title="Source Index",
                content="\n".join(index_lines).encode("utf-8"),
                workbook_id=task.workbook_id,
                summary="Auto-generated index of all ingested sources",
            )
            task.artifacts_created.append(page.page_id)

        logger.info(
            "Cartographer created %d links, %d index pages for vault=%s workbook=%s",
            links_created,
            1 if source_pages else 0,
            task.vault_id,
            task.workbook_id,
        )

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Cartographer task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
