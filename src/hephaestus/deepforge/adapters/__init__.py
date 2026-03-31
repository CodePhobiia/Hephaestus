"""
DeepForge model adapters.

Provides uniform adapter classes for each supported LLM provider.
All adapters inherit from :class:`~hephaestus.deepforge.adapters.base.BaseAdapter`
and implement the same async interface.
"""

from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.adapters.anthropic import AnthropicAdapter, ANTHROPIC_MODELS
from hephaestus.deepforge.adapters.openai import OpenAIAdapter, OPENAI_MODELS

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
]
