"""Fusion stack adapter — converts between ForgeBase fusion models and transliminality models.

Handles three conversion families:
1. BridgeCandidate (ForgeBase → transliminality)
2. AnalogicalMap + AnalogyBreak (ForgeBase → transliminality)
3. TransferOpportunity (ForgeBase → transliminality)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator

if TYPE_CHECKING:
    from hephaestus.forgebase.fusion.models import (
        AnalogicalMap as FBAnalogicalMap,
    )
    from hephaestus.forgebase.fusion.models import (
        BridgeCandidate as FBBridgeCandidate,
    )
    from hephaestus.forgebase.fusion.models import (
        TransferOpportunity as FBTransferOpportunity,
    )
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    BridgeEntityKind,
    EpistemicState,
    RetrievalReason,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap as TlimAnalogicalMap,
)
from hephaestus.transliminality.domain.models import (
    AnalogyBreak as TlimAnalogyBreak,
)
from hephaestus.transliminality.domain.models import (
    BridgeCandidate as TlimBridgeCandidate,
)
from hephaestus.transliminality.domain.models import (
    ComponentMapping,
    EntityRef,
    TransferCaveat,
)
from hephaestus.transliminality.domain.models import (
    TransferOpportunity as TlimTransferOpportunity,
)

logger = logging.getLogger(__name__)

# Mapping from ForgeBase BridgeCandidateKind values to transliminality BridgeEntityKind
_KIND_MAP: dict[str, BridgeEntityKind] = {
    "concept": BridgeEntityKind.CONCEPT,
    "mechanism": BridgeEntityKind.MECHANISM,
    "claim_cluster": BridgeEntityKind.CLAIM_CLUSTER,
    "page_theme": BridgeEntityKind.PAGE_FAMILY,
    "exploratory": BridgeEntityKind.CONCEPT,  # exploratory → concept fallback
}

# Mapping from ForgeBase retrieval_reason strings to transliminality RetrievalReason
_REASON_MAP: dict[str, RetrievalReason] = {
    "cosine_similarity": RetrievalReason.EMBEDDING_SIMILARITY,
    "embedding_similarity": RetrievalReason.EMBEDDING_SIMILARITY,
    "role_match": RetrievalReason.ROLE_MATCH,
    "mechanism_match": RetrievalReason.MECHANISM_MATCH,
    "metadata_match": RetrievalReason.CONSTRAINT_MATCH,
}


def _map_kind(kind_value: str) -> BridgeEntityKind:
    """Map a ForgeBase BridgeCandidateKind string to transliminality BridgeEntityKind."""
    return _KIND_MAP.get(str(kind_value).lower(), BridgeEntityKind.CONCEPT)


def _map_reason(reason: str) -> RetrievalReason:
    """Map a ForgeBase retrieval_reason string to transliminality RetrievalReason."""
    return _REASON_MAP.get(reason.lower(), RetrievalReason.EMBEDDING_SIMILARITY)


def _ref_list(ids: list[EntityId], kind: str, vault_id: EntityId | None = None) -> list[EntityRef]:
    """Convert a list of EntityIds to EntityRefs."""
    return [EntityRef(entity_id=eid, entity_kind=kind, vault_id=vault_id) for eid in ids]


def convert_bridge_candidate(
    fb_candidate: FBBridgeCandidate,
    *,
    sig_ref_left: EntityRef | None = None,
    sig_ref_right: EntityRef | None = None,
) -> TlimBridgeCandidate:
    """Convert a ForgeBase BridgeCandidate to a transliminality BridgeCandidate.

    Parameters
    ----------
    fb_candidate:
        A ForgeBase ``BridgeCandidate`` dataclass instance.
    sig_ref_left, sig_ref_right:
        Optional signature references to associate with each side.
    """
    candidate_id: EntityId = fb_candidate.candidate_id
    left_vault_id: EntityId = fb_candidate.left_vault_id
    right_vault_id: EntityId = fb_candidate.right_vault_id

    left_ref = EntityRef(
        entity_id=fb_candidate.left_entity_ref,
        entity_kind="entity",
        vault_id=left_vault_id,
    )
    right_ref = EntityRef(
        entity_id=fb_candidate.right_entity_ref,
        entity_kind="entity",
        vault_id=right_vault_id,
    )

    if sig_ref_left is None:
        sig_ref_left = EntityRef(entity_id=candidate_id, entity_kind="signature_placeholder")
    if sig_ref_right is None:
        sig_ref_right = EntityRef(entity_id=candidate_id, entity_kind="signature_placeholder")

    return TlimBridgeCandidate(
        candidate_id=candidate_id,
        left_ref=left_ref,
        right_ref=right_ref,
        left_signature_ref=sig_ref_left,
        right_signature_ref=sig_ref_right,
        left_kind=_map_kind(str(fb_candidate.left_kind)),
        right_kind=_map_kind(str(fb_candidate.right_kind)),
        retrieval_reason=_map_reason(fb_candidate.retrieval_reason),
        similarity_score=float(fb_candidate.similarity_score),
        left_claim_refs=_ref_list(fb_candidate.left_claim_refs, "claim", left_vault_id),
        right_claim_refs=_ref_list(fb_candidate.right_claim_refs, "claim", right_vault_id),
        left_source_refs=_ref_list(fb_candidate.left_source_refs, "source", left_vault_id),
        right_source_refs=_ref_list(fb_candidate.right_source_refs, "source", right_vault_id),
        left_revision_ref=fb_candidate.left_revision_ref,
        right_revision_ref=fb_candidate.right_revision_ref,
        epistemic_filter_passed=fb_candidate.epistemic_filter_passed,
    )


# ---------------------------------------------------------------------------
# Verdict mapping (ForgeBase AnalogyVerdict → transliminality AnalogicalVerdict)
# ---------------------------------------------------------------------------

_VERDICT_MAP: dict[str, AnalogicalVerdict] = {
    "strong_analogy": AnalogicalVerdict.VALID,
    "weak_analogy": AnalogicalVerdict.WEAK,
    "no_analogy": AnalogicalVerdict.INVALID,
    "invalid": AnalogicalVerdict.INVALID,
}

# Break category mapping — ForgeBase uses string categories
_BREAK_CATEGORY_MAP: dict[str, AnalogyBreakCategory] = {
    "scale": AnalogyBreakCategory.SCALE_MISMATCH,
    "scale_mismatch": AnalogyBreakCategory.SCALE_MISMATCH,
    "constraint": AnalogyBreakCategory.CONSTRAINT_VIOLATION,
    "constraint_violation": AnalogyBreakCategory.CONSTRAINT_VIOLATION,
    "role": AnalogyBreakCategory.ROLE_DIVERGENCE,
    "role_divergence": AnalogyBreakCategory.ROLE_DIVERGENCE,
    "missing": AnalogyBreakCategory.MISSING_COMPONENT,
    "missing_component": AnalogyBreakCategory.MISSING_COMPONENT,
    "topology": AnalogyBreakCategory.TOPOLOGY_MISMATCH,
    "temporal": AnalogyBreakCategory.TEMPORAL_MISMATCH,
    "resource": AnalogyBreakCategory.RESOURCE_MISMATCH,
    "boundary": AnalogyBreakCategory.BOUNDARY_CONDITION_FAILURE,
}


def _map_verdict(verdict_value: str) -> AnalogicalVerdict:
    """Map a ForgeBase AnalogyVerdict string to transliminality AnalogicalVerdict."""
    return _VERDICT_MAP.get(str(verdict_value).lower(), AnalogicalVerdict.INVALID)


def _map_break_category(category: str) -> AnalogyBreakCategory:
    """Map a break category string to AnalogyBreakCategory."""
    return _BREAK_CATEGORY_MAP.get(
        category.lower(), AnalogyBreakCategory.CONSTRAINT_VIOLATION,
    )


# ---------------------------------------------------------------------------
# AnalogicalMap conversion
# ---------------------------------------------------------------------------

def convert_analogical_map(
    fb_map: FBAnalogicalMap,
    *,
    id_generator: IdGenerator,
) -> TlimAnalogicalMap:
    """Convert a ForgeBase AnalogicalMap to a transliminality AnalogicalMap."""
    map_id = id_generator.generate("amap")

    # Extract source candidate refs
    source_ids: list[EntityId] = getattr(fb_map, "source_candidates", [])
    candidate_ref = EntityRef(
        entity_id=source_ids[0] if source_ids else map_id,
        entity_kind="bridge_candidate",
    )

    # Convert component mappings
    mapped_components: list[ComponentMapping] = []
    for cm in getattr(fb_map, "mapped_components", []):
        mapped_components.append(ComponentMapping(
            left_component_ref=None,
            right_component_ref=None,
            shared_role=getattr(cm, "shared_role", getattr(cm, "role", "")),
            mapping_rationale=getattr(cm, "rationale", getattr(cm, "description", "")),
        ))

    # Convert analogy breaks
    breaks: list[TlimAnalogyBreak] = []
    for ab in getattr(fb_map, "analogy_breaks", []):
        category_str = getattr(ab, "category", "constraint")
        breaks.append(TlimAnalogyBreak(
            category=_map_break_category(str(category_str)),
            description=getattr(ab, "description", ""),
            severity=float(getattr(ab, "severity", 0.5)),
        ))

    # Extract constraint info
    preserved: list[str] = []
    broken: list[str] = []
    for mc in getattr(fb_map, "mapped_constraints", []):
        constraint_text = getattr(mc, "constraint", getattr(mc, "name", ""))
        if getattr(mc, "preserved", True):
            preserved.append(str(constraint_text))
        else:
            broken.append(str(constraint_text))

    fb_verdict = str(getattr(fb_map, "verdict", "no_analogy"))
    confidence = float(getattr(fb_map, "confidence", 0.0))

    # Provenance refs from page/claim refs
    provenance: list[EntityRef] = []
    for pid in getattr(fb_map, "left_page_refs", []):
        provenance.append(EntityRef(entity_id=pid, entity_kind="page"))
    for pid in getattr(fb_map, "right_page_refs", []):
        provenance.append(EntityRef(entity_id=pid, entity_kind="page"))

    return TlimAnalogicalMap(
        map_id=map_id,
        candidate_ref=candidate_ref,
        shared_role=getattr(fb_map, "bridge_concept", ""),
        mapped_components=mapped_components,
        preserved_constraints=preserved,
        broken_constraints=broken,
        analogy_breaks=breaks,
        structural_alignment_score=confidence,
        constraint_carryover_score=1.0 - (len(broken) / max(len(preserved) + len(broken), 1)),
        grounding_score=min(len(provenance) / 4.0, 1.0),
        confidence=confidence,
        verdict=_map_verdict(fb_verdict),
        rationale=getattr(fb_map, "left_structure", "") + " ↔ " + getattr(fb_map, "right_structure", ""),
        provenance_refs=provenance,
    )


# ---------------------------------------------------------------------------
# TransferOpportunity conversion
# ---------------------------------------------------------------------------

def convert_transfer_opportunity(
    fb_opp: FBTransferOpportunity,
    *,
    id_generator: IdGenerator,
) -> TlimTransferOpportunity:
    """Convert a ForgeBase TransferOpportunity to a transliminality TransferOpportunity."""
    opp_id = id_generator.generate("topp")

    map_id = getattr(fb_opp, "analogical_map_id", None)
    map_ref = EntityRef(
        entity_id=map_id if map_id else opp_id,
        entity_kind="analogical_map",
    )

    # Convert caveats
    raw_caveats: list[str] = getattr(fb_opp, "caveats", [])
    raw_categories: list[str] = getattr(fb_opp, "caveat_categories", [])
    caveats: list[TransferCaveat] = []
    for i, c in enumerate(raw_caveats):
        cat = raw_categories[i] if i < len(raw_categories) else "general"
        caveats.append(TransferCaveat(category=cat, description=c, severity=0.5))

    confidence = float(getattr(fb_opp, "confidence", 0.0))

    # Provenance
    supporting: list[EntityRef] = []
    for pid in getattr(fb_opp, "from_page_refs", []):
        supporting.append(EntityRef(entity_id=pid, entity_kind="page"))
    for pid in getattr(fb_opp, "to_page_refs", []):
        supporting.append(EntityRef(entity_id=pid, entity_kind="page"))

    return TlimTransferOpportunity(
        opportunity_id=opp_id,
        map_ref=map_ref,
        title=getattr(fb_opp, "mechanism", "untitled transfer"),
        transferred_mechanism=getattr(fb_opp, "mechanism", ""),
        target_problem_fit=getattr(fb_opp, "rationale", ""),
        expected_benefit=getattr(fb_opp, "rationale", ""),
        required_transformations=[],
        caveats=caveats,
        confidence=confidence,
        epistemic_state=EpistemicState.HYPOTHESIS if confidence < 0.7 else EpistemicState.VALIDATED,
        supporting_refs=supporting,
    )


# ---------------------------------------------------------------------------
# Batch conversion for analyzer results
# ---------------------------------------------------------------------------

def convert_analyzer_results(
    fb_maps: list[Any],
    fb_opportunities: list[Any],
    *,
    id_generator: IdGenerator,
) -> tuple[list[TlimAnalogicalMap], list[TlimTransferOpportunity]]:
    """Convert a full set of ForgeBase analyzer results to transliminality models."""
    maps = [convert_analogical_map(m, id_generator=id_generator) for m in fb_maps]
    opps = [convert_transfer_opportunity(o, id_generator=id_generator) for o in fb_opportunities]
    return maps, opps
