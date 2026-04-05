"""Tests for reference-lot resume gate."""

from __future__ import annotations

from hephaestus.lenses.state import (
    CompositeLens,
    LensBundleMember,
    LensBundleProof,
    LensEngineState,
    LensLineage,
    ResearchReferenceArtifact,
    ResearchReferenceState,
)
from hephaestus.session.reference_lots import (
    ReferenceLot,
    bind_reference_lot,
    default_probe_factory,
    evaluate_lot,
    evaluate_resume_gate,
)


def _lens_engine_state() -> LensEngineState:
    return LensEngineState(
        session_reference_generation=4,
        active_bundle_id="bundle:adaptive:test",
        members=[
            LensBundleMember(
                lens_id="biology_immune",
                lens_name="Immune System",
                domain_name="biology::Immune System",
                card_fingerprint64=111,
            )
        ],
        bundles=[
            LensBundleProof(
                bundle_id="bundle:adaptive:test",
                bundle_kind="adaptive_bundle",
                member_ids=["biology_immune"],
                status="active",
                proof_status="fallback",
                cohesion_score=0.60,
                proof_fingerprint="proof-fp",
                reference_generation=4,
                summary="Fallback bundle.",
            )
        ],
        lineages=[
            LensLineage(
                lineage_id="lineage:biology_immune:g1",
                entity_id="biology_immune",
                fingerprint="lineage-fp",
                reference_generation=4,
            )
        ],
        composites=[
            CompositeLens(
                composite_id="composite:test",
                component_lineage_ids=["lineage:biology_immune:g1"],
                component_lens_ids=["biology_immune"],
                derived_from_bundle_id="bundle:adaptive:test",
                version=2,
                reference_generation=4,
                fingerprint="composite-fp",
            )
        ],
        research=ResearchReferenceState(
            reference_generation=4,
            reference_signature="research-fp",
            artifacts=[
                ResearchReferenceArtifact(
                    artifact_name="baseline_dossier",
                    signature="artifact-fp",
                    citation_count=1,
                    citations=["https://example.com/ref"],
                )
            ],
        ),
    )


def test_reference_lot_roundtrip() -> None:
    lot = ReferenceLot(
        lot_id=1,
        kind="workspace",
        subject_key="repo",
        acquired_op=3,
        floor={"allowed": "1"},
        exact={"root": "/tmp/repo"},
        dependents=[3, 4],
    )
    lot2 = ReferenceLot.from_dict(lot.to_dict())
    assert lot2.kind == "workspace"
    assert lot2.exact["root"] == "/tmp/repo"
    assert lot2.dependents == [3, 4]


def test_bind_reference_lot_appends() -> None:
    lots: list[ReferenceLot] = []
    lot = bind_reference_lot(
        lots,
        kind="tool",
        subject_key="read_file",
        op_id=5,
        floor={"available": "1"},
    )
    assert lot.lot_id == 1
    assert len(lots) == 1


def test_evaluate_lot_floor_pass() -> None:
    lot = ReferenceLot(
        lot_id=1, kind="permission", subject_key="read", acquired_op=1, floor={"allowed": "1"}
    )
    ev = evaluate_lot(lot, {"allowed": "1"})
    assert ev.ok
    assert ev.score >= 0


def test_evaluate_lot_floor_fail() -> None:
    lot = ReferenceLot(
        lot_id=1, kind="permission", subject_key="read", acquired_op=1, floor={"allowed": "1"}
    )
    ev = evaluate_lot(lot, {"allowed": "0"})
    assert not ev.ok
    assert any("floor regression" in r for r in ev.reasons)


def test_evaluate_lot_exact_fail() -> None:
    lot = ReferenceLot(
        lot_id=1, kind="workspace", subject_key="repo", acquired_op=1, exact={"root": "/a"}
    )
    ev = evaluate_lot(lot, {"root": "/b"})
    assert not ev.ok
    assert any("exact mismatch" in r for r in ev.reasons)


def test_resume_gate_invalidates_dependents() -> None:
    lots: list[ReferenceLot] = []
    bind_reference_lot(
        lots,
        kind="permission",
        subject_key="write_file",
        op_id=10,
        floor={"allowed": "1"},
        dependents=[10, 11],
    )
    report = evaluate_resume_gate(lots, lambda _lot: {"allowed": "0"})
    assert report.invalid_ops == [10, 11]
    assert not report.passed


def test_resume_gate_passes() -> None:
    lots: list[ReferenceLot] = []
    bind_reference_lot(
        lots, kind="tool", subject_key="read_file", op_id=2, floor={"available": "1"}
    )
    report = evaluate_resume_gate(lots, lambda _lot: {"available": "1"})
    assert report.passed
    assert report.invalid_ops == []


def test_evaluate_lot_numeric_floor_uses_numeric_comparison() -> None:
    lot = ReferenceLot(
        lot_id=1,
        kind="composite_lens",
        subject_key="comp",
        acquired_op=1,
        floor={"version": "10"},
    )
    ev = evaluate_lot(lot, {"version": "2"})
    assert not ev.ok
    assert any("floor regression" in reason for reason in ev.reasons)


def test_default_probe_factory() -> None:
    probe = default_probe_factory(
        workspace_root="/repo",
        active_tools={"read_file"},
        permission_checker=lambda name: name == "read_file",
    )
    assert probe(ReferenceLot(1, "workspace", "repo", 0, exact={"root": "/repo"})) == {
        "root": "/repo"
    }
    assert probe(ReferenceLot(2, "tool", "read_file", 0)) == {"available": "1"}
    assert probe(ReferenceLot(3, "permission", "read_file", 0)) == {"allowed": "1"}


def test_default_probe_factory_supports_lens_engine_state() -> None:
    state = _lens_engine_state()
    probe = default_probe_factory(lens_engine_state=state)

    assert probe(ReferenceLot(1, "lens_bundle", "bundle:adaptive:test", 0)) == {
        "proof_fingerprint": "proof-fp",
        "reference_generation": "4",
        "status": "active",
    }
    assert probe(ReferenceLot(2, "lens_lineage", "lineage:biology_immune:g1", 0)) == {
        "fingerprint": "lineage-fp",
        "generation": "1",
        "reference_generation": "4",
    }
    assert probe(ReferenceLot(3, "composite_lens", "composite:test", 0)) == {
        "fingerprint": "composite-fp",
        "version": "2",
        "reference_generation": "4",
    }
    assert probe(ReferenceLot(4, "research_reference", "baseline_dossier", 0)) == {
        "signature": "artifact-fp",
        "reference_generation": "4",
    }
