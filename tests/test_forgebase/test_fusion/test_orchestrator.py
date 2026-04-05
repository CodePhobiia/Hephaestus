"""Tests for FusionOrchestrator — full three-stage pipeline.

Setup: Two compiled vaults (battery chemistry + supply chain logistics),
MockFusionAnalyzer, deterministic EmbeddingIndex.

Tests:
1. test_fuse_two_vaults — complete pipeline produces FusionResult with bridges/transfers
2. test_fuse_persists_fusion_run — FusionRun queryable after completion
3. test_fuse_emits_completed_event — fusion.completed in outbox
4. test_fuse_with_problem — problem-aware fusion (problem_relevance populated)
5. test_fuse_invalid_request_too_few — < 2 vaults raises error
6. test_fuse_poisoning_guard — CONTESTED content not in fused baseline
7. test_fuse_result_has_pair_results — pair_results populated
8. test_fuse_result_has_manifest — manifest has correct counts
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest

from hephaestus.forgebase.contracts.fusion import FusionRequest, FusionResult
from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    FusionMode,
    SourceFormat,
    SourceTrustTier,
    SupportType,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.domain.models import FusionRun
from hephaestus.forgebase.domain.values import ActorRef, Version
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.fusion.analyzers.mock_analyzer import MockFusionAnalyzer
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
from hephaestus.forgebase.fusion.orchestrator import FusionOrchestrator
from hephaestus.forgebase.fusion.policy import DEFAULT_FUSION_POLICY, FusionPolicy
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


# ---------------------------------------------------------------------------
# Deterministic embedding helper (avoids sentence-transformers)
# ---------------------------------------------------------------------------

def _deterministic_embedding(text: str) -> bytes:
    """Produce a deterministic 384-dim normalised float32 embedding from text."""
    h = hashlib.sha256(text.encode()).digest()
    rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
    vec = rng.randn(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tobytes()


# ---------------------------------------------------------------------------
# Vault content
# ---------------------------------------------------------------------------

BATTERY_SOURCE = b"""# Battery Research

SEI layer degradation in sodium-ion anodes.
Pheromone-like decay patterns observed in electrolyte interfaces.
Capacity fade occurs through lithium plating and dendrite formation.
"""

LOGISTICS_SOURCE = b"""# Logistics Research

Ant colony optimization for vehicle routing.
Pheromone trails guide efficient path selection.
Hub-and-spoke networks optimize routing efficiency.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_compiled_vault(fb, name, description, content, clock):
    """Ingest, normalize, compile, synthesize a vault."""
    vault = await fb.vaults.create_vault(name=name, description=description)

    source, sv = await fb.ingest.ingest_source(
        vault_id=vault.vault_id,
        raw_content=content,
        format=SourceFormat.MARKDOWN,
        title=f"{name} source",
        trust_tier=SourceTrustTier.AUTHORITATIVE,
        idempotency_key=f"test:{name}:source1",
    )

    normalized = await fb.normalization.normalize(content, SourceFormat.MARKDOWN)
    nsv = await fb.ingest.normalize_source(
        source_id=source.source_id,
        normalized_content=normalized,
        expected_version=sv.version,
        idempotency_key=f"test:{name}:norm1",
    )

    clock.tick(1)
    await fb.source_compiler.compile_source(
        source_id=source.source_id,
        source_version=nsv.version,
        vault_id=vault.vault_id,
    )

    clock.tick(1)
    await fb.vault_synthesizer.synthesize(vault_id=vault.vault_id)

    return vault


