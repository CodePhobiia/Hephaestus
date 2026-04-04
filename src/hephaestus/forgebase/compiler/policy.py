"""Versioned synthesis policies."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SynthesisPolicy:
    policy_version: str = "1.0.0"
    name_similarity_threshold: float = 0.85
    min_sources_for_promotion: int = 2
    min_salience_single_source: float = 0.8
    max_claims_per_page: int = 50
    max_related_concepts: int = 20
    dirty_threshold_for_auto_synthesis: int = 5
    debounce_minutes: float = 10.0
    min_evidence_strength_for_supported: float = 0.3


DEFAULT_POLICY = SynthesisPolicy()
