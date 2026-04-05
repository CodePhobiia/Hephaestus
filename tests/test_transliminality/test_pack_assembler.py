"""Tests for the channel-based pack assembler."""

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    SignatureSubjectKind,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogyBreak,
    ComponentMapping,
    EntityRef,
    RoleSignature,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityConfig,
)
from hephaestus.transliminality.service.pack_assembler import (
    ChannelPackAssembler,
    _estimate_integration_scores,
)

_idgen = DeterministicIdGenerator(seed=800)


def _ref(prefix: str = "test", kind: str = "test") -> EntityRef:
    return EntityRef(entity_id=_idgen.generate(prefix), entity_kind=kind)


def _sig() -> RoleSignature:
    return RoleSignature(
        signature_id=_idgen.generate("sig"),
        subject_ref=_ref("sig", "problem"),
        subject_kind=SignatureSubjectKind.PROBLEM,
    )


def _valid_map(*, confidence: float = 0.85) -> AnalogicalMap:
    return AnalogicalMap(
        map_id=_idgen.generate("map"),
        candidate_ref=_ref("bc", "bridge_candidate"),
        shared_role="selective filtering",
        mapped_components=[
            ComponentMapping(
                left_component_ref=_ref("c", "comp"),
                right_component_ref=_ref("c", "comp"),
                shared_role="gate",
                mapping_rationale="Both control admission under pressure",
            ),
        ],
        preserved_constraints=["capacity limit"],
        broken_constraints=[],
        structural_alignment_score=confidence,
        constraint_carryover_score=0.9,
        grounding_score=0.7,
        confidence=confidence,
        verdict=AnalogicalVerdict.VALID,
        rationale="Strong structural match",
        provenance_refs=[_ref("src", "source")],
    )


def _partial_map_with_breaks() -> AnalogicalMap:
    return AnalogicalMap(
        map_id=_idgen.generate("map"),
        candidate_ref=_ref("bc", "bridge_candidate"),
        shared_role="redundancy under failure",
        analogy_breaks=[
            AnalogyBreak(
                category=AnalogyBreakCategory.SCALE_MISMATCH,
                description="Source is molecular, target is macro",
                severity=0.6,
            ),
        ],
        broken_constraints=["energy bound"],
        confidence=0.65,
        verdict=AnalogicalVerdict.PARTIAL,
        rationale="Partial match with scale issues",
        provenance_refs=[_ref("src", "source")],
    )


def _invalid_map() -> AnalogicalMap:
    return AnalogicalMap(
        map_id=_idgen.generate("map"),
        candidate_ref=_ref("bc", "bridge_candidate"),
        shared_role="decorative analogy",
        verdict=AnalogicalVerdict.INVALID,
        confidence=0.1,
    )


def _opportunity(*, confidence: float = 0.75) -> TransferOpportunity:
    return TransferOpportunity(
        opportunity_id=_idgen.generate("topp"),
        map_ref=_ref("map", "analogical_map"),
        title="Immune checkpoint → Rate limiter",
        transferred_mechanism="staged activation gating",
        target_problem_fit="Rate limiting needs selective admission",
        expected_benefit="Adaptive gating",
        caveats=[TransferCaveat(category="scale", description="timescale differs", severity=0.4)],
        confidence=confidence,
        supporting_refs=[_ref("src", "source")],
    )


class TestChannelPackAssembler:
    async def test_valid_map_enters_soft_context(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[_idgen.generate("vault")],
            remote_vault_ids=[_idgen.generate("vault")],
            maps=[_valid_map()],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        # Valid map at 0.85 confidence with INTERNAL_UNVERIFIED trust → soft channel
        assert len(pack.soft_context_entries) > 0 or len(pack.strict_baseline_entries) > 0

    async def test_invalid_map_excluded(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[_idgen.generate("vault")],
            remote_vault_ids=[_idgen.generate("vault")],
            maps=[_invalid_map()],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        assert pack.strict_baseline_entries == []
        assert pack.soft_context_entries == []
        assert pack.strict_constraint_entries == []

    async def test_partial_map_breaks_enter_constraint_channel(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[_idgen.generate("vault")],
            remote_vault_ids=[_idgen.generate("vault")],
            maps=[_partial_map_with_breaks()],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        assert len(pack.strict_constraint_entries) > 0

    async def test_opportunity_creates_entry(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[_idgen.generate("vault")],
            remote_vault_ids=[_idgen.generate("vault")],
            maps=[],
            opportunities=[_opportunity()],
            config=TransliminalityConfig(),
        )
        total = (
            len(pack.strict_baseline_entries)
            + len(pack.soft_context_entries)
        )
        assert total > 0

    async def test_integration_score_preview_populated(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[_idgen.generate("vault")],
            remote_vault_ids=[_idgen.generate("vault")],
            maps=[_valid_map()],
            opportunities=[_opportunity()],
            config=TransliminalityConfig(),
        )
        assert pack.integration_score_preview.structural_alignment > 0

    async def test_empty_inputs_produce_empty_pack(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[],
            remote_vault_ids=[],
            maps=[],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        assert pack.strict_baseline_entries == []
        assert pack.soft_context_entries == []
        assert pack.strict_constraint_entries == []

    async def test_map_refs_tracked(self) -> None:
        assembler = ChannelPackAssembler(id_generator=_idgen)
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[],
            remote_vault_ids=[],
            maps=[_valid_map(), _partial_map_with_breaks(), _invalid_map()],
            opportunities=[_opportunity()],
            config=TransliminalityConfig(),
        )
        assert len(pack.validated_maps) == 3
        assert len(pack.transfer_opportunities) == 1


class TestEstimateIntegrationScores:
    def test_no_maps_returns_zeros(self) -> None:
        result = _estimate_integration_scores([], [])
        assert result.structural_alignment == 0.0

    def test_only_invalid_maps_returns_zeros(self) -> None:
        result = _estimate_integration_scores([_invalid_map()], [])
        assert result.structural_alignment == 0.0

    def test_valid_maps_produce_scores(self) -> None:
        result = _estimate_integration_scores(
            [_valid_map(confidence=0.9)],
            [_opportunity()],
        )
        assert result.structural_alignment > 0
        assert result.counterfactual_dependence > 0
