"""Tests for PriorArtBaselinePack extraction — the strictest channel.

Uses a real SQLite backend (no mocks) to exercise the full extraction stack.
Every test builds its scenario from scratch using the UoW layer.
"""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    PageType,
    ProvenanceKind,
    SupportType,
)
from hephaestus.forgebase.domain.models import (
    Claim,
    ClaimVersion,
    InventionPageMeta,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ContentHash,
    Version,
)
from hephaestus.forgebase.extraction.baseline_pack import extract_baseline_pack
from hephaestus.forgebase.extraction.policy import ExtractionPolicy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_page(uow_factory, vault_id, actor, *, page_type, page_key, title, summary=""):
    """Create a page of the given type, return page_id."""
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
    """Create a claim on a page, return claim_id."""
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


async def _create_invention_page(
    uow_factory,
    vault_id,
    actor,
    *,
    page_key,
    title,
    state,
    summary="",
    source_domain=None,
):
    """Create an INVENTION page + InventionPageMeta, return page_id."""
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
            source_domain=source_domain,
        )
        await uow.invention_meta.create(meta)
        await uow.commit()
    return page_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBaselinePackExtraction:
    async def test_includes_supported_claims(self, uow_factory, vault, actor):
        """SUPPORTED claims from concept pages appear in the baseline pack."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/ant-colony",
            title="Ant Colony Optimization",
        )
        claim_id = await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Pheromone evaporation prevents stagnation",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 1
        assert pack.entries[0].text == "Pheromone evaporation prevents stagnation"
        assert pack.entries[0].origin_kind == "concept_page"

    async def test_excludes_hypothesis_claims(self, uow_factory, vault, actor):
        """HYPOTHESIS claims do NOT appear in the baseline pack (default policy)."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/hypothesis-test",
            title="Some Concept",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="This is a hypothesis",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 0

    async def test_excludes_contested_claims(self, uow_factory, vault, actor):
        """CONTESTED claims do NOT appear in the baseline pack (default policy)."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.MECHANISM,
            page_key="mechanisms/contested",
            title="Some Mechanism",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="This claim is contested",
            status=ClaimStatus.CONTESTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 0

    async def test_includes_verified_inventions(self, uow_factory, vault, actor):
        """VERIFIED invention claims with SUPPORTED status appear."""
        vid = vault.vault_id
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/verified-1",
            title="Verified Invention",
            state=InventionEpistemicState.VERIFIED,
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Verified mechanism claim",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        invention_entries = [e for e in pack.entries if e.origin_kind == "invention"]
        assert len(invention_entries) == 1
        assert invention_entries[0].text == "Verified mechanism claim"

    async def test_excludes_rejected_inventions(self, uow_factory, vault, actor):
        """REJECTED invention claims do NOT appear in baseline pack."""
        vid = vault.vault_id
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/rejected-1",
            title="Rejected Invention",
            state=InventionEpistemicState.REJECTED,
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Rejected claim",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        # The REJECTED page should NOT have its claims in baseline
        invention_entries = [e for e in pack.entries if e.origin_kind == "invention"]
        assert len(invention_entries) == 0

    async def test_pack_is_revision_pinned(self, uow_factory, vault, actor):
        """vault_revision_id matches the current vault head."""
        vid = vault.vault_id
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.vault_revision_id == vault.head_revision_id
        assert pack.vault_id == vid

    async def test_entries_have_typed_structure(self, uow_factory, vault, actor):
        """PackEntry fields are populated with correct types."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/typed-test",
            title="Typed Test",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="A structured claim",
            status=ClaimStatus.SUPPORTED,
            support_type=SupportType.DIRECT,
            confidence=0.85,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 1
        entry = pack.entries[0]
        assert isinstance(entry.text, str)
        assert isinstance(entry.origin_kind, str)
        assert isinstance(entry.claim_ids, list)
        assert isinstance(entry.page_ids, list)
        assert isinstance(entry.source_refs, list)
        assert isinstance(entry.epistemic_state, str)
        assert isinstance(entry.trust_tier, str)
        assert isinstance(entry.salience, float)
        assert isinstance(entry.provenance_kind, ProvenanceKind)
        assert entry.epistemic_state == "supported"
        assert entry.salience == 0.85
        assert entry.provenance_kind == ProvenanceKind.EMPIRICAL

    async def test_verified_invention_hypothesis_excluded(self, uow_factory, vault, actor):
        """VERIFIED invention with HYPOTHESIS claims still excludes them."""
        vid = vault.vault_id
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/verified-hyp",
            title="Verified With Hypothesis",
            state=InventionEpistemicState.VERIFIED,
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Still a hypothesis",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 0

    async def test_policy_override_includes_hypothesis(self, uow_factory, vault, actor):
        """When policy.baseline_include_hypothesis=True, HYPOTHESIS claims pass."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/hyp-override",
            title="Hypothesis Override",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Hypothesis via override",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        policy = ExtractionPolicy(baseline_include_hypothesis=True)
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 1
        assert pack.entries[0].text == "Hypothesis via override"

    async def test_extraction_policy_version_in_pack(self, uow_factory, vault, actor):
        """Pack carries the extraction policy version and assembler version."""
        vid = vault.vault_id
        policy = ExtractionPolicy(policy_version="2.0.0", assembler_version="1.1.0")
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.extraction_policy_version == "2.0.0"
        assert pack.assembler_version == "1.1.0"

    async def test_mechanism_page_claims_included(self, uow_factory, vault, actor):
        """SUPPORTED claims from mechanism pages also appear."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.MECHANISM,
            page_key="mechanisms/test-mech",
            title="Test Mechanism",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Mechanism claim",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.entries) == 1
        assert pack.entries[0].origin_kind == "mechanism_page"

    async def test_contested_invention_excluded(self, uow_factory, vault, actor):
        """CONTESTED invention state does not produce baseline entries."""
        vid = vault.vault_id
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/contested-inv",
            title="Contested Invention",
            state=InventionEpistemicState.CONTESTED,
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Supported claim on contested invention",
            status=ClaimStatus.SUPPORTED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_baseline_pack(uow, vid, policy)
            await uow.rollback()

        invention_entries = [e for e in pack.entries if e.origin_kind == "invention"]
        assert len(invention_entries) == 0
