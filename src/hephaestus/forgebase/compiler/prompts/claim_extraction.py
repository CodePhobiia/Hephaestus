"""Claim extraction prompt — Tier 1.

Extracts factual assertions from a source text, each anchored to an
evidence segment with character offsets. This is the first extraction
pass in the Tier 1 pipeline.
"""

from __future__ import annotations

PROMPT_ID = "claim_extraction"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a precise knowledge extraction system specializing in identifying
factual claims within academic and technical documents.

Your task is to extract every discrete factual assertion from the provided
source text. For each claim you must:

1. State the claim as a single, self-contained declarative sentence that
   is understandable without the surrounding context.
2. Identify the exact evidence segment — the contiguous span of source text
   that supports the claim — and report its character offsets (0-indexed,
   inclusive start, exclusive end).
3. Assign a confidence score (0.0–1.0) reflecting how explicitly the source
   states the claim. Use 0.9+ for direct statements, 0.7–0.9 for strong
   implications, 0.5–0.7 for reasonable inferences, and below 0.5 for
   speculative extrapolations.
4. Classify the claim type:
   - **factual**: an empirical observation, measurement, or established fact
   - **methodological**: a description of a method, procedure, or protocol
   - **comparative**: a comparison between entities, approaches, or results
   - **limitation**: an acknowledged weakness, caveat, or boundary condition

Rules:
- Do NOT merge multiple distinct claims into one statement.
- Do NOT fabricate claims that are not supported by the source text.
- Character offsets must correspond exactly to contiguous text in the source.
- Prefer shorter, more precise evidence segments over long passages.
- If the source text is empty or contains no extractable claims, return an
  empty claims array.
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
Extract all factual claims from the following source text. For each claim,
provide the statement, the supporting evidence segment with its exact
character offsets, a confidence score, and the claim type.

Source text:
{source_text}

Source metadata:
{source_metadata}
"""

# ---------------------------------------------------------------------------
# Output JSON Schema
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "A self-contained declarative sentence stating the claim.",
                    },
                    "evidence_segment": {
                        "type": "string",
                        "description": "The exact text span from the source that supports this claim.",
                    },
                    "segment_start": {
                        "type": "integer",
                        "description": "0-indexed character offset where the evidence segment begins.",
                    },
                    "segment_end": {
                        "type": "integer",
                        "description": "0-indexed exclusive character offset where the evidence segment ends.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Confidence that the source explicitly supports this claim (0.0–1.0).",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": ["factual", "methodological", "comparative", "limitation"],
                        "description": "Category of the claim.",
                    },
                },
                "required": [
                    "statement",
                    "evidence_segment",
                    "segment_start",
                    "segment_end",
                    "confidence",
                    "claim_type",
                ],
            },
        },
    },
    "required": ["claims"],
}
