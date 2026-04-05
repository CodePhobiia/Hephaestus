"""Pack assembler — builds TransliminalityPack from validated maps and opportunities.

Uses channel policies to classify entries into strict baseline, soft context,
and strict constraint channels.  Computes an integration score preview.
"""

from __future__ import annotations

import logging

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    EpistemicState,
    PackOriginKind,
    TrustTier,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    EntityRef,
    IntegrationScoreBreakdown,
    KnowledgePackEntry,
    RoleSignature,
    TransferOpportunity,
    TransliminalityConfig,
    TransliminalityPack,
)
from hephaestus.transliminality.domain.policies import (
    Channel,
    classify_entry,
    classify_map_for_constraint_channel,
)
from hephaestus.transliminality.domain.scoring import compute_integration_score

logger = logging.getLogger(__name__)


def _entry_from_map(
    amap: AnalogicalMap,
    *,
    id_generator: IdGenerator,
) -> KnowledgePackEntry:
    """Build a KnowledgePackEntry from a validated AnalogicalMap."""
    text_parts = [f"Structural analogy: {amap.shared_role}"]
    if amap.mapped_components:
        for cm in amap.mapped_components:
            text_parts.append(f"  - {cm.shared_role}: {cm.mapping_rationale}")
    if amap.preserved_constraints:
        text_parts.append(f"  Preserved: {', '.join(amap.preserved_constraints)}")
    if amap.rationale:
        text_parts.append(f"  Rationale: {amap.rationale}")

    # Trust and epistemic state from verdict
    if amap.verdict == AnalogicalVerdict.VALID:
        epistemic = EpistemicState.VALIDATED
        trust = TrustTier.INTERNAL_VERIFIED
    elif amap.verdict == AnalogicalVerdict.PARTIAL:
        epistemic = EpistemicState.HYPOTHESIS
        trust = TrustTier.INTERNAL_UNVERIFIED
    else:
        epistemic = EpistemicState.EXPLORATORY
        trust = TrustTier.EXPLORATORY

    return KnowledgePackEntry(
        entry_id=id_generator.generate("kpe"),
        text="\n".join(text_parts),
        origin_kind=PackOriginKind.BRIDGE_SYNTHESIS,
        source_refs=list(amap.provenance_refs),
        epistemic_state=epistemic,
        trust_tier=trust,
        salience=amap.confidence,
    )


def _entry_from_opportunity(
    opp: TransferOpportunity,
    *,
    id_generator: IdGenerator,
) -> KnowledgePackEntry:
    """Build a KnowledgePackEntry from a TransferOpportunity."""
    text_parts = [
        f"Transfer opportunity: {opp.title}",
        f"  Mechanism: {opp.transferred_mechanism}",
        f"  Fit: {opp.target_problem_fit}",
        f"  Benefit: {opp.expected_benefit}",
    ]
    if opp.required_transformations:
        text_parts.append(f"  Requires: {', '.join(opp.required_transformations)}")
    if opp.caveats:
        for cav in opp.caveats:
            text_parts.append(f"  Caveat ({cav.category}): {cav.description}")

    if opp.epistemic_state == EpistemicState.VALIDATED:
        trust = TrustTier.INTERNAL_VERIFIED
    else:
        trust = TrustTier.INTERNAL_UNVERIFIED

    return KnowledgePackEntry(
        entry_id=id_generator.generate("kpe"),
        text="\n".join(text_parts),
        origin_kind=PackOriginKind.TRANSFER_OPPORTUNITY,
        source_refs=list(opp.supporting_refs),
        epistemic_state=opp.epistemic_state,
        trust_tier=trust,
        salience=opp.confidence,
    )


def _constraint_entry_from_map(
    amap: AnalogicalMap,
    *,
    id_generator: IdGenerator,
) -> KnowledgePackEntry:
    """Build a constraint-channel entry from map breaks and broken constraints."""
    text_parts = []
    if amap.broken_constraints:
        text_parts.append(f"Broken constraints: {', '.join(amap.broken_constraints)}")
    for brk in amap.analogy_breaks:
        text_parts.append(f"Analogy break ({brk.category.value}): {brk.description}")

    return KnowledgePackEntry(
        entry_id=id_generator.generate("kpe"),
        text="\n".join(text_parts) if text_parts else "Analogy has structural breaks",
        origin_kind=PackOriginKind.CONSTRAINT_EXTRACTION,
        source_refs=list(amap.provenance_refs),
        epistemic_state=EpistemicState.VALIDATED,
        trust_tier=TrustTier.INTERNAL_VERIFIED,
        salience=amap.confidence,
    )


