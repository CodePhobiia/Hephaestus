"""Pantheon injection adapter — converts TransliminalityPack into Pantheon-consumable dossier.

Produces a baseline dossier object for PantheonCoordinator.prepare_pipeline()
and registers transliminality-specific objection types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.transliminality.domain.enums import TransliminalObjectionType
from hephaestus.transliminality.domain.models import TransliminalityPack


@dataclass(frozen=True)
class TransliminalityDossier:
    """Dossier for Pantheon — carries constraint entries and analogy breaks.

    PantheonCoordinator accesses ``baseline_dossier.summary`` for its
    Athena/Hermes passes, so this object exposes a compatible interface.
    """

    summary: str
    constraint_entries: list[str] = field(default_factory=list)
    analogy_warnings: list[str] = field(default_factory=list)
    grounding_gaps: list[str] = field(default_factory=list)
    objection_types: list[str] = field(default_factory=list)


def build_pantheon_dossier(pack: TransliminalityPack) -> TransliminalityDossier:
    """Convert a TransliminalityPack into a Pantheon baseline dossier."""
    constraint_texts = [e.text for e in pack.strict_constraint_entries]
    warning_texts: list[str] = []
    gap_texts: list[str] = []

    # Extract analogy warnings from constraint entries
    for entry in pack.strict_constraint_entries:
        if "break" in entry.text.lower() or "broken" in entry.text.lower():
            warning_texts.append(entry.text)
        if not entry.source_refs:
            gap_texts.append(f"Ungrounded: {entry.text[:100]}")

    # Build summary for Pantheon's baseline accessor
    summary_parts = []
    if constraint_texts:
        summary_parts.append(
            f"Transliminality found {len(constraint_texts)} constraint warnings "
            f"from cross-domain synthesis."
        )
    if warning_texts:
        summary_parts.append(
            f"{len(warning_texts)} analogy breaks detected — verify structural validity."
        )
    if pack.soft_context_entries:
        summary_parts.append(
            f"{len(pack.soft_context_entries)} cross-domain bridges injected as soft context."
        )

    summary = " ".join(summary_parts) if summary_parts else "No transliminality context."

    # Register all transliminality objection types
    objection_types = [obj.value for obj in TransliminalObjectionType]

    return TransliminalityDossier(
        summary=summary,
        constraint_entries=constraint_texts,
        analogy_warnings=warning_texts,
        grounding_gaps=gap_texts,
        objection_types=objection_types,
    )
