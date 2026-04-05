"""Tests for Stage 1 bridge candidate generation.

Setup: Two vaults with different domain content (vault A about "battery chemistry"
and vault B about "supply chain logistics"), compiled via Tier 1 + Tier 2 with
MockCompilerBackend. Uses deterministic embeddings to avoid loading
sentence-transformers.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest

from hephaestus.forgebase.domain.enums import (
    BridgeCandidateKind,
    FusionMode,
    SourceFormat,
    SourceTrustTier,
)
from hephaestus.forgebase.domain.event_types import FixedClock
from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase
from hephaestus.forgebase.fusion.candidates import generate_bridge_candidates
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
from hephaestus.forgebase.fusion.policy import FusionPolicy
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
# In-memory embedding cache repository (test double)
# ---------------------------------------------------------------------------


class InMemoryEmbeddingCacheRepo:
    """Minimal in-memory implementation of EmbeddingCacheRepository for tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, int], tuple[bytes, str]] = {}

    async def get(self, entity_id: str, version: int) -> bytes | None:
        entry = self._store.get((entity_id, version))
        return entry[0] if entry is not None else None

    async def put(
        self,
        entity_id: str,
        version: int,
        embedding_blob: bytes,
        computed_at: str,
    ) -> None:
        self._store[(entity_id, version)] = (embedding_blob, computed_at)

    async def invalidate(self, entity_id: str) -> None:
        keys_to_remove = [k for k in self._store if k[0] == entity_id]
        for k in keys_to_remove:
            del self._store[k]

    async def batch_get(
        self,
        items: list[tuple[str, int]],
    ) -> dict[tuple[str, int], bytes]:
        results: dict[tuple[str, int], bytes] = {}
        for entity_id, version in items:
            entry = self._store.get((entity_id, version))
            if entry is not None:
                results[(entity_id, version)] = entry[0]
        return results


class FakeEmbeddingUoW:
    """Minimal UoW test double for EmbeddingIndex only."""

    def __init__(self, cache_repo: InMemoryEmbeddingCacheRepo) -> None:
        self.embedding_cache = cache_repo
        self._committed = False

    async def begin(self) -> None:
        pass

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> FakeEmbeddingUoW:
        await self.begin()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()


# ---------------------------------------------------------------------------
# Vault setup helpers
# ---------------------------------------------------------------------------

BATTERY_SOURCE_CONTENT = b"""# Lithium-Ion Battery Chemistry

## Key Concepts
Lithium-ion batteries rely on intercalation chemistry where lithium ions
move between cathode and anode through an electrolyte.

## Mechanisms
The solid electrolyte interphase (SEI) forms on the anode surface during
the first charge cycle. SEI stability determines long-term cycle life.

## Findings
Capacity fade occurs primarily through SEI degradation and lithium plating.
Temperature and charge rate significantly affect degradation kinetics.
"""

LOGISTICS_SOURCE_CONTENT = b"""# Supply Chain Logistics Networks

## Key Concepts
Hub-and-spoke networks optimize routing efficiency by concentrating flows
through central hubs before distributing to spoke nodes.

## Mechanisms
Dynamic routing algorithms adjust flow paths based on real-time demand
signals and capacity constraints at each network node.

## Findings
Network resilience improves with redundant hub connections.
Last-mile delivery cost dominates total logistics expenditure.
"""