def _estimate_integration_scores(
    maps: list[AnalogicalMap],
    opportunities: list[TransferOpportunity],
) -> IntegrationScoreBreakdown:
    """Estimate integration scores from map and opportunity statistics.

    This is a preview score computed at pack assembly time.
    Phase 4 adds the full IntegrationScorer with LLM-backed evaluation.
    """
    if not maps:
        return IntegrationScoreBreakdown()

    valid_maps = [m for m in maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)]
    if not valid_maps:
        return IntegrationScoreBreakdown()

    # Structural alignment: average confidence of valid maps
    structural = sum(m.structural_alignment_score for m in valid_maps) / len(valid_maps)

    # Constraint fidelity: average constraint carryover
    fidelity = sum(m.constraint_carryover_score for m in valid_maps) / len(valid_maps)

    # Source grounding: average grounding score
    grounding = sum(m.grounding_score for m in valid_maps) / len(valid_maps)

    # Counterfactual: higher if transfer opportunities exist and have caveats documented
    counterfactual = min(len(opportunities) / 3.0, 1.0) if opportunities else 0.0

    # Bidirectional: higher if maps have rationale and breaks documented
    has_rationale = sum(1 for m in valid_maps if m.rationale) / len(valid_maps)
    has_breaks = sum(1 for m in valid_maps if m.analogy_breaks) / len(valid_maps)
    bidirectional = (has_rationale + has_breaks) / 2.0

    # Non-ornamental: higher if maps have concrete component mappings
    has_components = sum(1 for m in valid_maps if m.mapped_components) / len(valid_maps)
    non_ornamental = has_components

    return IntegrationScoreBreakdown(
        structural_alignment=structural,
        constraint_fidelity=fidelity,
        source_grounding=grounding,
        counterfactual_dependence=counterfactual,
        bidirectional_explainability=bidirectional,
        non_ornamental_use=non_ornamental,
    )


class ChannelPackAssembler:
    """Assembles a TransliminalityPack using channel policy classification.

    For each validated map and transfer opportunity:
    1. Generates a KnowledgePackEntry
    2. Classifies it via channel policy
    3. Routes to the appropriate channel
    4. Computes integration score preview
    """

    def __init__(self, id_generator: IdGenerator) -> None:
        self._id_gen = id_generator

    async def assemble(
        self,
        run_id: EntityId,
        problem_signature: RoleSignature,
        home_vault_ids: list[EntityId],
        remote_vault_ids: list[EntityId],
        maps: list[AnalogicalMap],
        opportunities: list[TransferOpportunity],
        config: TransliminalityConfig,
    ) -> TransliminalityPack:
        """Assemble a TransliminalityPack with channel-classified entries."""
        strict_baseline: list[KnowledgePackEntry] = []
        soft_context: list[KnowledgePackEntry] = []
        strict_constraint: list[KnowledgePackEntry] = []

        bridge_refs: list[EntityRef] = []
        map_refs: list[EntityRef] = []
        opp_refs: list[EntityRef] = []

        # Process maps — collect bridge refs from candidate references
        for amap in maps:
            map_refs.append(EntityRef(entity_id=amap.map_id, entity_kind="analogical_map"))
            bridge_refs.append(amap.candidate_ref)

            if amap.verdict == AnalogicalVerdict.INVALID:
                continue

            # Generate content entry from map
            entry = _entry_from_map(amap, id_generator=self._id_gen)
            decision = classify_entry(entry, config)
            if decision.channel == Channel.STRICT_BASELINE:
                strict_baseline.append(entry)
            elif decision.channel == Channel.SOFT_CONTEXT:
                soft_context.append(entry)

            # Check if breaks should enter constraint channel
            constraint_decision = classify_map_for_constraint_channel(amap, config)
            if constraint_decision.channel == Channel.STRICT_CONSTRAINT:
                constraint_entry = _constraint_entry_from_map(amap, id_generator=self._id_gen)
                strict_constraint.append(constraint_entry)

        # Process transfer opportunities
        for opp in opportunities:
            opp_refs.append(EntityRef(
                entity_id=opp.opportunity_id, entity_kind="transfer_opportunity",
            ))

            entry = _entry_from_opportunity(opp, id_generator=self._id_gen)
            decision = classify_entry(entry, config)
            if decision.channel == Channel.STRICT_BASELINE:
                strict_baseline.append(entry)
            elif decision.channel == Channel.SOFT_CONTEXT:
                soft_context.append(entry)

        # Compute integration score preview
        score_preview = _estimate_integration_scores(maps, opportunities)

        pack_id = self._id_gen.generate("tpack")
        sig_ref = EntityRef(
            entity_id=problem_signature.signature_id,
            entity_kind="role_signature",
        )

        logger.info(
            "pack_assembled  strict=%d  soft=%d  constraint=%d  score=%.3f",
            len(strict_baseline), len(soft_context), len(strict_constraint),
            compute_integration_score(score_preview),
        )

        return TransliminalityPack(
            pack_id=pack_id,
            run_id=run_id,
            problem_signature_ref=sig_ref,
            home_vault_ids=list(home_vault_ids),
            remote_vault_ids=list(remote_vault_ids),
            bridge_candidates=bridge_refs,
            validated_maps=map_refs,
            transfer_opportunities=opp_refs,
            strict_baseline_entries=strict_baseline,
            soft_context_entries=soft_context,
            strict_constraint_entries=strict_constraint,
            integration_score_preview=score_preview,
        )
