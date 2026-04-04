"""Stage 3 fusion synthesis — ranking, dedup, grouping, provenance-aware pack merging.

Merges per-pair fusion results into a single FusionResult with fused packs.
Pack merging follows strict provenance rules:
- Baseline: strictest — only entries meeting trust requirements, deduped by canonical claim ID
- Context: broadest — union per category, deduped by provenance, capped by policy
- Dossier: governance-grade — union per category, deduped by provenance
"""
from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.forgebase.contracts.fusion import (
    FusionRequest,
    FusionResult,
    PairFusionResult,
)
from hephaestus.forgebase.domain.enums import AnalogyVerdict, ClaimStatus
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
    TransferOpportunity,
)
from hephaestus.forgebase.fusion.policy import FusionPolicy
from hephaestus.forgebase.service.id_generator import IdGenerator, UlidIdGenerator


# ---------------------------------------------------------------------------
# Epistemic trust ordering for baseline filtering
# ---------------------------------------------------------------------------

_CLAIM_STATUS_TRUST_ORDER: dict[str, int] = {
    ClaimStatus.SUPPORTED.value: 4,
    ClaimStatus.INFERRED.value: 3,
    ClaimStatus.HYPOTHESIS.value: 2,
    ClaimStatus.CONTESTED.value: 1,
    ClaimStatus.STALE.value: 0,
}


def _meets_baseline_trust(entry: PackEntry, min_status: ClaimStatus) -> bool:
    """Check whether a pack entry meets the minimum epistemic trust for baseline inclusion.

    Entries with epistemic_state at or above the minimum claim status are included.
    Unknown epistemic states are excluded (conservative).
    """
    min_trust = _CLAIM_STATUS_TRUST_ORDER.get(min_status.value, 4)
    entry_trust = _CLAIM_STATUS_TRUST_ORDER.get(entry.epistemic_state, -1)
    return entry_trust >= min_trust


# ---------------------------------------------------------------------------
# Provenance-aware dedup
# ---------------------------------------------------------------------------

def _dedup_pack_entries(entries: list[PackEntry]) -> list[PackEntry]:
    """Deduplicate pack entries by provenance fingerprint.

    - Entries with the same canonical claim/page ID -> merge (keep first, union refs)
    - Entries with different IDs but same text -> keep both (conservative)
    """
    seen_ids: set[str] = set()
    result: list[PackEntry] = []

    for entry in entries:
        # Fingerprint by first claim ID or first page ID
        fp: str | None = None
        if entry.claim_ids:
            fp = str(entry.claim_ids[0])
        elif entry.page_ids:
            fp = str(entry.page_ids[0])

        if fp and fp in seen_ids:
            continue  # Skip duplicate by provenance

        if fp:
            seen_ids.add(fp)
        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Map ranking and dedup
# ---------------------------------------------------------------------------

def _rank_and_cap_maps(
    maps: list[AnalogicalMap],
    max_maps: int,
) -> list[AnalogicalMap]:
    """Rank by confidence, suppress duplicates, cap.

    1. Remove NO_ANALOGY and INVALID verdict maps
    2. Sort by confidence descending
    3. Dedup by bridge_concept (case-insensitive, keep highest confidence)
    4. Cap to max_maps
    """
    # Remove NO_ANALOGY and INVALID
    valid = [
        m for m in maps
        if m.verdict in (AnalogyVerdict.STRONG_ANALOGY, AnalogyVerdict.WEAK_ANALOGY)
    ]
    # Sort by confidence descending
    valid.sort(key=lambda m: m.confidence, reverse=True)
    # Dedup by bridge_concept (keep highest confidence per concept)
    seen_concepts: set[str] = set()
    deduped: list[AnalogicalMap] = []
    for m in valid:
        concept_key = m.bridge_concept.lower().strip()
        if concept_key in seen_concepts:
            continue
        seen_concepts.add(concept_key)
        deduped.append(m)
    # Cap
    return deduped[:max_maps]


# ---------------------------------------------------------------------------
# Transfer grouping and dedup
# ---------------------------------------------------------------------------

def _group_and_cap_transfers(
    transfers: list[TransferOpportunity],
    max_transfers: int,
) -> list[TransferOpportunity]:
    """Group overlapping transfers, sort by confidence, cap.

    1. Sort by confidence descending
    2. Dedup by mechanism text (case-insensitive, first 100 chars)
    3. Cap to max_transfers
    """
    # Sort by confidence descending
    transfers.sort(key=lambda t: t.confidence, reverse=True)
    # Dedup by mechanism text similarity (simple: exact match after lowering)
    seen: set[str] = set()
    deduped: list[TransferOpportunity] = []
    for t in transfers:
        key = t.mechanism.lower().strip()[:100]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped[:max_transfers]


