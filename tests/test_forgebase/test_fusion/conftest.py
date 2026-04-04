"""Shared fixtures for ForgeBase fusion tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.domain.enums import BridgeCandidateKind
from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.extraction.models import DomainContextPack, PackEntry
from hephaestus.forgebase.domain.enums import ProvenanceKind
from hephaestus.forgebase.domain.values import VaultRevisionId
from hephaestus.forgebase.fusion.analyzers.mock_analyzer import MockFusionAnalyzer
from hephaestus.forgebase.fusion.models import BridgeCandidate
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def id_gen():
    """Provide a deterministic ID generator for tests."""
    return DeterministicIdGenerator()


@pytest.fixture
def mock_fusion_analyzer(id_gen):
    """Provide a MockFusionAnalyzer with deterministic IDs."""
    return MockFusionAnalyzer(id_gen=id_gen)


@pytest.fixture
def left_vault_id(id_gen) -> EntityId:
    return id_gen.vault_id()


@pytest.fixture
def right_vault_id(id_gen) -> EntityId:
    return id_gen.vault_id()


def _make_domain_context_pack(vault_id: EntityId) -> DomainContextPack:
    """Build a minimal DomainContextPack for testing."""
    return DomainContextPack(
        concepts=[
            PackEntry(
                text="Test concept",
                origin_kind="concept",
                claim_ids=[],
                page_ids=[],
                source_refs=[],
                epistemic_state="supported",
                trust_tier="standard",
                salience=0.8,
                provenance_kind=ProvenanceKind.EMPIRICAL,
            ),
        ],
        mechanisms=[],
        open_questions=[],
        explored_directions=[],
        vault_id=vault_id,
        vault_revision_id=VaultRevisionId(f"rev_{1:026d}"),
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_now(),
    )


@pytest.fixture
def left_context(left_vault_id) -> DomainContextPack:
    return _make_domain_context_pack(left_vault_id)


@pytest.fixture
def right_context(right_vault_id) -> DomainContextPack:
    return _make_domain_context_pack(right_vault_id)


def make_bridge_candidate(
    id_gen: DeterministicIdGenerator,
    left_vault_id: EntityId,
    right_vault_id: EntityId,
    similarity_score: float,
    left_text: str = "Li-ion intercalation chemistry",
    right_text: str = "Hub-spoke logistics routing",
    problem_relevance: float | None = None,
) -> BridgeCandidate:
    """Build a BridgeCandidate with the given similarity score."""
    return BridgeCandidate(
        candidate_id=id_gen.generate("bcand"),
        left_vault_id=left_vault_id,
        right_vault_id=right_vault_id,
        left_entity_ref=id_gen.page_id(),
        right_entity_ref=id_gen.page_id(),
        left_kind=BridgeCandidateKind.CONCEPT,
        right_kind=BridgeCandidateKind.MECHANISM,
        similarity_score=similarity_score,
        retrieval_reason="cosine_similarity",
        left_text=left_text,
        right_text=right_text,
        left_claim_refs=[id_gen.claim_id()],
        right_claim_refs=[id_gen.claim_id()],
        problem_relevance=problem_relevance,
    )
