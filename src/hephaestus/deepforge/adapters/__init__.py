"""
DeepForge model adapters.

Provides uniform adapter classes for each supported LLM provider.
All adapters inherit from :class:`~hephaestus.deepforge.adapters.base.BaseAdapter`
and implement the same async interface.
"""

from hephaestus.deepforge.adapters.anthropic import ANTHROPIC_MODELS, AnthropicAdapter
from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.adapters.codex_cli import CODEX_CLI_MODELS, CodexCliAdapter
from hephaestus.deepforge.adapters.codex_oauth import CODEX_OAUTH_MODELS, CodexOAuthAdapter
from hephaestus.deepforge.adapters.openai import OPENAI_MODELS, OpenAIAdapter
from hephaestus.deepforge.adapters.openrouter import OPENROUTER_MODELS, OpenRouterAdapter

__all__ = [
    # Base
    "BaseAdapter",
    "GenerationResult",
    "ModelCapability",
    "ModelConfig",
    "StreamChunk",
    # Providers
    "AnthropicAdapter",
    "ANTHROPIC_MODELS",
    "OpenAIAdapter",
    "OPENAI_MODELS",
    "OpenRouterAdapter",
    "OPENROUTER_MODELS",
    "CodexCliAdapter",
    "CODEX_CLI_MODELS",
    "CodexOAuthAdapter",
    "CODEX_OAUTH_MODELS",
]
