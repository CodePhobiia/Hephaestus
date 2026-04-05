"""LLM-backed fusion analyzer adapter — validates structural analogies.

Consumes bridge candidates and produces AnalogicalMaps + TransferOpportunities
using the analogy_validation and transfer_synthesis prompt templates via
DeepForgeHarness. This is the core intelligence of Stage 3.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from hephaestus.core.json_utils import loads_lenient
from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    EpistemicState,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogyBreak,
    BridgeCandidate,
    ComponentMapping,
    EntityRef,
    RoleSignature,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityConfig,
)
from hephaestus.transliminality.prompts.analogy_validation import (
    ANALOGY_VALIDATION_SYSTEM,
    ANALOGY_VALIDATION_USER,
)
from hephaestus.transliminality.prompts.transfer_synthesis import (
    TRANSFER_SYNTHESIS_SYSTEM,
    TRANSFER_SYNTHESIS_USER,
)

if TYPE_CHECKING:
    from hephaestus.deepforge.harness import DeepForgeHarness

logger = logging.getLogger(__name__)

_VERDICT_MAP: dict[str, AnalogicalVerdict] = {
    "valid": AnalogicalVerdict.VALID,
    "partial": AnalogicalVerdict.PARTIAL,
    "weak": AnalogicalVerdict.WEAK,
    "invalid": AnalogicalVerdict.INVALID,
}

_BREAK_MAP: dict[str, AnalogyBreakCategory] = {
    "scale_mismatch": AnalogyBreakCategory.SCALE_MISMATCH,
    "constraint_violation": AnalogyBreakCategory.CONSTRAINT_VIOLATION,
    "role_divergence": AnalogyBreakCategory.ROLE_DIVERGENCE,
    "missing_component": AnalogyBreakCategory.MISSING_COMPONENT,
    "topology_mismatch": AnalogyBreakCategory.TOPOLOGY_MISMATCH,
    "temporal_mismatch": AnalogyBreakCategory.TEMPORAL_MISMATCH,
    "resource_mismatch": AnalogyBreakCategory.RESOURCE_MISMATCH,
    "boundary_condition_failure": AnalogyBreakCategory.BOUNDARY_CONDITION_FAILURE,
}


def _parse_analogy_map(
    raw: dict[str, Any],
    candidate: BridgeCandidate,
    id_generator: IdGenerator,
) -> AnalogicalMap:
    """Parse LLM JSON into an AnalogicalMap."""
    verdict_str = str(raw.get("verdict", "invalid")).lower()
    verdict = _VERDICT_MAP.get(verdict_str, AnalogicalVerdict.INVALID)

    components = []
    for cm in raw.get("mapped_components", []):
        if isinstance(cm, dict):
            components.append(ComponentMapping(
                left_component_ref=None,
                right_component_ref=None,
                shared_role=str(cm.get("shared_role", "")),
                mapping_rationale=str(cm.get("mapping_rationale", "")),
            ))

    breaks = []
    for ab in raw.get("analogy_breaks", []):
        if isinstance(ab, dict):
            cat_str = str(ab.get("category", "constraint_violation")).lower()
            breaks.append(AnalogyBreak(
                category=_BREAK_MAP.get(cat_str, AnalogyBreakCategory.CONSTRAINT_VIOLATION),
                description=str(ab.get("description", "")),
                severity=float(ab.get("severity", 0.5)),
            ))

    preserved = [str(c) for c in raw.get("preserved_constraints", []) if c]
    broken = [str(c) for c in raw.get("broken_constraints", []) if c]
    confidence = float(raw.get("confidence", 0.0))

    return AnalogicalMap(
        map_id=id_generator.generate("amap"),
        candidate_ref=EntityRef(
            entity_id=candidate.candidate_id, entity_kind="bridge_candidate",
        ),
        shared_role=str(raw.get("shared_role", "")),
        mapped_components=components,
        preserved_constraints=preserved,
        broken_constraints=broken,
        analogy_breaks=breaks,
        structural_alignment_score=confidence,
        constraint_carryover_score=(
            len(preserved) / max(len(preserved) + len(broken), 1)
        ),
        grounding_score=min(
            (len(candidate.left_claim_refs) + len(candidate.right_claim_refs)) / 4.0,
            1.0,
        ),
        confidence=confidence,
        verdict=verdict,
        rationale=str(raw.get("rationale", "")),
        provenance_refs=(
            list(candidate.left_source_refs) + list(candidate.right_source_refs)
        ),
    )


def _parse_transfer_opportunities(
    raw_list: list[dict[str, Any]],
    amap: AnalogicalMap,
    id_generator: IdGenerator,
) -> list[TransferOpportunity]:
    """Parse LLM JSON array into TransferOpportunity list."""
    result = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        caveats = []
        for c in raw.get("caveats", []):
            if isinstance(c, dict):
                caveats.append(TransferCaveat(
                    category=str(c.get("category", "general")),
                    description=str(c.get("description", "")),
                    severity=float(c.get("severity", 0.5)),
                ))
        confidence = float(raw.get("confidence", 0.0))
        result.append(TransferOpportunity(
            opportunity_id=id_generator.generate("topp"),
            map_ref=EntityRef(entity_id=amap.map_id, entity_kind="analogical_map"),
            title=str(raw.get("title", "")),
            transferred_mechanism=str(raw.get("transferred_mechanism", "")),
            target_problem_fit=str(raw.get("target_problem_fit", "")),
            expected_benefit=str(raw.get("expected_benefit", "")),
            required_transformations=[
                str(t) for t in raw.get("required_transformations", []) if t
            ],
            caveats=caveats,
            confidence=confidence,
            epistemic_state=(
                EpistemicState.VALIDATED if confidence >= 0.7
                else EpistemicState.HYPOTHESIS
            ),
            supporting_refs=list(amap.provenance_refs),
        ))
    return result


class LLMFusionAnalyzerAdapter:
    """Validates structural analogies using LLM-backed analysis.

    For each bridge candidate:
    1. Sends to analogy validation prompt → AnalogicalMap
    2. If verdict is VALID or PARTIAL, sends to transfer synthesis → TransferOpportunity[]
    """

    def __init__(
        self,
        harness: DeepForgeHarness,
        id_generator: IdGenerator,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self._harness = harness
        self._id_gen = id_generator
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        problem_signature: RoleSignature,
        config: TransliminalityConfig,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity]]:
        """Analyze bridge candidates for structural analogies."""
        all_maps: list[AnalogicalMap] = []
        all_opps: list[TransferOpportunity] = []

        problem_context = self._build_problem_context(problem_signature)

        for candidate in candidates:
            try:
                amap = await self._validate_analogy(candidate, problem_context)
                all_maps.append(amap)

                if amap.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL):
                    opps = await self._synthesize_transfers(amap, problem_context)
                    all_opps.extend(opps)
            except Exception:
                logger.warning(
                    "Analogy analysis failed for candidate %s",
                    candidate.candidate_id,
                    exc_info=True,
                )
                # Produce an INVALID map so the candidate is tracked
                all_maps.append(AnalogicalMap(
                    map_id=self._id_gen.generate("amap"),
                    candidate_ref=EntityRef(
                        entity_id=candidate.candidate_id,
                        entity_kind="bridge_candidate",
                    ),
                    shared_role="analysis_failed",
                    verdict=AnalogicalVerdict.INVALID,
                    rationale="LLM analysis failed",
                ))

        logger.info(
            "fusion_analyzer  candidates=%d  maps=%d  valid=%d  opps=%d",
            len(candidates),
            len(all_maps),
            sum(1 for m in all_maps if m.verdict in (AnalogicalVerdict.VALID, AnalogicalVerdict.PARTIAL)),
            len(all_opps),
        )
        return all_maps, all_opps

    async def _validate_analogy(
        self,
        candidate: BridgeCandidate,
        problem_context: str,
    ) -> AnalogicalMap:
        """Run analogy validation prompt on a single candidate."""
        user_prompt = ANALOGY_VALIDATION_USER.format(
            left_domain=str(candidate.left_ref.vault_id or "unknown"),
            right_domain=str(candidate.right_ref.vault_id or "unknown"),
            left_text=str(candidate.left_ref),
            right_text=str(candidate.right_ref),
            similarity_score=candidate.similarity_score,
            retrieval_reason=candidate.retrieval_reason.value,
            problem_context=problem_context,
        )

        result = await self._harness.forge(
            user_prompt,
            system=ANALOGY_VALIDATION_SYSTEM,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        parsed = loads_lenient(result.output, default={}, label="analogy_validation")
        return _parse_analogy_map(parsed, candidate, self._id_gen)

    async def _synthesize_transfers(
        self,
        amap: AnalogicalMap,
        problem_context: str,
    ) -> list[TransferOpportunity]:
        """Run transfer synthesis prompt on a validated map."""
        components_text = "\n".join(
            f"  - {cm.shared_role}: {cm.mapping_rationale}"
            for cm in amap.mapped_components
        ) or "  (none)"

        user_prompt = TRANSFER_SYNTHESIS_USER.format(
            shared_role=amap.shared_role,
            mapped_components=components_text,
            preserved_constraints=", ".join(amap.preserved_constraints) or "(none)",
            broken_constraints=", ".join(amap.broken_constraints) or "(none)",
            analogy_breaks="\n".join(
                f"  - {b.category.value}: {b.description}" for b in amap.analogy_breaks
            ) or "  (none)",
            problem_context=problem_context,
        )

        result = await self._harness.forge(
            user_prompt,
            system=TRANSFER_SYNTHESIS_SYSTEM,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        parsed = loads_lenient(result.output, default=[], label="transfer_synthesis")
        if isinstance(parsed, list):
            return _parse_transfer_opportunities(parsed, amap, self._id_gen)
        if isinstance(parsed, dict):
            return _parse_transfer_opportunities([parsed], amap, self._id_gen)
        return []

    @staticmethod
    def _build_problem_context(sig: RoleSignature) -> str:
        """Build a problem context string from the role signature."""
        parts: list[str] = []
        if sig.functional_roles:
            parts.append("Roles: " + ", ".join(r.value for r in sig.functional_roles))
        if sig.constraints:
            parts.append("Constraints: " + ", ".join(c.value for c in sig.constraints))
        if sig.failure_modes:
            parts.append("Failure modes: " + ", ".join(f.value for f in sig.failure_modes))
        return ". ".join(parts) if parts else "No structured context available."
