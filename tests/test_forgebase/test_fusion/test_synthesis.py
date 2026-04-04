"""Tests for Stage 3 fusion synthesis — ranking, dedup, grouping, pack merging."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.contracts.fusion import (
    FusionRequest,
    FusionResult,
    PairFusionResult,
)
from hephaestus.forgebase.domain.enums import (
    AnalogyVerdict,
    ClaimStatus,
    FusionMode,
    ProvenanceKind,
)
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PackEntry,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.fusion.models import (
    AnalogicalMap,
    FusionManifest,
    PairFusionManifest,
    TransferOpportunity,
)
from hephaestus.forgebase.fusion.policy import FusionPolicy
from hephaestus.forgebase.fusion.synthesis import synthesize_fusion_result
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)


def _eid(prefix: str, n: int) -> EntityId:
    return EntityId(f"{prefix}_{n:026d}")


def _rev(n: int) -> VaultRevisionId:
    return VaultRevisionId(f"rev_{n:026d}")


def _pack_entry(
    text: str,
    claim_id: EntityId | None = None,
    page_id: EntityId | None = None,
    epistemic_state: str = "supported",
    trust_tier: str = "authoritative",
    salience: float = 0.8,
) -> PackEntry:
    return PackEntry(
        text=text,
        origin_kind="claim",
        claim_ids=[claim_id] if claim_id else [],
        page_ids=[page_id] if page_id else [],
        source_refs=[],
        epistemic_state=epistemic_state,
        trust_tier=trust_tier,
        salience=salience,
        provenance_kind=ProvenanceKind.DERIVED,
    )


def _baseline_pack(
    vault_n: int,
    entries: list[PackEntry],
) -> PriorArtBaselinePack:
    return PriorArtBaselinePack(
        entries=entries,
        vault_id=_eid("vault", vault_n),
        vault_revision_id=_rev(vault_n),
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


def _context_pack(
    vault_n: int,
    concepts: list[PackEntry] | None = None,
    mechanisms: list[PackEntry] | None = None,
    open_questions: list[PackEntry] | None = None,
    explored_directions: list[PackEntry] | None = None,
) -> DomainContextPack:
    return DomainContextPack(
        concepts=concepts or [],
        mechanisms=mechanisms or [],
        open_questions=open_questions or [],
        explored_directions=explored_directions or [],
        vault_id=_eid("vault", vault_n),
        vault_revision_id=_rev(vault_n),
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


def _dossier_pack(
    vault_n: int,
    hard_constraints: list[PackEntry] | None = None,
    known_failure_modes: list[PackEntry] | None = None,
    validated_objections: list[PackEntry] | None = None,
    unresolved_controversies: list[PackEntry] | None = None,
    competitive_landscape: list[PackEntry] | None = None,
) -> ConstraintDossierPack:
    return ConstraintDossierPack(
        hard_constraints=hard_constraints or [],
        known_failure_modes=known_failure_modes or [],
        validated_objections=validated_objections or [],
        unresolved_controversies=unresolved_controversies or [],
        competitive_landscape=competitive_landscape or [],
        vault_id=_eid("vault", vault_n),
        vault_revision_id=_rev(vault_n),
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


def _analogical_map(
    n: int,
    bridge_concept: str,
    confidence: float,
    verdict: AnalogyVerdict = AnalogyVerdict.STRONG_ANALOGY,
) -> AnalogicalMap:
    return AnalogicalMap(
        map_id=_eid("amap", n),
        bridge_concept=bridge_concept,
        left_structure=f"left_structure_{n}",
        right_structure=f"right_structure_{n}",
        confidence=confidence,
        verdict=verdict,
    )


def _transfer(
    n: int,
    mechanism: str,
    confidence: float,
) -> TransferOpportunity:
    return TransferOpportunity(
        opportunity_id=_eid("txfr", n),
        from_vault_id=_eid("vault", 1),
        to_vault_id=_eid("vault", 2),
        mechanism=mechanism,
        rationale=f"rationale_{n}",
        confidence=confidence,
    )


def _pair_manifest(left_n: int, right_n: int) -> PairFusionManifest:
    return PairFusionManifest(
        left_vault_id=_eid("vault", left_n),
        right_vault_id=_eid("vault", right_n),
        left_revision=_rev(left_n),
        right_revision=_rev(right_n),
        candidate_count=10,
        map_count=2,
        transfer_count=1,
    )


def _pair_result(
    left_n: int,
    right_n: int,
    maps: list[AnalogicalMap],
    transfers: list[TransferOpportunity],
    candidates_generated: int = 10,
) -> PairFusionResult:
    return PairFusionResult(
        left_vault_id=_eid("vault", left_n),
        right_vault_id=_eid("vault", right_n),
        candidates_generated=candidates_generated,
        maps_produced=maps,
        transfers_produced=transfers,
        pair_manifest=_pair_manifest(left_n, right_n),
    )


def _default_request(vault_ns: list[int] | None = None) -> FusionRequest:
    ns = vault_ns or [1, 2]
    return FusionRequest(
        vault_ids=[_eid("vault", n) for n in ns],
        problem="Improve battery longevity",
        fusion_mode=FusionMode.STRICT,
        max_bridges=20,
        max_transfers=10,
    )


def _default_metadata() -> dict:
    return {
        "analyzer_version": "mock_v1",
        "analyzer_calls": [],
        "created_at": _NOW,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSynthesizeMergesMaps:
    """Two pairs each with 2 maps -> merged, ranked by confidence."""

    @pytest.mark.asyncio
    async def test_synthesize_merges_maps(self):
        pair1_maps = [
            _analogical_map(1, "layered transport", 0.9),
            _analogical_map(2, "directed flow", 0.7),
        ]
        pair2_maps = [
            _analogical_map(3, "thermal gradient", 0.85),
            _analogical_map(4, "pressure equilibrium", 0.6),
        ]
        pair1 = _pair_result(1, 2, pair1_maps, [])
        pair2 = _pair_result(1, 3, pair2_maps, [])

        vault_packs = {
            _eid("vault", 1): (_baseline_pack(1, []), _context_pack(1), _dossier_pack(1)),
            _eid("vault", 2): (_baseline_pack(2, []), _context_pack(2), _dossier_pack(2)),
            _eid("vault", 3): (_baseline_pack(3, []), _context_pack(3), _dossier_pack(3)),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair1, pair2],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request([1, 2, 3]),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        assert isinstance(result, FusionResult)
        assert len(result.bridge_concepts) == 4
        # Ranked by confidence descending
        confidences = [m.confidence for m in result.bridge_concepts]
        assert confidences == sorted(confidences, reverse=True)


class TestSynthesizeDedupMaps:
    """Duplicate bridge concepts across pairs -> deduped, keeping highest confidence."""

    @pytest.mark.asyncio
    async def test_synthesize_dedup_maps(self):
        pair1_maps = [
            _analogical_map(1, "layered transport", 0.9),
            _analogical_map(2, "directed flow", 0.7),
        ]
        pair2_maps = [
            # Same bridge concept as pair1 map 1, lower confidence
            _analogical_map(3, "Layered Transport", 0.8),
            _analogical_map(4, "thermal gradient", 0.85),
        ]
        pair1 = _pair_result(1, 2, pair1_maps, [])
        pair2 = _pair_result(1, 3, pair2_maps, [])

        vault_packs = {
            _eid("vault", 1): (_baseline_pack(1, []), _context_pack(1), _dossier_pack(1)),
            _eid("vault", 2): (_baseline_pack(2, []), _context_pack(2), _dossier_pack(2)),
            _eid("vault", 3): (_baseline_pack(3, []), _context_pack(3), _dossier_pack(3)),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair1, pair2],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request([1, 2, 3]),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # "layered transport" appears twice (case-insensitive) -> only one kept
        bridge_concepts = [m.bridge_concept.lower().strip() for m in result.bridge_concepts]
        assert bridge_concepts.count("layered transport") == 1
        assert len(result.bridge_concepts) == 3

        # The kept one should be the highest confidence (0.9, not 0.8)
        layered = [m for m in result.bridge_concepts if m.bridge_concept.lower().strip() == "layered transport"][0]
        assert layered.confidence == 0.9


class TestSynthesizeCapsMaps:
    """More maps than max -> capped."""

    @pytest.mark.asyncio
    async def test_synthesize_caps_maps(self):
        maps = [
            _analogical_map(i, f"concept_{i}", confidence=1.0 - i * 0.05)
            for i in range(1, 15)
        ]
        pair = _pair_result(1, 2, maps, [])

        policy = FusionPolicy(max_analogical_maps=5)

        vault_packs = {
            _eid("vault", 1): (_baseline_pack(1, []), _context_pack(1), _dossier_pack(1)),
            _eid("vault", 2): (_baseline_pack(2, []), _context_pack(2), _dossier_pack(2)),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair],
            vault_packs=vault_packs,
            policy=policy,
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        assert len(result.bridge_concepts) == 5
        # Highest confidence maps kept
        assert result.bridge_concepts[0].confidence == 0.95  # concept_1
        assert result.bridge_concepts[4].confidence == 0.75  # concept_5


class TestSynthesizeGroupsTransfers:
    """Overlapping transfers deduped by mechanism."""

    @pytest.mark.asyncio
    async def test_synthesize_groups_transfers(self):
        transfers1 = [
            _transfer(1, "Apply hub-spoke optimization", 0.9),
            _transfer(2, "Use gradient descent for routing", 0.7),
        ]
        transfers2 = [
            # Duplicate mechanism (same text prefix after lower+strip)
            _transfer(3, "apply hub-spoke optimization", 0.8),
            _transfer(4, "Novel membrane approach", 0.85),
        ]
        pair1 = _pair_result(1, 2, [], transfers1)
        pair2 = _pair_result(1, 3, [], transfers2)

        vault_packs = {
            _eid("vault", 1): (_baseline_pack(1, []), _context_pack(1), _dossier_pack(1)),
            _eid("vault", 2): (_baseline_pack(2, []), _context_pack(2), _dossier_pack(2)),
            _eid("vault", 3): (_baseline_pack(3, []), _context_pack(3), _dossier_pack(3)),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair1, pair2],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request([1, 2, 3]),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # "apply hub-spoke optimization" deduped, keeping highest confidence (0.9)
        mechanisms = [t.mechanism.lower().strip()[:100] for t in result.transfer_opportunities]
        assert len(result.transfer_opportunities) == 3
        hub_spoke = [t for t in result.transfer_opportunities if "hub-spoke" in t.mechanism.lower()]
        assert len(hub_spoke) == 1
        assert hub_spoke[0].confidence == 0.9


class TestSynthesizeMergesBaselinePacks:
    """Entries from 2 vaults merged, provenance-deduped."""

    @pytest.mark.asyncio
    async def test_synthesize_merges_baseline_packs(self):
        # Shared claim ID -> should be deduped
        shared_claim = _eid("claim", 100)

        vault1_entries = [
            _pack_entry("Lithium intercalation is reversible", claim_id=shared_claim),
            _pack_entry("Cathode degradation under high C-rate", claim_id=_eid("claim", 101)),
        ]
        vault2_entries = [
            # Same canonical claim ID as vault1 entry 0 -> deduped
            _pack_entry("Li intercalation reversibility confirmed", claim_id=shared_claim),
            _pack_entry("Anode SEI layer growth", claim_id=_eid("claim", 201)),
        ]

        pair = _pair_result(1, 2, [], [])
        vault_packs = {
            _eid("vault", 1): (
                _baseline_pack(1, vault1_entries),
                _context_pack(1),
                _dossier_pack(1),
            ),
            _eid("vault", 2): (
                _baseline_pack(2, vault2_entries),
                _context_pack(2),
                _dossier_pack(2),
            ),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # 4 entries - 1 dedup (shared claim) = 3
        assert len(result.fused_baseline.entries) == 3


class TestSynthesizeMergesContextPacks:
    """Concepts/mechanisms from both vaults, capped per policy."""

    @pytest.mark.asyncio
    async def test_synthesize_merges_context_packs(self):
        vault1_concepts = [
            _pack_entry("Concept A", claim_id=_eid("claim", 1), salience=0.9),
            _pack_entry("Concept B", claim_id=_eid("claim", 2), salience=0.8),
        ]
        vault2_concepts = [
            # Different claim ID -> not deduped
            _pack_entry("Concept C", claim_id=_eid("claim", 3), salience=0.95),
            _pack_entry("Concept D", claim_id=_eid("claim", 4), salience=0.7),
        ]
        vault1_mechanisms = [
            _pack_entry("Mechanism X", claim_id=_eid("claim", 5), salience=0.85),
        ]
        vault2_mechanisms = [
            _pack_entry("Mechanism Y", claim_id=_eid("claim", 6), salience=0.9),
        ]

        pair = _pair_result(1, 2, [], [])
        vault_packs = {
            _eid("vault", 1): (
                _baseline_pack(1, []),
                _context_pack(1, concepts=vault1_concepts, mechanisms=vault1_mechanisms),
                _dossier_pack(1),
            ),
            _eid("vault", 2): (
                _baseline_pack(2, []),
                _context_pack(2, concepts=vault2_concepts, mechanisms=vault2_mechanisms),
                _dossier_pack(2),
            ),
        }

        # Cap concepts to 3 to verify capping
        policy = FusionPolicy(context_max_concepts=3)
        result = await synthesize_fusion_result(
            pair_results=[pair],
            vault_packs=vault_packs,
            policy=policy,
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # 4 concepts, capped to 3
        assert len(result.fused_context.concepts) == 3
        # Sorted by salience descending
        saliences = [e.salience for e in result.fused_context.concepts]
        assert saliences == sorted(saliences, reverse=True)
        # All mechanisms present (2 < default cap)
        assert len(result.fused_context.mechanisms) == 2


class TestSynthesizeMergesDossierPacks:
    """Constraints from both vaults, provenance-deduped."""

    @pytest.mark.asyncio
    async def test_synthesize_merges_dossier_packs(self):
        shared_claim = _eid("claim", 500)

        vault1_constraints = [
            _pack_entry("Must operate below 60C", claim_id=shared_claim),
            _pack_entry("Cycle count > 1000", claim_id=_eid("claim", 501)),
        ]
        vault2_constraints = [
            # Same canonical claim -> deduped
            _pack_entry("Operating temp below 60C required", claim_id=shared_claim),
            _pack_entry("Weight < 500g", claim_id=_eid("claim", 601)),
        ]
        vault1_failures = [
            _pack_entry("Thermal runaway at 80C", claim_id=_eid("claim", 502)),
        ]
        vault2_failures = [
            _pack_entry("Dendrite growth at high charge rate", claim_id=_eid("claim", 602)),
        ]

        pair = _pair_result(1, 2, [], [])
        vault_packs = {
            _eid("vault", 1): (
                _baseline_pack(1, []),
                _context_pack(1),
                _dossier_pack(
                    1,
                    hard_constraints=vault1_constraints,
                    known_failure_modes=vault1_failures,
                ),
            ),
            _eid("vault", 2): (
                _baseline_pack(2, []),
                _context_pack(2),
                _dossier_pack(
                    2,
                    hard_constraints=vault2_constraints,
                    known_failure_modes=vault2_failures,
                ),
            ),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # 4 constraints - 1 dedup = 3
        assert len(result.fused_dossier.hard_constraints) == 3
        # 2 failure modes, no dedup
        assert len(result.fused_dossier.known_failure_modes) == 2


class TestSynthesizePoisoningGuard:
    """CONTESTED entries must NOT appear in merged baseline."""

    @pytest.mark.asyncio
    async def test_synthesize_poisoning_guard(self):
        vault1_entries = [
            _pack_entry(
                "Verified safe claim",
                claim_id=_eid("claim", 1),
                epistemic_state="supported",
            ),
            _pack_entry(
                "Contested dangerous claim",
                claim_id=_eid("claim", 2),
                epistemic_state="contested",
            ),
        ]
        vault2_entries = [
            _pack_entry(
                "Another safe claim",
                claim_id=_eid("claim", 3),
                epistemic_state="supported",
            ),
            _pack_entry(
                "A hypothesis should be excluded from baseline",
                claim_id=_eid("claim", 4),
                epistemic_state="hypothesis",
            ),
        ]

        pair = _pair_result(1, 2, [], [])
        vault_packs = {
            _eid("vault", 1): (
                _baseline_pack(1, vault1_entries),
                _context_pack(1),
                _dossier_pack(1),
            ),
            _eid("vault", 2): (
                _baseline_pack(2, vault2_entries),
                _context_pack(2),
                _dossier_pack(2),
            ),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair],
            vault_packs=vault_packs,
            policy=FusionPolicy(baseline_min_claim_status=ClaimStatus.SUPPORTED),
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        # Only SUPPORTED entries survive
        assert len(result.fused_baseline.entries) == 2
        for entry in result.fused_baseline.entries:
            assert entry.epistemic_state == "supported"
            assert "contested" not in entry.text.lower() or entry.epistemic_state == "supported"


class TestSynthesizeBuildsManifest:
    """Manifest has correct counts and metadata."""

    @pytest.mark.asyncio
    async def test_synthesize_builds_manifest(self):
        maps1 = [_analogical_map(1, "concept A", 0.9)]
        maps2 = [_analogical_map(2, "concept B", 0.8), _analogical_map(3, "concept C", 0.7)]
        transfers1 = [_transfer(1, "transfer alpha", 0.85)]
        transfers2 = [_transfer(2, "transfer beta", 0.75)]

        pair1 = _pair_result(1, 2, maps1, transfers1, candidates_generated=15)
        pair2 = _pair_result(1, 3, maps2, transfers2, candidates_generated=20)

        vault_packs = {
            _eid("vault", 1): (_baseline_pack(1, []), _context_pack(1), _dossier_pack(1)),
            _eid("vault", 2): (_baseline_pack(2, []), _context_pack(2), _dossier_pack(2)),
            _eid("vault", 3): (_baseline_pack(3, []), _context_pack(3), _dossier_pack(3)),
        }

        result = await synthesize_fusion_result(
            pair_results=[pair1, pair2],
            vault_packs=vault_packs,
            policy=FusionPolicy(),
            request=_default_request([1, 2, 3]),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        manifest = result.fusion_manifest
        assert isinstance(manifest, FusionManifest)
        assert manifest.candidate_count == 35  # 15 + 20
        assert manifest.analyzed_count == 3  # 1 + 2 maps
        assert manifest.bridge_count == len(result.bridge_concepts)
        assert manifest.transfer_count == len(result.transfer_opportunities)
        assert manifest.policy_version == "1.0.0"
        assert manifest.analyzer_version == "mock_v1"
        assert manifest.created_at == _NOW
        assert len(manifest.pair_manifests) == 2
        assert manifest.vault_ids == [_eid("vault", 1), _eid("vault", 2), _eid("vault", 3)]
        assert manifest.problem == "Improve battery longevity"
        assert manifest.fusion_mode == FusionMode.STRICT


class TestSynthesizeEmptyPairs:
    """No pairs -> empty result."""

    @pytest.mark.asyncio
    async def test_synthesize_empty_pairs(self):
        result = await synthesize_fusion_result(
            pair_results=[],
            vault_packs={},
            policy=FusionPolicy(),
            request=_default_request(),
            manifest_metadata=_default_metadata(),
            id_generator=DeterministicIdGenerator(),
        )

        assert isinstance(result, FusionResult)
        assert result.bridge_concepts == []
        assert result.transfer_opportunities == []
        assert result.fused_baseline.entries == []
        assert result.fused_context.concepts == []
        assert result.fused_dossier.hard_constraints == []
        assert result.fusion_manifest.bridge_count == 0
        assert result.fusion_manifest.transfer_count == 0
        assert result.fusion_manifest.candidate_count == 0
