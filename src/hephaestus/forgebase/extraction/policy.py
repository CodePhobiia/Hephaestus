"""ExtractionPolicy — controls what vault knowledge flows into which injection channel.

Each extraction channel (baseline, context, dossier) has different trust
requirements. The policy dataclass encodes these per-channel filters so
that extraction logic never hard-codes trust thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from hephaestus.forgebase.domain.enums import (
    ClaimStatus,
    InventionEpistemicState,
    SourceTrustTier,
)


@dataclass
class ExtractionPolicy:
    """Controls what vault knowledge flows into which injection channel."""

    policy_version: str = "1.0.0"
    assembler_version: str = "1.0.0"

    # --- Prior-art baseline channel (strictest) ---
    baseline_min_external_source_trust: SourceTrustTier = SourceTrustTier.AUTHORITATIVE
    baseline_min_internal_invention_state: InventionEpistemicState = (
        InventionEpistemicState.VERIFIED
    )
    baseline_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    baseline_include_hypothesis: bool = False
    baseline_include_contested: bool = False

    # --- Domain context channel (broadest) ---
    context_include_hypothesis: bool = True
    context_include_contested: bool = True
    context_include_open_questions: bool = True
    context_include_prior_directions: bool = True
    context_max_concepts: int = 50
    context_max_mechanisms: int = 30
    context_max_open_questions: int = 20
    context_max_explored_directions: int = 20

    # --- Constraint dossier channel (governance-grade) ---
    dossier_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    dossier_include_resolved_objections: bool = True
    dossier_include_unresolved_controversies: bool = True
    dossier_include_failure_modes: bool = True
    dossier_max_claim_age_days: int | None = None


DEFAULT_EXTRACTION_POLICY = ExtractionPolicy()
