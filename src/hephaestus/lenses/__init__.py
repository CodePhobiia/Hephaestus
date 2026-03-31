"""
Cognitive Lens Library — the knowledge base powering Hephaestus's cross-domain invention.

A lens is a curated set of axioms and structural patterns from one knowledge domain
that, when injected into an LLM's reasoning mid-thought, forces it to reason from
a structurally foreign frame.

The further the source domain from the problem's native domain, the more inventive
pressure it creates — but it must still structurally map onto the problem.

Typical usage::

    from hephaestus.lenses import LensLoader, LensSelector

    # Load all 50 lenses
    loader = LensLoader()
    lenses = loader.load_all()
    print(f"Loaded {len(lenses)} lenses")

    # Select top 5 most distant lenses for a distributed systems problem
    selector = LensSelector(loader)
    scores = selector.select(
        problem_description="I need a trust system for anonymous actors with no persistent identity",
        problem_maps_to={"trust", "verification", "fraud_detection"},
        exclude_domains={"cs"},  # exclude the problem's native domain
        top_n=5,
    )

    for score in scores:
        print(f"{score.lens.name}: distance={score.domain_distance:.2f}, "
              f"relevance={score.structural_relevance:.2f}")
        print(f"  Inject: {score.lens.injection_prompt[:100]}...")
"""

from hephaestus.lenses.loader import (
    Lens,
    LensLoader,
    LensValidationError,
    StructuralPattern,
)
from hephaestus.lenses.selector import (
    EmbeddingModel,
    LensScore,
    LensSelector,
)

__all__ = [
    # Loader
    "LensLoader",
    "Lens",
    "StructuralPattern",
    "LensValidationError",
    # Selector
    "LensSelector",
    "LensScore",
    "EmbeddingModel",
]
