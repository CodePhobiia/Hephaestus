"""Prompt templates for LLM-backed integration grading.

Used by the IntegrationScorer when an LLM evaluator is available,
for counterfactual dependence and non-ornamental use dimensions.
"""

from __future__ import annotations

POLICY_VERSION = "1.0"

COUNTERFACTUAL_SYSTEM = """\
You are evaluating whether a cross-domain bridge is LOAD-BEARING or DECORATIVE.

Given an invention candidate and the cross-domain bridge that was used to generate it, answer:

If we REMOVE the bridge entirely, does the invention:
A) Collapse back into a generic or conventional answer (score 0.8-1.0 — bridge is essential)
B) Lose some specificity but retain its core idea (score 0.4-0.7 — bridge is helpful)
C) Remain essentially the same (score 0.0-0.3 — bridge is ornamental)

Return a JSON object:
{
  "score": 0.0-1.0,
  "reasoning": "brief explanation",
  "collapse_mode": "essential|helpful|ornamental"
}
"""

COUNTERFACTUAL_USER = """\
CROSS-DOMAIN BRIDGE:
{bridge_description}

INVENTION GENERATED WITH BRIDGE:
{invention_with_bridge}

WHAT WOULD THE INVENTION LOOK LIKE WITHOUT THIS BRIDGE?
"""

NON_ORNAMENTAL_SYSTEM = """\
You are evaluating whether a cross-domain bridge is doing FUNCTIONAL WORK or merely DECORATING the narrative.

Functional work means:
- The borrowed mechanism actually shapes the solution's logic
- Removing the cross-domain reference changes HOW the solution works, not just how it's described
- The bridge creates a specific design choice that wouldn't exist otherwise

Ornamental use means:
- The cross-domain reference adds vocabulary but not structure
- The solution would be designed the same way with different metaphors
- The bridge is mentioned in the description but absent from the mechanism

Return a JSON object:
{
  "score": 0.0-1.0,
  "reasoning": "brief explanation",
  "functional_elements": ["list of elements where the bridge does real work"],
  "ornamental_elements": ["list of elements where the bridge is decorative"]
}
"""

NON_ORNAMENTAL_USER = """\
CROSS-DOMAIN BRIDGE:
Shared role: {shared_role}
Mapped components: {mapped_components}

SOLUTION DESCRIPTION:
{solution_text}

Is this bridge doing functional work in the solution, or is it ornamental?
"""
