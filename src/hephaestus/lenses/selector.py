"""Adaptive bundle-proof lens selector."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

from hephaestus.lenses.bundles import (
    BundleCandidate,
    BundleComposer,
    BundleProof,
    BundleSelectionResult,
    FoldState,
    build_bundle_candidates,
)
from hephaestus.lenses.cards import LensCard, compile_lens_card, score_query_against_card
from hephaestus.lenses.cells import CohesionCellIndex
from hephaestus.lenses.exclusion_ledger import AdaptiveExclusionLedger
from hephaestus.lenses.lineage import LensLineage, build_native_lineage, validate_lineage
from hephaestus.lenses.loader import Lens, LensLoader, classify_domain_family

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_DISTANCE_ALPHA = 1.8
_MIN_DISTANCE_THRESHOLD = 0.05
_SAME_FAMILY_WEIGHT = 0.4
_NEAR_FAMILY_WEIGHT = 0.75
_DEFAULT_BUNDLE_MIN_SCORE = 0.58

_RELATED_FAMILIES: dict[str, set[str]] = {
    "engineering": {"mathematics", "physical_sciences", "economics", "military"},
    "mathematics": {"engineering", "physical_sciences", "economics"},
    "physical_sciences": {"engineering", "mathematics", "biology", "agriculture"},
    "biology": {"physical_sciences", "agriculture", "psychology"},
    "agriculture": {"biology", "physical_sciences"},
    "psychology": {"biology", "economics", "linguistics"},
    "economics": {"engineering", "mathematics", "psychology", "military"},
    "linguistics": {"psychology", "arts", "myth"},
    "arts": {"linguistics", "myth"},
    "myth": {"arts", "linguistics"},
    "military": {"engineering", "economics"},
}

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
    "composite": "composite cross-domain structure, proof-carrying bundle, fold-state synthesis",
}


@dataclass
class LensScore:
    """A scored lens candidate for a particular problem."""

    lens: Lens
    domain_distance: float
    structural_relevance: float
    composite_score: float
    matched_patterns: list[str]
    domain_family: str = "general"
    diversity_weight: float = 1.0
    bundle_id: str | None = None
    bundle_rank: int = 0
    bundle_score: float | None = None
    bundle_proof: BundleProof | None = None
    fold_state: FoldState | None = None
    lineage: LensLineage | None = None
    lineage_valid: bool = True
    selection_mode: str = "singleton"
    selection_reasons: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return (
            f"LensScore(id={self.lens.lens_id!r}, mode={self.selection_mode!r}, "
            f"dist={self.domain_distance:.3f}, rel={self.structural_relevance:.3f}, "
            f"family={self.domain_family!r}, score={self.composite_score:.3f})"
        )


@dataclass
class SelectionPlan:
    """Full selector output including bundle context."""

    mode: str
    scores: list[LensScore]
    primary_bundle: BundleCandidate | None = None
    query_terms: tuple[str, ...] = ()
    fallback_used: bool = False
    blocked_reasons: tuple[str, ...] = ()


class EmbeddingModel:
    _instance: EmbeddingModel | None = None
    _model: object | None = None

    def __new__(cls) -> EmbeddingModel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import (
                    SentenceTransformer,  # type: ignore[import-untyped]
                )

                logger.info("Loading embedding model %r", _EMBEDDING_MODEL)
                self._model = SentenceTransformer(_EMBEDDING_MODEL)
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is required for lens selection. "
                    "Install it: pip install sentence-transformers"
                ) from exc

    def encode(self, texts: list[str]) -> NDArray[np.float32]:
        self._ensure_loaded()
        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def encode_one(self, text: str) -> NDArray[np.float32]:
        return self.encode([text])[0]


def _cosine_distance(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    sim = float(np.dot(a, b))
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _domain_text(lens: Lens) -> str:
    domain_desc = _DOMAIN_DESCRIPTIONS.get(lens.domain, lens.domain)
    axiom_snippets = " ".join(lens.axioms[:2])
    summary = ""
    try:
        summary = compile_lens_card(lens).summary_text()
    except Exception:
        summary = ""
    parent_clause = ""
    if lens.parent_lens_ids:
        parent_clause = f" parents: {', '.join(lens.parent_lens_ids[:4])}."
    return f"{lens.name}: {domain_desc}. {summary} {axiom_snippets}{parent_clause}".strip()


def _structural_relevance(lens: Lens, problem_maps_to: set[str]) -> tuple[float, list[str]]:
    if not problem_maps_to:
        return 1.0, []
    lens_maps_to = {item.lower() for item in lens.all_maps_to}
    problem_lower = {item.lower() for item in problem_maps_to}
    matched = lens_maps_to & problem_lower
    score = len(matched) / len(problem_lower | lens_maps_to) if (problem_lower | lens_maps_to) else 0.0
    return float(score), sorted(matched)


def _target_domain_families(
    target_domain: str | None,
    exclude_domains: set[str] | None,
) -> set[str]:
    families: set[str] = set()
    if target_domain:
        family = classify_domain_family(target_domain)
        if family != "general":
            families.add(family)
    for domain in exclude_domains or set():
        family = classify_domain_family(domain)
        if family != "general":
            families.add(family)
    return families


def _diversity_weight(domain_family: str, target_families: set[str]) -> float:
    if not target_families or domain_family == "general":
        return 1.0
    weight = 1.0
    for target_family in target_families:
        if domain_family == target_family:
            weight = min(weight, _SAME_FAMILY_WEIGHT)
            continue
        related_to_target = domain_family in _RELATED_FAMILIES.get(target_family, set())
        target_related_to_domain = target_family in _RELATED_FAMILIES.get(domain_family, set())
        if related_to_target or target_related_to_domain:
            weight = min(weight, _NEAR_FAMILY_WEIGHT)
    return weight


def _query_terms(problem_description: str, problem_maps_to: set[str] | None) -> tuple[str, ...]:
    parts = {term.lower().strip() for term in (problem_maps_to or set()) if term.strip()}
    parts.update(term.lower() for term in problem_description.split() if len(term) > 3)
    normalized = {
        term.strip(".,:;!?()[]{}<>\"'").replace("-", "_")
        for term in parts
    }
    return tuple(sorted(term for term in normalized if term))


class LensSelector:
    """Bundle-first selector with proof-aware fallback."""

    def __init__(
        self,
        loader: LensLoader | None = None,
        embedding_model: EmbeddingModel | None = None,
        distance_alpha: float = _DISTANCE_ALPHA,
        min_distance: float = _MIN_DISTANCE_THRESHOLD,
        exclusion_ledger: AdaptiveExclusionLedger | None = None,
        bundle_min_score: float = _DEFAULT_BUNDLE_MIN_SCORE,
    ) -> None:
        self._loader = loader or LensLoader()
        self._embed = embedding_model or EmbeddingModel()
        self._alpha = distance_alpha
        self._min_distance = min_distance
        self._ledger = exclusion_ledger or AdaptiveExclusionLedger()
        self._bundle_min_score = bundle_min_score
        self._lens_embed_cache: dict[str, NDArray[np.float32]] = {}
        self._last_plan: SelectionPlan | None = None

    @property
    def last_plan(self) -> SelectionPlan | None:
        return self._last_plan

    def _get_lens_embedding(self, lens: Lens) -> NDArray[np.float32]:
        if lens.lens_id not in self._lens_embed_cache:
            self._lens_embed_cache[lens.lens_id] = self._embed.encode_one(_domain_text(lens))
        return self._lens_embed_cache[lens.lens_id]

    def precompute_embeddings(self) -> None:
        lenses = self._loader.load_all(skip_errors=True)
        texts = [_domain_text(lens) for lens in lenses.values()]
        lens_ids = list(lenses.keys())
        if not texts:
            return
        embeddings = self._embed.encode(texts)
        for lens_id, embedding in zip(lens_ids, embeddings):
            self._lens_embed_cache[lens_id] = embedding
        logger.info("Pre-computed embeddings for %d lenses", len(lens_ids))

    def compute_distance(self, problem_description: str, lens: Lens) -> float:
        problem_emb = self._embed.encode_one(problem_description)
        lens_emb = self._get_lens_embedding(lens)
        return _cosine_distance(problem_emb, lens_emb)

    def compute_all_distances(
        self,
        problem_description: str,
        lenses: list[Lens],
    ) -> dict[str, float]:
        if not lenses:
            return {}
        problem_emb = self._embed.encode_one(problem_description)
        uncached = [lens for lens in lenses if lens.lens_id not in self._lens_embed_cache]
        if uncached:
            embeddings = self._embed.encode([_domain_text(lens) for lens in uncached])
            for lens, embedding in zip(uncached, embeddings):
                self._lens_embed_cache[lens.lens_id] = embedding
        return {
            lens.lens_id: _cosine_distance(problem_emb, self._lens_embed_cache[lens.lens_id])
            for lens in lenses
        }

    def _prepare_cards_and_lineages(
        self,
        candidate_lenses: Sequence[Lens],
        *,
        reference_context: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, LensCard], dict[str, LensLineage], CohesionCellIndex]:
        cards: dict[str, LensCard] = {}
        lineages: dict[str, LensLineage] = {}
        library_revision = int(getattr(self._loader, "library_revision", 0) or 0)

        for lens in candidate_lenses:
            try:
                card = self._loader.get_card(lens.lens_id)
            except Exception:
                card = compile_lens_card(lens, reference_context=reference_context or {})
            cards[lens.lens_id] = card

            try:
                lineage = self._loader.get_lineage(lens.lens_id, reference_context=reference_context)
            except Exception:
                lineage = build_native_lineage(
                    lens_id=lens.lens_id,
                    version=getattr(lens, "version", 1),
                    card_fingerprint64=card.fingerprint64,
                    loader_revision=library_revision,
                    source_kind=getattr(lens, "source_kind", "library"),
                    derivation="runtime",
                )
            lineages[lens.lens_id] = lineage
            lens.lineage_token = lineage.proof_token
            card.lineage_token = lineage.proof_token

        try:
            full_lenses = self._loader.load_all(skip_errors=True)
            if set(full_lenses.keys()) == set(cards.keys()):
                candidate_index = self._loader.get_cell_index(reference_context=reference_context)
                if isinstance(candidate_index, CohesionCellIndex):
                    index = candidate_index
                else:
                    index = CohesionCellIndex.build(
                        cards,
                        lineages=lineages,
                        reference_context=reference_context,
                    )
            else:
                index = CohesionCellIndex.build(cards, lineages=lineages, reference_context=reference_context)
        except Exception:
            index = CohesionCellIndex.build(cards, lineages=lineages, reference_context=reference_context)
        return cards, lineages, index

    def select_plan(
        self,
        problem_description: str,
        problem_maps_to: set[str] | None = None,
        exclude_domains: set[str] | None = None,
        target_domain: str | None = None,
        top_n: int = 5,
        require_relevance: bool = False,
        reference_context: Mapping[str, Any] | None = None,
    ) -> SelectionPlan:
        all_lenses = self._loader.load_all(skip_errors=True)
        if not all_lenses:
            plan = SelectionPlan(mode="fallback", scores=[], fallback_used=True)
            self._last_plan = plan
            return plan

        exclude = {domain.lower() for domain in (exclude_domains or set())}
        maps_to = {mapping.lower() for mapping in (problem_maps_to or set())}
        query_terms = _query_terms(problem_description, maps_to)
        target_families = _target_domain_families(target_domain, exclude)
        candidate_lenses = [
            lens for lens in all_lenses.values() if lens.domain not in exclude
        ]
        if not candidate_lenses:
            plan = SelectionPlan(mode="fallback", scores=[], fallback_used=True)
            self._last_plan = plan
            return plan

        distances = self.compute_all_distances(problem_description, list(candidate_lenses))
        cards, lineages, cell_index = self._prepare_cards_and_lineages(
            candidate_lenses,
            reference_context=reference_context,
        )
        cell_scores = cell_index.score_lenses(query_terms)
        library_revision = int(getattr(self._loader, "library_revision", 0) or 0)

        singleton_scores: list[LensScore] = []
        for lens in candidate_lenses:
            distance = distances.get(lens.lens_id, 0.0)
            if distance < self._min_distance:
                continue

            relevance, matched = _structural_relevance(lens, maps_to)
            if require_relevance and relevance == 0.0:
                continue

            card = cards[lens.lens_id]
            lineage = lineages[lens.lens_id]
            validation = validate_lineage(
                lineage,
                current_cards=cards,
                current_lineages=lineages,
                loader_revision=library_revision,
                reference_context=reference_context,
            )
            if not validation.valid:
                self._ledger.register_blocked(
                    lens_ids=[lens.lens_id],
                    families=[card.domain_family],
                    novelty_axes=card.novelty_axes,
                    proof_token=lineage.proof_token,
                    reasons=validation.reasons,
                )
                continue

            diversity_weight = _diversity_weight(lens.domain_family, target_families)
            query_term_set = set(query_terms)
            card_score = score_query_against_card(query_term_set, card)
            card_bonus = 1.0 + min(card_score / 10.0, 0.5)
            cell_bonus = 1.0 + min(cell_scores.get(lens.lens_id, 0.0) / 8.0, 0.35)
            if maps_to:
                composite = (distance ** self._alpha) * max(relevance, 0.1) * diversity_weight * card_bonus * cell_bonus
            else:
                composite = (distance ** self._alpha) * diversity_weight * card_bonus * cell_bonus

            ledger_decision = self._ledger.decide(
                families=[card.domain_family],
                novelty_axes=card.novelty_axes,
                proof_token=lineage.proof_token,
                lineage_valid=validation.valid,
            )
            if ledger_decision.blocked:
                continue
            composite *= ledger_decision.multiplier

            singleton_scores.append(
                LensScore(
                    lens=lens,
                    domain_distance=distance,
                    structural_relevance=relevance,
                    composite_score=composite,
                    matched_patterns=matched or list(cell_index.matched_tokens_for_lens(lens.lens_id, query_terms)),
                    domain_family=lens.domain_family,
                    diversity_weight=diversity_weight,
                    lineage=lineage,
                    lineage_valid=True,
                    selection_reasons=ledger_decision.reasons,
                )
            )

        singleton_scores.sort(key=lambda score: score.composite_score, reverse=True)
        if not singleton_scores:
            plan = SelectionPlan(
                mode="fallback",
                scores=[],
                query_terms=query_terms,
                fallback_used=True,
            )
            self._last_plan = plan
            return plan

        base_scores = {score.lens.lens_id: score.composite_score for score in singleton_scores}
        bundle_candidates = build_bundle_candidates(
            cards={score.lens.lens_id: cards[score.lens.lens_id] for score in singleton_scores},
            lineages={score.lens.lens_id: lineages[score.lens.lens_id] for score in singleton_scores},
            cell_index=cell_index,
            query_terms=query_terms,
            base_scores=base_scores,
            loader_revision=library_revision,
            reference_context=reference_context,
            ledger=self._ledger,
        )

        primary_bundle = bundle_candidates[0] if bundle_candidates else None
        if primary_bundle and primary_bundle.bundle_score >= self._bundle_min_score:
            singleton_by_id = {score.lens.lens_id: score for score in singleton_scores}
            bundle_scores: list[LensScore] = []
            max_contribution = max(primary_bundle.fold_state.member_contributions.values(), default=1.0)
            for rank, lens_id in enumerate(
                sorted(
                    primary_bundle.lens_ids,
                    key=lambda item: primary_bundle.fold_state.member_contributions.get(item, 0.0),
                    reverse=True,
                ),
                start=1,
            ):
                base = singleton_by_id[lens_id]
                contribution = primary_bundle.fold_state.member_contributions.get(lens_id, 0.0)
                contribution_ratio = contribution / max(0.001, max_contribution)
                boosted_score = base.composite_score * (
                    1.0 + 0.35 * primary_bundle.bundle_score + 0.1 * contribution_ratio
                )
                bundle_scores.append(
                    LensScore(
                        lens=base.lens,
                        domain_distance=base.domain_distance,
                        structural_relevance=base.structural_relevance,
                        composite_score=boosted_score,
                        matched_patterns=sorted(
                            {
                                *base.matched_patterns,
                                *primary_bundle.fold_state.matched_terms,
                            }
                        ),
                        domain_family=base.domain_family,
                        diversity_weight=base.diversity_weight,
                        bundle_id=primary_bundle.proof.bundle_id,
                        bundle_rank=rank,
                        bundle_score=primary_bundle.bundle_score,
                        bundle_proof=primary_bundle.proof,
                        fold_state=primary_bundle.fold_state,
                        lineage=base.lineage,
                        lineage_valid=base.lineage_valid,
                        selection_mode="bundle",
                        selection_reasons=tuple(
                            dict.fromkeys(
                                [
                                    *base.selection_reasons,
                                    *primary_bundle.ledger_decision.reasons,
                                ]
                            )
                        ),
                    )
                )

            remaining = [
                score
                for score in singleton_scores
                if score.lens.lens_id not in set(primary_bundle.lens_ids)
            ]
            combined = bundle_scores + remaining
            combined.sort(key=lambda score: score.composite_score, reverse=True)
            selected = combined[:top_n]
            self._ledger.register_selected(
                lens_ids=primary_bundle.lens_ids,
                families=primary_bundle.families,
                novelty_axes=primary_bundle.novelty_axes,
                proof_token=primary_bundle.proof.bundle_id,
                weight=primary_bundle.bundle_score,
            )
            plan = SelectionPlan(
                mode="bundle",
                scores=selected,
                primary_bundle=primary_bundle,
                query_terms=query_terms,
            )
            self._last_plan = plan
            return plan

        selected = singleton_scores[:top_n]
        self._ledger.register_selected(
            lens_ids=[score.lens.lens_id for score in selected],
            families=[score.domain_family for score in selected],
            novelty_axes=[
                axis
                for score in selected
                for axis in cards[score.lens.lens_id].novelty_axes
            ],
            proof_token=selected[0].lineage.proof_token if selected and selected[0].lineage else "",
            weight=sum(score.composite_score for score in selected) / max(1, len(selected)),
        )
        plan = SelectionPlan(
            mode="fallback",
            scores=selected,
            query_terms=query_terms,
            fallback_used=True,
        )
        self._last_plan = plan
        return plan

    def select(
        self,
        problem_description: str,
        problem_maps_to: set[str] | None = None,
        exclude_domains: set[str] | None = None,
        target_domain: str | None = None,
        top_n: int = 5,
        require_relevance: bool = False,
        ) -> list[LensScore]:
        return self.select_plan(
            problem_description=problem_description,
            problem_maps_to=problem_maps_to,
            exclude_domains=exclude_domains,
            target_domain=target_domain,
            top_n=top_n,
            require_relevance=require_relevance,
        ).scores

    def select_bundle_first(
        self,
        *,
        problem_description: str,
        problem_maps_to: set[str] | None = None,
        exclude_domains: set[str] | None = None,
        target_domain: str | None = None,
        top_n: int = 5,
        require_relevance: bool = False,
        structure: Any | None = None,
        max_bundle_size: int = 3,
        exclusion_ledger: AdaptiveExclusionLedger | None = None,
        reference_context: Mapping[str, Any] | None = None,
        allow_singleton_fallback: bool = True,
    ) -> BundleSelectionResult:
        """Build a runtime bundle proof first, then fall back to singleton ranking."""

        plan = self.select_plan(
            problem_description=problem_description,
            problem_maps_to=problem_maps_to,
            exclude_domains=exclude_domains,
            target_domain=target_domain,
            top_n=max(top_n * 2, 6),
            require_relevance=require_relevance,
            reference_context=reference_context,
        )
        ledger = exclusion_ledger or self._ledger
        if not plan.scores:
            return BundleSelectionResult(
                retrieval_mode="singleton",
                selected_lenses=(),
                fallback_lenses=(),
                exclusion_snapshot=ledger.snapshot(),
            )

        if structure is None:
            structure = SimpleNamespace(
                structure=problem_description,
                mathematical_shape=problem_description,
                constraints=[],
                problem_maps_to=set(problem_maps_to or set()),
                baseline_dossier=None,
                reference_invalidation_epoch=0,
            )

        if plan.mode != "bundle":
            selected = tuple(plan.scores[:top_n])
            fallback = tuple(plan.scores[top_n:])
            return BundleSelectionResult(
                retrieval_mode="singleton",
                selected_lenses=selected,
                fallback_lenses=fallback,
                exclusion_snapshot=ledger.snapshot(),
            )

        composer = BundleComposer(
            exclusion_ledger=ledger,
            max_bundle_size=max_bundle_size,
            candidate_pool_size=max(max_bundle_size + 2, len(plan.scores)),
            allow_singleton_fallback=allow_singleton_fallback,
        )
        return composer.select(list(plan.scores), structure)

    def select_by_maximum_distance(
        self,
        problem_description: str,
        exclude_domains: set[str] | None = None,
        target_domain: str | None = None,
        top_n: int = 5,
    ) -> list[LensScore]:
        return self.select(
            problem_description=problem_description,
            problem_maps_to=None,
            exclude_domains=exclude_domains,
            target_domain=target_domain,
            top_n=top_n,
            require_relevance=False,
        )

    def select_for_problem_type(
        self,
        problem_type: str,
        exclude_domains: set[str] | None = None,
        target_domain: str | None = None,
        top_n: int = 5,
    ) -> list[LensScore]:
        return self.select(
            problem_description=problem_type,
            problem_maps_to={problem_type},
            exclude_domains=exclude_domains,
            target_domain=target_domain,
            top_n=top_n,
            require_relevance=True,
        )

    def invalidate_cache(self) -> None:
        self._lens_embed_cache.clear()
        self._last_plan = None

    def __repr__(self) -> str:
        return (
            f"LensSelector(alpha={self._alpha}, min_distance={self._min_distance}, "
            f"cached_embeddings={len(self._lens_embed_cache)}, bundle_min_score={self._bundle_min_score})"
        )
