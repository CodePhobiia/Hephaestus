"""Injection boundary renderers — convert typed PackEntry objects to injection formats.

These renderers sit at the boundary between ForgeBase's typed extraction
packs and Hephaestus's injection points.  They convert structured
``PackEntry`` objects to the plain data formats that DeepForge pressure,
LensSelector, and Pantheon dossier expect.
"""

from __future__ import annotations

from typing import Any

from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PriorArtBaselinePack,
)


def render_baseline_pack_to_blocked_paths(pack: PriorArtBaselinePack) -> list[str]:
    """Render typed PackEntry objects to plain strings for extra_blocked_paths."""
    return [entry.text for entry in pack.entries if entry.text.strip()]


def render_context_pack_to_reference_context(pack: DomainContextPack) -> dict[str, Any]:
    """Render to reference_context dict for LensSelector."""
    return {
        "concepts": [e.text for e in pack.concepts],
        "mechanisms": [e.text for e in pack.mechanisms],
        "open_questions": [e.text for e in pack.open_questions],
        "explored_directions": [e.text for e in pack.explored_directions],
        "vault_id": str(pack.vault_id),
        "vault_revision": str(pack.vault_revision_id),
    }


def render_dossier_pack_to_baseline_dossier(pack: ConstraintDossierPack) -> dict[str, Any]:
    """Render to BaselineDossier-compatible dict for Pantheon."""
    return {
        "summary": (
            f"Vault constraints from {len(pack.hard_constraints)} constraints, "
            f"{len(pack.known_failure_modes)} failure modes"
        ),
        "standard_approaches": [e.text for e in pack.competitive_landscape],
        "common_failure_modes": [e.text for e in pack.known_failure_modes],
        "known_bottlenecks": [e.text for e in pack.hard_constraints],
        "keywords_to_avoid": [],  # Could be derived from competitive landscape
        "representative_systems": [],
    }
