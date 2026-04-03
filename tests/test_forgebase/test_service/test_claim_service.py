"""Tests for ClaimService."""
from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import ClaimStatus, PageType, SupportType
from hephaestus.forgebase.domain.values import EntityId, Version
from hephaestus.forgebase.service.claim_service import ClaimService
from hephaestus.forgebase.service.exceptions import ConflictError
from hephaestus.forgebase.service.page_service import PageService
from hephaestus.forgebase.service.vault_service import VaultService


@pytest.mark.asyncio
class TestClaimService:
    async def _setup(self, uow_factory, actor):
        """Helper: create a vault and a page to attach claims to."""
        vault_svc = VaultService(uow_factory=uow_factory, default_actor=actor)
        page_svc = PageService(uow_factory=uow_factory, default_actor=actor)

        vault = await vault_svc.create_vault(name="TestVault")
        page, _ = await page_svc.create_page(
            vault_id=vault.vault_id,
            page_key="test-page",
            page_type=PageType.CONCEPT,
            title="Test Page",
            content=b"content",
        )
        return vault, page

    # ---- create_claim ----

    async def test_create_claim_basic(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, version = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Water boils at 100C",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.95,
        )

        assert claim.vault_id == vault.vault_id
        assert claim.page_id == page.page_id
        assert version.version == Version(1)
        assert version.statement == "Water boils at 100C"
        assert version.status == ClaimStatus.SUPPORTED
        assert version.confidence == 0.95

    async def test_create_claim_emits_event(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Test claim",
            status=ClaimStatus.INFERRED,
            support_type=SupportType.SYNTHESIZED,
            confidence=0.8,
        )

        cursor = await sqlite_db.execute(
            "SELECT event_type, aggregate_id FROM fb_domain_events WHERE event_type = ?",
            ("claim.version_created",),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["aggregate_id"] == str(claim.claim_id)

    async def test_create_claim_sets_canonical_head(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(claim.claim_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1

    async def test_create_claim_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
        wb_id = id_gen.workbook_id()

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Branch claim",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
            confidence=0.5,
            workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT head_version, base_version FROM fb_branch_claim_heads WHERE claim_id = ?",
            (str(claim.claim_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["head_version"] == 1
        assert row["base_version"] == 1

    # ---- update_claim ----

    async def test_update_claim(self, uow_factory, actor):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, v1 = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Original",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
            confidence=0.5,
        )

        v2 = await svc.update_claim(
            claim_id=claim.claim_id,
            expected_version=Version(1),
            statement="Revised statement",
            status=ClaimStatus.SUPPORTED,
            confidence=0.9,
        )

        assert v2.version == Version(2)
        assert v2.statement == "Revised statement"
        assert v2.status == ClaimStatus.SUPPORTED
        assert v2.confidence == 0.9

    async def test_update_claim_partial(self, uow_factory, actor):
        """Only update the fields that are provided; others carry over."""
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Keep this",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.8,
        )

        v2 = await svc.update_claim(
            claim_id=claim.claim_id,
            expected_version=Version(1),
            confidence=0.99,  # only change confidence
        )

        assert v2.statement == "Keep this"  # carried over
        assert v2.status == ClaimStatus.SUPPORTED  # carried over
        assert v2.confidence == 0.99

    async def test_update_claim_optimistic_concurrency(self, uow_factory, actor):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="V1",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        # Update to v2
        await svc.update_claim(claim.claim_id, Version(1), statement="V2")

        # Stale update
        with pytest.raises(ConflictError) as exc_info:
            await svc.update_claim(claim.claim_id, Version(1), statement="Stale")
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

    async def test_update_claim_not_found(self, uow_factory, actor, id_gen):
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
        fake = id_gen.claim_id()
        with pytest.raises(ValueError, match="Claim not found"):
            await svc.update_claim(fake, Version(1), statement="X")

    # ---- add_support ----

    async def test_add_support(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Supported claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
        )

        source_id = id_gen.source_id()
        support = await svc.add_support(
            claim_id=claim.claim_id,
            source_id=source_id,
            source_segment="p42-43",
            strength=0.85,
        )

        assert support.claim_id == claim.claim_id
        assert support.source_id == source_id
        assert support.source_segment == "p42-43"
        assert support.strength == 0.85

    async def test_add_support_emits_event(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="X",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        source_id = id_gen.source_id()
        await svc.add_support(claim.claim_id, source_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("claim.support_added",),
        )
        assert await cursor.fetchone() is not None

    async def test_add_support_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Branch support",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.9,
        )

        wb_id = id_gen.workbook_id()
        source_id = id_gen.source_id()
        support = await svc.add_support(
            claim.claim_id, source_id, workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT created_on_branch FROM fb_branch_claim_support_heads WHERE support_id = ?",
            (str(support.support_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["created_on_branch"] == 1

    # ---- remove_support ----

    async def test_remove_support(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="X",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        source_id = id_gen.source_id()
        support = await svc.add_support(claim.claim_id, source_id)

        await svc.remove_support(support.support_id)

        # Support should be gone
        cursor = await sqlite_db.execute(
            "SELECT * FROM fb_claim_supports WHERE support_id = ?",
            (str(support.support_id),),
        )
        assert await cursor.fetchone() is None

    async def test_remove_support_emits_event(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="X",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        source_id = id_gen.source_id()
        support = await svc.add_support(claim.claim_id, source_id)
        await svc.remove_support(support.support_id)

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("claim.support_removed",),
        )
        assert await cursor.fetchone() is not None

    async def test_remove_support_not_found(self, uow_factory, actor, id_gen):
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
        fake = id_gen.support_id()
        with pytest.raises(ValueError, match="ClaimSupport not found"):
            await svc.remove_support(fake)

    # ---- add_derivation ----

    async def test_add_derivation(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        parent_claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Parent",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=1.0,
        )

        child_claim, _ = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Derived from parent",
            status=ClaimStatus.INFERRED,
            support_type=SupportType.INHERITED,
            confidence=0.8,
        )

        derivation = await svc.add_derivation(
            claim_id=child_claim.claim_id,
            parent_claim_id=parent_claim.claim_id,
            relationship="inferred_from",
        )

        assert derivation.claim_id == child_claim.claim_id
        assert derivation.parent_claim_id == parent_claim.claim_id
        assert derivation.relationship == "inferred_from"

    async def test_add_derivation_emits_event(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        c1, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="P", status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT, confidence=1.0,
        )
        c2, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="C", status=ClaimStatus.INFERRED,
            support_type=SupportType.INHERITED, confidence=0.7,
        )

        await svc.add_derivation(c2.claim_id, c1.claim_id, "generalizes")

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("claim.derivation_added",),
        )
        assert await cursor.fetchone() is not None

    async def test_add_derivation_on_branch(self, uow_factory, actor, sqlite_db, id_gen):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
        wb_id = id_gen.workbook_id()

        c1, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="P", status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT, confidence=1.0,
        )
        c2, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="C", status=ClaimStatus.INFERRED,
            support_type=SupportType.INHERITED, confidence=0.7,
        )

        derivation = await svc.add_derivation(
            c2.claim_id, c1.claim_id, "refines", workbook_id=wb_id,
        )

        cursor = await sqlite_db.execute(
            "SELECT created_on_branch FROM fb_branch_claim_derivation_heads WHERE derivation_id = ?",
            (str(derivation.derivation_id),),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["created_on_branch"] == 1

    # ---- invalidate_claim ----

    async def test_invalidate_claim(self, uow_factory, actor):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, v1 = await svc.create_claim(
            vault_id=vault.vault_id,
            page_id=page.page_id,
            statement="Once true",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.95,
        )

        v2 = await svc.invalidate_claim(
            claim_id=claim.claim_id,
            reason="Contradicted by new evidence",
        )

        assert v2.version == Version(2)
        assert v2.status == ClaimStatus.CONTESTED
        assert v2.confidence == 0.0
        assert v2.statement == "Once true"  # statement preserved

    async def test_invalidate_claim_emits_event(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="X", status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT, confidence=1.0,
        )

        await svc.invalidate_claim(claim.claim_id, "reason")

        cursor = await sqlite_db.execute(
            "SELECT event_type FROM fb_domain_events WHERE event_type = ?",
            ("claim.invalidated",),
        )
        assert await cursor.fetchone() is not None

    async def test_invalidate_claim_updates_canonical_head(self, uow_factory, actor, sqlite_db):
        vault, page = await self._setup(uow_factory, actor)
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)

        claim, _ = await svc.create_claim(
            vault_id=vault.vault_id, page_id=page.page_id,
            statement="X", status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT, confidence=1.0,
        )

        await svc.invalidate_claim(claim.claim_id, "outdated")

        cursor = await sqlite_db.execute(
            "SELECT head_version FROM fb_canonical_heads WHERE entity_id = ?",
            (str(claim.claim_id),),
        )
        row = await cursor.fetchone()
        assert row["head_version"] == 2

    async def test_invalidate_claim_not_found(self, uow_factory, actor, id_gen):
        svc = ClaimService(uow_factory=uow_factory, default_actor=actor)
        fake = id_gen.claim_id()
        with pytest.raises(ValueError, match="Claim not found"):
            await svc.invalidate_claim(fake, "reason")
