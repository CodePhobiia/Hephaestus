"""Tests for fusion adapter — analogy/transfer model conversion."""

from hephaestus.forgebase.domain.values import EntityId
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.adapters.fusion import (
    _map_verdict,
    convert_analogical_map,
    convert_analyzer_results,
    convert_transfer_opportunity,
)
from hephaestus.transliminality.domain.enums import (
    AnalogicalVerdict,
    EpistemicState,
)

_idgen = DeterministicIdGenerator(seed=1000)


class _FakeComponentMapping:
    def __init__(self, role: str, rationale: str) -> None:
        self.shared_role = role
        self.rationale = rationale


class _FakeConstraintMapping:
    def __init__(self, name: str, *, preserved: bool = True) -> None:
        self.constraint = name
        self.preserved = preserved


class _FakeAnalogyBreak:
    def __init__(self, cat: str, desc: str, sev: float = 0.5) -> None:
        self.category = cat
        self.description = desc
        self.severity = sev


class _FakeFBMap:
    def __init__(
        self,
        *,
        verdict: str = "strong_analogy",
        confidence: float = 0.8,
    ) -> None:
        self.bridge_concept = "selective gating"
        self.left_structure = "immune checkpoint"
        self.right_structure = "rate limiter"
        self.verdict = verdict
        self.confidence = confidence
        self.source_candidates = [_idgen.generate("bcand")]
        self.mapped_components = [
            _FakeComponentMapping("gate", "Both control admission"),
        ]
        self.mapped_constraints = [
            _FakeConstraintMapping("capacity", preserved=True),
            _FakeConstraintMapping("energy", preserved=False),
        ]
        self.analogy_breaks = [
            _FakeAnalogyBreak("scale_mismatch", "Molecular vs macro"),
        ]
        self.left_page_refs = [_idgen.generate("page")]
        self.right_page_refs = [_idgen.generate("page")]
        self.left_claim_refs: list[EntityId] = []
        self.right_claim_refs: list[EntityId] = []


class _FakeFBOpportunity:
    def __init__(self, *, confidence: float = 0.7) -> None:
        self.mechanism = "staged activation gating"
        self.rationale = "Gating mechanism transfers to rate limiting"
        self.caveats = ["Scale differs", "Timing differs"]
        self.caveat_categories = ["scale", "temporal"]
        self.confidence = confidence
        self.analogical_map_id = _idgen.generate("amap")
        self.from_page_refs = [_idgen.generate("page")]
        self.to_page_refs = [_idgen.generate("page")]
        self.from_claim_refs: list[EntityId] = []


class TestVerdictMapping:
    def test_strong_maps_to_valid(self) -> None:
        assert _map_verdict("strong_analogy") == AnalogicalVerdict.VALID

    def test_weak_maps_to_weak(self) -> None:
        assert _map_verdict("weak_analogy") == AnalogicalVerdict.WEAK

    def test_no_analogy_maps_to_invalid(self) -> None:
        assert _map_verdict("no_analogy") == AnalogicalVerdict.INVALID

    def test_unknown_maps_to_invalid(self) -> None:
        assert _map_verdict("something_else") == AnalogicalVerdict.INVALID


class TestConvertAnalogicalMap:
    def test_basic_conversion(self) -> None:
        fb_map = _FakeFBMap()
        tlim = convert_analogical_map(fb_map, id_generator=_idgen)

        assert tlim.shared_role == "selective gating"
        assert tlim.verdict == AnalogicalVerdict.VALID
        assert tlim.confidence == 0.8
        assert len(tlim.mapped_components) == 1
        assert tlim.mapped_components[0].shared_role == "gate"

    def test_constraint_preservation(self) -> None:
        fb_map = _FakeFBMap()
        tlim = convert_analogical_map(fb_map, id_generator=_idgen)

        assert "capacity" in tlim.preserved_constraints
        assert "energy" in tlim.broken_constraints

    def test_breaks_converted(self) -> None:
        fb_map = _FakeFBMap()
        tlim = convert_analogical_map(fb_map, id_generator=_idgen)

        assert len(tlim.analogy_breaks) == 1
        assert "Molecular" in tlim.analogy_breaks[0].description

    def test_provenance_from_page_refs(self) -> None:
        fb_map = _FakeFBMap()
        tlim = convert_analogical_map(fb_map, id_generator=_idgen)

        assert len(tlim.provenance_refs) == 2  # left + right page refs

    def test_weak_verdict(self) -> None:
        fb_map = _FakeFBMap(verdict="weak_analogy", confidence=0.4)
        tlim = convert_analogical_map(fb_map, id_generator=_idgen)

        assert tlim.verdict == AnalogicalVerdict.WEAK
        assert tlim.confidence == 0.4


class TestConvertTransferOpportunity:
    def test_basic_conversion(self) -> None:
        fb_opp = _FakeFBOpportunity()
        tlim = convert_transfer_opportunity(fb_opp, id_generator=_idgen)

        assert tlim.title == "staged activation gating"
        assert tlim.transferred_mechanism == "staged activation gating"
        assert tlim.confidence == 0.7

    def test_caveats_converted(self) -> None:
        fb_opp = _FakeFBOpportunity()
        tlim = convert_transfer_opportunity(fb_opp, id_generator=_idgen)

        assert len(tlim.caveats) == 2
        assert tlim.caveats[0].category == "scale"
        assert tlim.caveats[1].category == "temporal"

    def test_low_confidence_is_hypothesis(self) -> None:
        fb_opp = _FakeFBOpportunity(confidence=0.4)
        tlim = convert_transfer_opportunity(fb_opp, id_generator=_idgen)

        assert tlim.epistemic_state == EpistemicState.HYPOTHESIS

    def test_high_confidence_is_validated(self) -> None:
        fb_opp = _FakeFBOpportunity(confidence=0.85)
        tlim = convert_transfer_opportunity(fb_opp, id_generator=_idgen)

        assert tlim.epistemic_state == EpistemicState.VALIDATED

    def test_supporting_refs_from_page_refs(self) -> None:
        fb_opp = _FakeFBOpportunity()
        tlim = convert_transfer_opportunity(fb_opp, id_generator=_idgen)

        assert len(tlim.supporting_refs) == 2  # from + to


class TestBatchConversion:
    def test_convert_analyzer_results(self) -> None:
        maps, opps = convert_analyzer_results(
            [_FakeFBMap(), _FakeFBMap(verdict="weak_analogy")],
            [_FakeFBOpportunity()],
            id_generator=_idgen,
        )
        assert len(maps) == 2
        assert len(opps) == 1
        assert maps[0].verdict == AnalogicalVerdict.VALID
        assert maps[1].verdict == AnalogicalVerdict.WEAK
