"""Tests for DomainContextPack extraction — the broadest channel.

Uses a real SQLite backend (no mocks) to exercise the full extraction stack.
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
    ClaimVersion,
    InventionPageMeta,
    Page,
    PageVersion,
)
from hephaestus.forgebase.domain.values import (
    ContentHash,
    Version,
)
from hephaestus.forgebase.extraction.context_pack import extract_domain_context_pack
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
    novelty_score=None,
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
            novelty_score=novelty_score,
        )
        await uow.invention_meta.create(meta)
        await uow.commit()
    return page_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContextPackExtraction:
    async def test_includes_concept_pages(self, uow_factory, vault, actor):
        """Concept page titles appear in the context pack."""
        vid = vault.vault_id
        await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/swarm",
            title="Swarm Intelligence",
            summary="Bio-inspired optimization",
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.concepts) == 1
        assert "Swarm Intelligence" in pack.concepts[0].text
        assert pack.concepts[0].origin_kind == "concept_page"

    async def test_includes_mechanism_pages(self, uow_factory, vault, actor):
        """Mechanism pages appear in the context pack."""
        vid = vault.vault_id
        await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.MECHANISM,
            page_key="mechanisms/pheromone",
            title="Pheromone Decay",
            summary="Evaporation-based load redistribution",
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.mechanisms) == 1
        assert "Pheromone Decay" in pack.mechanisms[0].text

    async def test_includes_open_questions(self, uow_factory, vault, actor):
        """Open question pages appear in the context pack."""
        vid = vault.vault_id
        await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.OPEN_QUESTION,
            page_key="questions/scaling",
            title="Does pheromone scale?",
            summary="Unknown if this scales",
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.open_questions) == 1
        assert "Does pheromone scale?" in pack.open_questions[0].text

    async def test_includes_hypothesis_claims(self, uow_factory, vault, actor):
        """Hypothesis claims on concept pages are included (broad channel)."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/hyp",
            title="Hypothesis Concept",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="A speculative hypothesis",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        # The context pack includes concept page summaries; claims affect salience
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        # The concept page should appear; hypotheses increase the claim count
        assert len(pack.concepts) == 1

    async def test_rejected_inventions_as_summaries_only(self, uow_factory, vault, actor):
        """Rejected inventions appear as summaries (title + domain), not full text."""
        vid = vault.vault_id
        # Create a rejected invention with detailed content
        page_id = await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/rejected-ctx",
            title="Failed Thermodynamic Engine",
            state=InventionEpistemicState.REJECTED,
            summary="Uses heat gradients for computation",
            source_domain="Thermodynamics",
        )
        # Add a claim (should NOT appear in the summary)
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Detailed implementation architecture for the engine",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.explored_directions) == 1
        direction = pack.explored_directions[0]
        # Summary should contain title and source domain
        assert "Failed Thermodynamic Engine" in direction.text
        assert "Thermodynamics" in direction.text
        # Should NOT contain the full claim text
        assert "Detailed implementation architecture" not in direction.text
        assert direction.origin_kind == "invention"
        assert direction.epistemic_state == "rejected"

    async def test_caps_entries_per_category(self, uow_factory, vault, actor):
        """Respects policy max counts per category."""
        vid = vault.vault_id
        # Create 5 concept pages
        for i in range(5):
            await _create_page(
                uow_factory,
                vid,
                actor,
                page_type=PageType.CONCEPT,
                page_key=f"concepts/cap-test-{i}",
                title=f"Concept {i}",
            )

        # Set max to 3
        policy = ExtractionPolicy(context_max_concepts=3)
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.concepts) == 3

    async def test_salience_ranked(self, uow_factory, vault, actor):
        """Higher-salience entries appear first within each category."""
        vid = vault.vault_id

        # Create concept pages with different claim counts (salience proxy)
        page_low = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/low-sal",
            title="Low Salience",
        )
        # 1 claim -> salience 0.2
        await _create_claim(
            uow_factory,
            vid,
            page_low,
            actor,
            statement="Claim on low-salience page",
        )

        page_high = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/high-sal",
            title="High Salience",
        )
        # 4 claims -> salience 0.8
        for i in range(4):
            await _create_claim(
                uow_factory,
                vid,
                page_high,
                actor,
                statement=f"Claim {i} on high-salience page",
            )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.concepts) == 2
        # Higher salience first
        assert pack.concepts[0].salience >= pack.concepts[1].salience
        assert "High Salience" in pack.concepts[0].text

    async def test_pack_is_revision_pinned(self, uow_factory, vault, actor):
        """vault_revision_id matches the current vault head."""
        vid = vault.vault_id
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.vault_revision_id == vault.head_revision_id
        assert pack.vault_id == vid

    async def test_verified_inventions_in_explored_directions(self, uow_factory, vault, actor):
        """VERIFIED inventions also appear in explored directions."""
        vid = vault.vault_id
        await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/verified-ctx",
            title="Verified Bio-Router",
            state=InventionEpistemicState.VERIFIED,
            source_domain="Biology",
        )

        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.explored_directions) == 1
        assert "Verified Bio-Router" in pack.explored_directions[0].text

    async def test_open_questions_disabled_by_policy(self, uow_factory, vault, actor):
        """When context_include_open_questions=False, open questions are excluded."""
        vid = vault.vault_id
        await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.OPEN_QUESTION,
            page_key="questions/disabled",
            title="Should be excluded",
        )

        policy = ExtractionPolicy(context_include_open_questions=False)
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.open_questions) == 0

    async def test_prior_directions_disabled_by_policy(self, uow_factory, vault, actor):
        """When context_include_prior_directions=False, explored directions are empty."""
        vid = vault.vault_id
        await _create_invention_page(
            uow_factory,
            vid,
            actor,
            page_key="inventions/no-dir",
            title="No Directions",
            state=InventionEpistemicState.PROPOSED,
        )

        policy = ExtractionPolicy(context_include_prior_directions=False)
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert len(pack.explored_directions) == 0

    async def test_empty_vault_produces_empty_pack(self, uow_factory, vault, actor):
        """An empty vault produces an empty context pack with all lists empty."""
        vid = vault.vault_id
        policy = ExtractionPolicy()
        uow = uow_factory()
        async with uow:
            pack = await extract_domain_context_pack(uow, vid, policy)
            await uow.rollback()

        assert pack.concepts == []
        assert pack.mechanisms == []
        assert pack.open_questions == []
        assert pack.explored_directions == []
