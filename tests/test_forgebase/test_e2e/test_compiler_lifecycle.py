"""End-to-end compiler lifecycle test.

Exercises all 7 minimum real flows from the spec through the
factory-wired ForgeBase instance, proving Sub-project 2 works
end-to-end with the mock compiler backend.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    BranchPurpose,
    ClaimStatus,
    SourceFormat,
    SourceStatus,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.mark.asyncio
async def test_full_compiler_lifecycle():
    """Execute all 7 minimum flows from the spec end-to-end."""

    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()

    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )

    # --- Flow 1: Ingest first markdown source -> normalize -> Tier 1 ---

    source1_content = b"""# Sodium-Ion Anode Research

## Methods
Electrochemical impedance spectroscopy was used to study SEI formation.

## Results
The solid electrolyte interphase (SEI) degrades during cycling,
leading to capacity fade. SEI instability is the primary degradation
mechanism in sodium-ion anodes.

## Limitations
Only tested at room temperature.
"""

    vault = await fb.vaults.create_vault(
        name="battery-research", description="Na-ion battery vault"
    )

    # Ingest
    source1, sv1 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=source1_content,
        format=SourceFormat.MARKDOWN,
        title="Anode Research Paper",
        trust_tier=SourceTrustTier.AUTHORITATIVE,
        idempotency_key="test:source1",
    )

    # Normalize
    normalized1 = await fb.normalization.normalize(source1_content, SourceFormat.MARKDOWN)
    nsv1 = await fb.ingest.normalize_source(
        source_id=source1.source_id,
        normalized_content=normalized1,
        expected_version=sv1.version,
        idempotency_key="test:norm1",
    )
    assert nsv1.status == SourceStatus.NORMALIZED

    # Tier 1 compile
    clock.tick(1)
    manifest1 = await fb.source_compiler.compile_source(
        source_id=source1.source_id,
        source_version=nsv1.version,
        vault_id=vault.vault_id,
    )
    assert manifest1.claim_count > 0
    assert manifest1.concept_count > 0

    # --- Flow 2: Ingest second source -> Tier 1 -> shared concepts ---

    source2_content = b"""# SEI Layer Formation Dynamics

## Abstract
This paper studies the formation dynamics of the solid electrolyte
interphase in sodium-ion batteries using in-situ TEM.

## Key Findings
SEI formation follows a two-stage nucleation process. The SEI layer
composition depends on electrolyte choice.
"""

    source2, sv2 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=source2_content,
        format=SourceFormat.MARKDOWN,
        title="SEI Formation Paper",
        trust_tier=SourceTrustTier.AUTHORITATIVE,
        idempotency_key="test:source2",
    )

    normalized2 = await fb.normalization.normalize(source2_content, SourceFormat.MARKDOWN)
    nsv2 = await fb.ingest.normalize_source(
        source_id=source2.source_id,
        normalized_content=normalized2,
        expected_version=sv2.version,
        idempotency_key="test:norm2",
    )

    clock.tick(1)
    manifest2 = await fb.source_compiler.compile_source(
        source_id=source2.source_id,
        source_version=nsv2.version,
        vault_id=vault.vault_id,
    )
    assert manifest2.claim_count > 0

    # --- Flow 3: Run Tier 2 -> concept pages synthesized ---

    clock.tick(1)
    synthesis_manifest = await fb.vault_synthesizer.synthesize(
        vault_id=vault.vault_id,
    )
    assert synthesis_manifest.candidates_resolved > 0

    # --- Flow 4: Verify claim provenance chain ---
    # The synthesized concept page should have claims with INFERRED status
    # and SYNTHESIZED support type.

    uow = fb.uow_factory()
    async with uow:
        # Find concept pages
        pages = await uow.pages.list_by_vault(vault.vault_id, page_type="concept")
        assert len(pages) > 0, "Expected at least one concept page from synthesis"

        # Check one concept page has synthesized claims
        concept_page = pages[0]
        claims = await uow.claims.list_by_page(concept_page.page_id)
        assert len(claims) > 0, "Expected claims on concept page"

        for claim in claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            assert head is not None
            assert head.status == ClaimStatus.INFERRED
            assert head.support_type == SupportType.SYNTHESIZED
        await uow.rollback()  # read-only, no changes to commit

    # --- Flow 5: Verify dirty markers consumed ---

    uow2 = fb.uow_factory()
    async with uow2:
        unconsumed = await uow2.dirty_markers.count_unconsumed(vault.vault_id)
        assert unconsumed == 0, "All dirty markers should be consumed after synthesis"
        await uow2.rollback()

    # --- Flow 6: Verify no-op on re-synthesis ---

    clock.tick(1)
    synthesis_manifest2 = await fb.vault_synthesizer.synthesize(
        vault_id=vault.vault_id,
    )
    # No new dirty markers, so no new work should be done
    assert synthesis_manifest2.candidates_resolved == 0

    # --- Flow 7: Compile on workbook branch -> branch-scoped ---

    workbook = await fb.branches.create_workbook(
        vault_id=vault.vault_id,
        name="branch-compile-test",
        purpose=BranchPurpose.COMPILATION,
    )

    source3_content = b"""# New Branch Source
Some branch-only research content about SEI dynamics.
"""
    source3, sv3 = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=source3_content,
        format=SourceFormat.MARKDOWN,
        title="Branch Source",
        workbook_id=workbook.workbook_id,
        idempotency_key="test:source3",
    )

    normalized3 = await fb.normalization.normalize(source3_content, SourceFormat.MARKDOWN)
    nsv3 = await fb.ingest.normalize_source(
        source_id=source3.source_id,
        normalized_content=normalized3,
        expected_version=sv3.version,
        workbook_id=workbook.workbook_id,
        idempotency_key="test:norm3",
    )

    clock.tick(1)
    branch_manifest = await fb.source_compiler.compile_source(
        source_id=source3.source_id,
        source_version=nsv3.version,
        vault_id=vault.vault_id,
        workbook_id=workbook.workbook_id,
    )
    assert branch_manifest.workbook_id == workbook.workbook_id

    # Verify branch-scoped: concept candidates should have workbook_id
    uow3 = fb.uow_factory()
    async with uow3:
        branch_candidates = await uow3.concept_candidates.list_active(
            vault.vault_id,
            workbook.workbook_id,
        )
        for c in branch_candidates:
            assert c.workbook_id == workbook.workbook_id
        await uow3.rollback()

    # Merge to canonical
    proposal = await fb.merge.propose_merge(workbook_id=workbook.workbook_id)
    new_revision = await fb.merge.execute_merge(merge_id=proposal.merge_id)
    assert new_revision is not None

    await fb.close()
