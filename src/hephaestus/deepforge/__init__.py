"""
DeepForge — The LLM harness that forces frontier models off their default
reasoning paths.

Three mechanisms combine to ensure structurally novel generation:

1. **Cognitive Interference** — injects foreign-domain axioms mid-reasoning
2. **Convergence Pruning** — kills predictable outputs in real time
3. **Anti-Training Pressure** — adversarial mirror + multi-round stacking

Quick start::

    from hephaestus.deepforge import DeepForgeHarness, HarnessConfig
    from hephaestus.deepforge.adapters import AnthropicAdapter
    from hephaestus.deepforge.interference import Lens

    adapter = AnthropicAdapter("claude-sonnet-4-5")
    lens = Lens(
        name="Immune System",
        domain="biology",
        axioms=["Trust is earned, not declared."],
    )
    harness = DeepForgeHarness(adapter, HarnessConfig(lenses=[lens]))
    result = await harness.forge("How do I design a trustless reputation system?")
    print(result.output)
"""

from hephaestus.deepforge.exceptions import (
    AdapterError,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    ConfigurationError,
    ConvergenceDetected,
    DeepForgeError,
    GenerationKilled,
    HarnessError,
    InterferenceError,
    ModelNotFoundError,
    PressureError,
    PrunerError,
    RateLimitError,
)
from hephaestus.deepforge.harness import (
    DeepForgeHarness,
    ForgeResult,
    ForgeTrace,
    HarnessConfig,
)
from hephaestus.deepforge.interference import (
    CognitiveInterferenceEngine,
    InjectionResult,
    InjectionStrategy,
    Lens,
    make_lens,
)
from hephaestus.deepforge.pressure import (
    AntiTrainingPressure,
    BlockedPath,
    PressureTrace,
)
from hephaestus.deepforge.pruner import (
    ConvergencePattern,
    ConvergencePruner,
    PrunerSession,
    PruneResult,
)

__all__ = [
    # Harness
    "DeepForgeHarness",
    "HarnessConfig",
    "ForgeResult",
    "ForgeTrace",
    # Interference
    "CognitiveInterferenceEngine",
    "InjectionResult",
    "InjectionStrategy",
    "Lens",
    "make_lens",
    # Pruner
    "ConvergencePruner",
    "ConvergencePattern",
    "PrunerSession",
    "PruneResult",
    # Pressure
    "AntiTrainingPressure",
    "BlockedPath",
    "PressureTrace",
    # Exceptions
    "DeepForgeError",
    "AdapterError",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
    "APIConnectionError",
    "APITimeoutError",
    "GenerationKilled",
    "ConvergenceDetected",
    "InterferenceError",
    "PrunerError",
    "PressureError",
    "HarnessError",
    "ConfigurationError",
]
