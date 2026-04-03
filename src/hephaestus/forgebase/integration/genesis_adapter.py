"""GenesisAdapter — translates Genesis pipeline outputs into ForgeBase artifacts.

The adapter accepts ``report: Any`` to avoid importing Genesis types and
creating circular dependencies.  It is resilient to missing fields on
the report object.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from hephaestus.forgebase.domain.enums import EntityKind, SourceFormat
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.ingest_service import IngestService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService

logger = logging.getLogger(__name__)


def _safe_bytes(value: Any) -> bytes:
    """Coerce a value to bytes for ingestion."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return str(value).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """Short hex digest for idempotency keys."""
    return hashlib.sha256(data).hexdigest()[:16]


class GenesisAdapter:
    """Translates Genesis pipeline outputs into ForgeBase artifacts.

    Workflow on ``handle_genesis_completed``:
      1. ``attach_run`` to record the Genesis run against the vault.
      2. For each research artifact in the report, ``ingest_source``
         with ``SourceFormat.HEPH_OUTPUT`` and an idempotency key of
         ``"{run_id}:{artifact_name}:{hash}"``.
      3. ``record_artifact`` for each ingested source entity.

    If any step fails the adapter updates the run ref's ``sync_status``
    to ``"failed"`` and re-raises so the bridge can catch it.
    """

    def __init__(
        self,
        run_integration_service: RunIntegrationService,
        ingest_service: IngestService,
        uow_factory: Callable[[], AbstractUnitOfWork],
    ) -> None:
        self._run_svc = run_integration_service
        self._ingest_svc = ingest_service
        self._uow_factory = uow_factory

    async def handle_genesis_completed(
        self,
        vault_id: EntityId,
        run_id: str,
        report: Any,
    ) -> None:
        """Called by the bridge when a Genesis run completes with a vault_id."""
        ref = await self._run_svc.attach_run(
            vault_id=vault_id,
            run_id=run_id,
            run_type="genesis",
            upstream_system="RunStore",
        )

        try:
            artifacts = _extract_artifacts(report)

            for artifact_name, artifact_content in artifacts:
                raw = _safe_bytes(artifact_content)
                content_hash = _content_hash(raw)
                idempotency_key = f"{run_id}:{artifact_name}:{content_hash}"

                source, _version = await self._ingest_svc.ingest_source(
                    vault_id=vault_id,
                    raw_content=raw,
                    format=SourceFormat.HEPH_OUTPUT,
                    title=artifact_name,
                    idempotency_key=idempotency_key,
                    metadata={
                        "genesis_run_id": run_id,
                        "artifact_name": artifact_name,
                    },
                )

                await self._run_svc.record_artifact(
                    ref_id=ref.ref_id,
                    entity_kind=EntityKind.SOURCE,
                    entity_id=source.source_id,
                    role="genesis_output",
                    idempotency_key=idempotency_key,
                )

            # Mark sync as completed
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


def _extract_artifacts(report: Any) -> list[tuple[str, Any]]:
    """Extract (name, content) pairs from a Genesis report.

    Supports multiple report shapes:
      - dict with ``"artifacts"`` key (list of dicts with ``name``/``content``)
      - object with ``artifacts`` attribute
      - dict with ``"research_artifacts"`` key
      - If none of the above, treat the whole report as a single artifact.
    """
    artifacts: list[tuple[str, Any]] = []

    # Dict-style report
    if isinstance(report, dict):
        raw_arts = report.get("artifacts") or report.get("research_artifacts") or []
        if isinstance(raw_arts, list):
            for item in raw_arts:
                if isinstance(item, dict):
                    name = item.get("name", "unnamed")
                    content = item.get("content", item.get("data", ""))
                    artifacts.append((str(name), content))
                else:
                    artifacts.append(("unnamed", item))
        # If no artifacts key found but report has content, treat as single artifact
        if not artifacts and report:
            artifacts.append(("genesis_report", report.get("content", str(report))))
        return artifacts

    # Object-style report
    raw_arts = getattr(report, "artifacts", None) or getattr(
        report, "research_artifacts", None
    )
    if raw_arts and isinstance(raw_arts, list):
        for item in raw_arts:
            name = getattr(item, "name", "unnamed")
            content = getattr(item, "content", getattr(item, "data", str(item)))
            artifacts.append((str(name), content))
        return artifacts

    # Fallback — treat entire report as a single artifact
    if report is not None:
        artifacts.append(("genesis_report", str(report)))

    return artifacts
