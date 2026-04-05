"""Tests for ConstraintDossierPack extraction — governance-grade channel.

Uses a real SQLite backend (no mocks) to exercise the full extraction stack.
"""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    LinkKind,
    PageType,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimSupport,
    ClaimVersion,
    InventionPageMeta,
    Link,
    LinkVersion,
    Page,
    PageVersion,
    Source,
    SourceVersion,
)
from hephaestus.forgebase.domain.values import (
    ContentHash,
    Version,
)
from hephaestus.forgebase.extraction.dossier_pack import extract_constraint_dossier_pack
from hephaestus.forgebase.extraction.policy import ExtractionPolicy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_page(uow_factory, vault_id, actor, *, page_type, page_key, title, summary=""):
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        page_id = uow.id_generator.page_id()
        content_bytes = f"# {title}\n{summary}".encode()
        pending = await uow.content.stage(content_bytes, "text/markdown")
        blob_ref = pending.to_blob_ref()
        content_hash = ContentHash.from_bytes(content_bytes)

        page = Page(
            page_id=page_id,
            vault_id=vault_id,
            page_type=page_type,
            page_key=page_key,
            created_at=now,
        )
        pv = PageVersion(
            page_id=page_id,
            version=Version(1),
            title=title,
            content_ref=blob_ref,
            content_hash=content_hash,
            summary=summary,
            compiled_from=[],
            created_at=now,
            created_by=actor,
        )
        await uow.pages.create(page, pv)
        await uow.vaults.set_canonical_page_head(vault_id, page_id, 1)
        await uow.commit()
    return page_id


async def _create_claim(
    uow_factory,
    vault_id,
    page_id,
    actor,
    *,
    statement,
    status=ClaimStatus.SUPPORTED,
    support_type=SupportType.DIRECT,
    confidence=0.9,
):
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
            status=status,
            support_type=support_type,
            confidence=confidence,
            validated_at=now,
            fresh_until=None,
            created_at=now,
            created_by=actor,
        )
        await uow.claims.create(claim, cv)
        await uow.vaults.set_canonical_claim_head(vault_id, claim_id, 1)
        await uow.commit()
    return claim_id


async def _create_source_with_trust(
    uow_factory,
    vault_id,
    actor,
    *,
    trust_tier=SourceTrustTier.AUTHORITATIVE,
):
    """Create a source with a specific trust tier, return source_id."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        source_id = uow.id_generator.source_id()
        content_bytes = b"Source content"
        pending = await uow.content.stage(content_bytes, "text/plain")
        blob_ref = pending.to_blob_ref()
        content_hash = ContentHash.from_bytes(content_bytes)

        source = Source(
            source_id=source_id,
            vault_id=vault_id,
            format=SourceFormat.MARKDOWN,
            origin_locator=None,
            created_at=now,
        )
        sv = SourceVersion(
            source_id=source_id,
            version=Version(1),
            title="Test Source",
            authors=[],
            url=None,
            raw_artifact_ref=blob_ref,
            normalized_ref=None,
            content_hash=content_hash,
            metadata={},
            trust_tier=trust_tier,
            status=SourceStatus.INGESTED,
            created_at=now,
            created_by=actor,
        )
        await uow.sources.create(source, sv)
        await uow.commit()
    return source_id


async def _add_claim_support(uow_factory, claim_id, source_id, actor):
    """Add a ClaimSupport linking a claim to a source."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        support_id = uow.id_generator.support_id()
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


async def _create_challenged_by_link(
    uow_factory,
    vault_id,
    actor,
    *,
    source_claim_id,
    objection_claim_id,
):
    """Create a CHALLENGED_BY link from source_claim to objection_claim."""
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        link_id = uow.id_generator.link_id()
        link = Link(
            link_id=link_id,
            vault_id=vault_id,
            kind=LinkKind.CHALLENGED_BY,
            created_at=now,
        )
        lv = LinkVersion(
            link_id=link_id,
            version=Version(1),
            source_entity=source_claim_id,
            target_entity=objection_claim_id,
            label="challenged_by",
            weight=1.0,
            created_at=now,
            created_by=actor,
        )
        await uow.links.create(link, lv)
        await uow.commit()
    return link_id


