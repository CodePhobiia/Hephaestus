"""Mock FusionAnalyzer for testing and development.

Returns deterministic results based on similarity scores -- no LLM calls.
Suitable for unit/integration tests and local development.
"""
from __future__ import annotations

from hephaestus.forgebase.domain.enums import AnalogyVerdict
from hephaestus.forgebase.domain.models import BackendCallRecord
from hephaestus.forgebase.extraction.models import DomainContextPack
from hephaestus.forgebase.fusion.analyzer import FusionAnalyzer
from hephaestus.forgebase.fusion.models import (
    AnalogicalMap,
    BridgeCandidate,
    ComponentMapping,
    TransferOpportunity,
)
from hephaestus.forgebase.service.id_generator import IdGenerator


class MockFusionAnalyzer(FusionAnalyzer):
    """Deterministic fusion analyzer for testing -- no LLM calls.

    Classification by ``similarity_score``:

    * >= 0.5  ->  STRONG_ANALOGY + one TransferOpportunity
    * 0.3-0.5 ->  WEAK_ANALOGY,  no transfer
    * < 0.3   ->  NO_ANALOGY
    """

    def __init__(self, id_gen: IdGenerator) -> None:
        self._id_gen = id_gen

    async def analyze_candidates(
        self,
        candidates: list[BridgeCandidate],
        left_context: DomainContextPack,
        right_context: DomainContextPack,
        problem: str | None = None,
    ) -> tuple[list[AnalogicalMap], list[TransferOpportunity], BackendCallRecord]:
        maps: list[AnalogicalMap] = []
        transfers: list[TransferOpportunity] = []

        for candidate in candidates:
            if candidate.similarity_score >= 0.5:
                verdict = AnalogyVerdict.STRONG_ANALOGY
                amap = AnalogicalMap(
                    map_id=self._id_gen.generate("amap"),
                    bridge_concept=(
                        f"Bridge: {candidate.left_text[:20]}"
                        f" \u2194 {candidate.right_text[:20]}"
                    ),
                    left_structure=candidate.left_text,
                    right_structure=candidate.right_text,
                    mapped_components=[
                        ComponentMapping(
                            left_component="Component A",
                            right_component="Component B",
                            left_ref=candidate.left_entity_ref,
                            right_ref=candidate.right_entity_ref,
                            mapping_confidence=candidate.similarity_score,
                        ),
                    ],
                    mapped_constraints=[],
                    analogy_breaks=[],
                    confidence=candidate.similarity_score,
                    verdict=verdict,
                    problem_relevance=candidate.problem_relevance,
                    source_candidates=[candidate.candidate_id],
                    left_page_refs=[candidate.left_entity_ref],
                    right_page_refs=[candidate.right_entity_ref],
                    left_claim_refs=candidate.left_claim_refs,
                    right_claim_refs=candidate.right_claim_refs,
                )
                maps.append(amap)

                transfers.append(
                    TransferOpportunity(
                        opportunity_id=self._id_gen.generate("txfr"),
                        from_vault_id=candidate.left_vault_id,
                        to_vault_id=candidate.right_vault_id,
                        mechanism=(
                            f"Transfer mechanism from {candidate.left_text[:30]}"
                        ),
                        rationale=(
                            f"Structural similarity ({candidate.similarity_score:.2f})"
                        ),
                        caveats=["Mock caveat"],
                        caveat_categories=["feasibility"],
                        analogical_map_id=amap.map_id,
                        confidence=candidate.similarity_score,
                        problem_relevance=candidate.problem_relevance,
                        from_page_refs=[candidate.left_entity_ref],
                        to_page_refs=[candidate.right_entity_ref],
                        from_claim_refs=candidate.left_claim_refs,
                    )
                )

            elif candidate.similarity_score >= 0.3:
                amap = AnalogicalMap(
                    map_id=self._id_gen.generate("amap"),
                    bridge_concept=(
                        f"Weak bridge: {candidate.left_text[:20]}"
                        f" \u2194 {candidate.right_text[:20]}"
                    ),
                    left_structure=candidate.left_text,
                    right_structure=candidate.right_text,
                    mapped_components=[],
                    mapped_constraints=[],
                    analogy_breaks=[],
                    confidence=candidate.similarity_score,
                    verdict=AnalogyVerdict.WEAK_ANALOGY,
                    problem_relevance=candidate.problem_relevance,
                    source_candidates=[candidate.candidate_id],
                    left_page_refs=[candidate.left_entity_ref],
                    right_page_refs=[candidate.right_entity_ref],
                    left_claim_refs=candidate.left_claim_refs,
                    right_claim_refs=candidate.right_claim_refs,
                )
                maps.append(amap)

            else:
                amap = AnalogicalMap(
                    map_id=self._id_gen.generate("amap"),
                    bridge_concept=(
                        f"No analogy: {candidate.left_text[:20]}"
                        f" \u2194 {candidate.right_text[:20]}"
                    ),
                    left_structure=candidate.left_text,
                    right_structure=candidate.right_text,
                    mapped_components=[],
                    mapped_constraints=[],
                    analogy_breaks=[],
                    confidence=candidate.similarity_score,
                    verdict=AnalogyVerdict.NO_ANALOGY,
                    problem_relevance=candidate.problem_relevance,
                    source_candidates=[candidate.candidate_id],
                    left_page_refs=[candidate.left_entity_ref],
                    right_page_refs=[candidate.right_entity_ref],
                    left_claim_refs=candidate.left_claim_refs,
                    right_claim_refs=candidate.right_claim_refs,
                )
                maps.append(amap)

        call_record = BackendCallRecord(
            model_name="mock",
            backend_kind="mock",
            prompt_id="fusion_analysis",
            prompt_version="1.0.0",
            schema_version=1,
            repair_invoked=False,
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
            raw_output_ref=None,
        )

        return maps, transfers, call_record
