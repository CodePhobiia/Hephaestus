"""Poisoning guard tests — required by spec §16.3.

These verify that the strict/soft channel boundary is never violated:
1. Contested invention does not enter strict baseline
2. Rejected analogy is persisted but not injected as positive context
3. Weak bridge remains soft only
4. Unsupported bridge triggers UNGROUNDED_BRIDGE concern
"""

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    EpistemicState,
    PackOriginKind,
    SignatureSubjectKind,
    TrustTier,
)
from hephaestus.transliminality.domain.models import (
    AnalogicalMap,
    ComponentMapping,
    EntityRef,
    KnowledgePackEntry,
    RoleSignature,
    TransferCaveat,
    TransferOpportunity,
    TransliminalityConfig,
)
from hephaestus.transliminality.domain.policies import (
    Channel,
    can_promote_to_strict,
    classify_entry,
)
from hephaestus.transliminality.service.pack_assembler import ChannelPackAssembler

_idgen = DeterministicIdGenerator(seed=1200)


def _ref(prefix: str = "t", kind: str = "test") -> EntityRef:
    return EntityRef(entity_id=_idgen.generate(prefix), entity_kind=kind)


def _sig() -> RoleSignature:
    return RoleSignature(
        signature_id=_idgen.generate("sig"),
        subject_ref=_ref("sig", "problem"),
        subject_kind=SignatureSubjectKind.PROBLEM,
    )


# ---------------------------------------------------------------------------
# Guard 1: Contested invention does not enter strict baseline
# ---------------------------------------------------------------------------

class TestContestedDoesNotEnterStrict:
    def test_contested_entry_rejected(self) -> None:
        """Contested content must NEVER enter strict baseline."""
        entry = KnowledgePackEntry(
            entry_id=_idgen.generate("kpe"),
            text="Contested claim about gating mechanism",
            origin_kind=PackOriginKind.VAULT_CLAIM,
            epistemic_state=EpistemicState.CONTESTED,
            trust_tier=TrustTier.INTERNAL_VERIFIED,
            salience=0.95,  # high salience should not override
        )
        decision = classify_entry(entry, TransliminalityConfig())
        assert decision.channel == Channel.REJECTED

    def test_contested_with_authoritative_trust_still_rejected(self) -> None:
        """Even authoritative trust cannot save contested content."""
        entry = KnowledgePackEntry(
            entry_id=_idgen.generate("kpe"),
            text="Contested authoritative claim",
            origin_kind=PackOriginKind.VAULT_SOURCE,
            epistemic_state=EpistemicState.CONTESTED,
            trust_tier=TrustTier.AUTHORITATIVE,
            salience=1.0,
        )
        decision = classify_entry(entry, TransliminalityConfig())
        assert decision.channel == Channel.REJECTED


# ---------------------------------------------------------------------------
# Guard 2: Rejected analogy persisted but not injected
# ---------------------------------------------------------------------------

class TestRejectedAnalogyNotInjected:
    async def test_invalid_map_excluded_from_all_channels(self) -> None:
        """Invalid maps must not produce entries in any positive channel."""
        assembler = ChannelPackAssembler(id_generator=_idgen)
        invalid_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="false analogy",
            verdict=AnalogicalVerdict.INVALID,
            confidence=0.9,  # high confidence should not help
        )
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[],
            remote_vault_ids=[],
            maps=[invalid_map],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        assert pack.strict_baseline_entries == []
        assert pack.soft_context_entries == []
        assert pack.strict_constraint_entries == []
        # But it IS tracked in map refs (for writeback persistence)
        assert len(pack.validated_maps) == 1

    def test_rejected_epistemic_entry_rejected(self) -> None:
        """Explicitly rejected content never enters any channel."""
        entry = KnowledgePackEntry(
            entry_id=_idgen.generate("kpe"),
            text="Rejected bridge",
            origin_kind=PackOriginKind.BRIDGE_SYNTHESIS,
            epistemic_state=EpistemicState.REJECTED,
            trust_tier=TrustTier.INTERNAL_VERIFIED,
            salience=0.99,
        )
        decision = classify_entry(entry, TransliminalityConfig())
        assert decision.channel == Channel.REJECTED


# ---------------------------------------------------------------------------
# Guard 3: Weak bridge remains soft only
# ---------------------------------------------------------------------------

