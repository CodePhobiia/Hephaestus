"""Tests for RunIntegrationService — attach runs and record artifacts."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import EntityKind, PageType
from hephaestus.forgebase.service.exceptions import EntityNotFoundError
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.run_integration_service import RunIntegrationService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestRunIntegrationService:
    async def _create_vault(self, uow_factory, actor):
        svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        return await svc.create_vault(name="RunVault")

    async def test_attach_run(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        ref = await svc.attach_run(
            vault_id=vault.vault_id,
            run_id="run-123",
            run_type="research",
            upstream_system="hephaestus",
        )

        assert ref.vault_id == vault.vault_id
        assert ref.run_id == "run-123"
        assert ref.run_type == "research"
        assert ref.upstream_system == "hephaestus"
        assert ref.sync_status == "attached"

    async def test_attach_run_with_upstream_ref(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        ref = await svc.attach_run(
            vault_id=vault.vault_id,
            run_id="run-456",
            run_type="invention",
            upstream_system="external",
            upstream_ref="ext-ref-789",
        )

        assert ref.upstream_ref == "ext-ref-789"

    async def test_attach_run_vault_not_found_raises(self, uow_factory, actor, id_gen):
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        with pytest.raises(EntityNotFoundError, match="Vault not found"):
            await svc.attach_run(
                vault_id=id_gen.vault_id(),
                run_id="run-ghost",
                run_type="research",
                upstream_system="hephaestus",
            )

    async def test_attach_run_emits_event(self, uow_factory, actor, sqlite_db):
        vault = await self._create_vault(uow_factory, actor)
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        await svc.attach_run(
            vault_id=vault.vault_id,
            run_id="run-event",
            run_type="research",
            upstream_system="hephaestus",
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = 'artifact.attached'"
        )
        row = await cursor.fetchone()
        assert row is not None

    async def test_record_artifact(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        ref = await svc.attach_run(
            vault_id=vault.vault_id,
            run_id="run-art",
            run_type="research",
            upstream_system="hephaestus",
        )

        # Create a page to reference
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="artifact-page",
            page_type=PageType.CONCEPT,
            title="Artifact Page",
            content=b"content",
        )

        artifact = await svc.record_artifact(
            ref_id=ref.ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=page.page_id,
            role="output",
            idempotency_key="art-001",
        )

        assert artifact.ref_id == ref.ref_id
        assert artifact.entity_kind == EntityKind.PAGE
        assert artifact.entity_id == page.page_id
        assert artifact.role == "output"

    async def test_record_artifact_idempotent(self, uow_factory, actor):
        vault = await self._create_vault(uow_factory, actor)
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        ref = await svc.attach_run(
            vault_id=vault.vault_id,
            run_id="run-idem",
            run_type="research",
            upstream_system="hephaestus",
        )

        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="idem-page",
            page_type=PageType.CONCEPT,
            title="Idem Page",
            content=b"content",
        )

        art1 = await svc.record_artifact(
            ref_id=ref.ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=page.page_id,
            role="output",
            idempotency_key="art-idem",
        )
        art2 = await svc.record_artifact(
            ref_id=ref.ref_id,
            entity_kind=EntityKind.PAGE,
            entity_id=page.page_id,
            role="output",
            idempotency_key="art-idem",
        )

        # Same artifact returned
        assert art1.entity_id == art2.entity_id
        assert art1.role == art2.role

    async def test_record_artifact_ref_not_found_raises(self, uow_factory, actor, id_gen):
        svc = RunIntegrationService(uow_factory=uow_factory, default_actor=actor)

        with pytest.raises(EntityNotFoundError, match="KnowledgeRunRef not found"):
            await svc.record_artifact(
                ref_id=id_gen.ref_id(),
                entity_kind=EntityKind.PAGE,
                entity_id=id_gen.page_id(),
                role="output",
                idempotency_key="art-ghost",
            )
