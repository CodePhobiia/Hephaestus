"""
Lens Selection Algorithm — selects the most structurally distant, semantically relevant
cognitive lenses for a given problem.

Core insight: the best lens is NOT the most similar domain — it's the most structurally
distant domain whose patterns still map onto the problem's mathematical shape. Maximum
semantic distance + structural relevance = maximum inventive pressure.

Selection strategy:
1. Embed the problem's abstract structural form
2. Embed each lens domain description
3. Compute cosine distance (1 - cosine_similarity) → higher = more distant
4. Filter by structural relevance (problem maps_to overlap)
5. Score: distance^α × relevance (superlinear reward for distance)
6. Exclude same-domain lenses
7. Return top-N
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

from hephaestus.lenses.loader import Lens, LensLoader

logger = logging.getLogger(__name__)

# Model used for all embeddings — small, fast, runs locally, no API calls
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Superlinear exponent: score = distance^α × relevance
# α > 1 means we strongly prefer distant domains over nearby ones
_DISTANCE_ALPHA = 1.8

# Minimum cosine distance to be considered "distant enough"
_MIN_DISTANCE_THRESHOLD = 0.05

# Domain description templates for embedding — gives richer semantic content
_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "biology": "biological systems, living organisms, evolution, cells, genetics, ecology",
    "physics": "physical laws, forces, energy, matter, thermodynamics, quantum mechanics, optics",
    "chemistry": "chemical reactions, molecular bonds, catalysis, polymers, atoms, compounds",
    "mathematics": "abstract mathematical structures, proofs, topology, logic, game theory, chaos",
    "math": "abstract mathematical structures, proofs, topology, logic, game theory, chaos",
    "cs": "computer science, algorithms, networks, cryptography, distributed systems, data structures",
    "military": "military strategy, tactics, logistics, intelligence, warfare, command and control",
    "economics": "economic systems, markets, incentives, game theory, behavioral economics, pricing",
    "music": "musical structure, harmony, rhythm, acoustics, composition, counterpoint",
    "linguistics": "language structure, syntax, semantics, grammar, meaning, communication",
    "neuroscience": "brain function, neurons, memory, perception, plasticity, cognition",
    "urban_planning": "urban design, city systems, infrastructure, zoning, public spaces",
    "urban": "urban design, city systems, infrastructure, zoning, public spaces",
    "architecture": "structural design, load distribution, materials, space, form, construction",
    "materials": "material properties, strength, phase transitions, crystalline structure, failure modes",
    "materials_science": "material properties, strength, phase transitions, crystalline structure, failure modes",
    "geology": "geological processes, tectonic forces, rock formation, deep time, plate tectonics",
    "meteorology": "weather patterns, atmospheric dynamics, pressure systems, fluid flow in atmosphere",
    "oceanography": "ocean currents, marine ecosystems, pressure, salinity, deep sea processes",
    "astronomy": "orbital mechanics, celestial dynamics, gravity, space, stellar evolution",
    "sociology": "social networks, group dynamics, norms, institutions, collective behavior",
    "psychology": "cognitive processes, perception, behavior, decision-making, mental models",
    "philosophy": "logic, reasoning, epistemology, ontology, ethics, formal argumentation",
    "agriculture": "farming systems, crop cycles, soil health, yield optimization, seasonal planning",
    "cooking": "fermentation, chemical transformation, flavor development, preservation, heat",
    "textiles": "weaving, pattern interlocking, fiber structure, tension, textile construction",
    "forestry": "forest management, succession, ecosystem services, long-cycle planning, disturbance",
    "epidemiology": "disease spread, contagion dynamics, population health, intervention, transmission",
    "mythology": "narrative archetypes, heroic journeys, symbolic patterns, cultural storytelling",
    "sports": "competitive strategy, team coordination, real-time adaptation, game theory",
    "film": "visual storytelling, cinematography, narrative pacing, framing, light and shadow",
    "martial_arts": "combat strategy, force economy, adaptive response, body mechanics, timing",
    "navigation": "wayfinding, dead reckoning, landmark-based orientation, path planning",
}


@dataclass
class LensScore:
    """A scored lens candidate for a particular problem."""

    lens: Lens
    domain_distance: float  # 0.0 (identical) to 1.0 (maximally distant)
    structural_relevance: float  # 0.0 (no overlap) to 1.0 (full overlap)
    composite_score: float  # distance^α × relevance
    matched_patterns: list[str]  # which maps_to tags matched the problem

    def __repr__(self) -> str:
        return (
            f"LensScore(id={self.lens.lens_id!r}, "
            f"dist={self.domain_distance:.3f}, "
            f"rel={self.structural_relevance:.3f}, "
            f"score={self.composite_score:.3f})"
        )


class EmbeddingModel:
    """
    Lazy wrapper around sentence-transformers.

    The model is loaded once on first use and cached for the lifetime of the process.
    This avoids paying the import cost until embeddings are actually needed.
    """

    _instance: "EmbeddingModel | None" = None
    _model: object | None = None

    def __new__(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

                logger.info("Loading embedding model %r (first use)…", _EMBEDDING_MODEL)
                self._model = SentenceTransformer(_EMBEDDING_MODEL)
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is required for lens selection. "
                    "Install it: pip install sentence-transformers"
                ) from exc

    def encode(self, texts: list[str]) -> "NDArray[np.float32]":
        """Encode a list of strings into normalized embedding vectors."""
        self._ensure_loaded()
        # sentence-transformers returns numpy array
        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def encode_one(self, text: str) -> "NDArray[np.float32]":
        return self.encode([text])[0]


def _cosine_distance(a: "NDArray[np.float32]", b: "NDArray[np.float32]") -> float:
    """Cosine distance: 1 - cosine_similarity. Vectors assumed normalized."""
    sim = float(np.dot(a, b))
    # Clamp to [-1, 1] to guard against float precision issues
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _domain_text(lens: Lens) -> str:
    """
    Build a rich textual description of a lens's domain for embedding.
    Combines domain template + lens name + axiom fragments.
    """
    domain_desc = _DOMAIN_DESCRIPTIONS.get(lens.domain, lens.domain)
    # Include a snippet from the first 2 axioms to enrich domain signal
    axiom_snippets = " ".join(lens.axioms[:2])
    return f"{lens.name}: {domain_desc}. {axiom_snippets}"


def _structural_relevance(lens: Lens, problem_maps_to: set[str]) -> tuple[float, list[str]]:
    """
    Compute structural relevance: fraction of the problem's abstract types
    that are covered by this lens's patterns.

    Returns (score ∈ [0, 1], list of matched tags).
    """
    if not problem_maps_to:
        # No structural info — treat all lenses as equally relevant
        return 1.0, []

    lens_maps_to = {m.lower() for m in lens.all_maps_to}
    problem_lower = {m.lower() for m in problem_maps_to}
    matched = lens_maps_to & problem_lower

    # Jaccard-style: |intersection| / |union|
    score = len(matched) / len(problem_lower | lens_maps_to) if (problem_lower | lens_maps_to) else 0.0
    return float(score), sorted(matched)


class LensSelector:
    """
    Selects the optimal cognitive lenses for a given problem.

    Strategy: maximize domain distance while maintaining structural relevance.
    The further the source domain, the more inventive pressure it creates — but
    it must still structurally map onto the problem (otherwise it's noise).

    Usage::

        loader = LensLoader()
        selector = LensSelector(loader)

        scores = selector.select(
            problem_description="I need a reputation system that resists Sybil attacks",
            problem_maps_to={"trust", "verification", "fraud_detection"},
            exclude_domains={"cs"},
            top_n=5,
        )
        for s in scores:
            print(s.lens.lens_id, s.composite_score)
    """

    def __init__(
        self,
        loader: LensLoader | None = None,
        embedding_model: EmbeddingModel | None = None,
        distance_alpha: float = _DISTANCE_ALPHA,
        min_distance: float = _MIN_DISTANCE_THRESHOLD,
    ) -> None:
        """
        Args:
            loader: LensLoader instance. Creates default loader if None.
            embedding_model: EmbeddingModel singleton. Creates default if None.
            distance_alpha: Superlinear exponent for distance reward. Default 1.8.
            min_distance: Minimum cosine distance to qualify as "distant enough".
        """
        self._loader = loader or LensLoader()
        self._embed = embedding_model or EmbeddingModel()
        self._alpha = distance_alpha
        self._min_distance = min_distance

        # Embedding cache: lens_id → embedding vector
        self._lens_embed_cache: dict[str, "NDArray[np.float32]"] = {}

    def _get_lens_embedding(self, lens: Lens) -> "NDArray[np.float32]":
        """Get or compute the embedding for a lens's domain description."""
        if lens.lens_id not in self._lens_embed_cache:
            text = _domain_text(lens)
            self._lens_embed_cache[lens.lens_id] = self._embed.encode_one(text)
        return self._lens_embed_cache[lens.lens_id]

    def precompute_embeddings(self) -> None:
        """
        Pre-compute and cache embeddings for all loaded lenses.
        Call this during startup to avoid latency on first select().
        """
        lenses = self._loader.load_all(skip_errors=True)
        texts = [_domain_text(l) for l in lenses.values()]
        lens_ids = list(lenses.keys())

        if not texts:
            return

        embeddings = self._embed.encode(texts)
        for lens_id, emb in zip(lens_ids, embeddings):
            self._lens_embed_cache[lens_id] = emb

        logger.info("Pre-computed embeddings for %d lenses", len(lens_ids))

    def compute_distance(self, problem_description: str, lens: Lens) -> float:
        """
        Compute cosine distance between a problem description and a lens's domain.

        Returns a float in [0, 1] where 1.0 = maximally distant.
        """
        problem_emb = self._embed.encode_one(problem_description)
        lens_emb = self._get_lens_embedding(lens)
        return _cosine_distance(problem_emb, lens_emb)

    def compute_all_distances(
        self,
        problem_description: str,
        lenses: list[Lens],
    ) -> dict[str, float]:
        """
        Batch-compute cosine distances from a problem to many lenses (faster than one-by-one).

        Returns mapping of lens_id → distance.
        """
        if not lenses:
            return {}

        # Encode problem
        problem_emb = self._embed.encode_one(problem_description)

        # Encode all lenses in one batch call (reuse cache for already-computed ones)
        uncached_lenses = [l for l in lenses if l.lens_id not in self._lens_embed_cache]
        if uncached_lenses:
            texts = [_domain_text(l) for l in uncached_lenses]
            embeddings = self._embed.encode(texts)
            for l, emb in zip(uncached_lenses, embeddings):
                self._lens_embed_cache[l.lens_id] = emb

        distances: dict[str, float] = {}
        for lens in lenses:
            lens_emb = self._lens_embed_cache[lens.lens_id]
            distances[lens.lens_id] = _cosine_distance(problem_emb, lens_emb)

        return distances

    def select(
        self,
        problem_description: str,
        problem_maps_to: set[str] | None = None,
        exclude_domains: set[str] | None = None,
        top_n: int = 5,
        require_relevance: bool = False,
    ) -> list[LensScore]:
        """
        Select the best cognitive lenses for a problem.

        Args:
            problem_description: Text describing the problem's abstract structure.
                                  Should use domain-neutral language for best results.
            problem_maps_to: Set of abstract problem type tags (e.g., {"trust", "optimization"}).
                             Used to filter by structural relevance.
            exclude_domains: Set of domains to exclude (usually the problem's native domain).
            top_n: Number of lenses to return.
            require_relevance: If True, only return lenses with relevance > 0.
                               If False, allow all lenses (distant wins even without overlap).

        Returns:
            List of LensScore objects, sorted by composite_score descending.
        """
        all_lenses = self._loader.load_all(skip_errors=True)
        if not all_lenses:
            return []

        exclude = {d.lower() for d in (exclude_domains or set())}
        maps_to = {m.lower() for m in (problem_maps_to or set())}

        # Filter out excluded domains
        candidate_lenses = [
            l for l in all_lenses.values() if l.domain not in exclude
        ]

        if not candidate_lenses:
            return []

        # Batch distance computation
        distances = self.compute_all_distances(problem_description, candidate_lenses)

        scores: list[LensScore] = []
        for lens in candidate_lenses:
            dist = distances.get(lens.lens_id, 0.0)

            # Skip lenses that are too similar to the problem domain
            if dist < self._min_distance:
                logger.debug("Skipping %s: distance %.3f below threshold", lens.lens_id, dist)
                continue

            relevance, matched = _structural_relevance(lens, maps_to)

            if require_relevance and relevance == 0.0:
                continue

            # Composite score: distance^α × relevance (or just distance^α if no maps_to)
            if maps_to:
                composite = (dist ** self._alpha) * max(relevance, 0.1)
            else:
                composite = dist ** self._alpha

            scores.append(
                LensScore(
                    lens=lens,
                    domain_distance=dist,
                    structural_relevance=relevance,
                    composite_score=composite,
                    matched_patterns=matched,
                )
            )

        # Sort by composite score descending
        scores.sort(key=lambda s: s.composite_score, reverse=True)
        return scores[:top_n]

    def select_by_maximum_distance(
        self,
        problem_description: str,
        exclude_domains: set[str] | None = None,
        top_n: int = 5,
    ) -> list[LensScore]:
        """
        Pure maximum-distance selection — ignores structural relevance.
        Use when you want maximum cognitive disruption regardless of fit.
        """
        return self.select(
            problem_description=problem_description,
            problem_maps_to=None,
            exclude_domains=exclude_domains,
            top_n=top_n,
            require_relevance=False,
        )

    def select_for_problem_type(
        self,
        problem_type: str,
        exclude_domains: set[str] | None = None,
        top_n: int = 5,
    ) -> list[LensScore]:
        """
        Select lenses by abstract problem type tag (e.g., 'trust', 'optimization').
        Uses the problem type itself as the description embedding.
        """
        return self.select(
            problem_description=problem_type,
            problem_maps_to={problem_type},
            exclude_domains=exclude_domains,
            top_n=top_n,
            require_relevance=True,
        )

    def invalidate_cache(self) -> None:
        """Clear the embedding cache (e.g., after hot-reload of lenses)."""
        self._lens_embed_cache.clear()

    def __repr__(self) -> str:
        return (
            f"LensSelector(alpha={self._alpha}, "
            f"min_distance={self._min_distance}, "
            f"cached_embeddings={len(self._lens_embed_cache)})"
        )