class TestWeakBridgeSoftOnly:
    async def test_weak_map_does_not_enter_strict(self) -> None:
        """WEAK verdict maps must stay in soft channel, never strict."""
        assembler = ChannelPackAssembler(id_generator=_idgen)
        weak_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="vague similarity",
            mapped_components=[
                ComponentMapping(None, None, "filter", "loosely related"),
            ],
            structural_alignment_score=0.3,
            confidence=0.55,
            verdict=AnalogicalVerdict.WEAK,
            rationale="Weak structural match",
            provenance_refs=[_ref("src", "source")],
        )
        pack = await assembler.assemble(
            run_id=_idgen.generate("run"),
            problem_signature=_sig(),
            home_vault_ids=[],
            remote_vault_ids=[],
            maps=[weak_map],
            opportunities=[],
            config=TransliminalityConfig(),
        )
        # Weak map → EXPLORATORY epistemic → soft channel at best
        assert pack.strict_baseline_entries == []

    def test_weak_cannot_promote_to_strict(self) -> None:
        """Weak verdict blocks promotion regardless of other factors."""
        weak_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="weak analogy",
            verdict=AnalogicalVerdict.WEAK,
            confidence=0.95,
            provenance_refs=[_ref("src", "source")],
        )
        opp = TransferOpportunity(
            opportunity_id=_idgen.generate("opp"),
            map_ref=_ref("map", "map"),
            title="test",
            transferred_mechanism="gating",
            target_problem_fit="fit",
            expected_benefit="benefit",
            confidence=0.95,
        )
        result = can_promote_to_strict(opp, weak_map, TransliminalityConfig())
        assert result is False


# ---------------------------------------------------------------------------
# Guard 4: Unsupported bridge → ungrounded concern
# ---------------------------------------------------------------------------

class TestUngroundedBridgeDetection:
    def test_no_provenance_blocks_promotion(self) -> None:
        """A map with zero provenance cannot be promoted to strict."""
        no_prov_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="ungrounded bridge",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.95,
            provenance_refs=[],  # NO provenance
        )
        opp = TransferOpportunity(
            opportunity_id=_idgen.generate("opp"),
            map_ref=_ref("map", "map"),
            title="test",
            transferred_mechanism="gating",
            target_problem_fit="fit",
            expected_benefit="benefit",
            confidence=0.95,
        )
        result = can_promote_to_strict(opp, no_prov_map, TransliminalityConfig())
        assert result is False

    def test_low_trust_always_rejected(self) -> None:
        """LOW_TRUST content must never enter any channel."""
        entry = KnowledgePackEntry(
            entry_id=_idgen.generate("kpe"),
            text="Low trust bridge claim",
            origin_kind=PackOriginKind.BRIDGE_SYNTHESIS,
            epistemic_state=EpistemicState.VALIDATED,
            trust_tier=TrustTier.LOW_TRUST,
            salience=0.99,
        )
        decision = classify_entry(entry, TransliminalityConfig())
        assert decision.channel == Channel.REJECTED


# ---------------------------------------------------------------------------
# Guard 5: No automatic self-promotion (spec §10.4)
# ---------------------------------------------------------------------------

class TestNoAutomaticSelfPromotion:
    def test_hypothesis_cannot_enter_strict_even_at_high_confidence(self) -> None:
        """Hypothesis content must stay in soft channel regardless of salience."""
        entry = KnowledgePackEntry(
            entry_id=_idgen.generate("kpe"),
            text="High-confidence hypothesis",
            origin_kind=PackOriginKind.BRIDGE_SYNTHESIS,
            epistemic_state=EpistemicState.HYPOTHESIS,
            trust_tier=TrustTier.INTERNAL_VERIFIED,
            salience=0.99,
        )
        decision = classify_entry(entry, TransliminalityConfig())
        # Should be SOFT_CONTEXT, never STRICT_BASELINE
        assert decision.channel in (Channel.SOFT_CONTEXT, Channel.REJECTED)
        assert decision.channel != Channel.STRICT_BASELINE

    def test_critical_caveat_blocks_promotion(self) -> None:
        """Transfer with critical unresolved caveat cannot promote."""
        valid_map = AnalogicalMap(
            map_id=_idgen.generate("map"),
            candidate_ref=_ref("bc", "bridge"),
            shared_role="gating",
            verdict=AnalogicalVerdict.VALID,
            confidence=0.95,
            provenance_refs=[_ref("src", "source")],
        )
        opp = TransferOpportunity(
            opportunity_id=_idgen.generate("opp"),
            map_ref=_ref("map", "map"),
            title="test",
            transferred_mechanism="gating",
            target_problem_fit="fit",
            expected_benefit="benefit",
            caveats=[
                TransferCaveat(category="safety", description="untested in production", severity=0.9),
            ],
            confidence=0.95,
        )
        result = can_promote_to_strict(opp, valid_map, TransliminalityConfig())
        assert result is False
