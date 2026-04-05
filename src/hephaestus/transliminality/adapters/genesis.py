"""Genesis injection adapter — converts TransliminalityPack into Genesis-consumable context.

Produces:
1. System prompt supplement for Genesis candidate generation
2. extra_blocked_paths for DeepForge pressure (strict baseline only)
3. reference_context for LensSelector
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hephaestus.transliminality.domain.models import TransliminalityPack


@dataclass(frozen=True)
class GenesisInjection:
    """Structured injection context for the Genesis pipeline."""

    system_prompt_supplement: str
    extra_blocked_paths: list[str]
    lens_reference_context: dict[str, Any]


_GENESIS_PREAMBLE = (
    "=== CROSS-DOMAIN SYNTHESIS CONTEXT (Transliminality Layer) ===\n"
    "The following structural bridges have been validated from remote domains.\n"
    "TRANSFORM these mechanisms — do NOT transplant them literally.\n"
    "Preserve required constraints. Do not use ornamental cross-domain language.\n"
)


def build_genesis_injection(pack: TransliminalityPack) -> GenesisInjection:
    """Convert a TransliminalityPack into Genesis pipeline injection context."""
    # --- System prompt supplement ---
    prompt_parts = [_GENESIS_PREAMBLE]

    if pack.soft_context_entries:
        prompt_parts.append("\n--- Validated bridges (use for invention scaffolding) ---")
        for entry in pack.soft_context_entries:
            prompt_parts.append(f"• {entry.text}")

    if pack.strict_constraint_entries:
        prompt_parts.append("\n--- Constraint warnings (respect these limits) ---")
        for entry in pack.strict_constraint_entries:
            prompt_parts.append(f"⚠ {entry.text}")

    system_supplement = "\n".join(prompt_parts) if len(prompt_parts) > 1 else ""

    # --- Extra blocked paths (strict baseline only, per spec §9.1) ---
    blocked: list[str] = []
    for entry in pack.strict_baseline_entries:
        # Strict baselines are validated prior art — block literal reuse
        blocked.append(entry.text)

    # --- Lens reference context ---
    ref_ctx: dict[str, Any] = {
        "transliminality_pack_id": str(pack.pack_id),
        "bridge_concepts": [e.text for e in pack.soft_context_entries],
        "constraint_warnings": [e.text for e in pack.strict_constraint_entries],
        "integration_score": {
            "structural_alignment": pack.integration_score_preview.structural_alignment,
            "constraint_fidelity": pack.integration_score_preview.constraint_fidelity,
            "source_grounding": pack.integration_score_preview.source_grounding,
        },
        "remote_vault_count": len(pack.remote_vault_ids),
        "validated_map_count": len(pack.validated_maps),
        "transfer_opportunity_count": len(pack.transfer_opportunities),
    }

    return GenesisInjection(
        system_prompt_supplement=system_supplement,
        extra_blocked_paths=blocked,
        lens_reference_context=ref_ctx,
    )