async def _create_invention_page(
    uow_factory,
    vault_id,
    actor,
    *,
    page_key,
    title,
    state,
    summary="",
):
    page_id = await _create_page(
        uow_factory,
        vault_id,
        actor,
        page_type=PageType.INVENTION,
        page_key=page_key,
        title=title,
        summary=summary,
    )
    uow = uow_factory()
    async with uow:
        now = uow.clock.now()
        meta = InventionPageMeta(
            page_id=page_id,
            vault_id=vault_id,
            invention_state=state,
            run_id="genesis-test",
            run_type="genesis",
            models_used=["test-model"],
            created_at=now,
            updated_at=now,
        )
        await uow.invention_meta.create(meta)
        await uow.commit()
    return page_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDossierPackExtraction:
    async def test_includes_hard_constraints(self, uow_factory, vault, actor):
        """SUPPORTED claims with constraint keywords appear as hard_constraints."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/constraints",
            title="System Constraints",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="The system must not exceed 100ms latency constraint",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.hard_constraints) == 1
        assert "constraint" in pack.hard_constraints[0].text.lower()
        assert pack.hard_constraints[0].origin_kind == "constraint"

    async def test_includes_failure_modes(self, uow_factory, vault, actor):
        """SUPPORTED claims from mechanism pages with failure keywords appear."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.MECHANISM,
            page_key="mechanisms/failure-test",
            title="Network Failure Modes",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="The routing algorithm fails under high-contention scenarios",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.known_failure_modes) == 1
        assert "fails" in pack.known_failure_modes[0].text.lower()
        assert pack.known_failure_modes[0].origin_kind == "failure_mode"

    async def test_includes_unresolved_controversies_labeled(self, uow_factory, vault, actor):
        """CONTESTED claims appear as unresolved_controversies, explicitly labeled."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/controversy",
            title="Controversial Topic",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="This mechanism is contested by multiple researchers",
            status=ClaimStatus.CONTESTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.unresolved_controversies) == 1
        assert pack.unresolved_controversies[0].epistemic_state == "contested"
        assert pack.unresolved_controversies[0].origin_kind == "controversy"

    async def test_excludes_hypothesis(self, uow_factory, vault, actor):
        """HYPOTHESIS claims do NOT appear in any dossier category."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/hyp-dossier",
            title="Hypothesis Concept",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="This is a hypothesis with constraint keyword",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        # HYPOTHESIS should not be in hard_constraints (requires SUPPORTED)
        assert len(pack.hard_constraints) == 0
        # HYPOTHESIS should not be in unresolved_controversies (requires CONTESTED)
        assert len(pack.unresolved_controversies) == 0
        # HYPOTHESIS should not be in failure modes (requires SUPPORTED)
        assert len(pack.known_failure_modes) == 0

    async def test_excludes_rejected_inventions(self, uow_factory, vault, actor):
        """REJECTED invention content does not appear in the dossier."""
        vid = vault.vault_id
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/rejected-dos",
            title="Rejected For Dossier",
            state=InventionEpistemicState.REJECTED,
        )
        # Even if the claim text has constraint keywords
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="This constraint is from a rejected invention",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        # INVENTION pages are not concept/mechanism, so their claims
        # do not feed into hard_constraints or failure_modes.
        assert len(pack.hard_constraints) == 0
        assert len(pack.known_failure_modes) == 0

    async def test_pack_revision_pinned(self, uow_factory, vault, actor):
        """vault_revision_id matches the current vault head."""
        vid = vault.vault_id
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.vault_revision_id == vault.head_revision_id
        assert pack.vault_id == vid

    async def test_validated_objections(self, uow_factory, vault, actor):
        """Resolved CHALLENGED_BY objections appear as validated_objections."""
        vid = vault.vault_id

        # Create two pages — the original claim and the objection claim
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/original",
            title="Original",
        )
        original_claim_id = await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Original mechanism assertion",
            status=ClaimStatus.SUPPORTED,
        )

        objection_page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/objection",
            title="Objection",
        )
        objection_claim_id = await _create_claim(
            uow_factory,
            vid,
            objection_page_id,
            actor,
            statement="The original assertion breaks under load",
            status=ClaimStatus.SUPPORTED,  # resolved — now supported
        )

        # Create the CHALLENGED_BY link
        await _create_challenged_by_link(
            uow_factory,
            vid,
            actor,
            source_claim_id=original_claim_id,
            objection_claim_id=objection_claim_id,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.validated_objections) == 1
        assert "breaks under load" in pack.validated_objections[0].text

    async def test_competitive_landscape_from_authoritative(self, uow_factory, vault, actor):
        """Claims with competitive keywords from AUTHORITATIVE sources appear."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/competitive",
            title="Competitive Analysis",
        )
        claim_id = await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Our approach outperforms the state-of-the-art by 2x",
            status=ClaimStatus.SUPPORTED,
        )

        # Create an authoritative source and link it
        source_id = await _create_source_with_trust(
            uow_factory,
            vid,
            actor,
            trust_tier=SourceTrustTier.AUTHORITATIVE,
        )
        await _add_claim_support(uow_factory, claim_id, source_id, actor)

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.competitive_landscape) == 1
        assert "outperforms" in pack.competitive_landscape[0].text

    async def test_competitive_not_included_without_authoritative_source(
        self, uow_factory, vault, actor
    ):
        """Competitive keywords without AUTHORITATIVE source do not appear."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/no-auth",
            title="No Authority",
        )
        claim_id = await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Our system outperforms alternatives",
            status=ClaimStatus.SUPPORTED,
        )

        # Create a LOW trust source
        source_id = await _create_source_with_trust(
            uow_factory,
            vid,
            actor,
            trust_tier=SourceTrustTier.LOW,
        )
        await _add_claim_support(uow_factory, claim_id, source_id, actor)

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.competitive_landscape) == 0

    async def test_dossier_controversies_disabled_by_policy(self, uow_factory, vault, actor):
        """When dossier_include_unresolved_controversies=False, controversies excluded."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/no-controversy",
            title="No Controversies",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Contested claim here",
            status=ClaimStatus.CONTESTED,
        )

        policy = ExtractionPolicy(dossier_include_unresolved_controversies=False)
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.unresolved_controversies) == 0

    async def test_empty_vault_produces_empty_dossier(self, uow_factory, vault, actor):
        """An empty vault produces an empty dossier pack."""
        vid = vault.vault_id
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_constraint_dossier_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.hard_constraints == []
        assert pack.known_failure_modes == []
        assert pack.validated_objections == []
        assert pack.unresolved_controversies == []
        assert pack.competitive_landscape == []
