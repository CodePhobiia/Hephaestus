"""Novelty analysis helpers."""

from hephaestus.novelty.solution_shapes import (
    COMMON_ARCHITECTURE_SHAPES,
    ShapeClassification,
    ShapeDefinition,
    ShapeMatch,
    aggregate_shape_scores,
    classify_architecture_text,
    classify_banned_baseline,
    classify_banned_baselines,
    classify_generated_invention,
    classify_generated_inventions,
    extract_invention_text,
    get_shape_library,
    shape_evidence_table,
    shape_overlap_score,
)

__all__ = [
    "COMMON_ARCHITECTURE_SHAPES",
    "ShapeClassification",
    "ShapeDefinition",
    "ShapeMatch",
    "aggregate_shape_scores",
    "classify_architecture_text",
    "classify_banned_baseline",
    "classify_banned_baselines",
    "classify_generated_invention",
    "classify_generated_inventions",
    "extract_invention_text",
    "get_shape_library",
    "shape_evidence_table",
    "shape_overlap_score",
]
