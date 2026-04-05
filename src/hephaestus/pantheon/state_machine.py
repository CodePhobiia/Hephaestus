"""Pantheon state machines — authoritative lifecycle transitions for objections and council phases."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class PantheonStateError(Exception):
    """Raised on invalid state transitions."""


# ---------------------------------------------------------------------------
# Objection Lifecycle State Machine
# ---------------------------------------------------------------------------

# Valid transitions: (from_status, to_status)
_VALID_OBJECTION_TRANSITIONS: set[tuple[str, str]] = {
    ("OPEN", "RESOLVED"),
    ("OPEN", "WAIVED"),
    ("OPEN", "ESCALATED"),
    ("RESOLVED", "OPEN"),  # Re-open if regression detected
    ("WAIVED", "OPEN"),  # Re-open if waiver withdrawn
    ("ESCALATED", "RESOLVED"),  # Escalation resolved
    ("ESCALATED", "WAIVED"),  # Escalation waived by authority
}

# Valid severity escalations
_VALID_SEVERITY_ESCALATIONS: set[tuple[str, str]] = {
    ("ADVISORY", "REPAIRABLE"),
    ("ADVISORY", "FATAL"),
    ("REPAIRABLE", "FATAL"),
    ("REPAIRABLE", "EVIDENCE_REQUEST"),
    ("EVIDENCE_REQUEST", "FATAL"),
    ("EVIDENCE_REQUEST", "REPAIRABLE"),
}


@dataclass
class TransitionRecord:
    """Audit trail entry for a state transition."""

    round_index: int
    agent: str
    from_status: str
    to_status: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_index,
            "agent": self.agent,
            "from": self.from_status,
            "to": self.to_status,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ObjectionLifecycleMachine:
    """Authoritative state machine for objection lifecycle transitions.

    Every status change must go through this machine. Invalid transitions
    raise PantheonStateError. All transitions are logged to an audit trail.
    """

    def __init__(self) -> None:
        self._history: list[TransitionRecord] = []

    @property
    def history(self) -> list[TransitionRecord]:
        return list(self._history)

    def transition(
        self,
        *,
        objection_id: str,
        from_status: str,
        to_status: str,
        round_index: int,
        agent: str,
        reason: str = "",
    ) -> TransitionRecord:
        """Execute a validated state transition.

        Raises PantheonStateError if the transition is invalid.
        """
        from_status = from_status.upper()
        to_status = to_status.upper()

        if (from_status, to_status) not in _VALID_OBJECTION_TRANSITIONS:
            raise PantheonStateError(
                f"Invalid objection transition: {from_status} → {to_status} "
                f"for objection {objection_id} by {agent} in round {round_index}"
            )

        record = TransitionRecord(
            round_index=round_index,
            agent=agent,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
        self._history.append(record)

        logger.info(
            "Objection %s: %s → %s (agent=%s round=%d reason=%s)",
            objection_id,
            from_status,
            to_status,
            agent,
            round_index,
            reason,
        )
        return record

    def validate_severity_change(
        self,
        *,
        from_severity: str,
        to_severity: str,
    ) -> bool:
        """Check if a severity escalation is valid."""
        from_severity = from_severity.upper()
        to_severity = to_severity.upper()
        return (from_severity, to_severity) in _VALID_SEVERITY_ESCALATIONS

    def escalate(
        self,
        *,
        objection_id: str,
        from_severity: str,
        to_severity: str,
        round_index: int,
        agent: str,
        reason: str = "",
    ) -> TransitionRecord:
        """Escalate objection severity with validation."""
        if not self.validate_severity_change(from_severity=from_severity, to_severity=to_severity):
            raise PantheonStateError(
                f"Invalid severity escalation: {from_severity} → {to_severity} "
                f"for objection {objection_id}"
            )

        record = TransitionRecord(
            round_index=round_index,
            agent=agent,
            from_status=f"severity:{from_severity}",
            to_status=f"severity:{to_severity}",
            reason=reason,
        )
        self._history.append(record)

        logger.info(
            "Objection %s severity: %s → %s (agent=%s)",
            objection_id,
            from_severity,
            to_severity,
            agent,
        )
        return record


# ---------------------------------------------------------------------------
# Council Phase State Machine
# ---------------------------------------------------------------------------

_COUNCIL_PHASES = [
    "PREPARE",
    "SCREEN",
    "INDEPENDENT_BALLOT",
    "COUNCIL",
    "REFORGE",
    "FINALIZE",
]

_VALID_PHASE_TRANSITIONS: set[tuple[str, str]] = {
    ("PREPARE", "SCREEN"),
    ("SCREEN", "INDEPENDENT_BALLOT"),
    ("INDEPENDENT_BALLOT", "COUNCIL"),
    ("COUNCIL", "REFORGE"),
    ("COUNCIL", "FINALIZE"),  # Direct if consensus
    ("REFORGE", "COUNCIL"),  # Loop back after reforge
    ("REFORGE", "FINALIZE"),  # Exhaust reforge rounds → finalize
}


class CouncilPhaseMachine:
    """Authoritative state machine for council phase transitions.

    Each transition validates preconditions. No phase can be skipped
    without explicit override.
    """

    def __init__(self) -> None:
        self._current_phase: str = "PREPARE"
        self._phase_history: list[dict[str, Any]] = []

    @property
    def current_phase(self) -> str:
        return self._current_phase

    @property
    def phase_history(self) -> list[dict[str, Any]]:
        return list(self._phase_history)

    def transition(
        self,
        to_phase: str,
        *,
        round_index: int = 0,
        reason: str = "",
        force: bool = False,
    ) -> None:
        """Transition to the next council phase.

        Args:
            to_phase: Target phase.
            round_index: Current round index for audit trail.
            reason: Reason for transition.
            force: If True, skip validation (emergency override only).

        Raises:
            PantheonStateError: If the transition is invalid and force=False.
        """
        to_phase = to_phase.upper()
        from_phase = self._current_phase

        if not force and (from_phase, to_phase) not in _VALID_PHASE_TRANSITIONS:
            raise PantheonStateError(
                f"Invalid council phase transition: {from_phase} → {to_phase} (round {round_index})"
            )

        self._phase_history.append(
            {
                "from": from_phase,
                "to": to_phase,
                "round": round_index,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
                "forced": force,
            }
        )

        self._current_phase = to_phase
        logger.info(
            "Council phase: %s → %s (round=%d%s)",
            from_phase,
            to_phase,
            round_index,
            " [FORCED]" if force else "",
        )

    def can_transition(self, to_phase: str) -> bool:
        """Check if a transition to the given phase is valid."""
        return (self._current_phase, to_phase.upper()) in _VALID_PHASE_TRANSITIONS

    def is_final(self) -> bool:
        """Check if the current phase is terminal."""
        return self._current_phase == "FINALIZE"


__all__ = [
    "CouncilPhaseMachine",
    "ObjectionLifecycleMachine",
    "PantheonStateError",
    "TransitionRecord",
]
