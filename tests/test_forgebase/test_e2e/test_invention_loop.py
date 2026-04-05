"""End-to-end closed-loop invention test — the definitive proof.

Exercises all 9 minimum flows from the spec:
  1. Genesis run -> invention page (PROPOSED)
  2. Pantheon -> REVIEWED
  3. Verification -> VERIFIED
  4. Promote claims
  5. Extract PriorArtBaselinePack
  6. Extract DomainContextPack
  7. Extract ConstraintDossierPack
  8. Render packs for injection
  9. POISONING GUARD — contested claims must NOT appear in baseline

Uses ``create_forgebase()`` with deterministic fixtures to prove the
factory wiring is correct and the full feedback loop works.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import (
    InventionEpistemicState,
    SourceFormat,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import ClaimSupport
from hephaestus.forgebase.domain.values import ActorRef
from hephaestus.forgebase.extraction.renderers import (
    render_baseline_pack_to_blocked_paths,
    render_context_pack_to_reference_context,
    render_dossier_pack_to_baseline_dossier,
)
from hephaestus.forgebase.factory import create_forgebase
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


@pytest.mark.asyncio
async def test_full_invention_loop():
    """Exercise all 9 minimum flows from the spec."""

    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(
        clock=clock,
        id_generator=id_gen,
    )

    try:
        # ---------------------------------------------------------------
        # Setup: create vault + ingest background sources for context
        # ---------------------------------------------------------------
        vault = await fb.vaults.create_vault(
            name="loop-test",
            description="Invention loop test",
        )
        vault_id = vault.vault_id

        # Ingest + compile a background source (gives vault content for extraction)
        s1, sv1 = await fb.ingest.ingest_source(
            vault_id=vault_id,
            raw_content=b"# Background\n\nExisting knowledge about load balancing approaches.",
            format=SourceFormat.MARKDOWN,
            title="Background Source",
            idempotency_key="bg1",
        )
        n1 = await fb.normalization.normalize(
            b"# Background\n\nExisting knowledge about load balancing approaches.",
            SourceFormat.MARKDOWN,
        )
        nsv1 = await fb.ingest.normalize_source(
            s1.source_id,
            n1,
            sv1.version,
            idempotency_key="n1",
        )
        clock.tick(1)
        await fb.source_compiler.compile_source(
            s1.source_id,
            nsv1.version,
            vault_id,
        )
        clock.tick(1)
        await fb.vault_synthesizer.synthesize(vault_id=vault_id)
        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 1: Genesis run -> invention page (PROPOSED) + claims
        # ---------------------------------------------------------------
        MOCK_REPORT = {
            "problem": "I need a load balancer for traffic spikes",
            "verified_inventions": [
                {
                    "invention_name": "Pheromone-Gradient Load Balancer",
                    "source_domain": "Biology - Ant Colony Foraging",
                    "mechanism": "Pheromone gradients enable decentralized routing.",
                    "mapping": "Ant -> Request, Pheromone -> Latency score",
                    "architecture": "Each server maintains pheromone level P(s,t).",
                    "roadmap": "Phase 1: Core router.",
                    "limitations": "Ants have path memory; HTTP requests don't.",
                    "novelty_score": 0.93,
                    "fidelity_score": 0.88,
                    "domain_distance": 0.91,
                },
            ],
            "total_cost_usd": 1.18,
            "models_used": ["claude-opus-4-5", "gpt-4o"],
        }

        pages = await fb.invention_ingester.ingest_invention_report(
            vault_id=vault_id,
            run_id="genesis-001",
            report=MOCK_REPORT,
        )
        assert len(pages) == 1
        inv_page_id = pages[0]

        # Verify PROPOSED state
        uow = fb.uow_factory()
        async with uow:
            meta = await uow.invention_meta.get(inv_page_id)
            assert meta is not None
            assert meta.invention_state == InventionEpistemicState.PROPOSED
            await uow.rollback()

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 2: Pantheon -> REVIEWED
        # ---------------------------------------------------------------
        MOCK_PANTHEON = {
            "final_verdict": "UNANIMOUS_CONSENSUS",
            "outcome_tier": "UNANIMOUS_CONSENSUS",
            "consensus_achieved": True,
            "canon": {
                "mandatory_constraints": ["Must handle 10K req/s"],
                "anti_goals": ["No central coordinator"],
            },
            "dossier": {
                "competitor_patterns": ["Round-robin", "Least-connections"],
                "ecosystem_constraints": ["HTTP stack compatible"],
            },
            "objection_ledger": [],
        }

        await fb.pantheon_ingester.ingest_pantheon_state(
            vault_id=vault_id,
            run_id="pantheon-001",
            state=MOCK_PANTHEON,
            invention_page_id=inv_page_id,
        )

        # Verify REVIEWED
        uow2 = fb.uow_factory()
        async with uow2:
            meta2 = await uow2.invention_meta.get(inv_page_id)
            assert meta2.invention_state == InventionEpistemicState.REVIEWED
            await uow2.rollback()

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 3: Verification -> VERIFIED
        # ---------------------------------------------------------------
        uow3 = fb.uow_factory()
        async with uow3:
            await uow3.invention_meta.update_state(
                inv_page_id,
                InventionEpistemicState.VERIFIED,
            )
            await uow3.commit()

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 4: Promote claims
        # ---------------------------------------------------------------
        # First: add ClaimSupport to make claims eligible for promotion
        uow4 = fb.uow_factory()
        async with uow4:
            claims = await uow4.claims.list_by_page(inv_page_id)
            assert len(claims) > 0, "Invention should have claims from ingestion"
            for claim in claims:
                support = ClaimSupport(
                    support_id=uow4.id_generator.support_id(),
                    claim_id=claim.claim_id,
                    source_id=s1.source_id,  # link to background source
                    source_segment="Background evidence",
                    strength=0.7,
                    created_at=clock.now(),
                    created_by=ActorRef.system(),
                )
                await uow4.claim_supports.create(support)
            await uow4.commit()

        clock.tick(1)

        result = await fb.promotion.evaluate_promotion(inv_page_id, vault_id)
        assert result.overall_eligible, (
            f"Expected eligible but got blocked: {result.blocked_claims}"
        )
        promoted = await fb.promotion.promote_claims(inv_page_id, vault_id)
        assert len(promoted) > 0, "Should have promoted at least one claim"

        clock.tick(1)

        # ---------------------------------------------------------------
        # Flow 5: Extract PriorArtBaselinePack
        # ---------------------------------------------------------------
        baseline = await fb.context_assembler.assemble_prior_art_pack(vault_id)
        # Promoted claims should now appear in the baseline
        assert len(baseline.entries) > 0, "Promoted claims should appear in baseline pack"

        # ---------------------------------------------------------------
        # Flow 6: Extract DomainContextPack
        # ---------------------------------------------------------------
        context = await fb.context_assembler.assemble_domain_context_pack(vault_id)
        total_context = (
            len(context.concepts)
            + len(context.mechanisms)
            + len(context.open_questions)
            + len(context.explored_directions)
        )
        assert total_context > 0, "Domain context should have entries"

        # ---------------------------------------------------------------
        # Flow 7: Extract ConstraintDossierPack
        # ---------------------------------------------------------------
        dossier = await fb.context_assembler.assemble_constraint_dossier_pack(vault_id)
        # May or may not have entries depending on vault content

        # ---------------------------------------------------------------
        # Flow 8: Render packs for injection
        # ---------------------------------------------------------------
        blocked_paths = render_baseline_pack_to_blocked_paths(baseline)
        ref_context = render_context_pack_to_reference_context(context)
        dossier_dict = render_dossier_pack_to_baseline_dossier(dossier)

        assert isinstance(blocked_paths, list)
        assert len(blocked_paths) > 0
        assert isinstance(ref_context, dict)
        assert "concepts" in ref_context
        assert "mechanisms" in ref_context
        assert "open_questions" in ref_context
        assert "explored_directions" in ref_context
        assert isinstance(dossier_dict, dict)
        assert "standard_approaches" in dossier_dict
        assert "common_failure_modes" in dossier_dict
        assert "known_bottlenecks" in dossier_dict

        # ---------------------------------------------------------------
        # Flow 9: POISONING GUARD
        # ---------------------------------------------------------------
        # Create a second (bad) invention
        MOCK_BAD_REPORT = {
            "problem": "Bad invention",
            "verified_inventions": [
                {
                    "invention_name": "Bad Idea Balancer",
                    "source_domain": "Bad Domain",
                    "mechanism": "This mechanism is contested and should not be in baseline.",
                    "novelty_score": 0.5,
                    "fidelity_score": 0.3,
                },
            ],
            "total_cost_usd": 0.5,
            "models_used": ["mock"],
        }

        clock.tick(1)
        bad_pages = await fb.invention_ingester.ingest_invention_report(
            vault_id=vault_id,
            run_id="genesis-bad",
            report=MOCK_BAD_REPORT,
        )
        assert len(bad_pages) == 1
        bad_page_id = bad_pages[0]

        # Mark as CONTESTED
        uow5 = fb.uow_factory()
        async with uow5:
            await uow5.invention_meta.update_state(
                bad_page_id,
                InventionEpistemicState.CONTESTED,
            )
            await uow5.commit()

        # Re-extract baseline — contested claims should NOT appear
        baseline2 = await fb.context_assembler.assemble_prior_art_pack(vault_id)

        # Collect all claim texts from the contested page
        contested_texts: set[str] = set()
        uow6 = fb.uow_factory()
        async with uow6:
            bad_claims = await uow6.claims.list_by_page(bad_page_id)
            for c in bad_claims:
                head = await uow6.claims.get_head_version(c.claim_id)
                if head:
                    contested_texts.add(head.statement)
            await uow6.rollback()

        assert len(contested_texts) > 0, "Bad invention should have claims for the guard to check"

        # Verify NO contested claim text appears in baseline
        baseline_texts = {e.text for e in baseline2.entries}
        overlap = contested_texts & baseline_texts
        assert len(overlap) == 0, (
            f"Poisoning guard failed: contested claims leaked into baseline: {overlap}"
        )

        # However, the contested invention SHOULD appear in domain context
        # (broadest channel — includes explored directions summaries)
        context2 = await fb.context_assembler.assemble_domain_context_pack(vault_id)
        direction_texts = [e.text for e in context2.explored_directions]
        # Both the good and bad invention should be in explored directions
        assert len(context2.explored_directions) >= 2, (
            f"Expected at least 2 explored directions (good + bad invention), "
            f"got {len(context2.explored_directions)}: {direction_texts}"
        )

    finally:
        await fb.close()


@pytest.mark.asyncio
async def test_rejected_invention_excluded_from_baseline():
    """REJECTED inventions must not appear in baseline pack (complementary guard)."""

    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()
    fb = await create_forgebase(clock=clock, id_generator=id_gen)

    try:
        vault = await fb.vaults.create_vault(
            name="rejection-test",
            description="Test rejection guard",
        )
        vault_id = vault.vault_id

        report = {
            "problem": "Test rejected",
            "verified_inventions": [
                {
                    "invention_name": "Rejected Idea",
                    "source_domain": "Physics",
                    "mechanism": "Perpetual motion machine for scheduling.",
                    "fidelity_score": 0.1,
                },
            ],
            "total_cost_usd": 0.1,
            "models_used": ["mock"],
        }

        pages = await fb.invention_ingester.ingest_invention_report(
            vault_id=vault_id,
            run_id="genesis-rej",
            report=report,
        )
        page_id = pages[0]

        # Reject it
        uow = fb.uow_factory()
        async with uow:
            await uow.invention_meta.update_state(
                page_id,
                InventionEpistemicState.REJECTED,
            )
            await uow.commit()

        baseline = await fb.context_assembler.assemble_prior_art_pack(vault_id)

        # Collect rejected claims
        rejected_texts: set[str] = set()
        uow2 = fb.uow_factory()
        async with uow2:
            claims = await uow2.claims.list_by_page(page_id)
            for c in claims:
                head = await uow2.claims.get_head_version(c.claim_id)
                if head:
                    rejected_texts.add(head.statement)
            await uow2.rollback()

        baseline_texts = {e.text for e in baseline.entries}
        overlap = rejected_texts & baseline_texts
        assert len(overlap) == 0, f"Rejected claims leaked into baseline: {overlap}"

    finally:
        await fb.close()
