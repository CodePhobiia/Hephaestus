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


def _branchgenome_outcome_for_verified(
    invention: Any,
    baselines: list[str],
) -> str:
    """Map verifier output onto the trimmed BranchGenome V1 ledger outcomes."""
    translation = getattr(invention, "translation", None)
    if translation is None:
        return "invalid"

    verdict = str(getattr(invention, "verdict", "")).upper()
    feasibility = str(getattr(invention, "feasibility_rating", "")).upper()
    if getattr(translation, "mechanism_is_decorative", False) or not getattr(invention, "load_bearing_passed", True):
        return "decorative"
    if verdict == "DERIVATIVE" or str(getattr(invention, "prior_art_status", "")) == "PRIOR_ART_FOUND":
        return "derivative"
    if verdict == "INVALID" or feasibility in {"LOW", "THEORETICAL"} or getattr(invention.adversarial_result, "fatal_flaws", []):
        return "invalid"

    try:
        from hephaestus.analytics.failure_log import detect_baseline_overlaps

        invention_text = " ".join(
            filter(
                None,
                [
                    str(getattr(translation, "key_insight", "") or ""),
                    str(getattr(translation, "architecture", "") or ""),
                    str(getattr(translation, "baseline_comparison", "") or ""),
                ],
            )
        )
        if detect_baseline_overlaps(invention_text, baselines):
            return "baseline_overlap"
    except Exception:
        pass

    return "accepted"


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
    use_perplexity_research:
        Whether to attach Perplexity grounding/reconnaissance when a key is
        configured (default: True).
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
    openrouter_api_key: str | None = None
    use_claude_cli: bool = False
    use_claude_max: bool = False
    use_codex_cli: bool = False

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
    use_perplexity_research: bool = True
    use_branchgenome_v1: bool = False
    use_adaptive_lens_engine: bool = True
    allow_lens_bundle_fallback: bool = True
    enable_derived_lens_composites: bool = True
    use_pantheon_mode: bool = False
    pantheon_max_rounds: int = 4
    pantheon_require_unanimity: bool = True
    pantheon_allow_fail_closed: bool = True
    pantheon_max_survivors_to_council: int = 2
    perplexity_model: str | None = None
    branchgenome_rejection_ledger_path: str | None = None

    # V2 system prompt parameters
    divergence_intensity: str = "STANDARD"  # STANDARD | AGGRESSIVE | MAXIMUM
    output_mode: str = "MECHANISM"  # MECHANISM | FRAMEWORK | NARRATIVE | SYSTEM | PROTOCOL | TAXONOMY | INTERFACE
    output_length: str = "FULL"  # DENSE | FULL | EXPANSIVE

    # Token budgets
    max_tokens_decompose: int = 16000
    max_tokens_search: int = 16000
    max_tokens_score: int = 16000
    max_tokens_translate: int = 16000
    max_tokens_verify: int = 16000

    # V2 mechanisms
    exclusion_zone: list[str] | None = None
    banned_baselines: list[str] | None = None
    max_rejection_retries: int = 1
    max_bundle_size: int = 3
    max_bundle_recompositions: int = 2

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
    baseline_dossier: Any | None = None
    lens_runtime: dict[str, Any] = field(default_factory=dict)
    lens_engine_state: Any | None = None
    pantheon_state: Any | None = None
    branchgenome_metrics: dict[str, Any] = field(default_factory=dict)
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
    def total_input_tokens(self) -> int:
        """Aggregate input tokens across unique stage traces."""
        total = 0
        seen: set[int] = set()
        traces = []
        traces.append(getattr(self.structure, "trace", None))
        traces.extend(getattr(c, "trace", None) for c in self.all_candidates)
        traces.extend(getattr(c, "scoring_trace", None) for c in self.scored_candidates)
        traces.extend(getattr(t, "trace", None) for t in self.translations)
        traces.extend(getattr(v, "trace", None) for v in self.verified_inventions)
        for trace in traces:
            if trace is None:
                continue
            ident = id(trace)
            if ident in seen:
                continue
            seen.add(ident)
            total += int(getattr(trace, "total_input_tokens", 0) or 0)
        return total

    @property
    def total_output_tokens(self) -> int:
        """Aggregate output tokens across unique stage traces."""
        total = 0
        seen: set[int] = set()
        traces = []
        traces.append(getattr(self.structure, "trace", None))
        traces.extend(getattr(c, "trace", None) for c in self.all_candidates)
        traces.extend(getattr(c, "scoring_trace", None) for c in self.scored_candidates)
        traces.extend(getattr(t, "trace", None) for t in self.translations)
        traces.extend(getattr(v, "trace", None) for v in self.verified_inventions)
        for trace in traces:
            if trace is None:
                continue
            ident = id(trace)
            if ident in seen:
                continue
            seen.add(ident)
            total += int(getattr(trace, "total_output_tokens", 0) or 0)
        return total

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
                "verdict": getattr(top, 'verdict', None) if top else None,
                "architecture": getattr(top.translation, 'architecture', None) if top and hasattr(top, 'translation') else None,
                "mapping": getattr(top.translation, 'mapping', None) if top and hasattr(top, 'translation') else None,
                "limitations": getattr(top.translation, 'limitations', None) if top and hasattr(top, 'translation') else None,
                "key_insight": getattr(top.translation, 'key_insight', None) if top and hasattr(top, 'translation') else None,
                "implementation_notes": getattr(top.translation, 'implementation_notes', None) if top and hasattr(top, 'translation') else None,
                "adversarial_critique": getattr(top, 'adversarial_result', None) if top else None,
                "validity_notes": getattr(top, 'validity_notes', None) if top else None,
                "recommended_next_steps": getattr(top, 'recommended_next_steps', None) if top else None,
                "grounding_report": getattr(top, 'grounding_report', None) if top else None,
                "implementation_risk_review": getattr(top, 'implementation_risk_review', None) if top else None,
                "bundle_acceptance_status": getattr(top, 'bundle_acceptance_status', None) if top else None,
                "orchestration_mode": getattr(top, 'orchestration_mode', None) if top else None,
                "guard_failures": getattr(top, 'guard_failures', None) if top else None,
                "lineage_stale": getattr(top, 'lineage_stale', None) if top else None,
            } if top else None,
            "baseline_dossier": self._research_to_dict(self.baseline_dossier),
            "lens_runtime": self._research_to_dict(self.lens_runtime),
            "lens_engine": self._research_to_dict(self.lens_engine_state),
            "pantheon": self._research_to_dict(self.pantheon_state),
            "alternatives": [
                {
                    "name": inv.invention_name,
                    "source_domain": inv.source_domain,
                    "novelty_score": inv.novelty_score,
                    "architecture": getattr(inv.translation, 'architecture', None) if hasattr(inv, 'translation') else None,
                    "key_insight": getattr(inv.translation, 'key_insight', None) if hasattr(inv, 'translation') else None,
                    "bundle_acceptance_status": getattr(inv, 'bundle_acceptance_status', None),
                    "orchestration_mode": getattr(inv, 'orchestration_mode', None),
                }
                for inv in self.alternative_inventions
            ],
            "cost_breakdown": self.cost_breakdown.to_dict(),
            "total_duration_seconds": self.total_duration_seconds,
            "models": self.model_config,
            "branchgenome": dict(self.branchgenome_metrics),
        }

    @staticmethod
    def _research_to_dict(obj: Any | None) -> Any:
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, list):
            return [InventionReport._research_to_dict(item) for item in obj]
        if isinstance(obj, dict):
            return {k: InventionReport._research_to_dict(v) for k, v in obj.items()}
        if hasattr(obj, "__dict__"):
            return {
                k: InventionReport._research_to_dict(v)
                for k, v in obj.__dict__.items()
            }
        return str(obj)

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
        branchgenome_metrics: dict[str, Any] = {}
        branchgenome_ledger: Any = None
        lens_runtime: dict[str, Any] = {}

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

            # ── Phase 0: Burn-Off (generate obvious baselines) ─────────────
            baselines: list[str] = list(self._config.banned_baselines or [])
            try:
                from hephaestus.core.burn_off import BurnOff
                burn_off = BurnOff(self._harnesses["decompose"])
                burn_off_results = await burn_off.generate_baselines(problem)
                if burn_off_results:
                    baselines.extend(burn_off_results)
                    logger.info("Burn-off produced %d baselines", len(burn_off_results))
            except Exception as exc:
                logger.warning("Burn-off skipped: %s", exc)

            # ── Anti-Memory query (exclusion zone) ─────────────────────────
            exclusion_zone: str = ""
            config_exclusions = self._config.exclusion_zone or []
            if config_exclusions:
                exclusion_zone = "\n".join(f"- {e}" for e in config_exclusions)
            try:
                from hephaestus.memory.anti_memory import AntiMemory
                anti_mem = AntiMemory()
                past_inventions = anti_mem.query(problem, top_k=5)
                if past_inventions:
                    mem_lines = [
                        f"- {p['invention_name']}: {p['text'][:120]}"
                        for p in past_inventions
                    ]
                    exclusion_zone = (exclusion_zone + "\n" + "\n".join(mem_lines)).strip()
                    logger.info("Anti-memory exclusion zone: %d past inventions", len(past_inventions))
            except Exception as exc:
                logger.warning("Anti-memory query skipped: %s", exc)

            # ── Build V2 system prompt (with burn-off + anti-memory) ───────
            v2_system_prompt: str | None = None
            try:
                from hephaestus.prompts.system_prompt import build_system_prompt
                v2_system_prompt = build_system_prompt(
                    user_prompt=problem,
                    anti_memory_zone=exclusion_zone,
                    banned_baselines="\n".join(f"- {b}" for b in baselines) if baselines else "",
                    output_mode=self._config.output_mode,
                    divergence_intensity=self._config.divergence_intensity,
                    output_length=self._config.output_length,
                )
                logger.info(
                    "V2 system prompt built | intensity=%s mode=%s baselines=%d",
                    self._config.divergence_intensity,
                    self._config.output_mode,
                    len(baselines),
                )
            except Exception as exc:
                logger.warning("V2 system prompt build failed, using per-stage prompts: %s", exc)

            # ── CrutchFilter injection ─────────────────────────────────────
            try:
                from hephaestus.deepforge.crutch_filter import CrutchFilter
                cf = CrutchFilter()
                crutch_constraint = cf.get_negative_constraint_for_claude()
                if v2_system_prompt:
                    v2_system_prompt = v2_system_prompt + "\n\n" + crutch_constraint
                logger.info("Crutch filter injected (%d banned words)", len(cf.words))
            except Exception as exc:
                logger.warning("Crutch filter skipped: %s", exc)

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

            # ── Stage 1.5: External reconnaissance (Perplexity) ──────────
            baseline_dossier = None
            pantheon_state = None
            if self._config.use_perplexity_research:
                try:
                    from hephaestus.research.perplexity import PerplexityClient

                    perplexity = PerplexityClient(
                        enabled=self._config.use_perplexity_research,
                        model=self._config.perplexity_model,
                    )
                    if perplexity.available():
                        baseline_dossier = await perplexity.build_baseline_dossier(
                            problem=problem,
                            native_domain=structure.native_domain,
                            mathematical_shape=structure.mathematical_shape,
                        )
                        structure.baseline_dossier = baseline_dossier
                        logger.info(
                            "Perplexity baseline dossier attached | standard=%d failures=%d avoid=%d",
                            len(getattr(baseline_dossier, "standard_approaches", [])),
                            len(getattr(baseline_dossier, "common_failure_modes", [])),
                            len(getattr(baseline_dossier, "keywords_to_avoid", [])),
                        )
                    await perplexity.close()
                except Exception as exc:
                    logger.warning("Perplexity baseline dossier skipped: %s", exc)

            # ── Stage 2: Search ─────────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.SEARCHING,
                message=f"Stage 2/5: Searching {self._config.num_search_lenses} domains for structural matches…",
                elapsed_seconds=elapsed(),
            )

            from hephaestus.core.searcher import SearchError

            loader = _LensLoader(
                self._config.lens_library_dir,
                allow_derived_composites=self._config.enable_derived_lens_composites,
            )
            selector = _LensSelector(loader)

            searcher = _CrossDomainSearcher(
                harness=self._harnesses["search"],
                loader=loader,
                selector=selector,
                num_candidates=self._config.num_candidates,
                num_lenses=self._config.num_search_lenses,
                min_confidence=self._config.min_search_confidence,
                max_bundle_size=self._config.max_bundle_size,
                use_adaptive_lens_engine=self._config.use_adaptive_lens_engine,
                allow_lens_bundle_fallback=self._config.allow_lens_bundle_fallback,
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
            if getattr(searcher, "last_runtime", None) is not None:
                lens_runtime["search"] = searcher.last_runtime.to_dict()

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

            translation_inputs = scored
            if self._config.use_branchgenome_v1:
                from hephaestus.branchgenome import (
                    RejectionLedger,
                    assay_branch,
                    branch_candidate_for_translation,
                    fingerprint_branch,
                    seed_branches_from_translation_inputs,
                    strategy_for_mode,
                )

                branch_strategy = strategy_for_mode(
                    self._config.divergence_intensity,
                    max_tokens_translate=self._config.max_tokens_translate,
                )
                branchgenome_ledger = RejectionLedger(self._config.branchgenome_rejection_ledger_path)
                branch_arena = seed_branches_from_translation_inputs(
                    scored,
                    structure,
                    branch_strategy,
                    banned_patterns=tuple(baselines),
                )

                for branch in branch_arena.active_branches():
                    candidate = scored[branch.source_candidate_index]
                    branch.metrics = assay_branch(
                        branch,
                        structure=structure,
                        candidate=candidate,
                        strategy=branch_strategy,
                        banned_patterns=tuple(baselines),
                        ledger=branchgenome_ledger,
                    )

                recovery_branches = branch_arena.spawn_recovery_branches(
                    branch_strategy,
                    structure=structure,
                    scored_candidates=scored,
                )
                for branch in recovery_branches:
                    candidate = scored[branch.source_candidate_index]
                    branch.metrics = assay_branch(
                        branch,
                        structure=structure,
                        candidate=candidate,
                        strategy=branch_strategy,
                        banned_patterns=tuple(baselines),
                        ledger=branchgenome_ledger,
                    )

                pruned = branch_arena.prune_over_budget(branch_strategy)
                for branch in pruned:
                    failed_checks = branch.metrics.perturbations_run - branch.metrics.perturbations_passed
                    if branch.metrics.rejection_overlap >= branch_strategy.baseline_equivalent_overlap:
                        outcome = "baseline_overlap"
                    elif (
                        branch.metrics.comfort_penalty >= branch_strategy.recovery_activation_threshold
                        and branch.metrics.future_option_preservation < branch_strategy.min_option_preservation
                    ):
                        outcome = "decorative"
                    elif failed_checks > branch_strategy.max_failed_perturbations or branch.metrics.collapse_risk >= 0.65:
                        outcome = "decorative"
                    else:
                        outcome = "invalid"
                    branchgenome_ledger.record(
                        fingerprint_branch(branch),
                        outcome,
                        f"Pre-translation prune for {branch.branch_id} (survival={branch.metrics.score_survival:.3f})",
                    )

                promote_limit = max(
                    1,
                    min(self._config.num_translations, branch_strategy.max_promoted_branches),
                )
                promoted_branches = branch_arena.promote_top_k(promote_limit)
                if not promoted_branches:
                    yield PipelineUpdate(
                        stage=PipelineStage.FAILED,
                        message="BranchGenome pruned all branches before translation",
                        data=None,
                        elapsed_seconds=elapsed(),
                    )
                    return

                translation_inputs = [
                    branch_candidate_for_translation(branch, scored[branch.source_candidate_index])
                    for branch in promoted_branches
                ]
                branchgenome_metrics = branch_arena.observability_snapshot()
                logger.info(
                    "BranchGenome promoted %d/%d branches | recovered=%d avg_spread=%.2f avg_option=%.2f avg_comfort=%.2f avg_baseline_attractor=%.2f avg_branch_fatigue=%.2f avg_collapse=%.2f",
                    branchgenome_metrics["branches_promoted"],
                    branchgenome_metrics["branches_seeded"],
                    branchgenome_metrics["branches_recovered"],
                    branchgenome_metrics["avg_spread_score"],
                    branchgenome_metrics["avg_future_option_preservation"],
                    branchgenome_metrics["avg_comfort_penalty"],
                    branchgenome_metrics["avg_baseline_attractor"],
                    branchgenome_metrics["avg_branch_fatigue"],
                    branchgenome_metrics["avg_collapse_risk"],
                )

            # ── Stage 4: Translate ──────────────────────────────────────────
            yield PipelineUpdate(
                stage=PipelineStage.TRANSLATING,
                message=(
                    f"Stage 4/5: Translating BranchGenome-promoted {len(translation_inputs)} branches…"
                    if self._config.use_branchgenome_v1
                    else f"Stage 4/5: Translating top {self._config.num_translations} candidates (interference active)…"
                ),
                elapsed_seconds=elapsed(),
            )

            # V2 system prompt is NOT passed to translator — it conflicts with
            # the JSON output format. Creativity forcing happens through the
            # mechanical constraints (burn-off, anti-memory, crutch filter,
            # lens selection, cognitive interference) not prompt overrides.
            # Banned baselines ARE injected into the translator prompt directly.
            translator = _SolutionTranslator(
                harness=self._harnesses["translate"],
                top_n=self._config.num_translations,
                max_bundle_recompositions=self._config.max_bundle_recompositions,
                allow_bundle_fallback=self._config.allow_lens_bundle_fallback,
            )
            translator._banned_baselines = baselines if baselines else []
            attempted_translation_inputs = translation_inputs[: self._config.num_translations]
            translations = await translator.translate(translation_inputs, structure)
            translation_runtime = getattr(translator, "last_runtime", None)
            if translation_runtime is not None:
                lens_runtime["translation"] = translation_runtime.to_dict()

            if self._config.use_pantheon_mode and translations:
                try:
                    from hephaestus.pantheon import PantheonCoordinator

                    pantheon = PantheonCoordinator(
                        athena_harness=self._harnesses["decompose"],
                        hermes_harness=self._harnesses["search"],
                        apollo_harness=self._harnesses["defend"],
                        max_rounds=self._config.pantheon_max_rounds,
                        require_unanimity=self._config.pantheon_require_unanimity,
                        allow_fail_closed=self._config.pantheon_allow_fail_closed,
                        max_survivors_to_council=self._config.pantheon_max_survivors_to_council,
                    )
                    translations, pantheon_state = await pantheon.deliberate(
                        problem=problem,
                        structure=structure,
                        translations=translations,
                        translator=translator,
                        baseline_dossier=baseline_dossier,
                    )
                    if pantheon_state is not None:
                        lens_runtime["pantheon"] = pantheon_state.to_dict()
                    if not translations:
                        yield PipelineUpdate(
                            stage=PipelineStage.FAILED,
                            message="Pantheon Mode failed to produce a council-surviving invention",
                            data=pantheon_state,
                            elapsed_seconds=elapsed(),
                        )
                        return
                except Exception as exc:
                    logger.warning("Pantheon Mode skipped after translation failure: %s", exc)

            if self._config.use_branchgenome_v1:
                from hephaestus.branchgenome.models import BranchStatus

                for translation in translations:
                    branch = getattr(getattr(translation, "source_candidate", None), "branch_genome", None)
                    if branch is not None:
                        branch.status = BranchStatus.TRANSLATED
                invalidated_lens_ids = set(
                    getattr(translation_runtime, "invalidated_lens_ids", ()) if translation_runtime is not None else ()
                )
                if invalidated_lens_ids:
                    for candidate in translation_inputs:
                        branch = getattr(candidate, "branch_genome", None)
                        if branch is not None and candidate.lens_id in invalidated_lens_ids:
                            branch.status = BranchStatus.PRUNED

            if (
                not translations
                and self._config.allow_lens_bundle_fallback
                and getattr(searcher, "last_runtime", None) is not None
            ):
                fallback_inputs = self._singleton_fallback_inputs(
                    scored=scored,
                    attempted=attempted_translation_inputs,
                    invalidated_lens_ids=set(
                        getattr(translation_runtime, "invalidated_lens_ids", ()) if translation_runtime is not None else ()
                    ),
                )
                if fallback_inputs:
                    logger.info(
                        "Bundle translation produced no valid outputs; retrying singleton fallback with %d candidates",
                        len(fallback_inputs),
                    )
                    translations = await translator.translate(
                        fallback_inputs,
                        structure,
                        top_n=min(self._config.num_translations, len(fallback_inputs)),
                    )
                    translation_runtime = getattr(translator, "last_runtime", None)
                    if translation_runtime is not None:
                        lens_runtime["translation_retry"] = translation_runtime.to_dict()

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
                use_perplexity_research=self._config.use_perplexity_research,
                perplexity_model=self._config.perplexity_model,
            )
            verified = await verifier.verify(translations, structure)
            if self._config.use_pantheon_mode and pantheon_state is not None:
                try:
                    from hephaestus.pantheon import PantheonCoordinator

                    pantheon_state = PantheonCoordinator(
                        athena_harness=self._harnesses["decompose"],
                        hermes_harness=self._harnesses["search"],
                        apollo_harness=self._harnesses["defend"],
                    ).finalize_with_verified(pantheon_state, verified)
                    lens_runtime["pantheon"] = pantheon_state.to_dict()
                except Exception as exc:
                    logger.warning("Pantheon finalization skipped: %s", exc)
            lens_runtime["verification"] = {
                "count": len(verified),
                "bundle_acceptance_statuses": [
                    getattr(invention, "bundle_acceptance_status", "singleton")
                    for invention in verified
                ],
                "orchestration_modes": [
                    getattr(invention, "orchestration_mode", "singleton")
                    for invention in verified
                ],
                "lineage_stale_count": sum(
                    1 for invention in verified if getattr(invention, "lineage_stale", False)
                ),
            }

            if branchgenome_ledger is not None:
                from hephaestus.branchgenome import fingerprint_translation
                from hephaestus.branchgenome.models import BranchStatus

                promoted_outcomes: dict[str, Any] = {}
                for invention in verified:
                    translation = getattr(invention, "translation", None)
                    branch = getattr(getattr(translation, "source_candidate", None), "branch_genome", None)
                    if branch is None or translation is None:
                        continue
                    branch.status = BranchStatus.VERIFIED
                    outcome = _branchgenome_outcome_for_verified(invention, baselines)
                    branchgenome_ledger.record(
                        fingerprint_translation(translation),
                        outcome,
                        (
                            f"{invention.invention_name} "
                            f"(branch={branch.branch_id}, verdict={getattr(invention, 'verdict', 'UNKNOWN')}, "
                            f"novelty={getattr(invention, 'novelty_score', 0.0):.2f})"
                        ),
                    )
                    promoted_outcomes[branch.branch_id] = {
                        "invention_name": invention.invention_name,
                        "verdict": getattr(invention, "verdict", "UNKNOWN"),
                        "novelty_score": getattr(invention, "novelty_score", 0.0),
                        "feasibility_rating": getattr(invention, "feasibility_rating", "UNKNOWN"),
                        "ledger_outcome": outcome,
                        "bundle_acceptance_status": getattr(invention, "bundle_acceptance_status", "singleton"),
                        "orchestration_mode": getattr(invention, "orchestration_mode", "singleton"),
                        "operator_family_pattern": branch.operator_family_pattern(),
                        "operator_families": [family.value for family in branch.operator_family_history],
                        "repeated_family_streak": branch.metrics.repeated_family_streak,
                        "branch_state": {
                            "mechanism_purity": branch.state_summary.mechanism_purity,
                            "baseline_attractor": branch.state_summary.baseline_attractor,
                            "transfer_slack": branch.state_summary.transfer_slack,
                            "branch_fatigue": branch.state_summary.branch_fatigue,
                        },
                    }
                branchgenome_metrics["promoted_branch_outcomes"] = promoted_outcomes

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

            # ── Failure log store (persist rejected inventions/critique) ───
            if verified:
                try:
                    from hephaestus.analytics.failure_log import FailureLog

                    failure_log = FailureLog()
                    rejected_records = failure_log.append_rejected_inventions(
                        verified,
                        target_domain=structure.native_domain,
                        problem=problem,
                        baselines=baselines,
                    )
                    if rejected_records:
                        logger.info(
                            "Stored %d rejected inventions in failure log",
                            len(rejected_records),
                        )
                except Exception as exc:
                    logger.warning("Failure log store skipped: %s", exc)

            # ── Anti-Memory store (persist inventions for future exclusion) ─
            if verified:
                try:
                    from hephaestus.memory.anti_memory import AntiMemory
                    anti_mem_store = AntiMemory()
                    for inv in verified:
                        anti_mem_store.store(
                            f"{inv.invention_name}: {inv.translation.architecture[:500]}",
                            metadata={
                                "invention_name": inv.invention_name,
                                "source_domain": inv.source_domain,
                            },
                        )
                    logger.info("Stored %d inventions in anti-memory", len(verified))
                except Exception as exc:
                    logger.warning("Anti-memory store skipped: %s", exc)

            # ── Build Report ─────────────────────────────────────────────────
            report = InventionReport(
                problem=problem,
                structure=structure,
                all_candidates=candidates,
                scored_candidates=scored,
                translations=translations,
                verified_inventions=verified,
                baseline_dossier=baseline_dossier,
                lens_runtime=lens_runtime,
                branchgenome_metrics=branchgenome_metrics,
                pantheon_state=pantheon_state,
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
            try:
                from hephaestus.lenses.state import LensEngineState

                report.lens_engine_state = LensEngineState.from_report(report)
            except Exception as exc:
                logger.warning("Lens-engine report surface skipped: %s", exc)

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

    @staticmethod
    def _singleton_fallback_inputs(
        *,
        scored: list[Any],
        attempted: list[Any],
        invalidated_lens_ids: set[str],
    ) -> list[Any]:
        attempted_ids = {candidate.lens_id for candidate in attempted}
        fallback: list[Any] = []
        for candidate in scored:
            if candidate.lens_id in attempted_ids or candidate.lens_id in invalidated_lens_ids:
                continue
            fallback.append(candidate)
        return fallback

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
        import os
        import hephaestus.core.genesis as _genesis_module
        _AnthropicAdapter = _genesis_module.AnthropicAdapter
        _OpenAIAdapter = _genesis_module.OpenAIAdapter

        adapters: dict[str, Any] = {}

        all_models = {
            cfg.decompose_model, cfg.search_model, cfg.score_model,
            cfg.translate_model, cfg.attack_model, cfg.defend_model
        }

        # Claude Max mode — route ALL models through OAT subscription auth
        if cfg.use_claude_max:
            from hephaestus.deepforge.adapters.claude_max import ClaudeMaxAdapter
            logger.info("Claude Max mode — routing all models via OAT subscription auth")
            # Map any non-Claude model names to Claude equivalents
            claude_default = "claude-sonnet-4-6"
            for model_name in all_models:
                # If it's already a Claude model, use it as-is
                if model_name.startswith("claude"):
                    adapters[model_name] = ClaudeMaxAdapter(model=model_name)
                else:
                    # Map non-Claude models (gpt-4o, o3-mini, etc.) to Claude
                    adapters[model_name] = ClaudeMaxAdapter(model=claude_default)
                    logger.info("Claude Max: mapped %s -> %s", model_name, claude_default)
            return adapters

        # Claude CLI mode
        if cfg.use_claude_cli:
            from hephaestus.deepforge.adapters.claude_cli import ClaudeCliAdapter
            logger.info("Claude CLI mode — routing all models through claude --print")
            for model_name in all_models:
                adapters[model_name] = ClaudeCliAdapter(model=model_name)
            return adapters

        # Codex CLI mode (ChatGPT/Codex OAuth, GPT Pro subscription)
        if cfg.use_codex_cli:
            from hephaestus.deepforge.adapters.codex_oauth import CodexOAuthAdapter
            logger.info("Codex OAuth mode — routing all models through native openai-codex-responses transport")
            codex_default = "gpt-5.4"
            for model_name in all_models:
                # Route every stage through Codex; unknown provider model names map to configured Codex model
                target_model = model_name if model_name.startswith("gpt-") else codex_default
                adapters[model_name] = CodexOAuthAdapter(model=target_model)
                if target_model != model_name:
                    logger.info("Codex OAuth: mapped %s -> %s", model_name, target_model)
            return adapters

        # OpenRouter mode
        openrouter_key = cfg.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            from hephaestus.deepforge.adapters.openrouter import OpenRouterAdapter
            logger.info("OpenRouter mode — routing all models through OpenRouter")
            for model_name in all_models:
                adapters[model_name] = OpenRouterAdapter(model=model_name, api_key=openrouter_key)
            return adapters

        # Direct API keys — deduplicate: build each unique model name once
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
                    except Exception as exc2:
                        logger.warning(
                            "No adapter created for model %s: anthropic=%s openai=%s",
                            model_name, exc, exc2,
                        )

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
