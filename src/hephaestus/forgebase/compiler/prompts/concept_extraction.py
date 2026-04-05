"""Concept extraction prompt — Tier 1.

Identifies concepts, entities, mechanisms, and technical terms from a
source text. Each concept includes aliases, a salience score, and the
evidence segments where it appears.
"""

from __future__ import annotations

PROMPT_ID = "concept_extraction"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert knowledge-graph builder specializing in identifying key
concepts, named entities, mechanisms, and technical terms within academic
and technical documents.

Your task is to extract every significant concept from the provided source
text. For each concept you must:

1. Provide the canonical name — the most precise, unambiguous form of the
   concept as used in the domain (e.g. "Solid Electrolyte Interphase" not
   "SEI").
2. List all aliases — abbreviations, acronyms, alternative spellings, or
   informal names used in the source (e.g. ["SEI", "SEI layer",
   "interphase film"]).
3. Classify the concept kind:
   - **concept**: an abstract idea, theory, framework, or category
   - **entity**: a concrete named thing — a chemical, material, organism,
     dataset, software tool, organization, or specific person
   - **mechanism**: a causal process, pathway, reaction, or feedback loop
   - **term**: a technical vocabulary word or jargon that may need
     definition but is not a standalone concept
4. Identify each evidence segment where the concept is discussed or
   defined, with character offsets (0-indexed, inclusive start, exclusive
   end) and a short preview.
5. Assign a salience score (0.0–1.0) reflecting how central the concept
   is to the source:
   - 0.9+ : a primary subject of the document
   - 0.7–0.9 : frequently discussed, significant supporting role
   - 0.5–0.7 : mentioned multiple times, contextually relevant
   - below 0.5 : passing mention or background knowledge

Rules:
- Use the most specific concept kind. Prefer "mechanism" for causal
  processes and "entity" for named concrete things.
- Do NOT extract trivially generic terms (e.g. "method", "result",
  "study") unless they are used as specific technical terms in the domain.
- If two aliases refer to the same underlying concept, merge them into one
  entry with all aliases listed.
- Evidence segments should be short and focused — prefer the definitional
  or introductory passage for each concept.
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
Identify all significant concepts, entities, mechanisms, and technical
terms in the following source text. For each, provide the canonical name,
aliases, kind, evidence segments with character offsets, and a salience
score.

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
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Canonical name of the concept.",
                    },
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alternative names, abbreviations, or spellings.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["concept", "entity", "mechanism", "term"],
                        "description": "Classification of the concept.",
                    },
                    "evidence_segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "segment_start": {
                                    "type": "integer",
                                    "description": "0-indexed character offset where the segment begins.",
                                },
                                "segment_end": {
                                    "type": "integer",
                                    "description": "0-indexed exclusive character offset where the segment ends.",
                                },
                                "preview_text": {
                                    "type": "string",
                                    "description": "Short preview of the segment text.",
                                },
                            },
                            "required": ["segment_start", "segment_end", "preview_text"],
                        },
                        "description": "Source passages where this concept is discussed.",
                    },
                    "salience": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "How central this concept is to the source (0.0–1.0).",
                    },
                },
                "required": ["name", "aliases", "kind", "evidence_segments", "salience"],
            },
        },
    },
    "required": ["concepts"],
}