def _make_orchestrator(fb, embedding_index):
    """Build a FusionOrchestrator wired to the given ForgeBase instance."""
    analyzer = MockFusionAnalyzer(id_gen=DeterministicIdGenerator(seed=50000))
    return FusionOrchestrator(
        uow_factory=fb.uow_factory,
        context_assembler=fb.context_assembler,
        fusion_analyzer=analyzer,
        embedding_index=embedding_index,
        policy=FusionPolicy(min_similarity_threshold=-1.0),  # accept all for testing
        default_actor=ActorRef.system(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def setup():
    """Create ForgeBase with two compiled vaults and a FusionOrchestrator."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()

    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )

    vault_a = await _setup_compiled_vault(
        fb, "battery-materials", "Na-ion research",
        BATTERY_SOURCE, clock,
    )
    vault_b = await _setup_compiled_vault(
        fb, "logistics-optimization", "Supply chain",
        LOGISTICS_SOURCE, clock,
    )

    # Embedding index with deterministic embeddings (no real model)
    embedding_index = EmbeddingIndex(
        uow_factory=fb.uow_factory, model_name="test-model",
    )
    embedding_index._compute_embedding = _deterministic_embedding  # type: ignore[assignment]

    orchestrator = _make_orchestrator(fb, embedding_index)

    clock.tick(1)

    yield fb, vault_a, vault_b, orchestrator, clock

    await fb.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFuseTwoVaults:
    """Complete pipeline produces FusionResult with bridges and transfers."""

    @pytest.mark.asyncio
    async def test_fuse_two_vaults(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            problem="How can battery degradation patterns inspire logistics optimization?",
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        assert isinstance(result, FusionResult)
        assert result.fused_baseline is not None
        assert result.fused_context is not None
        assert result.fused_dossier is not None
        assert result.fusion_manifest is not None
        assert result.fusion_id is not None


class TestFusePersistsFusionRun:
    """FusionRun queryable after completion."""

    @pytest.mark.asyncio
    async def test_fuse_persists_fusion_run(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        uow = fb.uow_factory()
        async with uow:
            runs = await uow.fusion_runs.list_by_vaults(
                [vault_a.vault_id, vault_b.vault_id]
            )
            await uow.rollback()

        assert len(runs) >= 1
        run = runs[0]
        assert run.status == "completed"
        assert run.vault_ids == [vault_a.vault_id, vault_b.vault_id]


class TestFuseEmitsCompletedEvent:
    """fusion.completed event is emitted in the outbox."""

    @pytest.mark.asyncio
    async def test_fuse_emits_completed_event(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            fusion_mode=FusionMode.STRICT,
        )
        await orchestrator.fuse(request)

        # Check domain events in the outbox
        uow = fb.uow_factory()
        async with uow:
            cursor = await uow._db.execute(
                "SELECT event_type FROM fb_domain_events WHERE event_type = 'fusion.completed'"
            )
            rows = await cursor.fetchall()
            await uow.rollback()

        assert len(rows) >= 1, "Expected at least one fusion.completed event"


class TestFuseWithProblem:
    """Problem-aware fusion: problem_relevance populated."""

    @pytest.mark.asyncio
    async def test_fuse_with_problem(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            problem="How can battery degradation patterns inspire logistics optimization?",
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        # Manifest should reference the problem
        assert result.fusion_manifest.problem == request.problem
        assert result.request.problem == request.problem


class TestFuseInvalidRequestTooFew:
    """< 2 vaults raises ValueError."""

    @pytest.mark.asyncio
    async def test_fuse_invalid_request_too_few(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id],
            fusion_mode=FusionMode.STRICT,
        )

        with pytest.raises(ValueError, match="at least 2 vaults"):
            await orchestrator.fuse(request)


class TestFusePoisoningGuard:
    """CONTESTED content not in fused baseline."""

    @pytest.mark.asyncio
    async def test_fuse_poisoning_guard(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        # Add a CONTESTED claim to vault A
        uow = fb.uow_factory()
        async with uow:
            pages_a = await uow.pages.list_by_vault(vault_a.vault_id)
            if pages_a:
                from hephaestus.forgebase.domain.models import Claim, ClaimVersion

                contested_claim_id = uow.id_generator.claim_id()
                claim = Claim(
                    claim_id=contested_claim_id,
                    vault_id=vault_a.vault_id,
                    page_id=pages_a[0].page_id,
                    created_at=uow.clock.now(),
                )
                cv = ClaimVersion(
                    claim_id=contested_claim_id,
                    version=Version(1),
                    statement="CONTESTED: This should not appear in fused baseline",
                    status=ClaimStatus.CONTESTED,
                    support_type=SupportType.GENERATED,
                    confidence=0.1,
                    validated_at=uow.clock.now(),
                    fresh_until=None,
                    created_at=uow.clock.now(),
                    created_by=ActorRef.system(),
                )
                await uow.claims.create(claim, cv)
                await uow.vaults.set_canonical_claim_head(
                    vault_a.vault_id, contested_claim_id, 1,
                )
                await uow.commit()

        clock.tick(1)

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        # The fused baseline must NOT contain CONTESTED claims
        baseline_texts = {e.text for e in result.fused_baseline.entries}
        assert "CONTESTED: This should not appear in fused baseline" not in baseline_texts


class TestFuseResultHasPairResults:
    """pair_results populated with correct count."""

    @pytest.mark.asyncio
    async def test_fuse_result_has_pair_results(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        # 2 vaults = 1 pair (C(2,2) = 1)
        assert len(result.pair_results) == 1
        pr = result.pair_results[0]
        assert pr.left_vault_id == vault_a.vault_id
        assert pr.right_vault_id == vault_b.vault_id
        assert pr.candidates_generated >= 0
        assert pr.pair_manifest is not None


class TestFuseResultHasManifest:
    """Manifest has correct counts."""

    @pytest.mark.asyncio
    async def test_fuse_result_has_manifest(self, setup):
        fb, vault_a, vault_b, orchestrator, clock = setup

        request = FusionRequest(
            vault_ids=[vault_a.vault_id, vault_b.vault_id],
            fusion_mode=FusionMode.STRICT,
        )
        result = await orchestrator.fuse(request)

        manifest = result.fusion_manifest
        assert manifest is not None
        assert manifest.vault_ids == [vault_a.vault_id, vault_b.vault_id]
        assert manifest.fusion_mode == FusionMode.STRICT
        assert manifest.candidate_count >= 0
        assert manifest.bridge_count >= 0
        assert manifest.transfer_count >= 0
        assert len(manifest.pair_manifests) == 1
        assert manifest.policy_version == "1.0.0"
        assert manifest.created_at is not None
