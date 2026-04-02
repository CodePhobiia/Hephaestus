"""Comprehensive tests for hephaestus.session.schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hephaestus.lenses.state import (
    CompositeLens,
    FoldState,
    GuardDecision,
    LensBundleMember,
    LensBundleProof,
    LensEngineState,
    LensLineage,
    ResearchReferenceArtifact,
    ResearchReferenceState,
)
from hephaestus.session.schema import (
    EntryType,
    InventionSnapshot,
    Role,
    Session,
    SessionMeta,
    TranscriptEntry,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_session(**kwargs) -> Session:
    """Create a session with sensible defaults."""
    meta = SessionMeta(
        id="abc123",
        name="test-session",
        model="claude-opus-4-5",
        backend="api",
        tags=["test"],
    )
    s = Session(meta=meta, **kwargs)
    return s


def _populated_session() -> Session:
    """Session with several transcript entries and an invention."""
    s = _make_session()
    for i in range(15):
        role = Role.USER.value if i % 2 == 0 else Role.ASSISTANT.value
        s.append_entry(role, f"message {i}")
    s.add_invention(
        invention_name="Solar Sail Membrane",
        source_domain="biology",
        key_insight="cell membrane selective permeability",
        score=8.5,
    )
    return s


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=2,
        active_bundle_id="bundle:adaptive:abc123",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
                source_domain="Immune System",
                domain_family="biology",
                domain_distance=0.91,
                structural_relevance=0.72,
                retrieval_score=0.86,
                fidelity_score=0.80,
                confidence=0.84,
                matched_patterns=["allocation", "memory"],
                evidence_atoms=["Memory persists."],
                card_fingerprint64=111,
            ),
            LensBundleMember(
                lens_id="economics_markets",
                lens_name="Market Making",
                domain_name="economics::Market Making",
                source_domain="Market Making",
                domain_family="economics",
                domain_distance=0.88,
                structural_relevance=0.66,
                retrieval_score=0.79,
                fidelity_score=0.74,
                confidence=0.76,
                matched_patterns=["allocation", "feedback"],
                evidence_atoms=["Prices encode pressure."],
                card_fingerprint64=222,
            ),
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:abc123",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune", "economics_markets"],
                status="active",
                proof_status="proven",
                cohesion_score=0.74,
                higher_order_score=0.63,
                proof_fingerprint="proof-abc123",
                reference_generation=2,
                shared_patterns=["allocation", "feedback"],
                complementary_axes=["biology", "economics"],
                clauses=["Bundle cleared cohesion floor."],
                summary="Adaptive bundle selected.",
            )
        ],
        lineages=[
            LensLineage(
                lineage_id="lineage:biology_immune:g1",
                entity_id="biology_immune",
                proof_bundle_id="bundle:adaptive:abc123",
                fingerprint="lineage-immune",
                reference_generation=2,
            ),
            LensLineage(
                lineage_id="lineage:economics_markets:g1",
                entity_id="economics_markets",
                proof_bundle_id="bundle:adaptive:abc123",
                fingerprint="lineage-markets",
                reference_generation=2,
            ),
        ],
        fold_states=[
            FoldState(
                fold_id="fold:bundle:adaptive:abc123",
                bundle_id="bundle:adaptive:abc123",
                status="composed",
                reference_generation=2,
                active_lineage_ids=[
                    "lineage:biology_immune:g1",
                    "lineage:economics_markets:g1",
                ],
                guard_ids=["guard:cohesion"],
                summary="Adaptive fold is active.",
            )
        ],
        guards=[
            GuardDecision(
                guard_id="guard:cohesion",
                kind="bundle_cohesion_floor",
                status="passed",
                target_id="bundle:adaptive:abc123",
                summary="Cohesion floor passed.",
                details=["cohesion=0.74"],
            )
        ],
        composites=[
            CompositeLens(
                composite_id="composite:abc123",
                component_lineage_ids=[
                    "lineage:biology_immune:g1",
                    "lineage:economics_markets:g1",
                ],
                component_lens_ids=["biology_immune", "economics_markets"],
                derived_from_bundle_id="bundle:adaptive:abc123",
                version=1,
                reference_generation=2,
                status="active",
                fingerprint="composite-fingerprint",
                summary="Composite lens derived from active bundle.",
            )
        ],
        research=ResearchReferenceState(
            reference_generation=2,
            provider="perplexity",
            model="sonar-pro",
            reference_signature="research-signature",
            artifacts=[
                ResearchReferenceArtifact(
                    artifact_name="baseline_dossier",
                    provider="perplexity",
                    model="sonar-pro",
                    summary="Modern systems use queues.",
                    signature="artifact-signature",
                    citation_count=1,
                    citations=["https://example.com/baseline"],
                    raw_digest="raw-digest",
                )
            ],
        ),
    )


# ---------------------------------------------------------------------------
# SessionMeta
# ---------------------------------------------------------------------------


class TestSessionMeta:
    def test_defaults(self):
        m = SessionMeta()
        assert len(m.id) == 32  # hex uuid
        assert m.name == ""
        assert isinstance(m.tags, list)

    def test_roundtrip(self):
        m = SessionMeta(id="x", name="n", tags=["a", "b"])
        d = m.to_dict()
        m2 = SessionMeta.from_dict(d)
        assert m2.id == "x"
        assert m2.tags == ["a", "b"]


# ---------------------------------------------------------------------------
# TranscriptEntry
# ---------------------------------------------------------------------------


class TestTranscriptEntry:
    def test_defaults(self):
        e = TranscriptEntry(role=Role.USER.value, content="hello")
        assert e.entry_type == EntryType.TEXT.value
        assert e.metadata == {}

    def test_roundtrip(self):
        e = TranscriptEntry(
            role=Role.ASSISTANT.value,
            content="hi",
            entry_type=EntryType.TOOL_USE.value,
            metadata={"tool": "grep"},
        )
        e2 = TranscriptEntry.from_dict(e.to_dict())
        assert e2.role == Role.ASSISTANT.value
        assert e2.metadata["tool"] == "grep"


# ---------------------------------------------------------------------------
# InventionSnapshot
# ---------------------------------------------------------------------------


class TestInventionSnapshot:
    def test_roundtrip(self):
        snap = InventionSnapshot(
            invention_name="BioLens",
            source_domain="optics",
            score=9.1,
        )
        snap2 = InventionSnapshot.from_dict(snap.to_dict())
        assert snap2.invention_name == "BioLens"
        assert snap2.score == pytest.approx(9.1)


# ---------------------------------------------------------------------------
# Session — creation & serialization
# ---------------------------------------------------------------------------


class TestSessionSerialization:
    def test_empty_session_roundtrip(self):
        s = Session()
        s2 = Session.from_json(s.to_json())
        assert s2.meta.id == s.meta.id
        assert s2.transcript == []
        assert s2.inventions == []

    def test_populated_roundtrip(self):
        s = _populated_session()
        s2 = Session.from_json(s.to_json())
        assert len(s2.transcript) == 15
        assert len(s2.inventions) == 1
        assert s2.inventions[0].invention_name == "Solar Sail Membrane"

    def test_to_json_is_valid_json(self):
        s = _populated_session()
        data = json.loads(s.to_json())
        assert "meta" in data
        assert "transcript" in data

    def test_from_json_invalid(self):
        with pytest.raises(json.JSONDecodeError):
            Session.from_json("not json")

    def test_from_json_missing_meta(self):
        with pytest.raises(KeyError):
            Session.from_json("{}")

    def test_roundtrip_preserves_lens_engine_state(self):
        s = Session()
        s.apply_lens_engine_state(_lens_engine_state(), op_id=3)
        s2 = Session.from_json(s.to_json())
        assert s2.lens_engine_state is not None
        assert s2.lens_engine_state.active_bundle_id == "bundle:adaptive:abc123"
        assert s2.lens_engine_state.research is not None
        assert s2.lens_engine_state.research.reference_generation == 2

    def test_from_report_coerces_research_reference_dict(self) -> None:
        from unittest.mock import MagicMock

        report = MagicMock()
        report.baseline_dossier = MagicMock(summary="Queues dominate", raw_text="baseline raw", citations=[])
        report.top_invention = None
        report.model_config = {"search": "sonar-pro"}
        report.scored_candidates = []
        report.all_candidates = []

        state = LensEngineState.from_report(report)

        assert state.research is not None
        assert isinstance(state.research, ResearchReferenceState)
        assert state.research.reference_generation == 1


# ---------------------------------------------------------------------------
# Session — file persistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    def test_save_load(self, tmp_path: Path):
        s = _populated_session()
        p = s.save(tmp_path / "session.json")
        assert p.exists()

        loaded = Session.load(p)
        assert loaded.meta.id == s.meta.id
        assert len(loaded.transcript) == len(s.transcript)

    def test_save_creates_parents(self, tmp_path: Path):
        s = Session()
        p = s.save(tmp_path / "a" / "b" / "session.json")
        assert p.exists()

    def test_load_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            Session.load(tmp_path / "nope.json")

    def test_load_corrupt_file(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{corrupt", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            Session.load(bad)

    def test_save_load_after_compaction_preserves_lens_engine_state(self, tmp_path: Path):
        s = _populated_session()
        s.apply_lens_engine_state(_lens_engine_state(), op_id=4)
        s.compact_transcript(keep_last_n=5)
        path = s.save(tmp_path / "session.json")

        loaded = Session.load(path)
        assert loaded.lens_engine_state is not None
        assert loaded.lens_engine_state.active_bundle_id == "bundle:adaptive:abc123"
        assert any(lot.kind == "lens_bundle" for lot in loaded.reference_lots)


# ---------------------------------------------------------------------------
# Session — append / add
# ---------------------------------------------------------------------------


class TestSessionMutation:
    def test_append_entry(self):
        s = Session()
        entry = s.append_entry(Role.USER.value, "hello")
        assert len(s.transcript) == 1
        assert entry.content == "hello"

    def test_append_entry_with_metadata(self):
        s = Session()
        entry = s.append_entry(
            Role.TOOL.value,
            "result",
            entry_type=EntryType.TOOL_RESULT.value,
            metadata={"tool_id": "t1"},
        )
        assert entry.entry_type == EntryType.TOOL_RESULT.value
        assert entry.metadata["tool_id"] == "t1"

    def test_add_invention(self):
        s = Session()
        snap = s.add_invention(
            invention_name="Widget",
            source_domain="robotics",
            score=7.0,
        )
        assert len(s.inventions) == 1
        assert snap.score == 7.0

    def test_add_invention_inherits_lens_engine_summary(self):
        s = Session()
        s.apply_lens_engine_state(_lens_engine_state(), op_id=1)
        snap = s.add_invention(
            invention_name="Adaptive Widget",
            source_domain="biology",
            score=8.1,
        )
        assert snap.lens_bundle_id == "bundle:adaptive:abc123"
        assert snap.lens_reference_generation == 2
        assert snap.lens_composites == ["composite:abc123"]


# ---------------------------------------------------------------------------
# Session — compact_transcript
# ---------------------------------------------------------------------------


class TestCompactTranscript:
    def test_compact_basic(self):
        s = _populated_session()
        assert len(s.transcript) == 15
        s.compact_transcript(keep_last_n=5)
        # 1 summary + 5 kept
        assert len(s.transcript) == 6
        assert s.transcript[0].entry_type == EntryType.SUMMARY.value
        assert "10" in s.transcript[0].content  # compacted 10 entries

    def test_compact_noop_when_small(self):
        s = Session()
        s.append_entry(Role.USER.value, "hi")
        s.compact_transcript(keep_last_n=10)
        assert len(s.transcript) == 1

    def test_compact_preserves_recent(self):
        s = _make_session()
        for i in range(20):
            s.append_entry(Role.USER.value, f"msg-{i}")
        s.compact_transcript(keep_last_n=5)
        contents = [e.content for e in s.transcript[1:]]
        assert contents == [f"msg-{i}" for i in range(15, 20)]

    def test_compact_large_transcript(self):
        s = Session()
        for i in range(500):
            s.append_entry(Role.USER.value, f"entry-{i}")
        s.compact_transcript(keep_last_n=10)
        assert len(s.transcript) == 11
        assert s.transcript[0].metadata["compacted_count"] == 490

    def test_compact_summary_metadata(self):
        s = _make_session()
        for _ in range(6):
            s.append_entry(Role.USER.value, "u")
        for _ in range(4):
            s.append_entry(Role.ASSISTANT.value, "a")
        s.compact_transcript(keep_last_n=3)
        meta = s.transcript[0].metadata
        assert meta["role_counts"]["user"] + meta["role_counts"]["assistant"] == 7


# ---------------------------------------------------------------------------
# Session — list_sessions & resume
# ---------------------------------------------------------------------------


class TestListAndResume:
    def test_list_sessions(self, tmp_path: Path):
        for i in range(3):
            s = Session(meta=SessionMeta(id=f"s{i}", name=f"session-{i}"))
            s.save(tmp_path / f"s{i}.json")
        metas = Session.list_sessions(tmp_path)
        assert len(metas) == 3
        names = {m.name for m in metas}
        assert names == {"session-0", "session-1", "session-2"}

    def test_list_sessions_skips_corrupt(self, tmp_path: Path):
        Session().save(tmp_path / "good.json")
        (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
        metas = Session.list_sessions(tmp_path)
        assert len(metas) == 1

    def test_list_sessions_empty_dir(self, tmp_path: Path):
        assert Session.list_sessions(tmp_path) == []

    def test_list_sessions_missing_dir(self, tmp_path: Path):
        assert Session.list_sessions(tmp_path / "nope") == []

    def test_resume(self, tmp_path: Path):
        s = _populated_session()
        old_updated = s.meta.updated_at
        p = s.save(tmp_path / "sess.json")
        resumed = Session.resume(p)
        assert resumed.meta.id == s.meta.id
        assert len(resumed.transcript) == len(s.transcript)
        assert resumed.meta.updated_at >= old_updated


# ---------------------------------------------------------------------------
# Session — pinned_context & active_tools
# ---------------------------------------------------------------------------


class TestSessionExtras:
    def test_pinned_context_roundtrip(self):
        s = Session(pinned_context=["ctx1", "ctx2"])
        s2 = Session.from_json(s.to_json())
        assert s2.pinned_context == ["ctx1", "ctx2"]

    def test_active_tools_roundtrip(self):
        s = Session(active_tools=["grep", "read"])
        s2 = Session.from_json(s.to_json())
        assert s2.active_tools == ["grep", "read"]