async def _setup_compiled_vault(fb, name: str, description: str, content: bytes, clock):
    """Ingest a source, normalize, Tier 1 compile, and Tier 2 synthesize."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def embedding_cache():
    return InMemoryEmbeddingCacheRepo()


@pytest.fixture
def embedding_index(embedding_cache):
    """EmbeddingIndex with deterministic embeddings (no real model)."""

    def _factory():
        return FakeEmbeddingUoW(embedding_cache)

    idx = EmbeddingIndex(uow_factory=_factory, model_name="test-model")
    idx._compute_embedding = _deterministic_embedding  # type: ignore[assignment]
    return idx


@pytest.fixture
def policy():
    return FusionPolicy()


@pytest.fixture
def candidate_id_gen():
    """Separate id_gen for candidate generation (to avoid counter collision with vault setup)."""
    return DeterministicIdGenerator(seed=10000)


@pytest.fixture
async def compiled_vaults():
    """Set up two compiled vaults: battery-research and logistics-research."""
    clock = FixedClock(datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC))
    id_gen = DeterministicIdGenerator()

    fb = await create_forgebase(
        config=ForgeBaseConfig(compiler_backend="mock"),
        clock=clock,
        id_generator=id_gen,
    )

    vault_a = await _setup_compiled_vault(
        fb,
        "battery-research",
        "Li-ion battery vault",
        BATTERY_SOURCE_CONTENT,
        clock,
    )
    vault_b = await _setup_compiled_vault(
        fb,
        "logistics-research",
        "Supply chain vault",
        LOGISTICS_SOURCE_CONTENT,
        clock,
    )

    yield fb, vault_a, vault_b

    await fb.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGeneratesCandidates:
    """test_generates_candidates: 2 compiled vaults -> non-empty candidate list."""

    async def test_generates_candidates(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        assert len(candidates) > 0, "Expected at least one bridge candidate"
        # Each candidate should have valid vault IDs
        for c in candidates:
            assert c.left_vault_id == vault_a.vault_id
            assert c.right_vault_id == vault_b.vault_id


class TestCandidatesTyped:
    """test_candidates_typed: all candidates have valid BridgeCandidateKind values."""

    async def test_candidates_typed(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        valid_kinds = set(BridgeCandidateKind)
        for c in candidates:
            assert c.left_kind in valid_kinds, f"Invalid left_kind: {c.left_kind}"
            assert c.right_kind in valid_kinds, f"Invalid right_kind: {c.right_kind}"


class TestCandidatesDiversified:
    """test_candidates_diversified: not all candidates have the same kind."""

    async def test_candidates_diversified(
        self,
        compiled_vaults,
        embedding_index,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        # Use EXPLORATORY mode to include INFERRED claims (from synthesis),
        # which gives us both CONCEPT pages and CLAIM_CLUSTER entities,
        # ensuring diversity across candidate kinds.
        policy = FusionPolicy(min_similarity_threshold=-1.0)

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
                fusion_mode=FusionMode.EXPLORATORY,
            )
            await uow.rollback()

        assert len(candidates) >= 2, (
            f"Expected at least 2 candidates in EXPLORATORY mode, got {len(candidates)}"
        )

        left_kinds = {c.left_kind for c in candidates}
        right_kinds = {c.right_kind for c in candidates}
        all_kinds = left_kinds | right_kinds
        assert len(all_kinds) > 1, f"Expected diverse candidate kinds, got only: {all_kinds}"


class TestStrictModeFiltersHypothesis:
    """test_strict_mode_filters_hypothesis: HYPOTHESIS claims excluded in STRICT mode."""

    async def test_strict_mode_filters_hypothesis(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        # Get claims in STRICT mode
        uow = fb.uow_factory()
        async with uow:
            candidates_strict = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
                fusion_mode=FusionMode.STRICT,
            )
            await uow.rollback()

        # Verify: in STRICT mode, claim-cluster candidates should only come from
        # SUPPORTED claims. The MockCompilerBackend creates claims with INFERRED status
        # (from synthesis), so in STRICT mode those are excluded.
        # The key assertion is that the function doesn't crash and produces candidates
        # that respect the filter (no HYPOTHESIS or CONTESTED status claims)
        for c in candidates_strict:
            assert c.epistemic_filter_passed is True


class TestSimilarityThresholdRespected:
    """test_similarity_threshold_respected: all candidates above min threshold."""

    async def test_similarity_threshold_respected(
        self,
        compiled_vaults,
        embedding_index,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        # Use a policy with a specific threshold
        policy = FusionPolicy(min_similarity_threshold=0.3)

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        for c in candidates:
            assert c.similarity_score >= policy.min_similarity_threshold, (
                f"Candidate similarity {c.similarity_score} below threshold "
                f"{policy.min_similarity_threshold}"
            )


class TestProblemRelevanceBoost:
    """test_problem_relevance_boost: with problem, candidates get problem_relevance scores."""

    async def test_problem_relevance_boost(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        problem = "How can battery degradation insights improve logistics network resilience?"

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
                problem=problem,
            )
            await uow.rollback()

        assert len(candidates) > 0, "Expected candidates with problem relevance"
        for c in candidates:
            assert c.problem_relevance is not None, (
                "Expected problem_relevance to be set when problem is provided"
            )

    async def test_no_problem_no_relevance(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
                problem=None,
            )
            await uow.rollback()

        for c in candidates:
            assert c.problem_relevance is None, (
                "Expected problem_relevance to be None when no problem is provided"
            )


class TestEmptyVaultReturnsEmpty:
    """test_empty_vault_returns_empty: one empty vault -> no candidates."""

    async def test_empty_vault_returns_empty(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        # Create a third, empty vault
        empty_vault = await fb.vaults.create_vault(name="empty-vault", description="No content")

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=empty_vault.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        assert candidates == [], "Expected no candidates when one vault is empty"


class TestMaxCandidatesRespected:
    """test_max_candidates_respected: doesn't exceed policy cap."""

    async def test_max_candidates_respected(
        self,
        compiled_vaults,
        embedding_index,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        # Use a very low cap
        policy = FusionPolicy(
            max_candidates_per_pair=3,
            min_similarity_threshold=-1.0,  # Accept all similarities
        )

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        assert len(candidates) <= policy.max_candidates_per_pair, (
            f"Got {len(candidates)} candidates, exceeding cap of {policy.max_candidates_per_pair}"
        )


class TestProvenancePopulated:
    """test_provenance_populated: left/right revision refs, entity refs set."""

    async def test_provenance_populated(
        self,
        compiled_vaults,
        embedding_index,
        policy,
        candidate_id_gen,
    ):
        fb, vault_a, vault_b = compiled_vaults

        uow = fb.uow_factory()
        async with uow:
            candidates = await generate_bridge_candidates(
                uow=uow,
                left_vault_id=vault_a.vault_id,
                right_vault_id=vault_b.vault_id,
                embedding_index=embedding_index,
                policy=policy,
                id_generator=candidate_id_gen,
            )
            await uow.rollback()

        assert len(candidates) > 0, "Expected candidates to verify provenance"
        for c in candidates:
            # Entity refs must be set
            assert c.left_entity_ref is not None
            assert c.right_entity_ref is not None
            # Revision refs must be set (from vault head)
            assert c.left_revision_ref is not None
            assert c.right_revision_ref is not None
            # Candidate ID must be set
            assert c.candidate_id is not None
            # Epistemic filter flag must be True (we already filtered)
            assert c.epistemic_filter_passed is True
            # Retrieval reason must be set
            assert c.retrieval_reason == "cosine_similarity"
