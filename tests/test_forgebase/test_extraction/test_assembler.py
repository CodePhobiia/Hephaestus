"""Tests for VaultContextAssembler — orchestrates extraction of all three packs.

Uses a real SQLite backend (no mocks) through the extraction conftest.
"""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
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
from hephaestus.forgebase.domain.values import ContentHash, Version
from hephaestus.forgebase.extraction.assembler import VaultContextAssembler
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.extraction.policy import ExtractionPolicy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_page(uow_factory, vault_id, actor, *, page_type, page_key, title, summary=""):
    """Create a page and return its page_id."""
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
    """Create a claim and return its claim_id."""
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
class TestVaultContextAssembler:
    async def test_assembler_produces_all_three_packs(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """assemble_all returns a 3-tuple of the correct pack types."""
        vid = vault.vault_id
        assembler = VaultContextAssembler(uow_factory)

        baseline, context, dossier = await assembler.assemble_all(vid)

        assert isinstance(baseline, PriorArtBaselinePack)
        assert isinstance(context, DomainContextPack)
        assert isinstance(dossier, ConstraintDossierPack)

    async def test_assembler_uses_custom_policy(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """Custom policy is respected — e.g. including hypotheses in baseline."""
        vid = vault.vault_id

        # Create a concept page with a HYPOTHESIS claim
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/custom-policy",
            title="Custom Policy Concept",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Hypothesis claim via custom policy",
            status=ClaimStatus.HYPOTHESIS,
            support_type=SupportType.GENERATED,
        )

        # Default policy excludes hypothesis from baseline
        default_assembler = VaultContextAssembler(uow_factory)
        baseline_default = await default_assembler.assemble_prior_art_pack(vid)
        assert len(baseline_default.entries) == 0

        # Custom policy includes hypothesis in baseline
        custom_policy = ExtractionPolicy(baseline_include_hypothesis=True)
        custom_assembler = VaultContextAssembler(uow_factory, policy=custom_policy)
        baseline_custom = await custom_assembler.assemble_prior_art_pack(vid)
        assert len(baseline_custom.entries) == 1

    async def test_assembler_individual_methods(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """Each individual method returns the correct type."""
        vid = vault.vault_id
        assembler = VaultContextAssembler(uow_factory)

        baseline = await assembler.assemble_prior_art_pack(vid)
        context = await assembler.assemble_domain_context_pack(vid)
        dossier = await assembler.assemble_constraint_dossier_pack(vid)

        assert isinstance(baseline, PriorArtBaselinePack)
        assert isinstance(context, DomainContextPack)
        assert isinstance(dossier, ConstraintDossierPack)

    async def test_assembler_empty_vault(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """Empty vault produces empty packs without errors."""
        vid = vault.vault_id
        assembler = VaultContextAssembler(uow_factory)

        baseline, context, dossier = await assembler.assemble_all(vid)

        assert len(baseline.entries) == 0
        assert len(context.concepts) == 0
        assert len(context.mechanisms) == 0
        assert len(context.open_questions) == 0
        assert len(context.explored_directions) == 0
        assert len(dossier.hard_constraints) == 0
        assert len(dossier.known_failure_modes) == 0

    async def test_assembler_baseline_has_supported_claims(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """Baseline pack contains SUPPORTED claims from concept pages."""
        vid = vault.vault_id
        page_id = await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/assembler-test",
            title="Assembler Test Concept",
        )
        await _create_claim(
            uow_factory,
            vid,
            page_id,
            actor,
            statement="Supported claim for assembler test",
            status=ClaimStatus.SUPPORTED,
        )

        assembler = VaultContextAssembler(uow_factory)
        baseline = await assembler.assemble_prior_art_pack(vid)

        assert len(baseline.entries) == 1
        assert baseline.entries[0].text == "Supported claim for assembler test"

    async def test_assembler_context_has_concepts(
        self,
        uow_factory,
        vault,
        actor,
    ):
        """Domain context pack contains concept pages."""
        vid = vault.vault_id
        await _create_page(
            uow_factory,
            vid,
            actor,
            page_type=PageType.CONCEPT,
            page_key="concepts/ctx-test",
            title="Context Test Concept",
            summary="A concept for context testing",
        )

        assembler = VaultContextAssembler(uow_factory)
        context = await assembler.assemble_domain_context_pack(vid)

        assert len(context.concepts) == 1
        assert "Context Test Concept" in context.concepts[0].text
