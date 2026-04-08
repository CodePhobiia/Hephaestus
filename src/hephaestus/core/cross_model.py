"""
Cross-Model Defaults — stage-to-model mapping for multi-provider runs.

When ``use_claude_max`` is active, all stages use the same model.
Cross-model asymmetry activates when API keys for multiple providers
are configured.

The default staged mapping remains the classic cross-model split
(``Claude + GPT``) unless the caller explicitly selects Codex OAuth.
The CROSS_MODEL_DEFAULTS dict defines the default stage interface for
library, web, and ``from_env()`` callers.

Usage::

    from hephaestus.core.cross_model import CROSS_MODEL_DEFAULTS, apply_cross_model_defaults

    config = GenesisConfig()
    apply_cross_model_defaults(config)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hephaestus.core.genesis import GenesisConfig

# ---------------------------------------------------------------------------
# Model presets — the SINGLE source of truth for per-stage model assignments.
# Every CLI flag / SDK option / config default must reference these dicts
# rather than hardcoding model names.
# ---------------------------------------------------------------------------

# Named presets for CLI --model flag / SDK model= parameter
MODEL_PRESETS: dict[str, dict[str, str]] = {
    "opus": {
        "decompose": "claude-opus-4-5",
        "search": "claude-opus-4-5",
        "score": "claude-opus-4-5",
        "translate": "claude-opus-4-5",
        "attack": "claude-opus-4-5",
        "defend": "claude-opus-4-5",
    },
    "gpt": {
        "decompose": "gpt-4o",
        "search": "gpt-4o",
        "score": "gpt-4o-mini",
        "translate": "gpt-4o",
        "attack": "gpt-4o",
        "defend": "gpt-4o",
    },
    "codex": {
        "decompose": "gpt-5.4",
        "search": "gpt-5.4",
        "score": "gpt-5.4",
        "translate": "gpt-5.4",
        "attack": "gpt-5.4",
        "defend": "gpt-5.4",
    },
    "both": {
        "decompose": "claude-opus-4-5",
        "search": "gpt-4o",
        "score": "gpt-4o-mini",
        "translate": "claude-opus-4-5",
        "attack": "gpt-4o",
        "defend": "claude-opus-4-5",
    },
    "qwen": {
        "decompose": "qwen/qwen3.6-plus:free",
        "search": "qwen/qwen3.6-plus:free",
        "score": "qwen/qwen3.6-plus:free",
        "translate": "qwen/qwen3.6-plus:free",
        "attack": "qwen/qwen3.6-plus:free",
        "defend": "qwen/qwen3.6-plus:free",
    },
    "pantheon_qwen": {
        "athena": "qwen/qwen3.6-plus:free",
        "hermes": "qwen/qwen3.6-plus:free",
        "apollo": "qwen/qwen3.6-plus:free",
        "hephaestus": "qwen/qwen3.6-plus:free",
    },
}

# Default repo-wide stage mapping.
# Keep this as a copy of the standard cross-model preset so callers do not
# silently route into Codex OAuth unless they requested it explicitly.
CROSS_MODEL_DEFAULTS: dict[str, str] = dict(MODEL_PRESETS["both"])

# The default model for interactive / REPL mode
DEFAULT_MODEL: str = CROSS_MODEL_DEFAULTS["decompose"]


def get_model_preset(preset: str) -> dict[str, str]:
    """
    Return a copy of the named model preset.

    Parameters
    ----------
    preset:
        One of ``"opus"``, ``"gpt"``, ``"both"``.  Falls back to ``"both"``.
    """
    return dict(MODEL_PRESETS.get(preset, MODEL_PRESETS["both"]))


def apply_cross_model_defaults(config: GenesisConfig) -> GenesisConfig:
    """
    Apply cross-model defaults to a :class:`GenesisConfig`.

    Overwrites the per-stage model fields with values from
    :data:`CROSS_MODEL_DEFAULTS`.  Returns the same config object
    (mutated in place) for chaining convenience.

    Parameters
    ----------
    config:
        The Genesis config to update.

    Returns
    -------
    GenesisConfig
        The same object, with model fields updated.
    """
    config.decompose_model = CROSS_MODEL_DEFAULTS["decompose"]
    config.search_model = CROSS_MODEL_DEFAULTS["search"]
    config.score_model = CROSS_MODEL_DEFAULTS["score"]
    config.translate_model = CROSS_MODEL_DEFAULTS["translate"]
    config.attack_model = CROSS_MODEL_DEFAULTS["attack"]
    config.defend_model = CROSS_MODEL_DEFAULTS["defend"]
    return config
