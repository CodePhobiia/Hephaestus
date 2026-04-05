"""Tests for injection adapters (Genesis, Pantheon)."""

from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.transliminality.adapters.genesis import (
    build_genesis_injection,
)
from hephaestus.transliminality.adapters.pantheon import (
    build_pantheon_dossier,
)
from hephaestus.transliminality.domain.enums import (
    EpistemicState,
    PackOriginKind,
    TransliminalObjectionType,
    TrustTier,
)
from hephaestus.transliminality.domain.models import (
    EntityRef,
    IntegrationScoreBreakdown,
    KnowledgePackEntry,
    TransliminalityPack,
)

_idgen = DeterministicIdGenerator(seed=900)


def _ref(prefix: str, kind: str) -> EntityRef:
    return EntityRef(entity_id=_idgen.generate(prefix), entity_kind=kind)


def _entry(text: str, *, epistemic: EpistemicState = EpistemicState.VALIDATED) -> KnowledgePackEntry:
    return KnowledgePackEntry(
        entry_id=_idgen.generate("kpe"),
        text=text,
        origin_kind=PackOriginKind.BRIDGE_SYNTHESIS,
        epistemic_state=epistemic,
        trust_tier=TrustTier.INTERNAL_VERIFIED,
        salience=0.8,
    )


def _pack(
    *,
    strict_baseline: list[KnowledgePackEntry] | None = None,
    soft_context: list[KnowledgePackEntry] | None = None,
    strict_constraint: list[KnowledgePackEntry] | None = None,
) -> TransliminalityPack:
    return TransliminalityPack(
        pack_id=_idgen.generate("tpack"),
        run_id=_idgen.generate("run"),
        problem_signature_ref=_ref("sig", "role_signature"),
        home_vault_ids=[_idgen.generate("vault")],
        remote_vault_ids=[_idgen.generate("vault")],
        validated_maps=[_ref("map", "analogical_map")],
        transfer_opportunities=[_ref("opp", "transfer_opportunity")],
        strict_baseline_entries=strict_baseline or [],
        soft_context_entries=soft_context or [],
        strict_constraint_entries=strict_constraint or [],
        integration_score_preview=IntegrationScoreBreakdown(
            structural_alignment=0.8,
            constraint_fidelity=0.7,
            source_grounding=0.6,
        ),
    )


# ---------------------------------------------------------------------------
# Genesis injection tests
# ---------------------------------------------------------------------------

class TestGenesisInjection:
    def test_empty_pack_produces_empty_supplement(self) -> None:
        pack = _pack()
        inj = build_genesis_injection(pack)
        assert inj.system_prompt_supplement == ""
        assert inj.extra_blocked_paths == []

    def test_soft_context_in_supplement(self) -> None:
        pack = _pack(soft_context=[_entry("Immune checkpoint gating mechanism")])
        inj = build_genesis_injection(pack)
        assert "Immune checkpoint" in inj.system_prompt_supplement
        assert "CROSS-DOMAIN SYNTHESIS" in inj.system_prompt_supplement

    def test_constraint_warnings_in_supplement(self) -> None:
        pack = _pack(strict_constraint=[_entry("Analogy break: scale mismatch")])
        inj = build_genesis_injection(pack)
        assert "scale mismatch" in inj.system_prompt_supplement

    def test_strict_baseline_becomes_blocked_path(self) -> None:
        pack = _pack(strict_baseline=[_entry("Prior art: conventional filter design")])
        inj = build_genesis_injection(pack)
        assert len(inj.extra_blocked_paths) == 1
        assert "conventional filter" in inj.extra_blocked_paths[0]

    def test_lens_reference_context_structure(self) -> None:
        pack = _pack(
            soft_context=[_entry("bridge concept A")],
            strict_constraint=[_entry("constraint warning B")],
        )
        inj = build_genesis_injection(pack)
        ctx = inj.lens_reference_context
        assert "transliminality_pack_id" in ctx
        assert len(ctx["bridge_concepts"]) == 1
        assert len(ctx["constraint_warnings"]) == 1
        assert ctx["validated_map_count"] == 1
        assert ctx["integration_score"]["structural_alignment"] == 0.8


# ---------------------------------------------------------------------------
# Pantheon injection tests
# ---------------------------------------------------------------------------

class TestPantheonDossier:
    def test_empty_pack_produces_no_context(self) -> None:
        pack = _pack()
        dossier = build_pantheon_dossier(pack)
        assert dossier.summary == "No transliminality context."

    def test_constraint_entries_in_dossier(self) -> None:
        pack = _pack(strict_constraint=[
            _entry("Broken constraint: energy bound"),
            _entry("Analogy break: scale mismatch"),
        ])
        dossier = build_pantheon_dossier(pack)
        assert len(dossier.constraint_entries) == 2
        assert "constraint" in dossier.summary.lower()

    def test_analogy_warnings_extracted(self) -> None:
        pack = _pack(strict_constraint=[
            _entry("Analogy break at scale boundary"),
        ])
        dossier = build_pantheon_dossier(pack)
        assert len(dossier.analogy_warnings) == 1

    def test_objection_types_registered(self) -> None:
        pack = _pack()
        dossier = build_pantheon_dossier(pack)
        assert len(dossier.objection_types) == len(TransliminalObjectionType)
        assert TransliminalObjectionType.ORNAMENTAL_ANALOGY.value in dossier.objection_types

    def test_summary_mentions_soft_context(self) -> None:
        pack = _pack(soft_context=[_entry("bridge A"), _entry("bridge B")])
        dossier = build_pantheon_dossier(pack)
        assert "2 cross-domain bridges" in dossier.summary

    def test_dossier_has_summary_attribute(self) -> None:
        """PantheonCoordinator accesses baseline_dossier.summary."""
        pack = _pack(strict_constraint=[_entry("test")])
        dossier = build_pantheon_dossier(pack)
        assert hasattr(dossier, "summary")
        assert isinstance(dossier.summary, str)
