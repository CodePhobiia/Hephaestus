"""IngestService — source ingestion and normalization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hephaestus.forgebase.domain.enums import SourceFormat, SourceStatus, SourceTrustTier
from hephaestus.forgebase.domain.models import (
    BranchSourceHead,
    Source,
    SourceVersion,
)
from hephaestus.forgebase.domain.values import (
    ActorRef,
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.exceptions import ConflictError


class IngestService:
    """Command service for source ingestion and normalization."""

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        default_actor: ActorRef,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_actor = default_actor

    async def ingest_source(
        self,
        vault_id: EntityId,
        raw_content: bytes,
        format: SourceFormat, # noqa: A002
        metadata: dict[str, Any] | None = None,
        workbook_id: EntityId | None = None,
        idempotency_key: str = "",
        title: str = "",
        authors: list[str] | None = None,
        url: str | None = None,
        trust_tier: SourceTrustTier = SourceTrustTier.STANDARD,
        origin_locator: str | None = None,
    ) -> tuple[Source, SourceVersion]:
        """Ingest raw content as a new source.

        Steps:
          1. Stage raw bytes via ContentStore -> PendingContentRef
          2. Create Source + SourceVersion(status=INGESTED, version=1)
          3. If workbook_id: set BranchSourceHead; else: set canonical source head
          4. Emit source.ingested
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()
            source_id = uow.id_generator.source_id()

            # 1. Stage raw bytes
            pending_ref = await uow.content.stage(raw_content, "application/octet-stream")
            blob_ref = pending_ref.to_blob_ref()
            content_hash = ContentHash.from_bytes(raw_content)

            # 2. Create Source + SourceVersion
            source = Source(
                source_id=source_id,
                vault_id=vault_id,
                format=format,
                origin_locator=origin_locator,
                created_at=now,
            )

            version = SourceVersion(
                source_id=source_id,
                version=Version(1),
                title=title,
                authors=authors or [],
                url=url,
                raw_artifact_ref=blob_ref,
                normalized_ref=None,
                content_hash=content_hash,
                metadata=metadata or {},
                trust_tier=trust_tier,
                status=SourceStatus.INGESTED,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.sources.create(source, version)

            # 3. Set head
            if workbook_id is not None:
                await uow.workbooks.set_source_head(
                    BranchSourceHead(
                        workbook_id=workbook_id,
                        source_id=source_id,
                        head_version=Version(1),
                        base_version=Version(1),  # Version(1) since born on branch as version 1
                    )
                )
            else:
                await uow.vaults.set_canonical_source_head(
                    vault_id,
                    source_id,
                    1,
                )

            # 4. Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="source.ingested",
                    aggregate_type="source",
                    aggregate_id=source_id,
                    aggregate_version=Version(1),
                    vault_id=vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "format": format.value,
                        "title": title,
                        "idempotency_key": idempotency_key,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return source, version

    async def normalize_source(
        self,
        source_id: EntityId,
        normalized_content: bytes,
        expected_version: Version,
        workbook_id: EntityId | None = None,
        idempotency_key: str = "",
    ) -> SourceVersion:
        """Normalize a previously ingested source.

        Steps:
          1. Stage normalized bytes -> PendingContentRef
          2. Create new SourceVersion with status=NORMALIZED, version=N+1
          3. Update branch or canonical head
          4. Emit source.normalized
        """
        uow = self._uow_factory()
        async with uow:
            now = uow.clock.now()

            # Get source and current head version
            source = await uow.sources.get(source_id)
            if source is None:
                raise ValueError(f"Source not found: {source_id}")

            current_head = await uow.sources.get_head_version(source_id)
            if current_head is None:
                raise ValueError(f"No versions found for source: {source_id}")

            # Optimistic concurrency check
            if current_head.version != expected_version:
                raise ConflictError(
                    entity_id=str(source_id),
                    expected=expected_version.number,
                    actual=current_head.version.number,
                )

            # 1. Stage normalized bytes
            pending_ref = await uow.content.stage(normalized_content, "text/plain")
            normalized_blob = pending_ref.to_blob_ref()
            content_hash = ContentHash.from_bytes(normalized_content)

            new_version_num = expected_version.next()

            # 2. Create new SourceVersion
            new_version = SourceVersion(
                source_id=source_id,
                version=new_version_num,
                title=current_head.title,
                authors=current_head.authors,
                url=current_head.url,
                raw_artifact_ref=current_head.raw_artifact_ref,
                normalized_ref=normalized_blob,
                content_hash=content_hash,
                metadata=current_head.metadata,
                trust_tier=current_head.trust_tier,
                status=SourceStatus.NORMALIZED,
                created_at=now,
                created_by=self._default_actor,
            )

            await uow.sources.create_version(new_version)

            # 3. Update head
            if workbook_id is not None:
                await uow.workbooks.set_source_head(
                    BranchSourceHead(
                        workbook_id=workbook_id,
                        source_id=source_id,
                        head_version=new_version_num,
                        base_version=expected_version,
                    )
                )
            else:
                await uow.vaults.set_canonical_source_head(
                    source.vault_id,
                    source_id,
                    new_version_num.number,
                )

            # 4. Emit event
            uow.record_event(
                uow.event_factory.create(
                    event_type="source.normalized",
                    aggregate_type="source",
                    aggregate_id=source_id,
                    aggregate_version=new_version_num,
                    vault_id=source.vault_id,
                    workbook_id=workbook_id,
                    payload={
                        "previous_version": expected_version.number,
                        "new_version": new_version_num.number,
                        "idempotency_key": idempotency_key,
                    },
                    actor=self._default_actor,
                )
            )

            await uow.commit()

        return new_version
