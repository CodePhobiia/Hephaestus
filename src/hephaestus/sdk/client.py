"""
Hephaestus Python SDK — High-Level Client.

The simplest possible interface to the Hephaestus invention engine.

Basic usage (3 lines)::

    from hephaestus import Hephaestus
    heph = Hephaestus.from_env()
    result = await heph.invent("I need a load balancer for traffic spikes")
    print(result.top_invention.invention_name)

Context manager::

    async with Hephaestus.from_env() as heph:
        result = await heph.invent("my problem")

Streaming::

    async for update in heph.invent_stream("my problem"):
        print(update.stage, update.message)

Raw DeepForge (no genesis pipeline)::

    forge_result = await heph.deepforge("raw prompt here")
    print(forge_result.output)

Lens introspection::

    lenses = heph.list_lenses()
    lens = heph.get_lens("biology_immune")
    print(lens.axioms)

Cost estimation::

    estimate = heph.estimate_cost("my problem description")
    print(f"Estimated: ${estimate['low']:.2f} — ${estimate['high']:.2f}")
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from hephaestus.core.genesis import (
    Genesis,
    GenesisConfig,
    InventionReport,
    PipelineUpdate,
)

__all__ = ["Hephaestus"]


class HephaestusError(Exception):
    """Base exception for Hephaestus SDK errors."""


class ConfigurationError(HephaestusError):
    """Raised when the client is misconfigured (missing API keys, etc.)."""


class Hephaestus:
    """
    High-level Python SDK client for the Hephaestus invention engine.

    Wraps the Genesis pipeline and DeepForge harness behind a clean,
    simple interface.

    Parameters
    ----------
    anthropic_key:
        Anthropic API key. If not provided, falls back to ``ANTHROPIC_API_KEY``
        environment variable.
    openai_key:
        OpenAI API key. If not provided, falls back to ``OPENAI_API_KEY``
        environment variable.
    model:
        Model selection strategy: ``"both"`` (default), ``"opus"``, or ``"gpt5"``.
    depth:
        Anti-training pressure depth (1–10, default 3). Higher = more novel,
        more expensive.
    candidates:
        Number of cross-domain search candidates (default 8).
    domain:
        Optional domain hint for the genesis pipeline.
    num_translations:
        Number of top candidates to translate (default 3).
    run_prior_art:
        Whether to run the prior art search in Stage 5 (default True).

    Raises
    ------
    ConfigurationError
        If no API keys are available for the selected model.
    """

    def __init__(
        self,
        anthropic_key: str | None = None,
        openai_key: str | None = None,
        *,
        model: str = "both",
        depth: int = 3,
        candidates: int = 8,
        domain: str | None = None,
        num_translations: int = 3,
        run_prior_art: bool = True,
    ) -> None:
        self._anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        self._openai_key = openai_key or os.environ.get("OPENAI_API_KEY")
        self._model = model.lower()
        self._depth = depth
        self._candidates = candidates
        self._domain = domain
        self._num_translations = num_translations
        self._run_prior_art = run_prior_art

        # Validate keys early
        self._validate_keys()

        # Genesis is built lazily on first use
        self._genesis: Genesis | None = None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        *,
        model: str = "both",
        depth: int = 3,
        candidates: int = 8,
    ) -> "Hephaestus":
        """
        Create a Hephaestus client using API keys from environment variables.

        Reads ``ANTHROPIC_API_KEY`` and ``OPENAI_API_KEY`` from the environment.

        Parameters
        ----------
        model:
            Model selection: ``"both"`` | ``"opus"`` | ``"gpt5"``.
        depth:
            Anti-training pressure depth (default 3).
        candidates:
            Number of search candidates (default 8).

        Returns
        -------
        Hephaestus
            Configured client ready to use.

        Example
        -------
        ::

            async with Hephaestus.from_env() as heph:
                result = await heph.invent("my problem")
        """
        return cls(
            anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
            openai_key=os.environ.get("OPENAI_API_KEY"),
            model=model,
            depth=depth,
            candidates=candidates,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "Hephaestus":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """
        Release any held resources.

        Called automatically when used as an async context manager.
        """
        # No persistent connections to close currently.
        self._genesis = None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def invent(self, problem: str) -> InventionReport:
        """
        Run the full Hephaestus invention pipeline on *problem*.

        Executes all 5 stages (Decompose → Search → Score → Translate → Verify)
        and returns the complete invention report.

        Parameters
        ----------
        problem:
            Natural language problem description.

        Returns
        -------
        InventionReport
            Complete results with the top invention, alternatives, cost, and trace.

        Raises
        ------
        HephaestusError
            If the pipeline fails.

        Example
        -------
        ::

            result = await heph.invent(
                "I need a reputation system for an anonymous marketplace"
            )
            print(result.top_invention.invention_name)
            print(f"From: {result.top_invention.source_domain}")
            print(f"Novelty: {result.top_invention.novelty_score:.2f}")
            print(f"Cost: ${result.total_cost_usd:.2f}")
        """
        genesis = self._get_genesis()
        try:
            return await genesis.invent(problem)
        except Exception as exc:
            raise HephaestusError(f"Invention pipeline failed: {exc}") from exc

    async def invent_stream(
        self, problem: str
    ) -> AsyncIterator[PipelineUpdate]:
        """
        Run the invention pipeline with streaming progress updates.

        Yields :class:`~hephaestus.core.genesis.PipelineUpdate` objects as each
        stage completes. The final update has ``stage=PipelineStage.COMPLETE``
        and ``data=InventionReport``.

        Parameters
        ----------
        problem:
            Natural language problem description.

        Yields
        ------
        PipelineUpdate
            Progress updates from each pipeline stage.

        Example
        -------
        ::

            async for update in heph.invent_stream("my problem"):
                print(f"[{update.stage.name}] {update.message}")
                if update.stage.name == "COMPLETE":
                    report = update.data
                    print(report.top_invention.invention_name)
        """
        genesis = self._get_genesis()
        async for update in genesis.invent_stream(problem):
            yield update

    async def deepforge(
        self,
        prompt: str,
        *,
        depth: int | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> Any:
        """
        Run DeepForge directly on a raw prompt — no Genesis pipeline.

        Uses the full harness stack (cognitive interference + convergence
        pruning + anti-training pressure) on a raw prompt.

        Parameters
        ----------
        prompt:
            The raw prompt to forge.
        depth:
            Pressure depth override (defaults to instance depth).
        model:
            Model override: ``"opus"`` | ``"gpt5"`` | ``"both"`` (uses primary).
        system:
            Optional system prompt override.

        Returns
        -------
        ForgeResult
            The forge result with ``output``, ``trace``, and ``success``.

        Example
        -------
        ::

            result = await heph.deepforge(
                "Design a trust system for ephemeral anonymous actors",
                depth=5,
            )
            print(result.output)
            print(f"Cost: ${result.trace.total_cost_usd:.4f}")
        """
        from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig

        effective_depth = depth if depth is not None else self._depth
        effective_model = (model or self._model).lower()

        adapter = self._build_adapter(effective_model)
        harness = DeepForgeHarness(
            adapter=adapter,
            config=HarnessConfig(
                use_interference=True,
                use_pruner=True,
                use_pressure=True,
                max_pressure_rounds=effective_depth,
                max_tokens=4096,
                temperature=0.9,
            ),
        )

        try:
            return await harness.forge(prompt, system=system)
        except Exception as exc:
            raise HephaestusError(f"DeepForge failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Lens introspection
    # ------------------------------------------------------------------

    def list_lenses(self) -> list[dict[str, Any]]:
        """
        List all available cognitive lenses in the library.

        Returns
        -------
        list[dict]
            List of lens metadata dicts, each with keys:
            ``lens_id``, ``name``, ``domain``, ``subdomain``,
            ``axiom_count``, ``pattern_count``, ``maps_to``, ``tags``.

        Example
        -------
        ::

            lenses = heph.list_lenses()
            for lens in lenses:
                print(f"{lens['lens_id']}: {lens['name']} ({lens['domain']})")
        """
        from hephaestus.lenses.loader import LensLoader

        loader = LensLoader()
        try:
            return loader.list_available(skip_errors=True)
        except Exception as exc:
            raise HephaestusError(f"Failed to list lenses: {exc}") from exc

    def get_lens(self, lens_id: str) -> Any:
        """
        Get the full details of a specific lens by its ID.

        Parameters
        ----------
        lens_id:
            Lens identifier (e.g., ``"biology_immune"``, ``"physics_thermodynamics"``).

        Returns
        -------
        Lens
            Full lens object with axioms, structural patterns, and injection prompt.

        Raises
        ------
        HephaestusError
            If the lens is not found.

        Example
        -------
        ::

            lens = heph.get_lens("biology_immune")
            print(lens.name)
            for axiom in lens.axioms:
                print(f"  • {axiom}")
        """
        from hephaestus.lenses.loader import LensLoader

        loader = LensLoader()
        try:
            return loader.load_one(lens_id)
        except FileNotFoundError:
            raise HephaestusError(
                f"Lens {lens_id!r} not found. "
                f"Call list_lenses() to see available lenses."
            )
        except Exception as exc:
            raise HephaestusError(f"Failed to load lens {lens_id!r}: {exc}") from exc

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cost(self, problem: str) -> dict[str, float]:
        """
        Estimate the API cost before running the invention pipeline.

        Returns rough USD estimates based on typical token usage for the
        configured models. Actual cost may vary.

        Parameters
        ----------
        problem:
            The problem description (length affects decomposition cost).

        Returns
        -------
        dict[str, float]
            Keys: ``low``, ``mid``, ``high``, ``breakdown``.
            All values in USD.

        Example
        -------
        ::

            estimate = heph.estimate_cost("complex routing problem")
            print(f"Estimated cost: ${estimate['mid']:.2f}")
            print(f"Range: ${estimate['low']:.2f} — ${estimate['high']:.2f}")
        """
        # Cost model from PRD §8
        # Base estimates per stage (USD)
        stage_estimates = {
            "decompose": (0.10, 0.15, 0.22),   # low, mid, high
            "search": (0.08, 0.12, 0.18),
            "score": (0.03, 0.05, 0.08),
            "translate": (0.30, 0.45, 0.65),
            "verify": (0.10, 0.15, 0.22),
            "convergence_kills": (0.08, 0.15, 0.25),
        }

        # Scale by depth (each pressure round adds ~30% cost to translate)
        depth_multiplier = 1.0 + (self._depth - 3) * 0.15

        # Scale by candidates (search scales sub-linearly)
        candidate_multiplier = (self._candidates / 8) ** 0.7

        totals = {"low": 0.0, "mid": 0.0, "high": 0.0}
        breakdown: dict[str, float] = {}

        for stage, (low, mid, high) in stage_estimates.items():
            if stage == "translate":
                low *= depth_multiplier
                mid *= depth_multiplier
                high *= depth_multiplier
            if stage == "search":
                low *= candidate_multiplier
                mid *= candidate_multiplier
                high *= candidate_multiplier

            totals["low"] += low
            totals["mid"] += mid
            totals["high"] += high
            breakdown[stage] = round(mid, 4)

        # Prompt length adjustment (longer problems → more decomp tokens)
        length_factor = min(2.0, 1.0 + len(problem) / 2000)
        for key in totals:
            totals[key] *= length_factor

        return {
            "low": round(totals["low"], 4),
            "mid": round(totals["mid"], 4),
            "high": round(totals["high"], 4),
            "breakdown": breakdown,
            "depth": self._depth,
            "candidates": self._candidates,
            "model": self._model,
            "note": "Estimates based on typical token usage. Actual cost may vary ±50%.",
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The configured model strategy."""
        return self._model

    @property
    def depth(self) -> int:
        """The configured pressure depth."""
        return self._depth

    @property
    def candidates(self) -> int:
        """The configured number of search candidates."""
        return self._candidates

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _validate_keys(self) -> None:
        """Validate that required API keys are present."""
        if self._model in ("opus", "both") and not self._anthropic_key:
            raise ConfigurationError(
                "Anthropic API key required for model='opus' or model='both'. "
                "Pass anthropic_key=... or set ANTHROPIC_API_KEY."
            )
        if self._model in ("gpt5", "both") and not self._openai_key:
            raise ConfigurationError(
                "OpenAI API key required for model='gpt5' or model='both'. "
                "Pass openai_key=... or set OPENAI_API_KEY."
            )

    def _get_genesis(self) -> Genesis:
        """Get or build the Genesis pipeline (lazy init)."""
        if self._genesis is None:
            self._genesis = self._build_genesis()
        return self._genesis

    def _build_genesis(self) -> Genesis:
        """Build the Genesis pipeline from current config."""
        from hephaestus.core.cross_model import get_model_preset

        preset_key = {"opus": "opus", "gpt5": "gpt"}.get(self._model, "both")
        models = get_model_preset(preset_key)

        config = GenesisConfig(
            anthropic_api_key=self._anthropic_key,
            openai_api_key=self._openai_key,
            decompose_model=models["decompose"],
            search_model=models["search"],
            score_model=models["score"],
            translate_model=models["translate"],
            attack_model=models["attack"],
            defend_model=models["defend"],
            num_candidates=self._candidates,
            num_translations=self._num_translations,
            run_prior_art=self._run_prior_art,
        )

        return Genesis(config)

    def _build_adapter(self, model: str) -> Any:
        """Build the appropriate adapter for raw deepforge."""
        from hephaestus.core.cross_model import get_model_preset

        preset_key = {"opus": "opus", "gpt5": "gpt"}.get(model, "both")
        models = get_model_preset(preset_key)

        if model in ("opus", "both"):
            from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
            return AnthropicAdapter(model=models["decompose"], api_key=self._anthropic_key)
        else:
            from hephaestus.deepforge.adapters.openai import OpenAIAdapter
            return OpenAIAdapter(model=models["decompose"], api_key=self._openai_key)

    def __repr__(self) -> str:
        return (
            f"Hephaestus(model={self._model!r}, depth={self._depth}, "
            f"candidates={self._candidates})"
        )
