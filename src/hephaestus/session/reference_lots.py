"""Reference-lot resume gate.

Preserves operational anchors across session compaction/resume so a restored
session can detect hidden state drift in tools, permissions, and workspace
facts instead of relying on text continuity alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hephaestus.lenses.state import LensEngineState


@dataclass
class ReferenceLot:
    """A compact anchor representing one operational dependency."""

    lot_id: int
    kind: str
    subject_key: str
    acquired_op: int
    owned: bool = True
    realized: bool = False
    floor: dict[str, str] = field(default_factory=dict)
    exact: dict[str, str] = field(default_factory=dict)
    penalty: dict[str, float] = field(default_factory=dict)
    dependents: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.penalty:
            self.penalty = {k: 2.0 for k in self.floor}

    def to_dict(self) -> dict[str, Any]:
        return {
            "lot_id": self.lot_id,
            "kind": self.kind,
            "subject_key": self.subject_key,
            "acquired_op": self.acquired_op,
            "owned": self.owned,
            "realized": self.realized,
            "floor": dict(self.floor),
            "exact": dict(self.exact),
            "penalty": dict(self.penalty),
            "dependents": list(self.dependents),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceLot:
        return cls(
            lot_id=int(data["lot_id"]),
            kind=str(data["kind"]),
            subject_key=str(data["subject_key"]),
            acquired_op=int(data.get("acquired_op", 0)),
            owned=bool(data.get("owned", True)),
            realized=bool(data.get("realized", False)),
            floor=dict(data.get("floor", {}) or {}),
            exact=dict(data.get("exact", {}) or {}),
            penalty={k: float(v) for k, v in dict(data.get("penalty", {}) or {}).items()},
            dependents=[int(x) for x in list(data.get("dependents", []) or [])],
        )


@dataclass
class LotEvaluation:
    """Result of checking one reference lot against current state."""

    lot_id: int
    ok: bool
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class ResumeGateReport:
    """Aggregate report over a session's unresolved reference lots."""

    invalid_ops: list[int] = field(default_factory=list)
    evaluations: list[LotEvaluation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.invalid_ops

    def summary(self) -> str:
        if self.passed:
            return "Resume gate passed — no invalidated operations."
        return (
            f"Resume gate invalidated ops: {', '.join(str(i) for i in self.invalid_ops[:10])}"
            f" across {len([ev for ev in self.evaluations if not ev.ok])} failing lots."
        )


def bind_reference_lot(
    lots: list[ReferenceLot],
    *,
    kind: str,
    subject_key: str,
    op_id: int,
    floor: dict[str, str] | None = None,
    exact: dict[str, str] | None = None,
    dependents: list[int] | None = None,
    owned: bool = True,
) -> ReferenceLot:
    """Append a new lot and return it."""
    next_id = max((lot.lot_id for lot in lots), default=0) + 1
    lot = ReferenceLot(
        lot_id=next_id,
        kind=kind,
        subject_key=subject_key,
        acquired_op=op_id,
        owned=owned,
        floor=floor or {},
        exact=exact or {},
        dependents=list(dependents or [op_id]),
    )
    lots.append(lot)
    return lot


def evaluate_lot(lot: ReferenceLot, current: dict[str, str]) -> LotEvaluation:
    """Evaluate one lot against current probed state."""
    score = 0.0
    reasons: list[str] = []

    for key, req in lot.floor.items():
        cur = current.get(key)
        if cur is None or _compare_floor(cur, req) < 0:
            score -= lot.penalty.get(key, 2.0)
            reasons.append(f"floor regression {key}: have={cur} need>={req}")
        elif _compare_floor(cur, req) > 0:
            score += 0.5

    for key, req in lot.exact.items():
        cur = current.get(key)
        if str(cur) != str(req):
            score -= 4.0
            reasons.append(f"exact mismatch {key}: have={cur} need={req}")

    return LotEvaluation(lot_id=lot.lot_id, ok=score >= 0.0, score=score, reasons=reasons)


def evaluate_resume_gate(
    lots: list[ReferenceLot],
    probe: Callable[[ReferenceLot], dict[str, str]],
) -> ResumeGateReport:
    """Evaluate all unresolved lots and collect invalidated operations."""
    invalid_ops: set[int] = set()
    evaluations: list[LotEvaluation] = []

    for lot in lots:
        if lot.realized:
            continue
        current = probe(lot)
        ev = evaluate_lot(lot, current)
        evaluations.append(ev)
        if not ev.ok and lot.owned:
            invalid_ops.update(lot.dependents)

    return ResumeGateReport(
        invalid_ops=sorted(invalid_ops),
        evaluations=evaluations,
    )


def default_probe_factory(
    *,
    workspace_root: str | None = None,
    active_tools: set[str] | None = None,
    permission_checker: Callable[[str], bool] | None = None,
    lens_engine_state: LensEngineState | None = None,
) -> Callable[[ReferenceLot], dict[str, str]]:
    """Build a simple probe for common lot kinds used in Hephaestus."""
    tool_set = active_tools or set()

    def probe(lot: ReferenceLot) -> dict[str, str]:
        if lot.kind == "workspace":
            return {"root": workspace_root or ""}
        if lot.kind == "tool":
            return {"available": "1" if lot.subject_key in tool_set else "0"}
        if lot.kind == "permission":
            allowed = permission_checker(lot.subject_key) if permission_checker else False
            return {"allowed": "1" if allowed else "0"}
        if lot.kind == "lens_bundle" and lens_engine_state is not None:
            bundle = next(
                (item for item in lens_engine_state.bundles if item.bundle_id == lot.subject_key),
                None,
            )
            if bundle is None:
                return {}
            return {
                "proof_fingerprint": bundle.proof_fingerprint,
                "reference_generation": str(bundle.reference_generation),
                "status": bundle.status,
            }
        if lot.kind == "lens_lineage" and lens_engine_state is not None:
            lineage = next(
                (item for item in lens_engine_state.lineages if item.lineage_id == lot.subject_key),
                None,
            )
            if lineage is None:
                return {}
            return {
                "fingerprint": lineage.fingerprint,
                "generation": str(lineage.generation),
                "reference_generation": str(lineage.reference_generation),
            }
        if lot.kind == "composite_lens" and lens_engine_state is not None:
            composite = next(
                (
                    item
                    for item in lens_engine_state.composites
                    if item.composite_id == lot.subject_key
                ),
                None,
            )
            if composite is None:
                return {}
            return {
                "fingerprint": composite.fingerprint,
                "version": str(composite.version),
                "reference_generation": str(composite.reference_generation),
            }
        if (
            lot.kind == "research_reference"
            and lens_engine_state is not None
            and lens_engine_state.research is not None
        ):
            artifact = next(
                (
                    item
                    for item in lens_engine_state.research.artifacts
                    if item.artifact_name == lot.subject_key
                ),
                None,
            )
            if artifact is None:
                return {}
            return {
                "signature": artifact.signature,
                "reference_generation": str(lens_engine_state.research.reference_generation),
            }
        return {}

    return probe


def _compare_floor(current: Any, required: Any) -> int:
    current_num = _coerce_number(current)
    required_num = _coerce_number(required)
    if current_num is not None and required_num is not None:
        if current_num < required_num:
            return -1
        if current_num > required_num:
            return 1
        return 0

    current_text = str(current)
    required_text = str(required)
    if current_text < required_text:
        return -1
    if current_text > required_text:
        return 1
    return 0


def _coerce_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ReferenceLot",
    "LotEvaluation",
    "ResumeGateReport",
    "bind_reference_lot",
    "evaluate_lot",
    "evaluate_resume_gate",
    "default_probe_factory",
]
