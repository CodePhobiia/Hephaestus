"""ResearchAdapter — translates Perplexity / Research outputs into ForgeBase sources.

The adapter accepts ``artifacts: list[Any]`` to avoid importing Research
types and creating circular dependencies.  It is resilient to missing fields.

After ingesting each source, the adapter schedules a durable Tier 1
compilation job as follow-on work (if a CompileService is available).
Research outputs become Flow A eligible only after ingest + Tier 1/Tier 2
processing.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from hephaestus.forgebase.domain.enums import EntityKind, SourceFormat
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService

if TYPE_CHECKING:
    from hephaestus.forgebase.service.compile_service import CompileService

logger = logging.getLogger(__name__)


def _safe_bytes(value: Any) -> bytes:
    """Coerce a value to bytes for ingestion."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    try:
        return json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return str(value).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """Short hex digest for idempotency keys."""
    return hashlib.sha256(data).hexdigest()[:16]


class ResearchAdapter:
    """Translates Perplexity / Research outputs into ForgeBase sources.

    Workflow on ``handle_research_completed``:
      1. ``attach_run`` to record the research run.
      2. For each artifact: ``ingest_source`` with idempotency.
      3. ``record_artifact`` for each created entity.
      4. Schedule durable Tier 1 compilation job for each ingested source (NEW).
      5. Track follow-on job references in the run record.

    When no CompileService is provided, step 4 is skipped and the follow-on
    intent is noted in the sync metadata instead.

    On failure: update ``sync_status`` to ``"failed"`` and re-raise.
    """

    def __init__(
        self,
        run_integration_service: RunIntegrationService,
        ingest_service: IngestService,
        uow_factory: Callable[[], AbstractUnitOfWork],
        *,
        compile_service: CompileService | None = None,
    ) -> None:
        self._run_svc = run_integration_service
        self._ingest_svc = ingest_service
        self._uow_factory = uow_factory
        self._compile_svc = compile_service

    async def handle_research_completed(
        self,
        vault_id: EntityId,
        run_id: str,
        artifacts: list[Any],
    ) -> None:
        """Called by the bridge when a Research run completes with a vault_id."""
        ref = await self._run_svc.attach_run(
            vault_id=vault_id,
            run_id=run_id,
            run_type="research",
            upstream_system="ResearchArtifactStore",
        )

        try:
            follow_on_jobs: list[EntityId] = []

            for i, artifact in enumerate(artifacts):
                name, content, url = _extract_research_item(artifact, i)
                raw = _safe_bytes(content)
                content_hash = _content_hash(raw)
                idempotency_key = f"{run_id}:research:{name}:{content_hash}"

                source, _version = await self._ingest_svc.ingest_source(
                    vault_id=vault_id,
                    raw_content=raw,
                    format=SourceFormat.HEPH_OUTPUT,
                    title=name,
                    url=url,
                    idempotency_key=idempotency_key,
                    metadata={
                        "research_run_id": run_id,
                        "artifact_index": i,
                        "artifact_name": name,
                    },
                )

                await self._run_svc.record_artifact(
                    ref_id=ref.ref_id,
                    entity_kind=EntityKind.SOURCE,
                    entity_id=source.source_id,
                    role="research_output",
                    idempotency_key=idempotency_key,
                )

                # Schedule durable Tier 1 compilation as follow-on work
                if self._compile_svc is not None:
                    compile_idem_key = (
                        f"{run_id}:research:compile:{name}:{content_hash}"
                    )
                    job = await self._compile_svc.schedule_compile(
                        vault_id=vault_id,
                        config={
                            "source_id": str(source.source_id),
                            "follow_on_from": run_id,
                            "artifact_name": name,
                        },
                        idempotency_key=compile_idem_key,
                    )
                    follow_on_jobs.append(job.job_id)

            # If we had follow-on jobs, update sync metadata to note them
            if follow_on_jobs:
                await self._update_sync_metadata(
                    ref.ref_id,
                    "synced",
                    follow_on_job_ids=[str(j) for j in follow_on_jobs],
                )
            else:
                await self._update_sync_status(ref.ref_id, "synced")

        except Exception:
            await self._update_sync_status(ref.ref_id, "failed")
            raise

    async def _update_sync_status(
        self, ref_id: EntityId, status: str
    ) -> None:
        """Update sync_status on the KnowledgeRunRef via a fresh UoW."""
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.run_refs.update_sync_status(ref_id, status)
                await uow.commit()
        except Exception:
            logger.exception(
                "Failed to update sync_status to %r for ref_id=%s", status, ref_id,
            )

    async def _update_sync_metadata(
        self,
        ref_id: EntityId,
        status: str,
        follow_on_job_ids: list[str],
    ) -> None:
        """Update sync_status and record follow-on job references.

        The follow-on job IDs are stored so that downstream consumers can
        track when the sources become fully processed (post Tier 1 compilation).
        """
        try:
            uow = self._uow_factory()
            async with uow:
                await uow.run_refs.update_sync_status(ref_id, status)
                # Record each follow-on job as a run artifact so the relationship
                # between the research run and its compilation jobs is durable.
                for job_id_str in follow_on_job_ids:
                    job_id = EntityId(job_id_str)
                    idem_key = f"{str(ref_id)}:followon:{job_id_str}"
                    # Use the run_artifacts repo directly since we're already
                    # inside a UoW — no need to go through the service layer.
                    from hephaestus.forgebase.domain.models import KnowledgeRunArtifact
                    existing = await uow.run_artifacts.list_by_ref(ref_id)
                    already_exists = any(
                        a.entity_id == job_id and a.role == "follow_on_compile"
                        for a in existing
                    )
                    if not already_exists:
                        artifact = KnowledgeRunArtifact(
                            ref_id=ref_id,
                            entity_kind=EntityKind.PAGE,  # closest fit for job refs
                            entity_id=job_id,
                            role="follow_on_compile",
                        )
                        await uow.run_artifacts.create(artifact)
                await uow.commit()
        except Exception:
            logger.exception(
                "Failed to update sync metadata for ref_id=%s", ref_id,
            )
            # Fall back to simple status update
            await self._update_sync_status(ref_id, status)


def _extract_research_item(
    artifact: Any, index: int
) -> tuple[str, Any, str | None]:
    """Extract (name, content, url) from a single research artifact.

    Supports:
      - dict with ``name``/``content``/``url`` keys
      - object with matching attributes
      - plain string (used as content directly)
    """
    if isinstance(artifact, dict):
        name = str(artifact.get("name", f"research_{index}"))
        content = artifact.get("content", artifact.get("data", artifact.get("text", "")))
        url = artifact.get("url") or artifact.get("source_url")
        return name, content, url

    if isinstance(artifact, str):
        return f"research_{index}", artifact, None

    # Object-style
    name = str(getattr(artifact, "name", f"research_{index}"))
    content = getattr(
        artifact, "content", getattr(artifact, "data", getattr(artifact, "text", str(artifact)))
    )
    url = getattr(artifact, "url", None) or getattr(artifact, "source_url", None)
    return name, content, url
