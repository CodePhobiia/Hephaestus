"""
DeepForge Harness — Main Orchestrator.

The ``DeepForgeHarness`` combines all three deepforge mechanisms into a single
configurable pipeline:

1. **Cognitive Interference** — injects a foreign-domain lens as assistant prefill
2. **Convergence Pruning** — monitors the stream and kills predictable outputs
3. **Anti-Training Pressure** — adversarial mirror + multi-round stacking

Each mechanism can be independently enabled/disabled via :class:`HarnessConfig`.
The harness drives retry loops, accumulates the full trace, tracks costs, and
returns a :class:`ForgeResult` with the final novel output.

Usage example::

    from hephaestus.deepforge.harness import DeepForgeHarness, HarnessConfig
    from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter
    from hephaestus.deepforge.interference import Lens

    adapter = AnthropicAdapter("claude-sonnet-4-5")
    lens = Lens(
        name="Immune System",
        domain="biology",
        axioms=["Trust is earned through molecular handshake, not declaration."],
    )
    harness = DeepForgeHarness(adapter, HarnessConfig(lenses=[lens]))
    result = await harness.forge("How do I design a trustless reputation system?")
    print(result.output)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from hephaestus.deepforge.adapters.base import BaseAdapter, GenerationResult
from hephaestus.deepforge.exceptions import (
    ConvergenceDetected,
    GenerationKilled,
    HarnessError,
)
from hephaestus.deepforge.interference import (
    CognitiveInterferenceEngine,
    InjectionResult,
    InjectionStrategy,
    Lens,
)
from hephaestus.deepforge.pressure import AntiTrainingPressure, PressureTrace
from hephaestus.deepforge.pruner import ConvergencePattern, ConvergencePruner, PrunerSession
from hephaestus.deepforge.retry import RetryConfig, with_retry, with_timeout

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class HarnessConfig:
    """
    Configuration for a :class:`DeepForgeHarness` run.

    Attributes
    ----------
    lenses:
        List of :class:`Lens` objects for Cognitive Interference.  An empty
        list disables interference.
    use_interference:
        Enable Cognitive Interference Engine (default ``True``).
    use_pruner:
        Enable Convergence Pruner (default ``True``).
    use_pressure:
        Enable Anti-Training Pressure / Adversarial Mirror (default ``True``).
    injection_strategy:
        Axiom injection strategy for the Interference Engine.
    max_pressure_rounds:
        Maximum rounds for the Anti-Training Pressure engine.
    similarity_threshold:
        Cosine similarity threshold for the Convergence Pruner.
    structural_distance_threshold:
        Minimum cosine distance for structural novelty in pressure rounds.
    max_pruner_retries:
        Maximum number of pruner kill/retry cycles per forge call.
    max_tokens:
        Maximum output tokens per generation call.
    temperature:
        Sampling temperature.
    convergence_patterns:
        Seed convergence patterns for the pruner.
    system_prompt:
        Base system instruction prepended to every generation call.
    """

    lenses: list[Lens] = field(default_factory=list)
    use_interference: bool = True
    use_pruner: bool = True
    use_pressure: bool = True
    injection_strategy: InjectionStrategy = InjectionStrategy.FULL
    max_pressure_rounds: int = 3
    similarity_threshold: float = 0.82
    structural_distance_threshold: float = 0.75
    max_pruner_retries: int = 5
    max_tokens: int = 4096
    temperature: float = 0.9
    convergence_patterns: list[ConvergencePattern] = field(default_factory=list)
    system_prompt: str | None = None
    retry_config: RetryConfig | None = None
    timeout_seconds: float = 120.0


# ---------------------------------------------------------------------------
# Trace and result types
# ---------------------------------------------------------------------------


@dataclass
class ForgeTrace:
    """
    Full execution trace of a single :meth:`DeepForgeHarness.forge` call.

    Attributes
    ----------
    prompt:
        The original prompt.
    attempts:
        Number of generation attempts made.
    interference_injections:
        List of :class:`InjectionResult` objects from the Interference Engine.
    pruner_kills:
        Number of times the pruner killed generation.
    pruner_session:
        The :class:`PrunerSession` state (blocked paths, etc.).
    pressure_trace:
        The :class:`PressureTrace` from the pressure engine (if used).
    total_cost_usd:
        Total estimated API cost in USD.
    total_input_tokens:
        Total input tokens consumed.
    total_output_tokens:
        Total output tokens generated.
    wall_time_seconds:
        Total elapsed wall-clock time.
    mechanisms_used:
        Which mechanisms were active.
    """

    prompt: str
    attempts: int = 0
    interference_injections: list[InjectionResult] = field(default_factory=list)
    pruner_kills: int = 0
    pruner_session: PrunerSession | None = None
    pressure_trace: PressureTrace | None = None
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    wall_time_seconds: float = 0.0
    mechanisms_used: list[str] = field(default_factory=list)

    def add_result(self, result: GenerationResult) -> None:
        """Accumulate token usage from a generation result."""
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_cost_usd += result.cost_usd


@dataclass
class ForgeResult:
    """
    The output of a :meth:`DeepForgeHarness.forge` call.

    Attributes
    ----------
    output:
        The final generated text (the novel output).
    trace:
        Full :class:`ForgeTrace` for debugging and cost attribution.
    success:
        Whether the forge pipeline considers the output genuinely novel.
    stop_reason:
        Why the final generation stopped.
    """

    output: str
    trace: ForgeTrace
    success: bool = True
    stop_reason: str = "end_turn"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class DeepForgeHarness:
    """
    Main DeepForge orchestrator.

    Combines the Cognitive Interference Engine, Convergence Pruner, and
    Anti-Training Pressure into a single unified pipeline.

    Parameters
    ----------
    adapter:
        The model adapter to use for generation.
    config:
        :class:`HarnessConfig` controlling which mechanisms are active and
        how they are configured.
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        config: HarnessConfig | None = None,
    ) -> None:
        self._adapter = adapter
        self._config = config or HarnessConfig()

        # Lazily initialised engines
        self._interference_engine: CognitiveInterferenceEngine | None = None
        self._pruner: ConvergencePruner | None = None
        self._pressure: AntiTrainingPressure | None = None

        self._setup_engines()

        logger.info(
            "DeepForgeHarness initialised | model=%s interference=%s pruner=%s pressure=%s",
            adapter.model_name,
            self._config.use_interference,
            self._config.use_pruner,
            self._config.use_pressure,
        )

    # ------------------------------------------------------------------
    # Engine setup
    # ------------------------------------------------------------------

    def _setup_engines(self) -> None:
        """Initialise the sub-engines based on :attr:`_config`."""
        cfg = self._config

        if cfg.use_interference and cfg.lenses:
            self._interference_engine = CognitiveInterferenceEngine(
                lenses=cfg.lenses,
                strategy=cfg.injection_strategy,
            )
            logger.debug(
                "Interference engine ready | lenses=%d strategy=%s",
                len(cfg.lenses),
                cfg.injection_strategy.name,
            )

        if cfg.use_pruner:
            self._pruner = ConvergencePruner(
                patterns=cfg.convergence_patterns or [],
                similarity_threshold=cfg.similarity_threshold,
            )
            logger.debug(
                "Convergence pruner ready | patterns=%d threshold=%.2f",
                len(cfg.convergence_patterns),
                cfg.similarity_threshold,
            )

        if cfg.use_pressure:
            self._pressure = AntiTrainingPressure(
                adapter=self._adapter,
                max_rounds=cfg.max_pressure_rounds,
                structural_distance_threshold=cfg.structural_distance_threshold,
            )
            logger.debug(
                "Anti-training pressure ready | max_rounds=%d",
                cfg.max_pressure_rounds,
            )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def forge(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> ForgeResult:
        """
        Run the full DeepForge pipeline on *prompt*.

        Executes mechanisms in this order:

        1. If interference is enabled: build prefill injection from the lens.
        2. If pruner is enabled: wrap generation in stream monitoring.
        3. Retry on ``ConvergenceDetected`` (up to ``max_pruner_retries``).
        4. If pressure is enabled: run the adversarial mirror pipeline on top.

        Parameters
        ----------
        prompt:
            The problem to forge a novel solution for.
        system:
            Override the base system prompt for this call.
        max_tokens:
            Override ``config.max_tokens`` for this call.
        temperature:
            Override ``config.temperature`` for this call.
        extra_context:
            Arbitrary extra data stored in the trace (not sent to the model).

        Returns
        -------
        ForgeResult
        """
        t_start = time.monotonic()
        cfg = self._config

        effective_max_tokens = max_tokens or cfg.max_tokens
        effective_temperature = temperature if temperature is not None else cfg.temperature
        effective_system = system or cfg.system_prompt

        trace = ForgeTrace(prompt=prompt)
        active_mechanisms: list[str] = []

        # ---- Step 1: Anti-Training Pressure (full pipeline mode) ----
        if self._pressure is not None:
            active_mechanisms.append("anti_training_pressure")

            # Collect pre-blocked paths from pruner if available
            extra_blocked: list[str] = []
            if self._pruner is not None:
                extra_blocked = list(self._pruner.session.blocked_paths)

            # Build the system prompt including interference injection if active
            pressure_system = effective_system
            if self._interference_engine is not None:
                active_mechanisms.append("cognitive_interference")
                injection = self._interference_engine.build_injection(attempt=0)
                trace.interference_injections.append(injection)
                pressure_system = self._build_interference_system(
                    base_system=effective_system,
                    injection_text=injection.prefill,
                )

            pressure_trace = await self._pressure.apply(
                prompt,
                system=pressure_system,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                extra_blocked_paths=extra_blocked,
            )

            trace.pressure_trace = pressure_trace
            trace.total_cost_usd += pressure_trace.total_cost_usd
            trace.total_input_tokens += pressure_trace.total_input_tokens
            trace.total_output_tokens += pressure_trace.total_output_tokens
            trace.attempts += pressure_trace.rounds_completed
            trace.mechanisms_used = active_mechanisms
            trace.wall_time_seconds = time.monotonic() - t_start

            if self._pruner:
                trace.pruner_session = self._pruner.session

            final_output = pressure_trace.final_output
            if not final_output and pressure_trace.blocked_paths:
                # Fallback: use the last blocked path's text (best we have)
                final_output = pressure_trace.blocked_paths[-1].text

            if not final_output:
                raise HarnessError("Pressure pipeline produced no output")

            return ForgeResult(
                output=final_output,
                trace=trace,
                success=pressure_trace.success,
                stop_reason="pressure_complete",
            )

        # ---- Step 2: Pruner-only mode (no pressure) ----
        if self._pruner is not None:
            active_mechanisms.append("convergence_pruner")

        if self._interference_engine is not None:
            active_mechanisms.append("cognitive_interference")

        result = await self._forge_with_pruner(
            prompt=prompt,
            system=effective_system,
            max_tokens=effective_max_tokens,
            temperature=effective_temperature,
            trace=trace,
        )

        trace.mechanisms_used = active_mechanisms
        trace.wall_time_seconds = time.monotonic() - t_start

        if self._pruner:
            trace.pruner_session = self._pruner.session

        return result

    # ------------------------------------------------------------------
    # Internal: pruner-wrapped generation loop
    # ------------------------------------------------------------------

    async def _forge_with_pruner(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
        trace: ForgeTrace,
    ) -> ForgeResult:
        """
        Run generation with convergence pruner monitoring and retry loop.

        If the pruner kills a generation, rotate the interference lens and
        retry up to ``max_pruner_retries`` times.
        """
        cfg = self._config
        last_result: GenerationResult | None = None
        last_text = ""

        for attempt in range(cfg.max_pruner_retries + 1):
            trace.attempts = attempt + 1

            # Build prefill from interference engine
            prefill: str | None = None
            if self._interference_engine is not None:
                injection = self._interference_engine.build_injection(attempt=attempt)
                trace.interference_injections.append(injection)
                prefill = injection.prefill
                if attempt > 0:
                    self._interference_engine.rotate_lens()

            try:
                if self._pruner is not None:
                    # Streaming path — pruner monitors in real time
                    async def _pruner_call(prefill: str | None = prefill) -> Any:
                        stream = self._adapter.generate_stream(
                            prompt,
                            system=system,
                            prefill=prefill,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                        return await self._pruner.monitor_stream(  # type: ignore[union-attr]
                            stream,
                            adapter=self._adapter,
                        )

                    if cfg.retry_config is not None:
                        prune_result = await with_retry(_pruner_call, cfg.retry_config)
                    elif cfg.timeout_seconds != 120.0:
                        prune_result = await with_timeout(_pruner_call(), cfg.timeout_seconds)
                    else:
                        prune_result = await _pruner_call()

                    last_text = prune_result.text
                    trace.total_input_tokens += prune_result.input_tokens
                    trace.total_output_tokens += prune_result.output_tokens
                    trace.total_cost_usd += prune_result.cost_usd

                else:
                    # Non-streaming path
                    async def _generate_call(prefill: str | None = prefill) -> GenerationResult:
                        coro = self._adapter.generate(
                            prompt,
                            system=system,
                            prefill=prefill,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                        if cfg.timeout_seconds != 120.0 and cfg.retry_config is None:
                            return await with_timeout(coro, cfg.timeout_seconds)
                        return await coro

                    if cfg.retry_config is not None:
                        last_result = await with_retry(_generate_call, cfg.retry_config)
                    else:
                        last_result = await _generate_call()

                    trace.add_result(last_result)
                    last_text = last_result.text

                # Generation completed without convergence kill — success
                logger.info(
                    "Forge completed | attempt=%d/%d out_tokens=%d",
                    attempt + 1,
                    cfg.max_pruner_retries + 1,
                    trace.total_output_tokens,
                )
                return ForgeResult(
                    output=last_text,
                    trace=trace,
                    success=True,
                    stop_reason=last_result.stop_reason if last_result else "end_turn",
                )

            except ConvergenceDetected as exc:
                trace.pruner_kills += 1
                logger.info(
                    "Convergence killed on attempt %d/%d | sim=%.3f",
                    attempt + 1,
                    cfg.max_pruner_retries + 1,
                    exc.pattern_similarity,
                )
                last_text = exc.partial_output
                continue

            except GenerationKilled as exc:
                trace.pruner_kills += 1
                logger.warning("Generation killed on attempt %d: %s", attempt + 1, exc.reason)
                last_text = exc.partial_output
                continue

        # Exhausted retries
        logger.warning(
            "Exhausted all %d forge attempts. Returning last output.",
            cfg.max_pruner_retries + 1,
        )
        return ForgeResult(
            output=last_text,
            trace=trace,
            success=False,
            stop_reason="max_retries_exhausted",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_interference_system(
        base_system: str | None,
        injection_text: str,
    ) -> str:
        """
        Merge the base system prompt with the interference lens framing.

        The lens instruction is appended to the base system rather than
        prepended, so that the base instruction anchors the model first.
        """
        parts: list[str] = []
        if base_system:
            parts.append(base_system.strip())
            parts.append("")
        parts.append("--- COGNITIVE INTERFERENCE LENS ACTIVE ---")
        parts.append(injection_text)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Accessors for testing / inspection
    # ------------------------------------------------------------------

    @property
    def adapter(self) -> BaseAdapter:
        """The model adapter used by this harness."""
        return self._adapter

    @property
    def config(self) -> HarnessConfig:
        """The harness configuration."""
        return self._config

    @property
    def pruner(self) -> ConvergencePruner | None:
        """The active :class:`ConvergencePruner`, or ``None`` if disabled."""
        return self._pruner

    @property
    def interference_engine(self) -> CognitiveInterferenceEngine | None:
        """The active :class:`CognitiveInterferenceEngine`, or ``None`` if disabled."""
        return self._interference_engine

    @property
    def pressure_engine(self) -> AntiTrainingPressure | None:
        """The active :class:`AntiTrainingPressure`, or ``None`` if disabled."""
        return self._pressure
