"""Vault routing — select remote vaults for cross-domain bridge retrieval.

Routing factors (spec §8.2):
- domain complementarity (prefer different domains)
- role-signature affinity (structural keyword overlap)
- novelty potential (prefer vaults not previously fused with home)
- policy exclusions (forbidden vaults, caps)
"""

from __future__ import annotations

import logging
from typing import Protocol

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.transliminality.domain.models import (
    RoleSignature,
    TransliminalityConfig,
    VaultMetadata,
)


class VaultMetadataProvider(Protocol):
    """Abstract vault metadata access — implemented by ForgeBaseVaultAdapter."""

    async def list_vault_metadata(self) -> list[VaultMetadata]: ...
    async def vault_exists(self, vault_id: EntityId) -> bool: ...

logger = logging.getLogger(__name__)


def _role_signature_keywords(sig: RoleSignature) -> set[str]:
    """Extract lowercase keywords from a role signature for text matching."""
    keywords: set[str] = set()
    for role in sig.functional_roles:
        keywords.add(role.value.lower())
    for c in sig.constraints:
        # Split CAPACITY_LIMIT → {"capacity", "limit"}
        keywords.update(c.value.lower().split("_"))
    for fm in sig.failure_modes:
        keywords.update(fm.value.lower().split("_"))
    for cp in sig.control_patterns:
        keywords.update(cp.value.lower().split("_"))
    for t in sig.topology:
        keywords.add(t.value.lower())
    for inp in sig.inputs:
        keywords.update(inp.name.lower().split())
    for out in sig.outputs:
        keywords.update(out.name.lower().split())
    # Remove noise words
    keywords -= {"of", "the", "a", "an", "in", "on", "at", "to", "for", "and", "or"}
    return keywords


def _score_vault(
    meta: VaultMetadata,
    keywords: set[str],
    home_domains: set[str],
) -> float:
    """Score a vault for cross-domain routing.

    High score = good candidate for remote traversal.
    Combines:
    - keyword overlap with role signature (affinity)
    - domain difference from home vaults (complementarity bonus)
    """
    summary_words = set(meta.text_summary.split())

    # Affinity: fraction of signature keywords found in vault description
    if not keywords:
        affinity = 0.0
    else:
        overlap = keywords & summary_words
        affinity = len(overlap) / len(keywords)

    # Complementarity: bonus for different domain
    if meta.domain and home_domains:
        is_different_domain = meta.domain.lower() not in home_domains
        complementarity = 0.3 if is_different_domain else 0.0
    else:
        complementarity = 0.1  # Unknown domain gets slight bonus

    return affinity + complementarity


class MetadataVaultRouter:
    """Selects remote vaults using vault metadata and role-signature keywords.

    Accepts any ``VaultMetadataProvider`` — not coupled to ForgeBase directly.
    """

    def __init__(self, vault_adapter: VaultMetadataProvider) -> None:
        self._vault_adapter = vault_adapter

    async def select_vaults(
        self,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        explicit_remote_vault_ids: list[EntityId] | None,
        config: TransliminalityConfig,
    ) -> list[EntityId]:
        """Select remote vaults for cross-domain bridge retrieval."""
        # If explicit vaults are provided, validate and return them
        if explicit_remote_vault_ids:
            valid = []
            for vid in explicit_remote_vault_ids:
                if await self._vault_adapter.vault_exists(vid):
                    valid.append(vid)
                else:
                    logger.warning("Explicit remote vault %s not found, skipping", vid)
            return valid[: config.max_remote_vaults]

        # Auto-select: list all vaults, score by affinity + complementarity
        all_metadata = await self._vault_adapter.list_vault_metadata()
        if not all_metadata:
            logger.info("No vaults available for routing")
            return []

        home_ids_set = set(str(v) for v in home_vault_ids)
        keywords = _role_signature_keywords(problem_signature)

        # Collect home domains for complementarity scoring
        home_domains: set[str] = set()
        for meta in all_metadata:
            if str(meta.vault_id) in home_ids_set and meta.domain:
                home_domains.add(meta.domain.lower())

        # Score and rank non-home vaults
        candidates: list[tuple[float, VaultMetadata]] = []
        for meta in all_metadata:
            if str(meta.vault_id) in home_ids_set:
                continue
            score = _score_vault(meta, keywords, home_domains)
            candidates.append((score, meta))

        # Sort descending by score
        candidates.sort(key=lambda x: x[0], reverse=True)

        selected = [meta.vault_id for _, meta in candidates[: config.max_remote_vaults]]
        logger.info(
            "vault_router selected %d/%d available vaults  keywords=%d",
            len(selected), len(candidates), len(keywords),
        )
        return selected
