"""Tests for ForgeBase extraction pack models."""

from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.forgebase.domain.enums import ProvenanceKind
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PackEntry,
    PriorArtBaselinePack,
)


def _eid(prefix: str, suffix: str = "01HXYZ12345678901234ABCDEF") -> EntityId:
    return EntityId(f"{prefix}_{suffix}")


def _rev(suffix: str = "01HXYZ12345678901234ABCDEF") -> VaultRevisionId:
    return VaultRevisionId(f"rev_{suffix}")


def _now() -> datetime:
    return datetime(2026, 4, 3, tzinfo=UTC)


def _make_entry(**overrides) -> PackEntry:
    defaults = dict(
        text="Pheromone decay enables load redistribution",
        origin_kind="concept_page",
        claim_ids=[_eid("claim")],
        page_ids=[_eid("page")],
        source_refs=[_eid("source")],
        epistemic_state="supported",
        trust_tier="authoritative",
        salience=0.85,
        provenance_kind=ProvenanceKind.EMPIRICAL,
    )
    defaults.update(overrides)
    return PackEntry(**defaults)


class TestPackEntry:
    def test_create(self):
        entry = _make_entry()
        assert entry.text == "Pheromone decay enables load redistribution"
        assert entry.origin_kind == "concept_page"
        assert len(entry.claim_ids) == 1
        assert len(entry.page_ids) == 1
        assert len(entry.source_refs) == 1
        assert entry.epistemic_state == "supported"
        assert entry.trust_tier == "authoritative"
        assert entry.salience == 0.85
        assert entry.provenance_kind == ProvenanceKind.EMPIRICAL

    def test_create_with_generated_provenance(self):
        entry = _make_entry(provenance_kind=ProvenanceKind.GENERATED)
        assert entry.provenance_kind == ProvenanceKind.GENERATED

    def test_create_with_empty_lists(self):
        entry = _make_entry(claim_ids=[], page_ids=[], source_refs=[])
        assert entry.claim_ids == []
        assert entry.page_ids == []
        assert entry.source_refs == []


class TestPriorArtBaselinePack:
    def test_create(self):
        pack = PriorArtBaselinePack(
            entries=[_make_entry(), _make_entry(text="Second entry")],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert len(pack.entries) == 2
        assert pack.vault_id == _eid("vault")
        assert pack.vault_revision_id == _rev()
        assert pack.branch_id is None
        assert pack.extraction_policy_version == "1.0.0"
        assert pack.assembler_version == "1.0.0"
        assert pack.extracted_at == _now()

    def test_create_empty(self):
        pack = PriorArtBaselinePack(
            entries=[],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert pack.entries == []

    def test_create_with_branch(self):
        pack = PriorArtBaselinePack(
            entries=[_make_entry()],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=_eid("wb"),
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert pack.branch_id == _eid("wb")


class TestDomainContextPack:
    def test_create(self):
        pack = DomainContextPack(
            concepts=[_make_entry(origin_kind="concept_page")],
            mechanisms=[_make_entry(origin_kind="mechanism_page")],
            open_questions=[_make_entry(origin_kind="open_question")],
            explored_directions=[_make_entry(origin_kind="invention")],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert len(pack.concepts) == 1
        assert len(pack.mechanisms) == 1
        assert len(pack.open_questions) == 1
        assert len(pack.explored_directions) == 1

    def test_create_empty_categories(self):
        pack = DomainContextPack(
            concepts=[],
            mechanisms=[],
            open_questions=[],
            explored_directions=[],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert pack.concepts == []
        assert pack.mechanisms == []
        assert pack.open_questions == []
        assert pack.explored_directions == []


class TestConstraintDossierPack:
    def test_create(self):
        pack = ConstraintDossierPack(
            hard_constraints=[_make_entry(origin_kind="constraint")],
            known_failure_modes=[_make_entry(origin_kind="failure_mode")],
            validated_objections=[_make_entry(origin_kind="objection")],
            unresolved_controversies=[_make_entry(origin_kind="controversy")],
            competitive_landscape=[_make_entry(origin_kind="competitive")],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert len(pack.hard_constraints) == 1
        assert len(pack.known_failure_modes) == 1
        assert len(pack.validated_objections) == 1
        assert len(pack.unresolved_controversies) == 1
        assert len(pack.competitive_landscape) == 1

    def test_create_empty_categories(self):
        pack = ConstraintDossierPack(
            hard_constraints=[],
            known_failure_modes=[],
            validated_objections=[],
            unresolved_controversies=[],
            competitive_landscape=[],
            vault_id=_eid("vault"),
            vault_revision_id=_rev(),
            branch_id=None,
            extraction_policy_version="1.0.0",
            assembler_version="1.0.0",
            extracted_at=_now(),
        )
        assert pack.hard_constraints == []
        assert pack.competitive_landscape == []
