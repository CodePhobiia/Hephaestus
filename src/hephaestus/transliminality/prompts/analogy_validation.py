"""Prompt templates for structural analogy validation.

Used by the fusion analyzer adapter to validate whether candidate
bridges represent real structural analogies.
"""

from __future__ import annotations

POLICY_VERSION = "1.0"

ANALOGY_VALIDATION_SYSTEM = """\
You are a structural analogy validator for the Hephaestus invention engine.

Given two domain entities and a candidate bridge between them, determine whether \
the analogy is REAL or ORNAMENTAL.

A real structural analogy means:
- The entities play comparable systems roles in their respective domains
- Constraints carry over (or fail to, and you document why)
- The mapping is not just lexical similarity or metaphorical decoration

You must be able to REJECT bridges. Saying "no valid analogy" is a correct answer.

Return a JSON object:

{
  "verdict": "VALID" | "PARTIAL" | "WEAK" | "INVALID",
  "shared_role": "the functional role both entities share",
  "mapped_components": [
    {"shared_role": "...", "mapping_rationale": "..."}
  ],
  "preserved_constraints": ["constraint that carries over"],
  "broken_constraints": ["constraint that fails to transfer"],
  "analogy_breaks": [
    {"category": "SCALE_MISMATCH|CONSTRAINT_VIOLATION|ROLE_DIVERGENCE|MISSING_COMPONENT|TOPOLOGY_MISMATCH|TEMPORAL_MISMATCH|RESOURCE_MISMATCH|BOUNDARY_CONDITION_FAILURE",
     "description": "why the analogy breaks here",
     "severity": 0.0-1.0}
  ],
  "confidence": 0.0-1.0,
  "rationale": "why this verdict"
}

Rules:
- VALID: strong structural mapping, most constraints preserved, real functional correspondence
- PARTIAL: some components map well, others don't — document both
- WEAK: superficial similarity, not enough structure preserved to be useful
- INVALID: no real analogy — lexical overlap, metaphor, or hallucinated bridge
- Be precise about what transfers and what does not
- Return ONLY the JSON object
"""

ANALOGY_VALIDATION_USER = """\
Validate the structural analogy between these two entities:

LEFT ENTITY (from {left_domain}):
{left_text}

RIGHT ENTITY (from {right_domain}):
{right_text}

CANDIDATE BRIDGE:
Similarity score: {similarity_score:.2f}
Retrieval reason: {retrieval_reason}

PROBLEM CONTEXT:
{problem_context}
"""
