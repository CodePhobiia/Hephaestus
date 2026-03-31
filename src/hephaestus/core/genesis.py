"""
Genesis — Main Invention Pipeline Orchestrator.

The ``Genesis`` class wires all 5 stages of the Hephaestus invention pipeline:

    problem → DECOMPOSE → SEARCH → SCORE → TRANSLATE → VERIFY → InventionReport

Usage::

    from hephaestus.core.genesis import Genesis, GenesisConfig

    genesis = Genesis(GenesisConfig(
        anthropic_api_key="sk-ant-...",
        openai_api_key="sk-...",
    ))
    report = await genesis.invent("I need a load balancer for traffic spikes")
    print(report.top_invention.invention_name)
    print(f"Cost: ${report.total_cost_usd:.2f}")

Streaming::

    async for update in genesis.invent_stream("my problem"):
        print(update.stage, update.message)
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

# Module-level imports for test patchability.
# These are the stage classes that tests patch via
# `patch("hephaestus.core.genesis.ProblemDecomposer", ...)` etc.
# Lazy-loaded on first _ensure_built() call to avoid circular imports.
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
from hephaestus.deepforge.adapters.openai import OpenAIAdapter
from hephaestus.lenses.loader import LensLoader
from hephaestus.lenses.selector import LensSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Late-imported stage classes (populated at first use, patchable by tests)
# ---------------------------------------------------------------------------

def _import_stage_classes() -> tuple[Any, Any, Any, Any, Any]:
    """Import stage classes. Call once; cache result."""
    from hephaestus.core.decomposer import ProblemDecomposer
    from hephaestus.core.searcher import CrossDomainSearcher
    from hephaestus.core.scorer import CandidateScorer
    from hephaestus.core.translator import SolutionTranslator
    from hephaestus.core.verifier import NoveltyVerifier
    return ProblemDecomposer, CrossDomainSearcher, CandidateScorer, SolutionTranslator, NoveltyVerifier


# These are set at module level so they can be patched by tests.
# They start as None and are populated the first time Genesis._ensure_built is called.
ProblemDecomposer: Any = None
CrossDomainSearcher: Any = None
CandidateScorer: Any = None
SolutionTranslator: Any = None
NoveltyVerifier: Any = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class GenesisConfig:
    """
    Configuration for the Genesis invention pipeline.

    Attributes
    ----------
    anthropic_api_key:
        Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
    openai_api_key:
        OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
    decompose_model:
        Model for Stage 1 decomposition (default: claude-opus-4-5).
    search_model:
        Model for Stage 2 cross-domain search (default: gpt-4o).
    score_model:
        Model for Stage 3 candidate scoring (default: gpt-4o-mini).
    translate_model:
        Model for Stage 4 translation (default: claude-opus-4-5).
    attack_model:
        Model for Stage 5 adversarial attack (default: gpt-4o).
    defend_model:
        Model for Stage 5 validity assessment (default: claude-opus-4-5).
    num_search_lenses:
        Number of lenses to query in Stage 2 (default: 10).
    num_candidates:
        Number of candidates returned from Stage 2 (default: 8).
    min_search_confidence:
        Minimum confidence to include a search candidate (default: 0.4).
    min_domain_distance:
        Minimum domain distance; closer candidates filtered out (default: 0.3).
    num_translations:
        Number of candidates to translate in Stage 4 (default: 3).
    use_interference_in_search:
        Whether to enable cognitive interference during search (default: False).
    use_interference_in_translate:
        Whether to enable cognitive interference during translation (default: True).
    run_prior_art:
        Whether to run the prior art search in Stage 5 (default: True).
    max_tokens_decompose:
        Max output tokens for decomposition (default: 1024).
    max_tokens_search:
        Max output tokens for per-lens search (default: 800).
    max_tokens_score:
        Max output tokens for fidelity scoring (default: 600).
    max_tokens_translate:
        Max output tokens for translation (default: 2500).
    max_tokens_verify:
        Max output tokens for verification (default: 800).
    lens_library_dir:
        Override lens library directory path.
    """

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Model selection
    decompose_model: str = "claude-opus-4-5"
    search_model: str = "gpt-4o"
    score_model: str = "gpt-4o-mini"
    translate_model: str = "claude-opus-4-5"
    attack_model: str = "gpt-4o"
    defend_model: str = "claude-opus-4-5"

    # Pipeline parameters
    num_search_lenses: int = 10
    num_candidates: int = 8
    min_search_confidence: float = 0.4
    min_domain_distance: float = 0.3
    num_translations: int = 3

    # Feature flags
    use_interference_in_search: bool = False
    use_interference_in_translate: bool = True
    run_prior_art: bool = True

    # Token budgets
    max_tokens_decompose: int = 1024
    max_tokens_search: int = 800
    max_tokens_score: int = 600
    max_tokens_translate: int = 2500
    max_tokens_verify: int = 800

    # Library override
    lens_library_dir: str | None = None


# ---------------------------------------------------------------------------
# Pipeline progress types (for streaming)
# ---------------------------------------------------------------------------


class PipelineStage(Enum):
    """Stages of the Genesis pipeline."""
    STARTING = auto()
    DECOMPOSING = auto()
    DECOMPOSED = auto()
    SEARCHING = auto()
    SEARCHED = auto()
    SCORING = auto()
    SCORED = auto()
    TRANSLATING = auto()
    TRANSLATED = auto()
    VERIFYING = auto()
    VERIFIED = auto()
    COMPLETE = auto()
    FAILED = auto()


@dataclass
class PipelineUpdate:
    """A streaming progress update from the pipeline."""
    stage: PipelineStage
    message: str
    data: Any = None
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


@dataclass
class CostBreakdown:
    """
    Per-stage cost breakdown for a pipeline run.

    All costs in USD.
    """
    decomposition_cost: float = 0.0
    search_cost: float = 0.0
    scoring_cost: float = 0.0
    translation_cost: float = 0.0
    verification_cost: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.decomposition_cost
            + self.search_cost
            + self.scoring_cost
            + self.translation_cost
            + self.verification_cost
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "decomposition": self.decomposition_cost,
            "search": self.search_cost,
            "scoring": self.scoring_cost,
            "translation": self.translation_cost,
            "verification": self.verification_cost,
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# Invention Report
# ---------------------------------------------------------------------------


@dataclass
class InventionReport:
    """
    The complete output of a Genesis pipeline run.

    Contains everything produced at every stage, plus cost, timing, and
    the final invented solutions ready for consumption.

    Attributes
    ----------
    problem:
        The original problem as submitted.
    structure:
        Stage 1 output: abstract structural form.
    all_candidates:
        Stage 2 output: all search candidates.
    scored_candidates:
        Stage 3 output: scored and filtered candidates.
    translations:
        Stage 4 output: full translations for top candidates.
    verified_inventions:
        Stage 5 output: adversarially verified inventions.
    top_invention:
        The highest-ranked verified invention.
    cost_breakdown:
        Per-stage USD cost breakdown.
    total_cost_usd:
        Total pipeline cost in USD.
    total_duration_seconds:
        Wall-clock time for the full pipeline.
    model_config:
        Which models were used for which stages.
    """

    problem: str
    structure: Any  # ProblemStructure
    all_candidates: list[Any]  # list[SearchCandidate]
    scored_candidates: list[Any]  # list[ScoredCandidate]
    translations: list[Any]  # list[Translation]
    verified_inventions: list[Any]  # list[VerifiedInvention]
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)
    total_duration_seconds: float = 0.0
    model_config: dict[str, str] = field(default_factory=dict)

    @property
    def top_invention(self) -> Any:
        """The highest-ranked verified invention, or None."""
        return self.verified_inventions[0] if self.verified_inventions else None

    @property
    def total_cost_usd(self) -> float:
        return self.cost_breakdown.total

    @property
    def alternative_inventions(self) -> list[Any]:
        """All inventions except the top one."""
        return self.verified_inventions[1:]

    def to_dict(self) -> dict[str, Any]:
        """Convert to a serializable dictionary."""
        top = self.top_invention
        return {
            "problem": self.problem,
            "native_domain": self.structure.native_domain,
            "mathematical_shape": self.structure.mathematical_shape,
            "top_invention": {
                "name": top.invention_name if top else None,
                "source_domain": top.source_domain if top else None,
                "novelty_score": top.novelty_score if top else None,
                "feasibility": top.feasibility_rating if top else None,
                "verdict": top.verdict if top else None,
            } if top else None,
            "alternatives": [
                {
                    "name": inv.invention_name,
                    "source_domain": inv.source_domain,
                    "novelty_score": inv.novelty_score,
                }
                for inv in self.alternative_inventions
            ],
            "cost_breakdown": self.cost_breakdown.to_dict(),
            "total_duration_seconds": self.total_duration_seconds,
            "models": self.model_config,
        }

    def summary(self) -> str:
        """Human-readable one-line summary."""
        top = self.top_invention
        if top:
            return (
                f"⚒️  {top.invention_name} "
                f"(from {top.source_domain}) | "
                f"novelty={top.novelty_score:.2f} "
                f"| ${self.total_cost_usd:.2f} "
                f"| {self.total_duration_seconds:.0f}s"
            )
        return f"Genesis ran but produced no inventions | cost=${self.total_cost_usd:.2f}"


# ---------------------------------------------------------------------------
# Genesis
# ---------------------------------------------------------------------------


class GenesisError(Exception):
    """Raised when the Genesis pipeline fails at a critical stage."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"Genesis failed at stage {stage!r}: {reason}")
        self.stage = stage
        self.reason = reason


