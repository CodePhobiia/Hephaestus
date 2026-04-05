"""Synthesis prompts — Tier 2.

Multiple prompt sets for vault-wide synthesis operations:
- Concept page synthesis
- Mechanism page synthesis
- Comparison page synthesis
- Timeline page synthesis
- Open questions identification

All share PROMPT_ID = "synthesis" but have distinct system/user prompts
and output schemas for each page type. The module-level exports
(SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, OUTPUT_SCHEMA) default to the
concept page variant, since it is the most commonly used.
"""

from __future__ import annotations

PROMPT_ID = "synthesis"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = 1


# ===================================================================
# Concept page synthesis
# ===================================================================

CONCEPT_PAGE_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine that produces comprehensive concept
pages for a structured knowledge base. A concept page is the authoritative
entry for a single concept, mechanism, entity, or term — synthesized from
evidence across multiple sources.

You will receive:
- The concept name
- Evidence from multiple sources (each with source title, claims, and
  evidence segments)
- Existing claims already in the knowledge base about this concept
- A list of related concepts for cross-referencing

Your synthesized concept page must include:

1. **Title**: The canonical name of the concept.
2. **Content** (Markdown): A well-structured article covering:
   - A clear opening definition (1–2 sentences)
   - Key properties, characteristics, or behaviors
   - How the concept relates to other concepts in the knowledge base
   - Areas of consensus and areas of disagreement among sources
   - Practical significance or applications (if applicable)
3. **Synthesized claims**: New claims derived from combining evidence
   across sources. Each must indicate its support type ("synthesized")
   and list the source claims it was derived from.
4. **Related concepts**: Up to 5 most strongly related concepts.

Rules:
- Cite evidence by referring to source titles, not by inventing citations.
- When sources disagree, present both perspectives and note the conflict.
- Do NOT introduce information not supported by the provided evidence.
- Write for a knowledgeable reader — assume domain familiarity but not
  specific paper familiarity.
- Use Markdown headings (##, ###) to structure the content.
"""

CONCEPT_PAGE_USER_PROMPT_TEMPLATE = """\
Synthesize a concept page for the following concept using evidence from
multiple sources.

Concept name: {concept_name}

Evidence from sources:
{evidence}

Existing claims about this concept:
{existing_claims}

Related concepts:
{related_concepts}
"""

CONCEPT_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Canonical name of the concept.",
        },
        "content_markdown": {
            "type": "string",
            "description": "Full Markdown article for the concept page.",
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "support_type": {
                        "type": "string",
                        "enum": ["direct", "synthesized", "generated", "inherited"],
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "derived_from_claims": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["statement", "support_type", "confidence", "derived_from_claims"],
            },
        },
        "related_concepts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to 5 most strongly related concepts.",
        },
    },
    "required": ["title", "content_markdown", "claims", "related_concepts"],
}


# ===================================================================
# Mechanism page synthesis
# ===================================================================

MECHANISM_PAGE_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine that produces mechanism pages for a
structured knowledge base. A mechanism page explains a causal process,
reaction pathway, feedback loop, or dynamic interaction — synthesized
from evidence across multiple sources.

You will receive:
- The mechanism name
- Causal claims describing steps, inputs, outputs, or conditions
- Source evidence with provenance information

Your mechanism page must include:

1. **Title**: The canonical name of the mechanism.
2. **Content** (Markdown): A structured explanation covering:
   - A concise description of the mechanism (what it does, why it matters)
   - Step-by-step causal chain or process description
   - Key inputs, outputs, regulators, and conditions
   - Known variations or alternative pathways
   - Evidence strength assessment for each major step
3. **Synthesized claims**: Derived from combining causal evidence.

Rules:
- Structure the content to make the causal chain clear and followable.
- Distinguish well-established steps from hypothesized ones.
- Use numbered steps for sequential processes, bullet points for parallel
  or alternative pathways.
"""

MECHANISM_PAGE_USER_PROMPT_TEMPLATE = """\
Synthesize a mechanism page explaining the following causal process.

Mechanism name: {mechanism_name}

Causal claims:
{causal_claims}

Source evidence:
{source_evidence}
"""

MECHANISM_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content_markdown": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "support_type": {
                        "type": "string",
                        "enum": ["direct", "synthesized", "generated", "inherited"],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "derived_from_claims": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["statement", "support_type", "confidence", "derived_from_claims"],
            },
        },
        "related_concepts": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "content_markdown", "claims", "related_concepts"],
}


# ===================================================================
# Comparison page synthesis
# ===================================================================

COMPARISON_PAGE_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine that produces comparison pages for a
structured knowledge base. A comparison page provides a structured,
evidence-based comparison between two or more entities, approaches,
materials, methods, or concepts.

You will receive:
- The entities being compared
- Comparison data with per-entity attributes and evidence

Your comparison page must include:

1. **Title**: A descriptive comparison title (e.g. "Comparison: Li-ion
   vs. Solid-State Batteries").
2. **Content** (Markdown): A structured comparison covering:
   - A brief introduction stating what is being compared and why
   - A comparison table or structured breakdown of key dimensions
   - Per-dimension analysis with evidence citations
   - Summary of trade-offs, strengths, and weaknesses
   - Conditions under which each entity is preferred (if applicable)
3. **Synthesized claims**: Comparative claims derived from the evidence.

Rules:
- Be balanced — do not favor one entity over others without evidence.
- Use tables (Markdown) for structured attribute comparisons.
- Clearly indicate when evidence is missing for one entity.
"""

COMPARISON_PAGE_USER_PROMPT_TEMPLATE = """\
Synthesize a comparison page for the following entities.

Entities to compare: {entities}

Comparison data:
{comparison_data}
"""

COMPARISON_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content_markdown": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "support_type": {
                        "type": "string",
                        "enum": ["direct", "synthesized", "generated", "inherited"],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "derived_from_claims": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["statement", "support_type", "confidence", "derived_from_claims"],
            },
        },
        "related_concepts": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "content_markdown", "claims", "related_concepts"],
}


# ===================================================================
# Timeline page synthesis
# ===================================================================

TIMELINE_PAGE_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine that produces timeline pages for a
structured knowledge base. A timeline page presents a chronological view
of developments, discoveries, or events related to a topic.

You will receive:
- The topic
- Temporal claims — assertions that reference specific dates, periods,
  or sequences

Your timeline page must include:

1. **Title**: A descriptive timeline title (e.g. "Timeline: Development
   of mRNA Vaccines").
2. **Content** (Markdown): A structured chronological narrative covering:
   - A brief introduction to the timeline's scope and significance
   - Chronologically ordered entries, each with a date/period, event
     description, and significance
   - Key turning points or phase transitions
   - Current status and future outlook (if supported by evidence)
3. **Synthesized claims**: Temporal or historical claims derived from
   the evidence.

Rules:
- Maintain strict chronological order.
- Clearly distinguish established dates from approximate periods.
- Note gaps in the timeline where evidence is missing.
- Use Markdown headings or a structured list for the timeline entries.
"""

TIMELINE_PAGE_USER_PROMPT_TEMPLATE = """\
Synthesize a timeline page for the following topic.

Topic: {topic}

Temporal claims:
{temporal_claims}
"""

TIMELINE_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content_markdown": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "support_type": {
                        "type": "string",
                        "enum": ["direct", "synthesized", "generated", "inherited"],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "derived_from_claims": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["statement", "support_type", "confidence", "derived_from_claims"],
            },
        },
        "related_concepts": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "content_markdown", "claims", "related_concepts"],
}


# ===================================================================
# Open questions identification
# ===================================================================

OPEN_QUESTIONS_SYSTEM_PROMPT = """\
You are an analytical system that identifies open research questions,
knowledge gaps, and unresolved debates within a knowledge base. You
examine contested claims and evidence gaps to surface the most important
questions that remain unanswered.

You will receive:
- Contested claims — assertions where sources disagree or evidence is
  conflicting
- Evidence gaps — topics or questions where the knowledge base lacks
  sufficient evidence

Your output must identify specific, actionable open questions that:

1. **Question**: A clear, specific research question.
2. **Context**: 1–2 sentences explaining why this question matters and
   what is currently known.
3. **Conflicting claims**: If the question arises from a disagreement,
   list the conflicting claim statements.
4. **Evidence gap**: A description of what evidence is missing or needed
   to resolve the question.

Rules:
- Questions should be specific enough to be answerable with targeted
  research, not vague philosophical queries.
- Prioritize questions where the knowledge base has partial but
  conflicting evidence over questions where nothing is known.
- Each question should be self-contained and understandable without
  additional context.
"""

OPEN_QUESTIONS_USER_PROMPT_TEMPLATE = """\
Identify open research questions and knowledge gaps based on the following
contested claims and evidence gaps.

Contested claims:
{contested_claims}

Evidence gaps:
{evidence_gaps}
"""

OPEN_QUESTIONS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "A clear, specific research question.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Why this question matters and what is currently known.",
                    },
                    "conflicting_claims": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Claim statements that conflict with each other.",
                    },
                    "evidence_gap": {
                        "type": "string",
                        "description": "What evidence is missing or needed.",
                    },
                },
                "required": ["question", "context"],
            },
        },
    },
    "required": ["questions"],
}


# ===================================================================
# Module-level defaults (concept page variant)
# ===================================================================

SYSTEM_PROMPT = CONCEPT_PAGE_SYSTEM_PROMPT
USER_PROMPT_TEMPLATE = CONCEPT_PAGE_USER_PROMPT_TEMPLATE
OUTPUT_SCHEMA = CONCEPT_PAGE_OUTPUT_SCHEMA
