"""Evidence grading prompt — Tier 1.

Assesses the strength and methodology quality of evidence supporting a
specific claim. Used after claim extraction to enrich each claim with
a quality assessment.
"""

from __future__ import annotations

PROMPT_ID = "evidence_grading"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an evidence quality assessor for a scientific knowledge base. Your
role is to evaluate how strongly a specific piece of evidence supports a
given claim, and to assess the methodological quality of that evidence.

You will receive:
- A claim statement
- The evidence segment from the source that purportedly supports the claim
- The full source text for context

Your assessment must include:

1. **Strength** (0.0–1.0): How strongly the evidence segment supports the
   claim.
   - 0.9–1.0: The evidence directly and unambiguously states or
     demonstrates the claim with quantitative data or rigorous proof.
   - 0.7–0.9: The evidence strongly supports the claim through clear
     reasoning, well-designed experiments, or consistent observations.
   - 0.5–0.7: The evidence provides moderate support — the claim is a
     reasonable interpretation but other interpretations exist.
   - 0.3–0.5: Weak support — the evidence is tangentially related or the
     connection requires significant inference.
   - 0.0–0.3: Minimal or no support — the evidence does not substantively
     back the claim.

2. **Methodology quality** (one of: "strong", "moderate", "weak",
   "unknown"):
   - **strong**: Peer-reviewed, adequate sample size, controlled design,
     reproducible methods, quantitative measurements.
   - **moderate**: Published work with reasonable methodology but some
     gaps — limited sample, observational design, or partial controls.
   - **weak**: Anecdotal, unreplicated, poorly controlled, or from an
     unreliable source.
   - **unknown**: Insufficient information to assess methodology (e.g.
     secondary citation, news article, opinion piece).

3. **Reasoning** (1–3 sentences): A concise explanation of why you
   assigned the strength and quality ratings. Reference specific
   methodological features or deficiencies.

Rules:
- Assess only the relationship between the specific claim and the provided
  evidence — do not evaluate the claim's truth in general.
- If the evidence segment is empty or clearly irrelevant, assign strength
  0.0 and explain why.
- Be calibrated: reserve scores above 0.9 for quantitative, peer-reviewed
  evidence with strong experimental design.
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
Assess the evidence strength and methodology quality for the following
claim and its supporting evidence segment.

Claim:
{claim}

Evidence segment:
{evidence_segment}

Full source text (for context):
{source_text}
"""

# ---------------------------------------------------------------------------
# Output JSON Schema
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "strength": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How strongly the evidence supports the claim (0.0–1.0).",
        },
        "methodology_quality": {
            "type": "string",
            "enum": ["strong", "moderate", "weak", "unknown"],
            "description": "Assessment of the evidence's methodological rigor.",
        },
        "reasoning": {
            "type": "string",
            "description": "1–3 sentence explanation of the assessment rationale.",
        },
    },
    "required": ["strength", "methodology_quality", "reasoning"],
}
