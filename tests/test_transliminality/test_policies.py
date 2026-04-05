"""Tests for transliminality channel policies."""


from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    AnalogyBreakCategory,
    EpistemicState,
    PackOriginKind,
    TrustTier,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    AnalogyBreak,
    EntityRef,
    KnowledgePackEntry,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityConfig,
)
from hephaestus.transliminality.domain.policies import (
    Channel,
    can_promote_to_strict,
    classify_entry,
    classify_map_for_constraint_channel,
)

_idgen = DeterministicIdGenerator(seed=100)


def _entry(
    *,
    epistemic: EpistemicState = EpistemicState.VALIDATED,
    trust: TrustTier = TrustTier.INTERNAL_VERIFIED,
    salience: float = 0.9,
) -> KnowledgePackEntry:
    return KnowledgePackEntry(
        entry_id=_idgen.generate("kpe"),
        text="test entry",
        origin_kind=PackOriginKind.VAULT_CLAIM,
        epistemic_state=epistemic,
        trust_tier=trust,
        salience=salience,
    )


def _map_ref() -> EntityRef:
    return EntityRef(entity_id=_idgen.generate("bc"), entity_kind="bridge_candidate")


def _prov_ref() -> EntityRef:
    return EntityRef(entity_id=_idgen.generate("src"), entity_kind="source")


class TestClassifyEntry:
    def test_verified_high_trust_enters_strict(self) -> None:
        cfg = TransliminalityConfig()
        entry = _entry(
            epistemic=EpistemicState.VERIFIED,
            trust=TrustTier.AUTHORITATIVE,
            salience=0.9,
        )
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.STRICT_BASELINE

    def test_rejected_always_rejected(self) -> None:
        cfg = TransliminalityConfig()
        entry = _entry(epistemic=EpistemicState.REJECTED)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_low_trust_always_rejected(self) -> None:
        cfg = TransliminalityConfig()
        entry = _entry(trust=TrustTier.LOW_TRUST)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_contested_rejected(self) -> None:
        cfg = TransliminalityConfig()
        entry = _entry(epistemic=EpistemicState.CONTESTED)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_hypothesis_enters_soft_when_allowed(self) -> None:
        cfg = TransliminalityConfig(allow_hypothesis_in_soft_channel=True)
        entry = _entry(epistemic=EpistemicState.HYPOTHESIS, salience=0.6)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.SOFT_CONTEXT

    def test_hypothesis_rejected_when_disallowed(self) -> None:
        cfg = TransliminalityConfig(allow_hypothesis_in_soft_channel=False)
        entry = _entry(epistemic=EpistemicState.HYPOTHESIS, salience=0.9)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_hypothesis_below_threshold_rejected(self) -> None:
        cfg = TransliminalityConfig(soft_channel_min_confidence=0.5)
        entry = _entry(epistemic=EpistemicState.HYPOTHESIS, salience=0.3)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_exploratory_enters_soft_above_threshold(self) -> None:
        cfg = TransliminalityConfig()
        entry = _entry(epistemic=EpistemicState.EXPLORATORY, salience=0.6)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.SOFT_CONTEXT

    def test_exploratory_below_threshold_rejected(self) -> None:
        cfg = TransliminalityConfig(soft_channel_min_confidence=0.5)
        entry = _entry(epistemic=EpistemicState.EXPLORATORY, salience=0.3)
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.REJECTED

    def test_validated_low_trust_enters_soft(self) -> None:
        """Validated content with non-strict trust goes to soft channel."""
        cfg = TransliminalityConfig()
        entry = _entry(
            epistemic=EpistemicState.VALIDATED,
            trust=TrustTier.INTERNAL_UNVERIFIED,
            salience=0.7,
        )
        result = classify_entry(entry, cfg)
        assert result.channel == Channel.SOFT_CONTEXT

    def test_strict_threshold_matters(self) -> None:
        """Even verified + authoritative fails if below strict threshold."""
        cfg = TransliminalityConfig(strict_channel_min_confidence=0.9)
        entry = _entry(
            epistemic=EpistemicState.VERIFIED,
            trust=TrustTier.AUTHORITATIVE,
            salience=0.85,
        )
        result = classify_entry(entry, cfg)
        # Falls through to soft channel since it's still validated
        assert result.channel == Channel.SOFT_CONTEXT


class TestClassifyMapForConstraintChannel:
    def test_invalid_map_rejected(self) -> None:
        cfg = TransliminalityConfig()
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="gating",
            verdict=AnalogicalVerdict.INVALID,
        )
        result = classify_map_for_constraint_channel(amap, cfg)
        assert result.channel == Channel.REJECTED

    def test_map_with_breaks_enters_constraint(self) -> None:
        cfg = TransliminalityConfig()
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="buffering",
            analogy_breaks=[
                AnalogyBreak(
                    category=AnalogyBreakCategory.SCALE_MISMATCH,
                    description="Molecular vs macro",
                    severity=0.5,
                ),
            ],
            verdict=AnalogicalVerdict.PARTIAL,
            confidence=0.65,
        )
        result = classify_map_for_constraint_channel(amap, cfg)
        assert result.channel == Channel.STRICT_CONSTRAINT

    def test_clean_map_no_constraint_entry(self) -> None:
        cfg = TransliminalityConfig()
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="routing",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.9,
        )
        result = classify_map_for_constraint_channel(amap, cfg)
        assert result.channel == Channel.REJECTED


class TestCanPromoteToStrict:
    def _opportunity(self, *, confidence: float = 0.9) -> TransferOpportunity:
        return TransferOpportunity(
            opportunity_id=_idgen.generate("top"),
            map_ref=_map_ref(),
            title="Test transfer",
            transferred_mechanism="gating",
            target_problem_fit="good fit",
            expected_benefit="improved selectivity",
            confidence=confidence,
        )

    def _valid_map(self) -> AnalogicalMap:
        return AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.9,
            provenance_refs=[_prov_ref()],
        )

    def test_valid_map_high_confidence_promotes(self) -> None:
        cfg = TransliminalityConfig()
        assert can_promote_to_strict(self._opportunity(), self._valid_map(), cfg)

    def test_partial_map_blocks_promotion(self) -> None:
        cfg = TransliminalityConfig()
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="gating",
            verdict=AnalogicalVerdict.PARTIAL,
            confidence=0.9,
            provenance_refs=[_prov_ref()],
        )
        assert not can_promote_to_strict(self._opportunity(), amap, cfg)

    def test_low_confidence_blocks_promotion(self) -> None:
        cfg = TransliminalityConfig(strict_channel_min_confidence=0.8)
        assert not can_promote_to_strict(
            self._opportunity(confidence=0.5), self._valid_map(), cfg,
        )

    def test_critical_caveat_blocks_promotion(self) -> None:
        cfg = TransliminalityConfig()
        opp = TransferOpportunity(
            opportunity_id=_idgen.generate("top"),
            map_ref=_map_ref(),
            title="Test",
            transferred_mechanism="gating",
            target_problem_fit="fit",
            expected_benefit="benefit",
            caveats=[TransferCaveat(category="safety", description="untested", severity=0.9)],
            confidence=0.9,
        )
        assert not can_promote_to_strict(opp, self._valid_map(), cfg)

    def test_no_provenance_blocks_promotion(self) -> None:
        cfg = TransliminalityConfig()
        amap = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_map_ref(),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.9,
            provenance_refs=[],  # no provenance
        )
        assert not can_promote_to_strict(self._opportunity(), amap, cfg)
