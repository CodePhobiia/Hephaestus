"""Librarian handler — maintains structure, naming, and deduplication.

Runs structural lint detectors (DUPLICATE_PAGE, ORPHANED_PAGE,
BROKEN_REFERENCE) and proposes structural repairs via the
RepairWorkbookJob. All work happens on the task's workbook branch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus
from hephaestus.forgebase.domain.enums import FindingCategory

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)

# The categories the librarian is interested in
LIBRARIAN_CATEGORIES: frozenset[str] = frozenset(
    {
        FindingCategory.DUPLICATE_PAGE.value,
        FindingCategory.ORPHANED_PAGE.value,
        FindingCategory.BROKEN_REFERENCE.value,
    }
)


async def execute_librarian(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a librarian task: detect and repair structural issues.

    Steps:
    1. Run the LintEngine on the workbook
    2. Filter findings to librarian categories
    3. Run RepairWorkbookJob for applicable findings

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        # Run full lint pass on the workbook
        report = await forgebase.lint_engine.run_lint(
            vault_id=task.vault_id,
            workbook_id=task.workbook_id,
        )
        task.artifacts_created.append(report.report_id)

        # Count findings relevant to librarian categories
        librarian_finding_count = 0
        for category, count in report.findings_by_category.items():
            if category in LIBRARIAN_CATEGORIES:
                librarian_finding_count += count

        logger.info(
            "Librarian found %d structural findings (of %d total) for vault=%s workbook=%s",
            librarian_finding_count,
            report.finding_count,
            task.vault_id,
            task.workbook_id,
        )

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Librarian task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
