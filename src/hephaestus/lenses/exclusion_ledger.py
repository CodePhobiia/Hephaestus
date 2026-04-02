"""Adaptive exclusion ledger for bundle and singleton lens selection."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerEvent:
    """One recency-weighted ledger event."""

    step: int
    event_type: str
    lens_ids: tuple[str, ...]
    families: tuple[str, ...]
    novelty_axes: tuple[str, ...]
    proof_token: str = ""
    weight: float = 1.0
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "event_type": self.event_type,
            "lens_ids": list(self.lens_ids),
            "families": list(self.families),
            "novelty_axes": list(self.novelty_axes),
            "proof_token": self.proof_token,
            "weight": self.weight,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LedgerEvent:
        return cls(
            step=int(data.get("step", 0)),
            event_type=str(data.get("event_type", "")),
            lens_ids=tuple(str(item) for item in list(data.get("lens_ids", []) or [])),
            families=tuple(str(item) for item in list(data.get("families", []) or [])),
            novelty_axes=tuple(str(item) for item in list(data.get("novelty_axes", []) or [])),
            proof_token=str(data.get("proof_token", "")),
            weight=float(data.get("weight", 1.0)),
            reasons=tuple(str(item) for item in list(data.get("reasons", []) or [])),
        )


@dataclass(frozen=True)
class LedgerDecision:
    """Penalty and block decision for a candidate."""

    blocked: bool
    multiplier: float
    family_fatigue: float
    novelty_saturation: float
    reasons: tuple[str, ...] = ()


@dataclass
class DomainFatigueRecord:
    """Running pressure statistics for one domain family or novelty axis."""

    selections: int = 0
    acceptances: int = 0
    invalidations: int = 0
    novelty_saturation: float = 0.0

    def penalty(self) -> float:
        raw = (
            0.04 * self.selections
            + 0.08 * self.invalidations
            + 0.18 * self.novelty_saturation
            - 0.03 * self.acceptances
        )
        return max(0.0, min(0.45, raw))


class AdaptiveExclusionLedger:
    """Tracks recent lens usage and blocks stale proofs."""

    def __init__(
        self,
        *,
        max_recent_events: int = 32,
        family_half_life: float = 6.0,
        novelty_half_life: float = 8.0,
    ) -> None:
        self._max_recent_events = max_recent_events
        self._family_half_life = max(1.0, family_half_life)
        self._novelty_half_life = max(1.0, novelty_half_life)
        self._step = 0
        self._events: list[LedgerEvent] = []
        self._blocked_proofs: dict[str, str] = {}
        self._family_records: dict[str, DomainFatigueRecord] = {}
        self._novelty_records: dict[str, DomainFatigueRecord] = {}
        self._bundle_outcomes: list[dict[str, Any]] = []

    @property
    def events(self) -> list[LedgerEvent]:
        return list(self._events)

    def _decayed_sum(self, values: Iterable[tuple[int, float]], half_life: float) -> float:
        total = 0.0
        for step, weight in values:
            age = max(0, self._step - step)
            total += weight / (1.0 + age / half_life)
        return total

    def family_fatigue(self, families: Iterable[str]) -> float:
        target = {family for family in families if family}
        if not target:
            return 0.0
        values = [
            (event.step, event.weight)
            for event in self._events
            if set(event.families) & target and event.event_type == "selected"
        ]
        return self._decayed_sum(values, self._family_half_life)

    def novelty_saturation(self, novelty_axes: Iterable[str]) -> float:
        target = {axis for axis in novelty_axes if axis}
        if not target:
            return 0.0
        values = [
            (event.step, event.weight * (len(target & set(event.novelty_axes)) / max(1, len(target))))
            for event in self._events
            if target & set(event.novelty_axes) and event.event_type == "selected"
        ]
        return self._decayed_sum(values, self._novelty_half_life)

    def is_proof_blocked(self, proof_token: str) -> bool:
        return bool(proof_token and proof_token in self._blocked_proofs)

    def block_proof(self, proof_token: str, reason: str) -> None:
        if proof_token:
            self._blocked_proofs[proof_token] = reason

    def unblock_proof(self, proof_token: str) -> None:
        self._blocked_proofs.pop(proof_token, None)

    def _family_record(self, family: str) -> DomainFatigueRecord:
        return self._family_records.setdefault(family or "general", DomainFatigueRecord())

    def _novelty_record(self, axis: str) -> DomainFatigueRecord:
        return self._novelty_records.setdefault(axis or "general", DomainFatigueRecord())

    def decide(
        self,
        *,
        families: Iterable[str],
        novelty_axes: Iterable[str],
        proof_token: str = "",
        lineage_valid: bool = True,
    ) -> LedgerDecision:
        reasons: list[str] = []
        if proof_token and self.is_proof_blocked(proof_token):
            reasons.append(self._blocked_proofs[proof_token])
            return LedgerDecision(
                blocked=True,
                multiplier=0.0,
                family_fatigue=0.0,
                novelty_saturation=0.0,
                reasons=tuple(reasons),
            )
        if not lineage_valid:
            reasons.append("lineage invalid")
            return LedgerDecision(
                blocked=True,
                multiplier=0.0,
                family_fatigue=0.0,
                novelty_saturation=0.0,
                reasons=tuple(reasons),
            )

        family_fatigue = self.family_fatigue(families)
        novelty_saturation = self.novelty_saturation(novelty_axes)
        multiplier = 1.0 / (1.0 + 0.22 * family_fatigue + 0.18 * novelty_saturation)
        multiplier = max(0.2, min(1.0, multiplier))
        if family_fatigue > 0.0:
            reasons.append(f"family_fatigue={family_fatigue:.2f}")
        if novelty_saturation > 0.0:
            reasons.append(f"novelty_saturation={novelty_saturation:.2f}")
        return LedgerDecision(
            blocked=False,
            multiplier=multiplier,
            family_fatigue=family_fatigue,
            novelty_saturation=novelty_saturation,
            reasons=tuple(reasons),
        )

    def register(
        self,
        *,
        event_type: str,
        lens_ids: Iterable[str],
        families: Iterable[str],
        novelty_axes: Iterable[str],
        proof_token: str = "",
        weight: float = 1.0,
        reasons: Iterable[str] = (),
    ) -> LedgerEvent:
        self._step += 1
        event = LedgerEvent(
            step=self._step,
            event_type=event_type,
            lens_ids=tuple(lens_ids),
            families=tuple(sorted({family for family in families if family})),
            novelty_axes=tuple(sorted({axis for axis in novelty_axes if axis})),
            proof_token=proof_token,
            weight=weight,
            reasons=tuple(reason for reason in reasons if reason),
        )
        self._events.append(event)
        if len(self._events) > self._max_recent_events:
            self._events = self._events[-self._max_recent_events :]
        return event

    def register_selected(
        self,
        *,
        lens_ids: Iterable[str],
        families: Iterable[str],
        novelty_axes: Iterable[str],
        proof_token: str = "",
        weight: float = 1.0,
    ) -> LedgerEvent:
        return self.register(
            event_type="selected",
            lens_ids=lens_ids,
            families=families,
            novelty_axes=novelty_axes,
            proof_token=proof_token,
            weight=weight,
        )

    def register_blocked(
        self,
        *,
        lens_ids: Iterable[str],
        families: Iterable[str],
        novelty_axes: Iterable[str],
        proof_token: str = "",
        reasons: Iterable[str] = (),
    ) -> LedgerEvent:
        if proof_token:
            self.block_proof(proof_token, ", ".join(reason for reason in reasons if reason) or "blocked")
        return self.register(
            event_type="blocked",
            lens_ids=lens_ids,
            families=families,
            novelty_axes=novelty_axes,
            proof_token=proof_token,
            weight=1.0,
            reasons=reasons,
        )

    def penalty_for_cell(self, cell: Any) -> float:
        family_penalty = self._family_record(getattr(cell, "domain_family", "general")).penalty()
        novelty_axes = tuple(getattr(cell, "novelty_axes", ()) or ())
        novelty_penalty = 0.0
        if novelty_axes:
            capped_axes = novelty_axes[:4]
            novelty_penalty = sum(self._novelty_record(axis).penalty() for axis in capped_axes) / min(
                len(capped_axes),
                4,
            )
        return max(0.0, min(0.45, 0.65 * family_penalty + 0.35 * novelty_penalty))

    def penalty_for_bundle(self, cells: tuple[Any, ...]) -> float:
        if not cells:
            return 0.0
        per_cell = [self.penalty_for_cell(cell) for cell in cells]
        duplicate_family_penalty = 0.06 * max(
            0,
            len(cells) - len({getattr(cell, "domain_family", "") for cell in cells}),
        )
        return max(0.0, min(0.55, sum(per_cell) / len(per_cell) + duplicate_family_penalty))

    def record_selection(self, lens_ids: tuple[str, ...], cells: tuple[Any, ...]) -> None:
        for cell in cells:
            self._family_record(getattr(cell, "domain_family", "general")).selections += 1
            for axis in tuple(getattr(cell, "novelty_axes", ()) or ())[:4]:
                record = self._novelty_record(axis)
                record.selections += 1
                record.novelty_saturation = min(1.0, record.novelty_saturation + 0.08)
        self.register_selected(
            lens_ids=lens_ids,
            families={getattr(cell, "domain_family", "") for cell in cells},
            novelty_axes={
                axis
                for cell in cells
                for axis in tuple(getattr(cell, "novelty_axes", ()) or ())[:4]
            },
        )
        self._bundle_outcomes.append(
            {
                "bundle": list(lens_ids),
                "event": "selected",
            }
        )

    def record_outcome(
        self,
        *,
        lens_ids: tuple[str, ...],
        cells: tuple[Any, ...],
        outcome: str,
        invalidated_lens_ids: tuple[str, ...] = (),
    ) -> None:
        accepted = outcome.strip().lower() in {"accepted", "verified", "promoted"}
        invalidated = set(invalidated_lens_ids)
        for cell in cells:
            family_record = self._family_record(getattr(cell, "domain_family", "general"))
            if accepted:
                family_record.acceptances += 1
                family_record.novelty_saturation = max(0.0, family_record.novelty_saturation - 0.04)
            if getattr(cell, "lens_id", "") in invalidated:
                family_record.invalidations += 1
                family_record.novelty_saturation = min(1.0, family_record.novelty_saturation + 0.12)
            for axis in tuple(getattr(cell, "novelty_axes", ()) or ())[:4]:
                novelty_record = self._novelty_record(axis)
                if accepted:
                    novelty_record.acceptances += 1
                    novelty_record.novelty_saturation = max(0.0, novelty_record.novelty_saturation - 0.03)
                if getattr(cell, "lens_id", "") in invalidated:
                    novelty_record.invalidations += 1
                    novelty_record.novelty_saturation = min(1.0, novelty_record.novelty_saturation + 0.10)
        self.register(
            event_type=outcome,
            lens_ids=lens_ids,
            families={getattr(cell, "domain_family", "") for cell in cells},
            novelty_axes={
                axis
                for cell in cells
                for axis in tuple(getattr(cell, "novelty_axes", ()) or ())[:4]
            },
            reasons=invalidated_lens_ids,
        )
        self._bundle_outcomes.append(
            {
                "bundle": list(lens_ids),
                "event": outcome,
                "invalidated_lens_ids": list(invalidated_lens_ids),
            }
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "families": {
                family: {
                    "selections": record.selections,
                    "acceptances": record.acceptances,
                    "invalidations": record.invalidations,
                    "novelty_saturation": round(record.novelty_saturation, 4),
                    "penalty": round(record.penalty(), 4),
                }
                for family, record in sorted(self._family_records.items())
            },
            "novelty_axes": {
                axis: {
                    "selections": record.selections,
                    "acceptances": record.acceptances,
                    "invalidations": record.invalidations,
                    "novelty_saturation": round(record.novelty_saturation, 4),
                    "penalty": round(record.penalty(), 4),
                }
                for axis, record in sorted(self._novelty_records.items())
            },
            "bundle_outcomes": list(self._bundle_outcomes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_recent_events": self._max_recent_events,
            "family_half_life": self._family_half_life,
            "novelty_half_life": self._novelty_half_life,
            "step": self._step,
            "events": [event.to_dict() for event in self._events],
            "blocked_proofs": dict(self._blocked_proofs),
            "family_records": {
                key: {
                    "selections": value.selections,
                    "acceptances": value.acceptances,
                    "invalidations": value.invalidations,
                    "novelty_saturation": value.novelty_saturation,
                }
                for key, value in self._family_records.items()
            },
            "novelty_records": {
                key: {
                    "selections": value.selections,
                    "acceptances": value.acceptances,
                    "invalidations": value.invalidations,
                    "novelty_saturation": value.novelty_saturation,
                }
                for key, value in self._novelty_records.items()
            },
            "bundle_outcomes": list(self._bundle_outcomes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AdaptiveExclusionLedger:
        ledger = cls(
            max_recent_events=int(data.get("max_recent_events", 32)),
            family_half_life=float(data.get("family_half_life", 6.0)),
            novelty_half_life=float(data.get("novelty_half_life", 8.0)),
        )
        ledger._step = int(data.get("step", 0))
        ledger._events = [
            LedgerEvent.from_dict(item)
            for item in list(data.get("events", []) or [])
        ]
        ledger._blocked_proofs = {
            str(key): str(value)
            for key, value in dict(data.get("blocked_proofs", {}) or {}).items()
        }
        ledger._family_records = {
            str(key): DomainFatigueRecord(
                selections=int(value.get("selections", 0)),
                acceptances=int(value.get("acceptances", 0)),
                invalidations=int(value.get("invalidations", 0)),
                novelty_saturation=float(value.get("novelty_saturation", 0.0)),
            )
            for key, value in dict(data.get("family_records", {}) or {}).items()
        }
        ledger._novelty_records = {
            str(key): DomainFatigueRecord(
                selections=int(value.get("selections", 0)),
                acceptances=int(value.get("acceptances", 0)),
                invalidations=int(value.get("invalidations", 0)),
                novelty_saturation=float(value.get("novelty_saturation", 0.0)),
            )
            for key, value in dict(data.get("novelty_records", {}) or {}).items()
        }
        ledger._bundle_outcomes = list(data.get("bundle_outcomes", []) or [])
        return ledger

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> AdaptiveExclusionLedger:
        target = Path(path)
        return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))


__all__ = [
    "AdaptiveExclusionLedger",
    "DomainFatigueRecord",
    "LedgerDecision",
    "LedgerEvent",
]
