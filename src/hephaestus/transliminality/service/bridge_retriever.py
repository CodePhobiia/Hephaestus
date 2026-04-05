"""Bridge retrieval — problem-conditioned cross-vault candidate generation.

Uses the existing ForgeBase fusion stack (generate_bridge_candidates) to
retrieve structurally relevant bridge candidates, then converts them to
transliminality domain models.

Per spec §8.3, this is NOT just top cosine similar pairs — diversity
and role coverage are required.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.adapters.fusion import convert_bridge_candidate
from hephaestus.transliminality.domain.models import (
    BridgeCandidate,
    EntityRef,
    RoleSignature,
    TransliminalityConfig,
)

if TYPE_CHECKING:
    from hephaestus.forgebase.fusion.embeddings import EmbeddingIndex
    from hephaestus.forgebase.repository.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


def _build_problem_text(sig: RoleSignature) -> str:
    """Build a problem-context string from a role signature for fusion retrieval.

    The fusion stack accepts an optional `problem` string that boosts
    candidates by problem relevance.  We construct one from the signature's
    structural tags to guide retrieval toward role-relevant candidates.
    """
    parts: list[str] = []
    if sig.functional_roles:
        parts.append("Functional roles: " + ", ".join(r.value for r in sig.functional_roles))
    if sig.constraints:
        parts.append("Constraints: " + ", ".join(c.value for c in sig.constraints))
    if sig.failure_modes:
        parts.append("Failure modes: " + ", ".join(f.value for f in sig.failure_modes))
    if sig.control_patterns:
        parts.append("Control patterns: " + ", ".join(cp.value for cp in sig.control_patterns))
    if sig.inputs:
        parts.append("Inputs: " + ", ".join(i.name for i in sig.inputs))
    if sig.outputs:
        parts.append("Outputs: " + ", ".join(o.name for o in sig.outputs))
    return ". ".join(parts) if parts else ""


def _diversified_select(
    candidates: list[BridgeCandidate],
    top_k: int,
) -> list[BridgeCandidate]:
    """Select top-K candidates with diversity across entity kinds and vault pairs.

    Allocates slots by entity kind (concept, mechanism, claim_cluster, etc.)
    to prevent all candidates coming from the same type. Within each bucket,
    ranks by similarity score. Fills remaining slots from the global top.
    """
    if len(candidates) <= top_k:
        return candidates

    # Group by left_kind (primary structural type)
    buckets: dict[str, list[BridgeCandidate]] = {}
    for c in candidates:
        key = c.left_kind.value
        buckets.setdefault(key, []).append(c)

    # Sort each bucket by similarity
    for bucket in buckets.values():
        bucket.sort(key=lambda c: c.similarity_score, reverse=True)

    # Round-robin allocation: at least 1 per bucket, then fill by score
    selected: list[BridgeCandidate] = []
    selected_ids: set[str] = set()

    # Phase 1: one from each bucket
    for bucket in buckets.values():
        if bucket and len(selected) < top_k:
            c = bucket[0]
            selected.append(c)
            selected_ids.add(str(c.candidate_id))

    # Phase 2: fill remaining slots from global top by score
    all_sorted = sorted(candidates, key=lambda c: c.similarity_score, reverse=True)
    for c in all_sorted:
        if len(selected) >= top_k:
            break
        if str(c.candidate_id) not in selected_ids:
            selected.append(c)
            selected_ids.add(str(c.candidate_id))

    return selected


class FusionBridgeRetriever:
    """Retrieves cross-vault bridge candidates using the ForgeBase fusion stack.

    For each (home, remote) vault pair, calls generate_bridge_candidates
    with problem conditioning from the role signature, then converts and
    aggregates results. Uses diversified selection to ensure kind coverage.
    """

    def __init__(
        self,
        uow_factory: Callable[[], AbstractUnitOfWork],
        embedding_index: EmbeddingIndex,
        id_generator: IdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._embedding_index = embedding_index
        self._id_gen = id_generator

    async def retrieve(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        config: TransliminalityConfig,
    ) -> list[BridgeCandidate]:
        """Retrieve bridge candidates across all home × remote vault pairs."""
        # Lazy import to avoid circular/heavy imports at module level
        from hephaestus.forgebase.fusion.candidates import (
            generate_bridge_candidates as _gen_candidates,
        )
        from hephaestus.forgebase.fusion.policy import FusionPolicy

        problem_text = _build_problem_text(problem_signature)

        # Build a policy from our config
        policy = FusionPolicy(
            max_candidates_per_pair=config.prefilter_top_k,
            min_similarity_threshold=0.25,
            problem_relevance_weight=0.4,  # heavier problem weighting for transliminality
        )

        sig_ref = EntityRef(
            entity_id=problem_signature.signature_id,
            entity_kind="role_signature",
        )

        all_candidates: list[BridgeCandidate] = []
        seen_pairs: set[tuple[str, str]] = set()

        # Generate for each home × remote pair
        for home_id in home_vault_ids:
            for remote_id in remote_vault_ids:
                pair_key = (str(home_id), str(remote_id))
                if pair_key in seen_pairs or pair_key[::-1] in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                try:
                    uow = self._uow_factory()
                    async with uow:
                        fb_candidates = await _gen_candidates(
                            uow=uow,
                            left_vault_id=home_id,
                            right_vault_id=remote_id,
                            embedding_index=self._embedding_index,
                            policy=policy,
                            id_generator=self._id_gen,
                            problem=problem_text or None,
                        )

                    for fb_c in fb_candidates:
                        tlim_c = convert_bridge_candidate(
                            fb_c,
                            sig_ref_left=sig_ref,
                            sig_ref_right=sig_ref,
                        )
                        all_candidates.append(tlim_c)

                    logger.info(
                        "bridge_retrieval  pair=(%s, %s)  candidates=%d",
                        home_id, remote_id, len(fb_candidates),
                    )

                except Exception:
                    logger.exception(
                        "bridge_retrieval failed for pair (%s, %s)",
                        home_id, remote_id,
                    )

        # Diversified selection: ensure coverage across entity kinds and vault pairs
        capped = _diversified_select(all_candidates, config.prefilter_top_k)

        logger.info(
            "bridge_retrieval_completed  total_raw=%d  after_cap=%d  pairs=%d",
            len(all_candidates), len(capped), len(seen_pairs),
        )
        return capped
