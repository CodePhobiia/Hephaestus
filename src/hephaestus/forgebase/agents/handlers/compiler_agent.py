"""Compiler handler — writes or updates pages via Tier 1 / Tier 2 compilation.

Delegates to SourceCompiler (per-source extraction) and VaultSynthesizer
(vault-wide synthesis). All work happens on the task's workbook branch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hephaestus.forgebase.contracts.agent import AgentTask, TaskStatus

if TYPE_CHECKING:
    from hephaestus.forgebase.factory import ForgeBase

logger = logging.getLogger(__name__)


async def execute_compiler(forgebase: ForgeBase, task: AgentTask) -> AgentTask:
    """Execute a compiler task: run Tier 1 on un-compiled sources, then Tier 2.

    Steps:
    1. List sources on the workbook that are in NORMALIZED status
    2. Run SourceCompiler.compile_source() for each (Tier 1)
    3. Run VaultSynthesizer.synthesize() for vault-wide synthesis (Tier 2)

    All work happens on ``task.workbook_id`` -- never on canonical.
    """
    task.status = TaskStatus.RUNNING

    try:
        # Read sources visible on the workbook
        uow = forgebase.uow_factory()
        source_ids_to_compile: list[tuple] = []  # (source_id, version)
        seen_source_ids: set[str] = set()

        async with uow:
            # Get sources from the workbook's branch heads
            source_heads = await uow.workbooks.list_source_heads(task.workbook_id)
            for sh in source_heads:
                src_ver = await uow.sources.get_version(sh.source_id, sh.head_version)
                if src_ver is not None and src_ver.normalized_ref is not None:
                    source_ids_to_compile.append((sh.source_id, sh.head_version))
                    seen_source_ids.add(str(sh.source_id))

            # Also check vault-level sources that are normalized
            all_sources = await uow.sources.list_by_vault(task.vault_id)
            for source in all_sources:
                if str(source.source_id) in seen_source_ids:
                    continue
                head_ver = await uow.sources.get_head_version(source.source_id)
                if head_ver is not None and head_ver.normalized_ref is not None:
                    source_ids_to_compile.append((source.source_id, head_ver.version))

            await uow.rollback()  # read-only pass

        # Tier 1: compile each source
        compiled_count = 0
        for source_id, source_version in source_ids_to_compile:
            try:
                manifest = await forgebase.source_compiler.compile_source(
                    source_id=source_id,
                    source_version=source_version,
                    vault_id=task.vault_id,
                    workbook_id=task.workbook_id,
                )
                task.artifacts_created.append(manifest.manifest_id)
                compiled_count += 1
            except Exception as exc:
                logger.warning(
                    "Tier 1 compile failed for source %s: %s",
                    source_id,
                    exc,
                )

        # Tier 2: vault-wide synthesis
        try:
            synth_manifest = await forgebase.vault_synthesizer.synthesize(
                vault_id=task.vault_id,
                workbook_id=task.workbook_id,
            )
            task.artifacts_created.append(synth_manifest.manifest_id)
        except Exception as exc:
            logger.warning("Tier 2 synthesis failed: %s", exc)

        logger.info(
            "Compiler compiled %d sources for vault=%s workbook=%s",
            compiled_count,
            task.vault_id,
            task.workbook_id,
        )

        task.status = TaskStatus.COMPLETED

    except Exception as exc:
        logger.error("Compiler task %s failed: %s", task.task_id, exc)
        task.status = TaskStatus.FAILED
        task.error = str(exc)

    return task