# ---------------------------------------------------------------------------
# Pack merging helpers
# ---------------------------------------------------------------------------

def _merge_baseline_packs(
    packs: list[PriorArtBaselinePack],
    policy: FusionPolicy,
) -> list[PackEntry]:
    """Merge baseline packs with strictest rules.

    - Union entries from all vaults
    - Filter by baseline trust requirements (only SUPPORTED or above)
    - Dedup by provenance (canonical claim/page ID)
    """
    all_entries: list[PackEntry] = []
    for pack in packs:
        for entry in pack.entries:
            if _meets_baseline_trust(entry, policy.baseline_min_claim_status):
                all_entries.append(entry)
    return _dedup_pack_entries(all_entries)


def _merge_context_category(
    entries: list[PackEntry],
    max_count: int,
) -> list[PackEntry]:
    """Merge a single context category: dedup, sort by salience, cap."""
    deduped = _dedup_pack_entries(entries)
    deduped.sort(key=lambda e: e.salience, reverse=True)
    return deduped[:max_count]


def _merge_context_packs(
    packs: list[DomainContextPack],
    policy: FusionPolicy,
) -> tuple[list[PackEntry], list[PackEntry], list[PackEntry], list[PackEntry]]:
    """Merge context packs: union per category, dedup, sort by salience, cap.

    Returns (concepts, mechanisms, open_questions, explored_directions).
    """
    all_concepts: list[PackEntry] = []
    all_mechanisms: list[PackEntry] = []
    all_open_questions: list[PackEntry] = []
    all_explored_directions: list[PackEntry] = []

    for pack in packs:
        all_concepts.extend(pack.concepts)
        all_mechanisms.extend(pack.mechanisms)
        all_open_questions.extend(pack.open_questions)
        all_explored_directions.extend(pack.explored_directions)

    concepts = _merge_context_category(all_concepts, policy.context_max_concepts)
    mechanisms = _merge_context_category(all_mechanisms, policy.context_max_mechanisms)
    open_questions = _merge_context_category(all_open_questions, policy.context_max_open_questions)
    explored_directions = _merge_context_category(
        all_explored_directions, policy.context_max_explored_directions,
    )

    return concepts, mechanisms, open_questions, explored_directions


def _merge_dossier_packs(
    packs: list[ConstraintDossierPack],
) -> tuple[
    list[PackEntry],
    list[PackEntry],
    list[PackEntry],
    list[PackEntry],
    list[PackEntry],
]:
    """Merge dossier packs: union per category, provenance-deduped.

    Returns (hard_constraints, known_failure_modes, validated_objections,
             unresolved_controversies, competitive_landscape).
    """
    all_hard: list[PackEntry] = []
    all_failures: list[PackEntry] = []
    all_objections: list[PackEntry] = []
    all_controversies: list[PackEntry] = []
    all_competitive: list[PackEntry] = []

    for pack in packs:
        all_hard.extend(pack.hard_constraints)
        all_failures.extend(pack.known_failure_modes)
        all_objections.extend(pack.validated_objections)
        all_controversies.extend(pack.unresolved_controversies)
        all_competitive.extend(pack.competitive_landscape)

    return (
        _dedup_pack_entries(all_hard),
        _dedup_pack_entries(all_failures),
        _dedup_pack_entries(all_objections),
        _dedup_pack_entries(all_controversies),
        _dedup_pack_entries(all_competitive),
    )


# ---------------------------------------------------------------------------
# Main synthesis function
# ---------------------------------------------------------------------------

