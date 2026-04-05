"""Tests for injection boundary renderers.

These tests use synthetic pack objects — no database interaction required.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hephaestus.forgebase.domain.enums import ProvenanceKind, SourceTrustTier
from hephaestus.forgebase.domain.values import EntityId, VaultRevisionId
from hephaestus.forgebase.extraction.models import (
    ConstraintDossierPack,
    DomainContextPack,
    PackEntry,
    PriorArtBaselinePack,
)
from hephaestus.forgebase.extraction.renderers import (
    render_baseline_pack_to_blocked_paths,
    render_context_pack_to_reference_context,
    render_dossier_pack_to_baseline_dossier,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VAULT_ID = EntityId("vault_01AAAAAAAAAAAAAAAAAAA")
_REV_ID = VaultRevisionId("rev_01AAAAAAAAAAAAAAAAAAA")
_NOW = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)


def _entry(text: str, origin_kind: str = "test", salience: float = 0.5) -> PackEntry:
    """Create a minimal PackEntry for testing."""
    return PackEntry(
        text=text,
        origin_kind=origin_kind,
        claim_ids=[],
        page_ids=[],
        source_refs=[],
        epistemic_state="supported",
        trust_tier=SourceTrustTier.STANDARD.value,
        salience=salience,
        provenance_kind=ProvenanceKind.EMPIRICAL,
    )


def _baseline_pack(entries: list[PackEntry] | None = None) -> PriorArtBaselinePack:
    return PriorArtBaselinePack(
        entries=entries or [],
        vault_id=_VAULT_ID,
        vault_revision_id=_REV_ID,
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


def _context_pack(
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
        vault_id=_VAULT_ID,
        vault_revision_id=_REV_ID,
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


def _dossier_pack(
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
        vault_id=_VAULT_ID,
        vault_revision_id=_REV_ID,
        branch_id=None,
        extraction_policy_version="1.0.0",
        assembler_version="1.0.0",
        extracted_at=_NOW,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderBaselineToBlockedPaths:
    def test_render_baseline_to_strings(self):
        """Renders entries to a list of plain strings."""
        pack = _baseline_pack(
            [
                _entry("Pheromone evaporation prevents stagnation"),
                _entry("Swarm consensus requires quorum"),
            ]
        )
        result = render_baseline_pack_to_blocked_paths(pack)

        assert result == [
            "Pheromone evaporation prevents stagnation",
            "Swarm consensus requires quorum",
        ]

    def test_render_baseline_empty(self):
        """Empty pack produces empty list."""
        pack = _baseline_pack([])
        result = render_baseline_pack_to_blocked_paths(pack)
        assert result == []

    def test_render_baseline_strips_blank_entries(self):
        """Entries with blank text are filtered out."""
        pack = _baseline_pack(
            [
                _entry("Real claim"),
                _entry(""),
                _entry("   "),
                _entry("Another real claim"),
            ]
        )
        result = render_baseline_pack_to_blocked_paths(pack)
        assert result == ["Real claim", "Another real claim"]


class TestRenderContextToReferenceContext:
    def test_render_context_to_dict(self):
        """Produces a dict with expected keys."""
        pack = _context_pack(
            concepts=[_entry("Ant colony optimization")],
            mechanisms=[_entry("Pheromone gradient routing")],
            open_questions=[_entry("How does evaporation rate affect convergence?")],
            explored_directions=[_entry("Prior: centralized routing")],
        )
        result = render_context_pack_to_reference_context(pack)

        assert isinstance(result, dict)
        assert result["concepts"] == ["Ant colony optimization"]
        assert result["mechanisms"] == ["Pheromone gradient routing"]
        assert result["open_questions"] == ["How does evaporation rate affect convergence?"]
        assert result["explored_directions"] == ["Prior: centralized routing"]
        assert result["vault_id"] == str(_VAULT_ID)
        assert result["vault_revision"] == str(_REV_ID)

    def test_render_context_empty(self):
        """Empty pack produces dict with empty lists."""
        pack = _context_pack()
        result = render_context_pack_to_reference_context(pack)

        assert result["concepts"] == []
        assert result["mechanisms"] == []
        assert result["open_questions"] == []
        assert result["explored_directions"] == []


class TestRenderDossierToBaselineDossier:
    def test_render_dossier_to_baseline(self):
        """Produces a dict with standard_approaches, common_failure_modes, known_bottlenecks."""
        pack = _dossier_pack(
            hard_constraints=[_entry("Must handle 10K req/s")],
            known_failure_modes=[_entry("Cascade failure under flash crowds")],
            competitive_landscape=[_entry("Round-robin is the baseline")],
        )
        result = render_dossier_pack_to_baseline_dossier(pack)

        assert isinstance(result, dict)
        assert "Must handle 10K req/s" in result["known_bottlenecks"]
        assert "Cascade failure under flash crowds" in result["common_failure_modes"]
        assert "Round-robin is the baseline" in result["standard_approaches"]
        assert "summary" in result
        assert "keywords_to_avoid" in result
        assert "representative_systems" in result

    def test_render_dossier_empty(self):
        """Empty pack produces dict with empty lists."""
        pack = _dossier_pack()
        result = render_dossier_pack_to_baseline_dossier(pack)

        assert result["standard_approaches"] == []
        assert result["common_failure_modes"] == []
        assert result["known_bottlenecks"] == []
        assert result["keywords_to_avoid"] == []
        assert result["representative_systems"] == []

    def test_render_dossier_summary_format(self):
        """Summary includes constraint and failure mode counts."""
        pack = _dossier_pack(
            hard_constraints=[_entry("C1"), _entry("C2"), _entry("C3")],
            known_failure_modes=[_entry("F1")],
        )
        result = render_dossier_pack_to_baseline_dossier(pack)

        assert "3 constraints" in result["summary"]
        assert "1 failure modes" in result["summary"]