class Genesis:
    """
    Main Hephaestus invention pipeline orchestrator.

    Wires all 5 stages (Decompose → Search → Score → Translate → Verify)
    into a single ``invent()`` call that accepts a natural language problem
    and returns an ``InventionReport``.

    Parameters
    ----------
    config:
        ``GenesisConfig`` controlling models, parameters, and features.
    """

    def __init__(self, config: GenesisConfig | None = None) -> None:
        self._config = config or GenesisConfig()
        self._adapters: dict[str, Any] = {}
        self._harnesses: dict[str, Any] = {}
        self._stages_built = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def invent(self, problem: str) -> InventionReport:
        """
        Run the full Genesis pipeline on *problem*.

        Parameters
        ----------
        problem:
            Natural language problem description.

        Returns
        -------
        InventionReport
            Complete results including the top invention and cost breakdown.

        Raises
        ------
        GenesisError
            If a critical stage fails (decomposition failure, no candidates, etc.).
        """
        async for update in self.invent_stream(problem):
            if update.stage == PipelineStage.COMPLETE:
                return update.data  # type: ignore[return-value]
            elif update.stage == PipelineStage.FAILED:
                if isinstance(update.data, Exception):
                    raise GenesisError("pipeline", str(update.data)) from update.data
                raise GenesisError("pipeline", update.message)
        # Should not reach here
        raise GenesisError("pipeline", "Stream ended without COMPLETE event")

    async def invent_stream(
        self, problem: str
    ) -> AsyncIterator[PipelineUpdate]:
        """
        Run the Genesis pipeline with streaming progress updates.

        Yields ``PipelineUpdate`` objects as each stage completes.
        The final update has ``stage=PipelineStage.COMPLETE`` and
        ``data=InventionReport``.

        Parameters
        ----------
        problem:
            Natural language problem description.

        Yields
        ------
        PipelineUpdate
        """
        t_start = time.monotonic()
        cost = CostBreakdown()

        def elapsed() -> float:
            return time.monotonic() - t_start

        yield PipelineUpdate(
            stage=PipelineStage.STARTING,
            message=f"Starting Genesis pipeline for: {problem[:80]}…",
            elapsed_seconds=elapsed(),
        )

        try:
            # Build harnesses lazily (also populates module-level stage names)
            self._ensure_built()

            # Reference the module-level names (patchable in tests)
            import hephaestus.core.genesis as _genesis_module

            _ProblemDecomposer = _genesis_module.ProblemDecomposer
            _CrossDomainSearcher = _genesis_module.CrossDomainSearcher
            _CandidateScorer = _genesis_module.CandidateScorer
            _SolutionTranslator = _genesis_module.SolutionTranslator
            _NoveltyVerifier = _genesis_module.NoveltyVerifier
            _LensLoader = _genesis_module.LensLoader
            _LensSelector = _genesis_module.LensSelector

            # ── Stage 1: Decompose ──────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.DECOMPOSING,
                message="Stage 1/5: Extracting abstract structural form…",
                elapsed_seconds=elapsed(),
            )

            from hephaestus.core.decomposer import DecompositionError

            decomposer = _ProblemDecomposer(self._harnesses["decompose"])
            try:
                structure = await decomposer.decompose(problem)
            except DecompositionError as exc:
                yield PipelineUpdate(
                    stage=PipelineStage.FAILED,
                    message=f"Decomposition failed: {exc}",
                    data=exc,
                    elapsed_seconds=elapsed(),
                )
                return

            cost.decomposition_cost = structure.cost_usd

            yield PipelineUpdate(
                stage=PipelineStage.DECOMPOSED,
                message=(
                    f"Decomposed: [{structure.native_domain}] "
                    f"{structure.mathematical_shape[:80]}"
                ),
                data=structure,
                elapsed_seconds=elapsed(),
            )

            # ── Stage 2: Search ─────────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.SEARCHING,
                message=f"Stage 2/5: Searching {self._config.num_search_lenses} domains for structural matches…",
                elapsed_seconds=elapsed(),
            )

            from hephaestus.core.searcher import SearchError

            loader = _LensLoader(self._config.lens_library_dir)
            selector = _LensSelector(loader)

            searcher = _CrossDomainSearcher(
                harness=self._harnesses["search"],
                loader=loader,
                selector=selector,
                num_candidates=self._config.num_candidates,
                num_lenses=self._config.num_search_lenses,
                min_confidence=self._config.min_search_confidence,
            )
            try:
                candidates = await searcher.search(structure)
            except SearchError as exc:
                yield PipelineUpdate(
                    stage=PipelineStage.FAILED,
                    message=f"Search failed: {exc}",
                    data=exc,
                    elapsed_seconds=elapsed(),
                )
                return

            if not candidates:
                yield PipelineUpdate(
                    stage=PipelineStage.FAILED,
                    message="No candidates found — try a different problem description",
                    data=None,
                    elapsed_seconds=elapsed(),
                )
                return

            cost.search_cost = sum(c.cost_usd for c in candidates)

            yield PipelineUpdate(
                stage=PipelineStage.SEARCHED,
                message=f"Found {len(candidates)} cross-domain candidates",
                data=candidates,
                elapsed_seconds=elapsed(),
            )

            # ── Stage 3: Score ──────────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.SCORING,
                message=f"Stage 3/5: Scoring {len(candidates)} candidates (fidelity × distance^1.5)…",
                elapsed_seconds=elapsed(),
            )

            scorer = _CandidateScorer(
                harness=self._harnesses["score"],
                min_domain_distance=self._config.min_domain_distance,
            )
            scored = await scorer.score(candidates, structure)

            if not scored:
                yield PipelineUpdate(
                    stage=PipelineStage.FAILED,
                    message="All candidates filtered (too adjacent to native domain)",
                    data=None,
                    elapsed_seconds=elapsed(),
                )
                return

            cost.scoring_cost = sum(s.scoring_cost_usd for s in scored)

            yield PipelineUpdate(
                stage=PipelineStage.SCORED,
                message=(
                    f"Scored {len(scored)} candidates. "
                    f"Top: {scored[0].source_domain} "
                    f"(score={scored[0].combined_score:.3f})"
                ),
                data=scored,
                elapsed_seconds=elapsed(),
            )

            # ── Stage 4: Translate ──────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.TRANSLATING,
                message=f"Stage 4/5: Translating top {self._config.num_translations} candidates (interference active)…",
                elapsed_seconds=elapsed(),
            )

            translator = _SolutionTranslator(
                harness=self._harnesses["translate"],
                top_n=self._config.num_translations,
            )
            translations = await translator.translate(scored, structure)

            if not translations:
                yield PipelineUpdate(
                    stage=PipelineStage.FAILED,
                    message="All translations failed",
                    data=None,
                    elapsed_seconds=elapsed(),
                )
                return

            cost.translation_cost = sum(t.cost_usd for t in translations)

            yield PipelineUpdate(
                stage=PipelineStage.TRANSLATED,
                message=(
                    f"Translated {len(translations)} inventions. "
                    f"Top: {translations[0].invention_name}"
                ),
                data=translations,
                elapsed_seconds=elapsed(),
            )

            # ── Stage 5: Verify ─────────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.VERIFYING,
                message="Stage 5/5: Adversarial novelty verification…",
                elapsed_seconds=elapsed(),
            )

            verifier = _NoveltyVerifier(
                attack_harness=self._harnesses["attack"],
                defend_harness=self._harnesses["defend"],
                run_prior_art=self._config.run_prior_art,
            )
            verified = await verifier.verify(translations, structure)

            cost.verification_cost = sum(v.verification_cost_usd for v in verified)

            yield PipelineUpdate(
                stage=PipelineStage.VERIFIED,
                message=(
                    f"Verified {len(verified)} inventions. "
                    f"Top novelty: {verified[0].novelty_score:.2f}" if verified else "Verification complete"
                ),
                data=verified,
                elapsed_seconds=elapsed(),
            )

            # ── Build Report ─────────────────────────────────────────────────
            report = InventionReport(
                problem=problem,
                structure=structure,
                all_candidates=candidates,
                scored_candidates=scored,
                translations=translations,
                verified_inventions=verified,
                cost_breakdown=cost,
                total_duration_seconds=elapsed(),
                model_config={
                    "decompose": self._config.decompose_model,
                    "search": self._config.search_model,
                    "score": self._config.score_model,
                    "translate": self._config.translate_model,
                    "attack": self._config.attack_model,
                    "defend": self._config.defend_model,
                },
            )

            logger.info(
                "Genesis complete | %s | cost=$%.3f | time=%.1fs",
                report.summary(),
                report.total_cost_usd,
                report.total_duration_seconds,
            )

            yield PipelineUpdate(
                stage=PipelineStage.COMPLETE,
                message=report.summary(),
                data=report,
                elapsed_seconds=elapsed(),
            )

        except Exception as exc:
            logger.exception("Genesis pipeline failed with unexpected error")
            yield PipelineUpdate(
                stage=PipelineStage.FAILED,
                message=f"Pipeline failed: {exc}",
                data=exc,
                elapsed_seconds=elapsed(),
            )

    # ------------------------------------------------------------------
    # Internal: build adapters and harnesses
    # ------------------------------------------------------------------

    def _ensure_built(self) -> None:
        """Lazily build all adapters and harnesses."""
        if self._stages_built:
            return

        # Populate module-level stage class names (avoids circular imports at load time)
        import hephaestus.core.genesis as _self
        (
            _self.ProblemDecomposer,
            _self.CrossDomainSearcher,
            _self.CandidateScorer,
            _self.SolutionTranslator,
            _self.NoveltyVerifier,
        ) = _import_stage_classes()

        # Ensure adapter classes are also populated
        from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter as _AA
        from hephaestus.deepforge.adapters.openai import OpenAIAdapter as _OA
        from hephaestus.lenses.loader import LensLoader as _LL
        from hephaestus.lenses.selector import LensSelector as _LS
        _self.AnthropicAdapter = _AA
        _self.OpenAIAdapter = _OA
        _self.LensLoader = _LL
        _self.LensSelector = _LS

        cfg = self._config
        self._adapters = self._build_adapters(cfg)
        self._harnesses = self._build_harnesses(cfg, self._adapters)
        self._stages_built = True
        logger.info("Genesis stages built")

    @staticmethod
    def _build_adapters(cfg: GenesisConfig) -> dict[str, Any]:
        """Build the model adapters needed for each stage."""
        import hephaestus.core.genesis as _genesis_module
        _AnthropicAdapter = _genesis_module.AnthropicAdapter
        _OpenAIAdapter = _genesis_module.OpenAIAdapter

        adapters: dict[str, Any] = {}

        # Deduplicate: build each unique model name once
        anthropic_models = {
            n for n in [
                cfg.decompose_model,
                cfg.translate_model,
                cfg.defend_model,
            ]
            if n.startswith("claude")
        }
        openai_models = {
            n for n in [
                cfg.search_model,
                cfg.score_model,
                cfg.attack_model,
            ]
            if n.startswith("gpt") or n.startswith("o3") or n.startswith("o4")
        }

        for model_name in anthropic_models:
            adapters[model_name] = _AnthropicAdapter(
                model=model_name,
                api_key=cfg.anthropic_api_key,
            )

        for model_name in openai_models:
            adapters[model_name] = _OpenAIAdapter(
                model=model_name,
                api_key=cfg.openai_api_key,
            )

        # Fallback: if a model wasn't categorised, try anthropic first
        all_models = {
            cfg.decompose_model, cfg.search_model, cfg.score_model,
            cfg.translate_model, cfg.attack_model, cfg.defend_model
        }
        for model_name in all_models:
            if model_name not in adapters:
                try:
                    adapters[model_name] = _AnthropicAdapter(
                        model=model_name,
                        api_key=cfg.anthropic_api_key,
                    )
                except Exception:
                    try:
                        adapters[model_name] = _OpenAIAdapter(
                            model=model_name,
                            api_key=cfg.openai_api_key,
                        )
                    except Exception:
                        pass

        return adapters

    @staticmethod
    def _build_harnesses(
        cfg: GenesisConfig,
        adapters: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the DeepForge harnesses for each pipeline stage."""
        from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig

        def get_adapter(model: str) -> Any:
            if model not in adapters:
                raise GenesisError(
                    "init",
                    f"No adapter available for model {model!r}. Check your API keys.",
                )
            return adapters[model]

        harnesses: dict[str, Any] = {}

        # Decompose: no interference (clean structural extraction)
        harnesses["decompose"] = DeepForgeHarness(
            adapter=get_adapter(cfg.decompose_model),
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_decompose,
                temperature=0.3,
            ),
        )

        # Search: optional interference
        harnesses["search"] = DeepForgeHarness(
            adapter=get_adapter(cfg.search_model),
            config=HarnessConfig(
                use_interference=cfg.use_interference_in_search,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_search,
                temperature=0.5,
            ),
        )

        # Score: no interference (objective assessment)
        harnesses["score"] = DeepForgeHarness(
            adapter=get_adapter(cfg.score_model),
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_score,
                temperature=0.2,
            ),
        )

        # Translate: cognitive interference handled inside SolutionTranslator
        harnesses["translate"] = DeepForgeHarness(
            adapter=get_adapter(cfg.translate_model),
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_translate,
                temperature=0.7,
            ),
        )

        # Attack: no interference (adversarial should be objective)
        harnesses["attack"] = DeepForgeHarness(
            adapter=get_adapter(cfg.attack_model),
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_verify,
                temperature=0.4,
            ),
        )

        # Defend: no interference (validity assessment should be clear-eyed)
        harnesses["defend"] = DeepForgeHarness(
            adapter=get_adapter(cfg.defend_model),
            config=HarnessConfig(
                use_interference=False,
                use_pruner=False,
                use_pressure=False,
                max_tokens=cfg.max_tokens_verify,
                temperature=0.3,
            ),
        )

        return harnesses

    # ------------------------------------------------------------------
    # Convenience class method
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "Genesis":
        """
        Create a Genesis instance using API keys from environment variables.

        Reads ``ANTHROPIC_API_KEY`` and ``OPENAI_API_KEY`` from the environment.
        """
        import os

        return cls(
            GenesisConfig(
                anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
                openai_api_key=os.environ.get("OPENAI_API_KEY"),
            )
        )
