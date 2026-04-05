"""Source card generation prompt — Tier 1.

Generates a structured summary card for a source document, drawing on
previously extracted claims and concepts to produce a concise overview
of what the source contributes to the knowledge base.
"""

from __future__ import annotations

PROMPT_ID = "source_card"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a scholarly summarization system that produces structured source
cards for a knowledge base. A source card is a concise, high-signal
summary of a single document that helps researchers quickly understand
what the source contributes.

You will receive the original source text along with claims and concepts
that have already been extracted from it. Use these extractions to inform
your summary — do not re-extract; instead, synthesize them into a
coherent card.

Your source card must include:

1. **Summary** (2–4 sentences): A plain-language overview of the source's
   main contribution, written for a knowledgeable reader who has not read
   the document.
2. **Key claims** (bulleted list): The 3–7 most important factual
   assertions from the extraction results, stated as concise declarative
   sentences.
3. **Methods** (bulleted list): Research methods, experimental setups,
   analytical approaches, or computational techniques described in the
   source. If the source is not empirical, list the reasoning methodology
   or framework used. If none, return an empty list.
4. **Limitations** (bulleted list): Acknowledged weaknesses, scope
   restrictions, or caveats. If none are stated, infer the most obvious
   limitation and note it as inferred.
5. **Evidence quality** (one of: "strong", "moderate", "weak", "unknown"):
   An overall assessment of the evidence quality based on methodology
   rigor, sample size, reproducibility, and peer-review status.
6. **Concepts mentioned** (list of concept names): The canonical names of
   all concepts extracted from this source, in descending order of
   salience.

Rules:
- The summary should NOT begin with "This paper" or "This study" — start
  with the substantive finding or contribution.
- Key claims should be taken directly from the extracted claims, possibly
  lightly rephrased for clarity.
- Do NOT introduce new claims not present in the extraction results.
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
Generate a structured source card for the following document. Use the
extracted claims and concepts provided below to inform your summary.

Source text:
{source_text}

Source metadata:
{source_metadata}

Extracted claims:
{extracted_claims}

Extracted concepts:
{extracted_concepts}
"""

# ---------------------------------------------------------------------------
# Output JSON Schema
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2–4 sentence overview of the source's main contribution.",
        },
        "key_claims": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3–7 most important factual assertions from the source.",
        },
        "methods": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Research methods or analytical approaches described.",
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Acknowledged weaknesses, scope restrictions, or caveats.",
        },
        "evidence_quality": {
            "type": "string",
            "enum": ["strong", "moderate", "weak", "unknown"],
            "description": "Overall evidence quality assessment.",
        },
        "concepts_mentioned": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Canonical names of concepts from this source, by descending salience.",
        },
    },
    "required": [
        "summary",
        "key_claims",
        "methods",
        "limitations",
        "evidence_quality",
        "concepts_mentioned",
    ],
}
