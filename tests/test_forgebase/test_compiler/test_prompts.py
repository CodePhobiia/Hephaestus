"""Tests for versioned prompt templates.

Verifies that every prompt module exports all required fields with valid
types and that schemas are structurally correct JSON Schema objects.
"""

from __future__ import annotations

import re
from types import ModuleType

import pytest

from hephaestus.forgebase.compiler.prompts import (
    ALL_PROMPT_MODULES,
    claim_extraction,
    concept_extraction,
    evidence_grading,
    source_card,
    synthesis,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

REQUIRED_EXPORTS = [
    "PROMPT_ID",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "OUTPUT_SCHEMA",
]


# -------------------------------------------------------------------
# Parametrised tests across all prompt modules
# -------------------------------------------------------------------


class TestAllPromptModulesExportRequiredFields:
    """Every prompt module must export the required metadata fields."""

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_has_all_required_exports(self, mod: ModuleType):
        for attr in REQUIRED_EXPORTS:
            assert hasattr(mod, attr), f"{mod.__name__} is missing required export: {attr}"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_prompt_id_is_nonempty_string(self, mod: ModuleType):
        pid = mod.PROMPT_ID
        assert isinstance(pid, str), f"PROMPT_ID should be str, got {type(pid)}"
        assert len(pid) > 0, "PROMPT_ID must not be empty"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_prompt_version_matches_semver(self, mod: ModuleType):
        ver = mod.PROMPT_VERSION
        assert isinstance(ver, str), f"PROMPT_VERSION should be str, got {type(ver)}"
        assert SEMVER_RE.match(ver), f"PROMPT_VERSION '{ver}' does not match semver pattern X.Y.Z"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_schema_version_is_positive_int(self, mod: ModuleType):
        sv = mod.SCHEMA_VERSION
        assert isinstance(sv, int), f"SCHEMA_VERSION should be int, got {type(sv)}"
        assert sv >= 1, f"SCHEMA_VERSION must be >= 1, got {sv}"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_output_schema_is_valid(self, mod: ModuleType):
        schema = mod.OUTPUT_SCHEMA
        assert isinstance(schema, dict), f"OUTPUT_SCHEMA should be dict, got {type(schema)}"
        assert "type" in schema, "OUTPUT_SCHEMA must have a 'type' key"
        assert schema["type"] == "object", (
            f"OUTPUT_SCHEMA type should be 'object', got {schema['type']!r}"
        )
        assert "properties" in schema, "OUTPUT_SCHEMA must have 'properties'"
        assert "required" in schema, "OUTPUT_SCHEMA must have 'required'"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_system_prompt_is_nonempty_string(self, mod: ModuleType):
        sp = mod.SYSTEM_PROMPT
        assert isinstance(sp, str), f"SYSTEM_PROMPT should be str, got {type(sp)}"
        assert len(sp.strip()) > 50, "SYSTEM_PROMPT should be substantial (> 50 chars)"

    @pytest.mark.parametrize("mod", ALL_PROMPT_MODULES, ids=lambda m: m.PROMPT_ID)
    def test_user_prompt_template_contains_placeholders(self, mod: ModuleType):
        tpl = mod.USER_PROMPT_TEMPLATE
        assert isinstance(tpl, str), f"USER_PROMPT_TEMPLATE should be str, got {type(tpl)}"
        # Must contain at least one {placeholder}
        placeholders = re.findall(r"\{(\w+)\}", tpl)
        assert len(placeholders) > 0, (
            "USER_PROMPT_TEMPLATE must contain at least one {placeholder} variable"
        )


# -------------------------------------------------------------------
# Prompt-specific tests
# -------------------------------------------------------------------


class TestClaimExtraction:
    def test_prompt_id(self):
        assert claim_extraction.PROMPT_ID == "claim_extraction"

    def test_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", claim_extraction.USER_PROMPT_TEMPLATE)
        assert "source_text" in placeholders
        assert "source_metadata" in placeholders

    def test_output_schema_has_claims_array(self):
        props = claim_extraction.OUTPUT_SCHEMA["properties"]
        assert "claims" in props
        assert props["claims"]["type"] == "array"
        item_props = props["claims"]["items"]["properties"]
        assert "statement" in item_props
        assert "evidence_segment" in item_props
        assert "segment_start" in item_props
        assert "segment_end" in item_props
        assert "confidence" in item_props
        assert "claim_type" in item_props


class TestConceptExtraction:
    def test_prompt_id(self):
        assert concept_extraction.PROMPT_ID == "concept_extraction"

    def test_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", concept_extraction.USER_PROMPT_TEMPLATE)
        assert "source_text" in placeholders
        assert "source_metadata" in placeholders

    def test_output_schema_has_concepts_array(self):
        props = concept_extraction.OUTPUT_SCHEMA["properties"]
        assert "concepts" in props
        assert props["concepts"]["type"] == "array"
        item_props = props["concepts"]["items"]["properties"]
        assert "name" in item_props
        assert "aliases" in item_props
        assert "kind" in item_props
        assert "evidence_segments" in item_props
        assert "salience" in item_props


class TestSourceCard:
    def test_prompt_id(self):
        assert source_card.PROMPT_ID == "source_card"

    def test_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", source_card.USER_PROMPT_TEMPLATE)
        assert "source_text" in placeholders
        assert "source_metadata" in placeholders
        assert "extracted_claims" in placeholders
        assert "extracted_concepts" in placeholders

    def test_output_schema_has_all_card_fields(self):
        props = source_card.OUTPUT_SCHEMA["properties"]
        expected = [
            "summary",
            "key_claims",
            "methods",
            "limitations",
            "evidence_quality",
            "concepts_mentioned",
        ]
        for field in expected:
            assert field in props, f"source_card OUTPUT_SCHEMA missing '{field}'"


class TestEvidenceGrading:
    def test_prompt_id(self):
        assert evidence_grading.PROMPT_ID == "evidence_grading"

    def test_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", evidence_grading.USER_PROMPT_TEMPLATE)
        assert "claim" in placeholders
        assert "evidence_segment" in placeholders
        assert "source_text" in placeholders

    def test_output_schema_has_grading_fields(self):
        props = evidence_grading.OUTPUT_SCHEMA["properties"]
        assert "strength" in props
        assert "methodology_quality" in props
        assert "reasoning" in props


class TestSynthesis:
    def test_prompt_id(self):
        assert synthesis.PROMPT_ID == "synthesis"

    def test_module_level_defaults_are_concept_page(self):
        assert synthesis.SYSTEM_PROMPT == synthesis.CONCEPT_PAGE_SYSTEM_PROMPT
        assert synthesis.USER_PROMPT_TEMPLATE == synthesis.CONCEPT_PAGE_USER_PROMPT_TEMPLATE
        assert synthesis.OUTPUT_SCHEMA == synthesis.CONCEPT_PAGE_OUTPUT_SCHEMA

    def test_concept_page_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", synthesis.CONCEPT_PAGE_USER_PROMPT_TEMPLATE)
        assert "concept_name" in placeholders
        assert "evidence" in placeholders
        assert "existing_claims" in placeholders
        assert "related_concepts" in placeholders

    def test_mechanism_page_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", synthesis.MECHANISM_PAGE_USER_PROMPT_TEMPLATE)
        assert "mechanism_name" in placeholders
        assert "causal_claims" in placeholders
        assert "source_evidence" in placeholders

    def test_comparison_page_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", synthesis.COMPARISON_PAGE_USER_PROMPT_TEMPLATE)
        assert "entities" in placeholders
        assert "comparison_data" in placeholders

    def test_timeline_page_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", synthesis.TIMELINE_PAGE_USER_PROMPT_TEMPLATE)
        assert "topic" in placeholders
        assert "temporal_claims" in placeholders

    def test_open_questions_template_placeholders(self):
        placeholders = re.findall(r"\{(\w+)\}", synthesis.OPEN_QUESTIONS_USER_PROMPT_TEMPLATE)
        assert "contested_claims" in placeholders
        assert "evidence_gaps" in placeholders

    def test_all_synthesis_schemas_are_valid(self):
        schemas = [
            synthesis.CONCEPT_PAGE_OUTPUT_SCHEMA,
            synthesis.MECHANISM_PAGE_OUTPUT_SCHEMA,
            synthesis.COMPARISON_PAGE_OUTPUT_SCHEMA,
            synthesis.TIMELINE_PAGE_OUTPUT_SCHEMA,
            synthesis.OPEN_QUESTIONS_OUTPUT_SCHEMA,
        ]
        for schema in schemas:
            assert isinstance(schema, dict)
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema

    def test_all_synthesis_system_prompts_are_nonempty(self):
        prompts = [
            synthesis.CONCEPT_PAGE_SYSTEM_PROMPT,
            synthesis.MECHANISM_PAGE_SYSTEM_PROMPT,
            synthesis.COMPARISON_PAGE_SYSTEM_PROMPT,
            synthesis.TIMELINE_PAGE_SYSTEM_PROMPT,
            synthesis.OPEN_QUESTIONS_SYSTEM_PROMPT,
        ]
        for prompt in prompts:
            assert isinstance(prompt, str)
            assert len(prompt.strip()) > 50


# -------------------------------------------------------------------
# Cross-module uniqueness
# -------------------------------------------------------------------


class TestPromptIdUniqueness:
    def test_prompt_ids_are_unique(self):
        ids = [mod.PROMPT_ID for mod in ALL_PROMPT_MODULES]
        assert len(ids) == len(set(ids)), f"Duplicate PROMPT_IDs found: {ids}"
