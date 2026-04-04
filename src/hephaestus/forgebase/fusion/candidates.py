"""Stage 1 bridge candidate generation — typed, diversified cross-vault selection.

Generates bridge candidates by:
1. Extracting pages + claims from both vaults
2. Applying epistemic filters (STRICT vs EXPLORATORY)
3. Classifying entities by BridgeCandidateKind
4. Computing/retrieving embeddings via EmbeddingIndex
5. Cross-vault cosine similarity (numpy)
6. Optional problem-relevance boosting
7. Diversified selection by type allocation + similarity bands
8. Building BridgeCandidates with provenance
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from hephaestus.forgebase.domain.enums import (
    BridgeCandidateKind,
    ClaimStatus,
    FusionMode,
    PageType,
)
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId, Version
from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
from hephaestus.forgebase.fusion.models import BridgeCandidate
from hephaestus.forgebase.fusion.policy import FusionPolicy
from hephaestus.forgebase.repository.uow import AbstractUnitOfWork
from hephaestus.forgebase.service.id_generator import IdGenerator


# ---------------------------------------------------------------------------
# Internal entity representation
# ---------------------------------------------------------------------------

@dataclass
class _VaultEntity:
    """Internal representation of an extracted vault entity for candidate generation."""

    entity_id: EntityId
    version: Version
    text: str
    kind: BridgeCandidateKind
    claim_refs: list[EntityId]
    source_refs: list[EntityId]


# ---------------------------------------------------------------------------
# Page type -> BridgeCandidateKind classification
# ---------------------------------------------------------------------------

_PAGE_TYPE_TO_KIND: dict[PageType, BridgeCandidateKind] = {
    PageType.CONCEPT: BridgeCandidateKind.CONCEPT,
    PageType.MECHANISM: BridgeCandidateKind.MECHANISM,
    PageType.COMPARISON: BridgeCandidateKind.PAGE_THEME,
    PageType.TIMELINE: BridgeCandidateKind.PAGE_THEME,
    PageType.OPEN_QUESTION: BridgeCandidateKind.PAGE_THEME,
    PageType.EXPERIMENT: BridgeCandidateKind.PAGE_THEME,
    PageType.INVENTION: BridgeCandidateKind.PAGE_THEME,
    PageType.PROBLEM: BridgeCandidateKind.PAGE_THEME,
}

# Page types to skip entirely (source infrastructure, not knowledge)
_SKIP_PAGE_TYPES: set[PageType] = {
    PageType.SOURCE_INDEX,
    PageType.SOURCE_CARD,
}

# Claim statuses that pass epistemic filter in STRICT mode
_STRICT_CLAIM_STATUSES: set[ClaimStatus] = {
    ClaimStatus.SUPPORTED,
}

# Claim statuses excluded even in EXPLORATORY mode
_EXPLORATORY_EXCLUDED_STATUSES: set[ClaimStatus] = {
    ClaimStatus.CONTESTED,
    ClaimStatus.STALE,
}


# ---------------------------------------------------------------------------
# Step 1-2: Entity extraction
# ---------------------------------------------------------------------------

async def _extract_entities(
    uow: AbstractUnitOfWork,
    vault_id: EntityId,
    fusion_mode: FusionMode,
) -> list[_VaultEntity]:
    """Extract entities from a vault, filtered by epistemic mode.

    STRICT mode: concept/mechanism pages + SUPPORTED claims only.
    EXPLORATORY mode: broader page types + SUPPORTED/INFERRED/HYPOTHESIS claims.

    Returns a list of _VaultEntity tuples with classification and provenance.
    """
    entities: list[_VaultEntity] = []

    # --- Pages ---
    pages = await uow.pages.list_by_vault(vault_id)
    for page in pages:
        # Classify page type
        kind = _PAGE_TYPE_TO_KIND.get(page.page_type)
        if kind is None:
            continue  # Skip unclassified page types

        # In STRICT mode, only concept and mechanism pages
        if fusion_mode == FusionMode.STRICT and kind not in (
            BridgeCandidateKind.CONCEPT,
            BridgeCandidateKind.MECHANISM,
        ):
            continue

        head = await uow.pages.get_head_version(page.page_id)
        if head is None:
            continue

        text = head.title
        if head.summary:
            text = f"{head.title}: {head.summary}"

        entities.append(_VaultEntity(
            entity_id=page.page_id,
            version=head.version,
            text=text,
            kind=kind,
            claim_refs=[],
            source_refs=[],
        ))

    # --- Claims ---
    for page in pages:
        page_claims = await uow.claims.list_by_page(page.page_id)
        for claim in page_claims:
            head = await uow.claims.get_head_version(claim.claim_id)
            if head is None:
                continue

            # Epistemic filter
            if fusion_mode == FusionMode.STRICT:
                if head.status not in _STRICT_CLAIM_STATUSES:
                    continue
            elif fusion_mode == FusionMode.EXPLORATORY:
                if head.status in _EXPLORATORY_EXCLUDED_STATUSES:
                    continue

            entities.append(_VaultEntity(
                entity_id=claim.claim_id,
                version=head.version,
                text=head.statement,
                kind=BridgeCandidateKind.CLAIM_CLUSTER,
                claim_refs=[claim.claim_id],
                source_refs=[],
            ))

    return entities


# ---------------------------------------------------------------------------
# Step 4-5: Embeddings + cross-vault cosine similarity
# ---------------------------------------------------------------------------

@dataclass
class _SimilarityPair:
    """A scored pair of entities from left and right vaults."""

    left_idx: int
    right_idx: int
    similarity: float
    problem_relevance: float | None


async def _compute_cross_similarity(
    left_entities: Sequence[_VaultEntity],
    right_entities: Sequence[_VaultEntity],
    embedding_index: EmbeddingIndex,
    problem: str | None,
    problem_weight: float,
) -> list[_SimilarityPair]:
    """Compute cross-vault cosine similarity between all entity pairs.

    Uses the EmbeddingIndex for cached, version-pinned embeddings.
    Embeddings are assumed normalized (dot product == cosine similarity).

    If a problem string is provided, also computes problem relevance
    as the average of each entity's cosine similarity to the problem embedding.

    Returns all pairs (unfiltered) with their scores.
    """
    if not left_entities or not right_entities:
        return []

    # Get embeddings for both sides
    left_embeddings = await embedding_index.batch_get_or_compute(
        [(e.entity_id, e.version, e.text) for e in left_entities]
    )
    right_embeddings = await embedding_index.batch_get_or_compute(
        [(e.entity_id, e.version, e.text) for e in right_entities]
    )

    # Convert to numpy matrices (each row is a normalised float32 vector)
    left_mat = np.array(
        [np.frombuffer(e, dtype=np.float32) for e in left_embeddings]
    )
    right_mat = np.array(
        [np.frombuffer(e, dtype=np.float32) for e in right_embeddings]
    )

    # Cosine similarity matrix (dot product of normalised vectors)
    sim_matrix = left_mat @ right_mat.T

    # Problem relevance (optional)
    left_prob_sim: np.ndarray | None = None
    right_prob_sim: np.ndarray | None = None
    if problem:
        # Use a synthetic entity ID for the problem embedding
        problem_emb_bytes = await embedding_index.get_or_compute(
            EntityId("prob_00000000000000000000000001"),
            Version(1),
            problem,
        )
        problem_emb = np.frombuffer(problem_emb_bytes, dtype=np.float32)
        left_prob_sim = left_mat @ problem_emb
        right_prob_sim = right_mat @ problem_emb

    # Build all pairs
    results: list[_SimilarityPair] = []
    n_left, n_right = len(left_entities), len(right_entities)
    for i in range(n_left):
        for j in range(n_right):
            sim = float(sim_matrix[i, j])
            prob_rel: float | None = None
            if left_prob_sim is not None and right_prob_sim is not None:
                prob_rel = float((left_prob_sim[i] + right_prob_sim[j]) / 2.0)
            results.append(_SimilarityPair(
                left_idx=i,
                right_idx=j,
                similarity=sim,
                problem_relevance=prob_rel,
            ))

    return results


# ---------------------------------------------------------------------------
# Step 7: Diversified selection
# ---------------------------------------------------------------------------

def _kind_to_bucket(kind: BridgeCandidateKind) -> str:
    """Map a BridgeCandidateKind to an allocation bucket name."""
    if kind == BridgeCandidateKind.CONCEPT:
        return "concept"
    if kind == BridgeCandidateKind.MECHANISM:
        return "mechanism"
    if kind == BridgeCandidateKind.CLAIM_CLUSTER:
        return "claim_cluster"
    return "exploratory"


def _diversified_select(
    all_pairs: list[_SimilarityPair],
    left_entities: Sequence[_VaultEntity],
    right_entities: Sequence[_VaultEntity],
    policy: FusionPolicy,
    problem_weight: float,
) -> list[_SimilarityPair]:
    """Select diverse candidates across types and similarity bands.

    1. Filter by min similarity threshold
    2. Score each pair: similarity + problem_relevance * weight
    3. Group by allocation bucket (based on the "higher priority" kind)
    4. Allocate budget per bucket from policy
    5. Fill remaining budget from top-scoring pairs regardless of bucket
    """
    # Filter by threshold
    filtered = [
        p for p in all_pairs
        if p.similarity >= policy.min_similarity_threshold
    ]
    if not filtered:
        return []

    # Scoring function
    def score(pair: _SimilarityPair) -> float:
        base = pair.similarity
        pr = pair.problem_relevance or 0.0
        return base + pr * problem_weight

    filtered.sort(key=score, reverse=True)

    # Group by bucket (use the "primary" kind: prefer concept > mechanism > claim_cluster)
    type_groups: dict[str, list[_SimilarityPair]] = defaultdict(list)
    for pair in filtered:
        left_kind = left_entities[pair.left_idx].kind
        right_kind = right_entities[pair.right_idx].kind

        # Use the higher-priority kind to assign the bucket
        left_bucket = _kind_to_bucket(left_kind)
        right_bucket = _kind_to_bucket(right_kind)

        # Priority: concept > mechanism > claim_cluster > exploratory
        bucket_priority = {"concept": 3, "mechanism": 2, "claim_cluster": 1, "exploratory": 0}
        if bucket_priority.get(left_bucket, 0) >= bucket_priority.get(right_bucket, 0):
            bucket = left_bucket
        else:
            bucket = right_bucket

        type_groups[bucket].append(pair)

    # Allocate budget per bucket
    max_total = policy.max_candidates_per_pair
    allocation = policy.candidate_type_allocation

    selected: list[_SimilarityPair] = []
    selected_set: set[tuple[int, int]] = set()

    for bucket, fraction in allocation.items():
        budget = max(1, int(max_total * fraction))
        pool = type_groups.get(bucket, [])
        for pair in pool:
            if len(selected) >= max_total:
                break
            if (pair.left_idx, pair.right_idx) not in selected_set:
                selected.append(pair)
                selected_set.add((pair.left_idx, pair.right_idx))
                budget -= 1
                if budget <= 0:
                    break

    # Fill remaining budget from top-scoring regardless of bucket
    for pair in filtered:
        if len(selected) >= max_total:
            break
        if (pair.left_idx, pair.right_idx) not in selected_set:
            selected.append(pair)
            selected_set.add((pair.left_idx, pair.right_idx))

    return selected[:max_total]


# ---------------------------------------------------------------------------
# Step 8: Build BridgeCandidates
# ---------------------------------------------------------------------------

def _get_vault_head_revision_id(vault_id: EntityId) -> VaultRevisionId:
    """Create a placeholder VaultRevisionId referencing the vault's head.

    In a full implementation this would look up the actual vault head.
    For candidate generation we create a reference that ties the candidate
    back to the vault for provenance tracking.
    """
    return VaultRevisionId(f"rev_{str(vault_id.ulid_part).zfill(26)}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_bridge_candidates(
    uow: AbstractUnitOfWork,
    left_vault_id: EntityId,
    right_vault_id: EntityId,
    embedding_index: EmbeddingIndex,
    policy: FusionPolicy,
    id_generator: IdGenerator,
    problem: str | None = None,
    fusion_mode: FusionMode = FusionMode.STRICT,
) -> list[BridgeCandidate]:
    """Generate typed, diversified cross-vault bridge candidates.

    Steps:
    1. Extract pages + claims from both vaults
    2. Apply epistemic filter (STRICT: concept/mechanism pages + SUPPORTED claims)
    3. Classify each entity by BridgeCandidateKind
    4. Get/compute embeddings via EmbeddingIndex
    5. Cross-vault cosine similarity (numpy, dot product of normalised vectors)
    6. If problem provided: embed problem, boost candidates by problem relevance
    7. Diversified selection by type allocation + similarity bands
    8. Build BridgeCandidates with left/right provenance, revision refs

    Args:
        uow: Unit of work for repository access (already entered).
        left_vault_id: The first vault in the pair.
        right_vault_id: The second vault in the pair.
        embedding_index: Persistent, version-pinned embedding cache.
        policy: Fusion policy with thresholds, allocations, caps.
        id_generator: For generating candidate IDs.
        problem: Optional problem statement for relevance boosting.
        fusion_mode: STRICT (default) or EXPLORATORY.

    Returns:
        List of BridgeCandidates, diversified by type and capped by policy.
    """
    # Step 1-2: Extract and filter entities from both vaults
    left_entities = await _extract_entities(uow, left_vault_id, fusion_mode)
    right_entities = await _extract_entities(uow, right_vault_id, fusion_mode)

    # Early exit if either vault is empty
    if not left_entities or not right_entities:
        return []

    # Step 4-5: Compute cross-vault similarity
    all_pairs = await _compute_cross_similarity(
        left_entities=left_entities,
        right_entities=right_entities,
        embedding_index=embedding_index,
        problem=problem,
        problem_weight=policy.problem_relevance_weight,
    )

    # Step 7: Diversified selection
    selected = _diversified_select(
        all_pairs=all_pairs,
        left_entities=left_entities,
        right_entities=right_entities,
        policy=policy,
        problem_weight=policy.problem_relevance_weight,
    )

    # Step 8: Build BridgeCandidates
    # Look up vault head revisions for provenance
    left_vault = await uow.vaults.get(left_vault_id)
    right_vault = await uow.vaults.get(right_vault_id)

    left_rev_ref = left_vault.head_revision_id if left_vault else None
    right_rev_ref = right_vault.head_revision_id if right_vault else None

    candidates: list[BridgeCandidate] = []
    for pair in selected:
        left_entity = left_entities[pair.left_idx]
        right_entity = right_entities[pair.right_idx]

        candidate = BridgeCandidate(
            candidate_id=id_generator.generate("bcand"),
            left_vault_id=left_vault_id,
            right_vault_id=right_vault_id,
            left_entity_ref=left_entity.entity_id,
            right_entity_ref=right_entity.entity_id,
            left_kind=left_entity.kind,
            right_kind=right_entity.kind,
            similarity_score=pair.similarity,
            retrieval_reason="cosine_similarity",
            left_text=left_entity.text,
            right_text=right_entity.text,
            left_claim_refs=list(left_entity.claim_refs),
            right_claim_refs=list(right_entity.claim_refs),
            left_source_refs=list(left_entity.source_refs),
            right_source_refs=list(right_entity.source_refs),
            left_revision_ref=left_rev_ref,
            right_revision_ref=right_rev_ref,
            epistemic_filter_passed=True,
            problem_relevance=pair.problem_relevance,
        )
        candidates.append(candidate)

    return candidates
