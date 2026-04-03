"""PantheonAdapter — translates Pantheon deliberation outputs into ForgeBase artifacts.

The adapter accepts ``state: Any`` to avoid importing Pantheon types and
creating circular dependencies.  It is resilient to missing fields.
"""
from __future__ import annotations

import hashlib
import json
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
    try:
        return json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return str(value).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """Short hex digest for idempotency keys."""
    return hashlib.sha256(data).hexdigest()[:16]


class PantheonAdapter:
    """Translates Pantheon deliberation outputs into ForgeBase artifacts.

    Workflow on ``handle_pantheon_completed``:
      1. ``attach_run`` to record the Pantheon run.
      2. Ingest the verdict (if present) as a ``HEPH_OUTPUT`` source.
      3. Ingest any objections / deliberation artifacts.
      4. ``record_artifact`` for each created entity.

    On failure: update ``sync_status`` to ``"failed"`` and re-raise.
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

    async def handle_pantheon_completed(
        self,
        vault_id: EntityId,
        run_id: str,
        state: Any,
    ) -> None:
        """Called by the bridge when a Pantheon run completes with a vault_id."""
        ref = await self._run_svc.attach_run(
            vault_id=vault_id,
            run_id=run_id,
            run_type="pantheon",
            upstream_system="CouncilArtifactStore",
        )

        try:
            items = _extract_pantheon_items(state)

            for item_name, item_content in items:
                raw = _safe_bytes(item_content)
                content_hash = _content_hash(raw)
                idempotency_key = f"{run_id}:pantheon:{item_name}:{content_hash}"

                source, _version = await self._ingest_svc.ingest_source(
                    vault_id=vault_id,
                    raw_content=raw,
                    format=SourceFormat.HEPH_OUTPUT,
                    title=item_name,
                    idempotency_key=idempotency_key,
                    metadata={
                        "pantheon_run_id": run_id,
                        "artifact_type": item_name,
                    },
                )

                await self._run_svc.record_artifact(
                    ref_id=ref.ref_id,
                    entity_kind=EntityKind.SOURCE,
                    entity_id=source.source_id,
                    role="pantheon_output",
                    idempotency_key=idempotency_key,
                )

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


def _extract_pantheon_items(state: Any) -> list[tuple[str, Any]]:
    """Extract (name, content) pairs from a Pantheon state.

    Supports multiple state shapes:
      - dict with ``"verdict"`` and/or ``"objections"`` keys
      - object with ``verdict``, ``objections``, ``deliberation`` attributes
      - Fallback: treat the entire state as a single artifact
    """
    items: list[tuple[str, Any]] = []

    if isinstance(state, dict):
        verdict = state.get("verdict")
        if verdict is not None:
            items.append(("verdict", verdict))

        objections = state.get("objections")
        if isinstance(objections, list):
            for i, obj in enumerate(objections):
                items.append((f"objection_{i}", obj))

        deliberation = state.get("deliberation")
        if deliberation is not None:
            items.append(("deliberation", deliberation))

        # If nothing extracted, treat state as single artifact
        if not items and state:
            items.append(("pantheon_state", state))

        return items

    # Object-style
    verdict = getattr(state, "verdict", None)
    if verdict is not None:
        items.append(("verdict", verdict))

    objections = getattr(state, "objections", None)
    if isinstance(objections, list):
        for i, obj in enumerate(objections):
            items.append((f"objection_{i}", obj))

    deliberation = getattr(state, "deliberation", None)
    if deliberation is not None:
        items.append(("deliberation", deliberation))

    if not items and state is not None:
        items.append(("pantheon_state", str(state)))

    return items
