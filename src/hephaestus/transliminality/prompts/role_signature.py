"""Prompt templates and response parsing for role signature extraction.

These are versioned policy artifacts — not ad-hoc strings.
"""

from __future__ import annotations

import logging
from typing import Any

from hephaestus.forgebase.service.id_generator import IdGenerator
from hephaestus.transliminality.domain.enums import (
    ConstraintTag,
    ControlPatternTag,
    FailureModeTag,
    RoleTag,
    SignatureSubjectKind,
    TimeScaleTag,
    TopologyTag,
)
from hephaestus.transliminality.domain.models import (
    EntityRef,
    ResourceTag,
    RoleSignature,
    SignalTag,
)

logger = logging.getLogger(__name__)

POLICY_VERSION = "1.0"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

ROLE_SIGNATURE_SYSTEM = """\
You are a structural analyst for the Hephaestus invention engine.

Your job is to extract the FUNCTIONAL SHAPE of a problem — not its topic, \
not its keywords, but its underlying structural roles, constraints, failure \
modes, and control patterns.  This signature will be used to find structurally \
similar mechanisms in remote domains for cross-domain invention.

Think about what the problem DOES, not what it IS ABOUT.

Return a single JSON object with exactly these fields:

{
  "functional_roles": ["FILTER", "GATE", ...],
  "inputs": [{"name": "...", "description": "..."}],
  "outputs": [{"name": "...", "description": "..."}],
  "constraints": ["CAPACITY_LIMIT", "LATENCY_BOUND", ...],
  "failure_modes": ["OVERLOAD", "LEAKAGE", ...],
  "control_patterns": ["FEEDBACK", "THRESHOLDING", ...],
  "timescale": "MILLISECOND" | null,
  "resource_profile": [{"name": "...", "direction": "consumed|produced|both", "description": "..."}],
  "topology": ["LAYERED", "GRAPH", ...],
  "confidence": 0.85,
  "rationale": "Brief explanation of why these structural tags fit."
}

Valid values for each field:

functional_roles: FILTER, GATE, BUFFER, ROUTE, DETECT, ISOLATE, AMPLIFY, DAMP, \
COORDINATE, DISTRIBUTE, CHECKPOINT, REPAIR, TRANSFORM, SEQUENCE, REDUNDANCY, SELECT

constraints: CAPACITY_LIMIT, LATENCY_BOUND, ENERGY_BOUND, SELECTIVITY_REQUIREMENT, \
SAFETY_LIMIT, COMPLIANCE_LIMIT, COST_LIMIT, PRECISION_REQUIREMENT, \
ROBUSTNESS_REQUIREMENT, SCALABILITY_LIMIT

failure_modes: OVERLOAD, LEAKAGE, CONTAMINATION, DRIFT, OSCILLATION, DEADLOCK, \
STARVATION, BRITTLENESS, SPOOFING, CASCADE_FAILURE

control_patterns: FEEDBACK, FEEDFORWARD, THRESHOLDING, STAGED_ACTIVATION, \
REDUNDANCY, VOTING, BATCHING, DIFFUSION, PRIORITIZATION, ADAPTIVE_ROUTING

timescale: NANOSECOND, MICROSECOND, MILLISECOND, SECOND, MINUTE, HOUR, DAY, \
WEEK, MONTH, YEAR, DECADE

topology: LINEAR, TREE, DAG, GRAPH, RING, STAR, MESH, HIERARCHICAL, LAYERED, BROADCAST

Rules:
- Choose 2-6 functional_roles that describe what the problem structurally requires
- Choose constraints that genuinely bind the problem
- Choose failure modes that are real risks, not theoretical
- Be precise: fewer accurate tags beat many vague ones
- confidence should reflect how well you can characterize the structural shape
- Return ONLY the JSON object, no other text
"""

ROLE_SIGNATURE_USER = """\
Extract the structural role signature of this problem:

{problem}
"""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _safe_enum_list(raw_list: Any, enum_cls: type) -> list:
    """Parse a list of strings into enum members, skipping invalid values."""
    if not isinstance(raw_list, list):
        return []
    result = []
    members = {m.name: m for m in enum_cls}
    for item in raw_list:
        if isinstance(item, str):
            key = item.upper().strip()
            if key in members:
                result.append(members[key])
            else:
                logger.debug("Skipping unknown %s value: %s", enum_cls.__name__, item)
    return result


def _parse_signals(raw_list: Any) -> list[SignalTag]:
    """Parse a list of signal dicts into SignalTag objects."""
    if not isinstance(raw_list, list):
        return []
    result = []
    for item in raw_list:
        if isinstance(item, dict):
            name = item.get("name", "")
            if name:
                result.append(SignalTag(
                    name=str(name),
                    description=str(item.get("description", "")),
                ))
        elif isinstance(item, str):
            result.append(SignalTag(name=item))
    return result


def _parse_resources(raw_list: Any) -> list[ResourceTag]:
    """Parse a list of resource dicts into ResourceTag objects."""
    if not isinstance(raw_list, list):
        return []
    result = []
    for item in raw_list:
        if isinstance(item, dict):
            name = item.get("name", "")
            if name:
                result.append(ResourceTag(
                    name=str(name),
                    direction=str(item.get("direction", "consumed")),
                    description=str(item.get("description", "")),
                ))
        elif isinstance(item, str):
            result.append(ResourceTag(name=item))
    return result


def _parse_timescale(raw: Any) -> TimeScaleTag | None:
    """Parse a timescale string into a TimeScaleTag, or None."""
    if raw is None or raw == "null":
        return None
    if isinstance(raw, str):
        key = raw.upper().strip()
        members = {m.name: m for m in TimeScaleTag}
        return members.get(key)
    return None


def parse_role_signature(
    raw: dict[str, Any],
    *,
    problem: str,
    id_generator: IdGenerator,
) -> RoleSignature:
    """Convert parsed LLM JSON into a RoleSignature domain model."""
    sig_id = id_generator.generate("sig")
    subject_ref = EntityRef(entity_id=sig_id, entity_kind="problem")

    return RoleSignature(
        signature_id=sig_id,
        subject_ref=subject_ref,
        subject_kind=SignatureSubjectKind.PROBLEM,
        functional_roles=_safe_enum_list(raw.get("functional_roles", []), RoleTag),
        inputs=_parse_signals(raw.get("inputs", [])),
        outputs=_parse_signals(raw.get("outputs", [])),
        constraints=_safe_enum_list(raw.get("constraints", []), ConstraintTag),
        failure_modes=_safe_enum_list(raw.get("failure_modes", []), FailureModeTag),
        control_patterns=_safe_enum_list(raw.get("control_patterns", []), ControlPatternTag),
        timescale=_parse_timescale(raw.get("timescale")),
        resource_profile=_parse_resources(raw.get("resource_profile", [])),
        topology=_safe_enum_list(raw.get("topology", []), TopologyTag),
        confidence=float(raw.get("confidence", 0.0)),
        policy_version=POLICY_VERSION,
    )
