"""Fusion policy — configurable parameters for the fusion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from hephaestus.forgebase.domain.enums import ClaimStatus


@dataclass
class FusionPolicy:
    """All configurable parameters for the cross-vault fusion pipeline."""

    policy_version: str = "1.0.0"
    max_candidates_per_pair: int = 50
    candidate_type_allocation: dict[str, float] = field(
        default_factory=lambda: {
            "concept": 0.4,
            "mechanism": 0.3,
            "claim_cluster": 0.2,
            "exploratory": 0.1,
        }
    )
    similarity_bands: list[tuple[float, float]] = field(
        default_factory=lambda: [
            (0.7, 1.0),
            (0.5, 0.7),
            (0.3, 0.5),
        ]
    )
    min_similarity_threshold: float = 0.3
    max_analogical_maps: int = 20
    max_transfer_opportunities: int = 10
    # Epistemic filters (inherit ExtractionPolicy patterns)
    baseline_min_claim_status: ClaimStatus = ClaimStatus.SUPPORTED
    context_include_hypothesis: bool = True
    dossier_include_unresolved: bool = True
    # Context pack caps (for synthesis merging)
    context_max_concepts: int = 50
    context_max_mechanisms: int = 30
    context_max_open_questions: int = 20
    context_max_explored_directions: int = 20
    # Problem relevance boost
    problem_relevance_weight: float = 0.3


DEFAULT_FUSION_POLICY = FusionPolicy()
