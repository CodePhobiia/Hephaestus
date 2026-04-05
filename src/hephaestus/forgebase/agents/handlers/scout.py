"""Scout handler — finds and ingests missing sources.

Uses ResearchAugmentor to discover sources and IngestService to
schedule ingestion into the vault workbook.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus
from hephaestus.forgebase.domain.enums import SourceFormat

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)


async def execute_scout(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a scout task: discover missing sources and ingest them.

    The scout reads the task objective as the research query, calls
    ResearchAugmentor.find_supporting_evidence() to discover relevant
    sources, then ingests each discovered source into the workbook.

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        # Parse evidence gaps from constraints, default to objective
        evidence_gaps = task.constraints if task.constraints else [task.objective]

        # Use the research augmentor (wired via research_job.augmentor
        # or directly via the factory). The augmentor is on research_job.
        augmentor = forgebase.research_job._augmentor

        discovered = await augmentor.find_supporting_evidence(
            concept=task.objective,
            evidence_gaps=evidence_gaps,
        )

        logger.info(
            "Scout discovered %d sources for vault=%s workbook=%s",
            len(discovered),
            task.vault_id,
            task.workbook_id,
        )

        # Ingest each discovered source into the workbook
        for source in discovered:
            content_text = f"# {source.title}\n\n{source.summary}"
            if source.url:
                content_text += f"\n\nSource URL: {source.url}"

            src, _version = await forgebase.ingest.ingest_source(
                vault_id=task.vault_id,
                raw_content=content_text.encode("utf-8"),
                format=SourceFormat.MARKDOWN,
                title=source.title,
                url=source.url or None,
                workbook_id=task.workbook_id,
            )
            task.artifacts_created.append(src.source_id)

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Scout task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
