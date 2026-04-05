"""Tests for PromotionService — explicit claim promotion from HYPOTHESIS to SUPPORTED.

Uses a real SQLite backend (no mocks) to exercise the full domain stack.
Every test builds its own scenario from scratch using the service/UoW layer.
"""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    PageType,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimDerivation,
    ClaimSupport,
    ClaimVersion,
    InventionPageMeta,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ContentHash,
    EntityId,
    Version,
)
from hephaestus.forgebase.integration.promotion import PromotionService

# ---------------------------------------------------------------------------
# Helpers — build raw domain objects via UoW for test setup
# ---------------------------------------------------------------------------


async def _create_invention_page(uow_factory, vault_id, actor, *, page_key="inv-1"):
    """Create an INVENTION page + InventionPageMeta (PROPOSED) inside the vault."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        page_id = uow.id_generator.page_id()

        content_bytes = b"# Invention\nTest invention content"
        pending = await uow.content.stage(content_bytes, "text/markdown")
        blob_ref = pending.to_blob_ref()
        content_hash = ContentHash.from_bytes(content_bytes)

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=PageType.INVENTION,
            page_key=page_key,
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title="Test Invention",
            content_ref=blob_ref,
            content_hash=content_hash,
            summary="Test",
            compiled_from=[],
            created_at=now,
            created_by=actor,
        )
        await uow.pages.create(page, pv)
        await uow.vaults.set_canonical_page_head(vault_id, page_id, 1)

        meta = InventionPageMeta(
            page_id=page_id,
            vault_id=vault_id,
            invention_state=InventionEpistemicState.PROPOSED,
            run_id="genesis-test",
            run_type="genesis",
            models_used=["test-model"],
            created_at=now,
            updated_at=now,
        )
        await uow.invention_meta.create(meta)

        await uow.commit()

    return page_id


async def _create_hypothesis_claim(
    uow_factory, vault_id, page_id, actor, *, statement="Test hypothesis claim"
):
    """Create a HYPOTHESIS claim on the given page, return claim_id."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        claim_id = uow.id_generator.claim_id()

        claim = Claim(
            claim_id=claim_id,
            vault_id=vault_id,
            page_id=page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement=statement,
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
            confidence=0.7,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=actor,
        )
        await uow.claims.create(claim, cv)
        await uow.vaults.set_canonical_claim_head(vault_id, claim_id, 1)
        await uow.commit()

    return claim_id


async def _create_supported_claim(
    uow_factory, vault_id, page_id, actor, *, statement="Already supported"
):
    """Create a SUPPORTED claim on the given page, return claim_id."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        claim_id = uow.id_generator.claim_id()

        claim = Claim(
            claim_id=claim_id,
            vault_id=vault_id,
            page_id=page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement=statement,
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.95,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=actor,
        )
        await uow.claims.create(claim, cv)
        await uow.vaults.set_canonical_claim_head(vault_id, claim_id, 1)
        await uow.commit()

    return claim_id


async def _create_contested_claim(
    uow_factory, vault_id, page_id, actor, *, statement="Contested claim"
):
    """Create a CONTESTED claim on the given page, return claim_id."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        claim_id = uow.id_generator.claim_id()

        claim = Claim(
            claim_id=claim_id,
            vault_id=vault_id,
            page_id=page_id,
            created_at=now,
        )
        cv = ClaimVersion(
            claim_id=claim_id,
            version=Version(1),
            statement=statement,
            status=ClaimStatus.CONTESTED,
            support_type=SupportType.GENERATED,
            confidence=0.3,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=actor,
        )
        await uow.claims.create(claim, cv)
        await uow.vaults.set_canonical_claim_head(vault_id, claim_id, 1)
        await uow.commit()

    return claim_id


async def _add_claim_support(uow_factory, claim_id, actor):
    """Add a ClaimSupport record for the given claim (fabricated source)."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        support_id = uow.id_generator.support_id()
        source_id = uow.id_generator.source_id()

        support = ClaimSupport(
            support_id=support_id,
            claim_id=claim_id,
            source_id=source_id,
            source_segment=None,
            strength=0.9,
            created_at=now,
            created_by=actor,
        )
        await uow.claim_supports.create(support)
        await uow.commit()

    return support_id


async def _add_claim_derivation(uow_factory, claim_id, parent_claim_id, actor):
    """Add a ClaimDerivation record for the given claim."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        derivation_id = uow.id_generator.derivation_id()

        derivation = ClaimDerivation(
            derivation_id=derivation_id,
            claim_id=claim_id,
            parent_claim_id=parent_claim_id,
            relationship="derived_from",
            created_at=now,
            created_by=actor,
        )
        await uow.claim_derivations.create(derivation)
        await uow.commit()

    return derivation_id