async def synthesize_fusion_result(
    pair_results: list[PairFusionResult],
    vault_packs: dict[EntityId, tuple[PriorArtBaselinePack, DomainContextPack, ConstraintDossierPack]],
    policy: FusionPolicy,
    request: FusionRequest,
    manifest_metadata: dict,
    id_generator: IdGenerator | None = None,
) -> FusionResult:
    """Synthesize final fusion output from pair-level results.

    1. Collect all AnalogicalMaps from all pairs, rank by confidence
    2. Suppress duplicate maps (same bridge concept + same vault pair)
    3. Collect all TransferOpportunities, group overlapping ones
    4. Cap maps and transfers per policy
    5. Merge baseline packs (strict, provenance-aware dedup)
    6. Merge context packs (broad, capped per category)
    7. Merge dossier packs (governance-grade)
    8. Build FusionManifest
    9. Return FusionResult
    """
    id_gen = id_generator or UlidIdGenerator()

    # --- 1-4. Collect, rank, dedup, cap maps and transfers ---
    all_maps: list[AnalogicalMap] = []
    all_transfers: list[TransferOpportunity] = []

    for pr in pair_results:
        all_maps.extend(pr.maps_produced)
        all_transfers.extend(pr.transfers_produced)

    final_maps = _rank_and_cap_maps(all_maps, policy.max_analogical_maps)
    final_transfers = _group_and_cap_transfers(all_transfers, policy.max_transfer_opportunities)

    # --- 5. Merge baseline packs ---
    baseline_packs = [bp for bp, _, _ in vault_packs.values()]
    merged_baseline_entries = _merge_baseline_packs(baseline_packs, policy)

    # Build a synthetic fused baseline pack (not tied to a single vault)
    fused_baseline = PriorArtBaselinePack(
        entries=merged_baseline_entries,
        vault_id=id_gen.generate("fvault"),
        vault_revision_id=VaultRevisionId(f"rev_{0:026d}"),
        branch_id=None,
        extraction_policy_version=policy.policy_version,
        assembler_version="fusion_synthesis_v1",
        extracted_at=manifest_metadata.get("created_at", datetime.now(UTC)),
    )

    # --- 6. Merge context packs ---
    context_packs = [cp for _, cp, _ in vault_packs.values()]
    concepts, mechanisms, open_questions, explored_directions = _merge_context_packs(
        context_packs, policy,
    )

    fused_context = DomainContextPack(
        concepts=concepts,
        mechanisms=mechanisms,
        open_questions=open_questions,
        explored_directions=explored_directions,
        vault_id=id_gen.generate("fvault"),
        vault_revision_id=VaultRevisionId(f"rev_{0:026d}"),
        branch_id=None,
        extraction_policy_version=policy.policy_version,
        assembler_version="fusion_synthesis_v1",
        extracted_at=manifest_metadata.get("created_at", datetime.now(UTC)),
    )

    # --- 7. Merge dossier packs ---
    dossier_packs = [dp for _, _, dp in vault_packs.values()]
    (
        hard_constraints,
        known_failure_modes,
        validated_objections,
        unresolved_controversies,
        competitive_landscape,
    ) = _merge_dossier_packs(dossier_packs)

    fused_dossier = ConstraintDossierPack(
        hard_constraints=hard_constraints,
        known_failure_modes=known_failure_modes,
        validated_objections=validated_objections,
        unresolved_controversies=unresolved_controversies,
        competitive_landscape=competitive_landscape,
        vault_id=id_gen.generate("fvault"),
        vault_revision_id=VaultRevisionId(f"rev_{0:026d}"),
        branch_id=None,
        extraction_policy_version=policy.policy_version,
        assembler_version="fusion_synthesis_v1",
        extracted_at=manifest_metadata.get("created_at", datetime.now(UTC)),
    )

    # --- 8. Build FusionManifest ---
    manifest = FusionManifest(
        manifest_id=id_gen.generate("fmfst"),
        vault_ids=request.vault_ids,
        problem=request.problem,
        fusion_mode=request.fusion_mode,
        candidate_count=sum(pr.candidates_generated for pr in pair_results),
        analyzed_count=sum(len(pr.maps_produced) for pr in pair_results),
        bridge_count=len(final_maps),
        transfer_count=len(final_transfers),
        policy_version=policy.policy_version,
        analyzer_version=manifest_metadata.get("analyzer_version", ""),
        analyzer_calls=manifest_metadata.get("analyzer_calls", []),
        pair_manifests=[pr.pair_manifest for pr in pair_results],
        created_at=manifest_metadata.get("created_at", datetime.now(UTC)),
    )

    # --- 9. Build FusionResult ---
    return FusionResult(
        fusion_id=id_gen.generate("fusion"),
        request=request,
        bridge_concepts=final_maps,
        transfer_opportunities=final_transfers,
        fused_baseline=fused_baseline,
        fused_context=fused_context,
        fused_dossier=fused_dossier,
        pair_results=list(pair_results),
        fusion_manifest=manifest,
        created_at=manifest_metadata.get("created_at", datetime.now(UTC)),
    )
