"""Skeptic handler — finds contradictions and unsupported claims.

Runs targeted lint detectors focused on CONTRADICTORY_CLAIM,
UNSUPPORTED_CLAIM, and SOURCE_GAP finding categories.
All work happens on the task's workbook branch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus
from hephaestus.forgebase.domain.enums import FindingCategory

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)

# The categories the skeptic is interested in
SKEPTIC_CATEGORIES: frozenset[str] = frozenset(
    {
        FindingCategory.CONTRADICTORY_CLAIM.value,
        FindingCategory.UNSUPPORTED_CLAIM.value,
        FindingCategory.SOURCE_GAP.value,
    }
)


async def execute_skeptic(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a skeptic task: find contradictions and unsupported claims.

    Runs the LintEngine on the workbook and collects findings
    matching the skeptic's categories of interest.

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        # Run full lint pass on the workbook
        report = await forgebase.lint_engine.run_lint(
            vault_id=task.vault_id,
            workbook_id=task.workbook_id,
        )

        # Record the report as an artifact
        task.artifacts_created.append(report.report_id)

        # Count findings relevant to skeptic categories
        skeptic_finding_count = 0
        for category, count in report.findings_by_category.items():
            if category in SKEPTIC_CATEGORIES:
                skeptic_finding_count += count

        logger.info(
            "Skeptic found %d relevant findings (of %d total) for vault=%s workbook=%s",
            skeptic_finding_count,
            report.finding_count,
            task.vault_id,
            task.workbook_id,
        )

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Skeptic task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