async def _set_invention_state(uow_factory, page_id, state):
    """Update InventionPageMeta state."""
    uow = uow_factory()
    async with uow:
        await uow.invention_meta.update_state(page_id, state)
        await uow.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def promotion_service(uow_factory, actor) -> PromotionService:
    return PromotionService(uow_factory=uow_factory, default_actor=actor)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluatePromotion:
    """Tests for PromotionService.evaluate_promotion."""

    async def test_evaluate_verified_page_eligible(
        self, promotion_service, uow_factory, vault, actor
    ):
        """VERIFIED page with supported claims -> eligible."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, claim_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        result = await promotion_service.evaluate_promotion(page_id, vault.vault_id)

        assert result.overall_eligible is True
        assert claim_id in result.eligible_claims
        assert len(result.blocked_claims) == 0

    async def test_evaluate_proposed_page_not_eligible(
        self, promotion_service, uow_factory, vault, actor
    ):
        """PROPOSED page -> nothing eligible, all claims blocked."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, claim_id, actor)
        # State is still PROPOSED (default)

        result = await promotion_service.evaluate_promotion(page_id, vault.vault_id)

        assert result.overall_eligible is False
        assert len(result.eligible_claims) == 0
        assert len(result.blocked_claims) == 1
        assert result.blocked_claims[0][0] == claim_id
        assert "proposed" in result.blocked_claims[0][1]

    async def test_evaluate_contested_claims_blocked(
        self, promotion_service, uow_factory, vault, actor
    ):
        """VERIFIED page with CONTESTED claims -> those claims blocked."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        contested_id = await _create_contested_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, contested_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        result = await promotion_service.evaluate_promotion(page_id, vault.vault_id)

        assert result.overall_eligible is False
        blocked_ids = [b[0] for b in result.blocked_claims]
        assert contested_id in blocked_ids
        reason = next(r for cid, r in result.blocked_claims if cid == contested_id)
        assert "CONTESTED" in reason

    async def test_evaluate_no_support_blocked(self, promotion_service, uow_factory, vault, actor):
        """VERIFIED page with claims lacking support/derivation -> blocked."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        # No support or derivation added
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        result = await promotion_service.evaluate_promotion(page_id, vault.vault_id)

        assert result.overall_eligible is False
        blocked_ids = [b[0] for b in result.blocked_claims]
        assert claim_id in blocked_ids
        reason = next(r for cid, r in result.blocked_claims if cid == claim_id)
        assert "ClaimSupport" in reason or "ClaimDerivation" in reason

    async def test_evaluate_nonexistent_page_returns_empty(self, promotion_service, vault):
        """Evaluating a non-existent page returns empty result."""
        fake_page_id = EntityId("page_00000000000000000099999999")

        result = await promotion_service.evaluate_promotion(fake_page_id, vault.vault_id)

        assert result.overall_eligible is False
        assert result.eligible_claims == []
        assert result.blocked_claims == []

    async def test_evaluate_derivation_counts_as_support(
        self, promotion_service, uow_factory, vault, actor
    ):
        """A claim with ClaimDerivation (but no ClaimSupport) is eligible."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        parent_claim_id = await _create_hypothesis_claim(
            uow_factory,
            vault.vault_id,
            page_id,
            actor,
            statement="Parent claim",
        )
        child_claim_id = await _create_hypothesis_claim(
            uow_factory,
            vault.vault_id,
            page_id,
            actor,
            statement="Derived claim",
        )
        # Add support to parent so it's not blocked for lack of support
        await _add_claim_support(uow_factory, parent_claim_id, actor)
        # Add derivation (not support) to child
        await _add_claim_derivation(uow_factory, child_claim_id, parent_claim_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        result = await promotion_service.evaluate_promotion(page_id, vault.vault_id)

        assert result.overall_eligible is True
        assert child_claim_id in result.eligible_claims
        assert parent_claim_id in result.eligible_claims


@pytest.mark.asyncio
class TestPromoteClaims:
    """Tests for PromotionService.promote_claims."""

    async def test_promote_updates_claim_status(self, promotion_service, uow_factory, vault, actor):
        """Promote turns HYPOTHESIS into SUPPORTED."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, claim_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        promoted = await promotion_service.promote_claims(page_id, vault.vault_id)

        assert claim_id in promoted

        # Verify the head version is now SUPPORTED
        uow = uow_factory()
        async with uow:
            head = await uow.claims.get_head_version(claim_id)
            assert head is not None
            assert head.status == ClaimStatus.SUPPORTED
            assert head.version == Version(2)
            await uow.rollback()

    async def test_promote_emits_event(self, promotion_service, uow_factory, vault, actor):
        """Promotion must emit an 'invention.promoted' event."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, claim_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        promoted = await promotion_service.promote_claims(page_id, vault.vault_id)

        assert len(promoted) == 1

        # Verify the event was persisted in the outbox
        uow = uow_factory()
        async with uow:
            # Read events from the SQLite event outbox
            cursor = await uow._db.execute(
                "SELECT event_type, payload FROM fb_domain_events "
                "WHERE event_type = 'invention.promoted' "
                "ORDER BY rowid DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["event_type"] == "invention.promoted"
            await uow.rollback()

    async def test_promote_skips_already_supported(
        self, promotion_service, uow_factory, vault, actor
    ):
        """Already SUPPORTED claims are not re-promoted."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        supported_id = await _create_supported_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, supported_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        promoted = await promotion_service.promote_claims(page_id, vault.vault_id)

        assert promoted == []

        # Verify claim is still at version 1
        uow = uow_factory()
        async with uow:
            head = await uow.claims.get_head_version(supported_id)
            assert head is not None
            assert head.version == Version(1)
            assert head.status == ClaimStatus.SUPPORTED
            await uow.rollback()

    async def test_promote_specific_claims_only(self, promotion_service, uow_factory, vault, actor):
        """When claim_ids is provided, only those (eligible) claims are promoted."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_a = await _create_hypothesis_claim(
            uow_factory,
            vault.vault_id,
            page_id,
            actor,
            statement="Claim A",
        )
        claim_b = await _create_hypothesis_claim(
            uow_factory,
            vault.vault_id,
            page_id,
            actor,
            statement="Claim B",
        )
        await _add_claim_support(uow_factory, claim_a, actor)
        await _add_claim_support(uow_factory, claim_b, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        # Only promote claim_a
        promoted = await promotion_service.promote_claims(
            page_id, vault.vault_id, claim_ids=[claim_a]
        )

        assert claim_a in promoted
        assert claim_b not in promoted

        # Verify claim_b is still HYPOTHESIS
        uow = uow_factory()
        async with uow:
            head_b = await uow.claims.get_head_version(claim_b)
            assert head_b is not None
            assert head_b.status == ClaimStatus.HYPOTHESIS
            await uow.rollback()

    async def test_promote_ineligible_claim_ids_skipped(
        self, promotion_service, uow_factory, vault, actor
    ):
        """Passing ineligible claim_ids results in no promotions."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        # No support added -- claim is ineligible
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        promoted = await promotion_service.promote_claims(
            page_id, vault.vault_id, claim_ids=[claim_id]
        )

        assert promoted == []

    async def test_promote_returns_empty_for_proposed_page(
        self, promotion_service, uow_factory, vault, actor
    ):
        """Promoting claims on a PROPOSED page returns empty list."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(uow_factory, vault.vault_id, page_id, actor)
        await _add_claim_support(uow_factory, claim_id, actor)
        # State is still PROPOSED

        promoted = await promotion_service.promote_claims(page_id, vault.vault_id)

        assert promoted == []

    async def test_promote_preserves_claim_statement_and_metadata(
        self, promotion_service, uow_factory, vault, actor
    ):
        """Promoted claim retains original statement, support_type, and confidence."""
        page_id = await _create_invention_page(uow_factory, vault.vault_id, actor)
        claim_id = await _create_hypothesis_claim(
            uow_factory,
            vault.vault_id,
            page_id,
            actor,
            statement="Specific mechanism claim",
        )
        await _add_claim_support(uow_factory, claim_id, actor)
        await _set_invention_state(uow_factory, page_id, InventionEpistemicState.VERIFIED)

        promoted = await promotion_service.promote_claims(page_id, vault.vault_id)

        assert claim_id in promoted

        uow = uow_factory()
        async with uow:
            head = await uow.claims.get_head_version(claim_id)
            assert head is not None
            assert head.statement == "Specific mechanism claim"
            assert head.support_type == SupportType.GENERATED
            assert head.confidence == 0.7
            assert head.status == ClaimStatus.SUPPORTED
            await uow.rollback()
