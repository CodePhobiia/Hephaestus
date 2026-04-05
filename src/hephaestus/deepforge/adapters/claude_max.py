"""
Claude Max adapter for DeepForge.

Routes API calls through the Anthropic Messages API using an OAT (OAuth
Access Token) from a Claude Max/Pro subscription.  Uses the same auth
method as OpenClaw — no separate API key needed.

Requires:
- An OAT token (``sk-ant-oat01-...``) in the OpenClaw auth-profiles store
- The mandatory Claude Code identity system prompt prefix
- Claude Code beta headers for OAT validation
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.exceptions import (
    AdapterError,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    ModelNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# The system prompt prefix required for OAT token validation
CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."

# Beta headers required for OAT auth
OAT_BETA_HEADERS = "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14"
CLAUDE_CLI_VERSION = "2.1.75"
_RETRY_DELAYS = [1.0, 2.0, 4.0, 8.0]

CLAUDE_MAX_MODELS: dict[str, ModelConfig] = {
    "claude-sonnet-4-6": ModelConfig(
        name="claude-sonnet-4-6",
        provider="claude-max",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
    "claude-opus-4-6": ModelConfig(
        name="claude-opus-4-6",
        provider="claude-max",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
    "claude-haiku-4-5": ModelConfig(
        name="claude-haiku-4-5",
        provider="claude-max",
        context_window=200_000,
        max_output_tokens=8192,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
        },
    ),
}


@dataclass
class ClaudeToolCall:
    """One native Anthropic tool call emitted by the model."""

    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaudeToolGenerationResult:
    """Structured result for Claude tool-enabled generations."""

    text: str
    content_blocks: list[dict[str, Any]]
    tool_calls: list[ClaudeToolCall]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    stop_reason: str
    raw: Any = None


def _load_oat_token() -> str:
    """Load the OAT token from OpenClaw's auth-profiles store."""
    store_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
    if not store_path.exists():
        raise AuthenticationError(
            f"Auth profiles not found at {store_path}. "
            "Run 'openclaw models auth setup-token' first."
        )
    store = json.loads(store_path.read_text())
    profile = store.get("profiles", {}).get("anthropic:default")
    if not profile or not profile.get("token"):
        raise AuthenticationError(
            "No Anthropic token in auth-profiles. Run 'openclaw models auth setup-token' first."
        )
    token = profile["token"]
    if not token.startswith("sk-ant-oat"):
        raise AuthenticationError(
            f"Token doesn't look like an OAT token (expected sk-ant-oat prefix): {token[:4]}**REDACTED**..."
        )
    return token


class ClaudeMaxAdapter(BaseAdapter):
    """
    Adapter that calls Anthropic's Messages API using a Claude Max OAT token.

    This is the same auth path OpenClaw uses — persistent HTTP connection,
    proper SDK, no CLI shelling.  Zero API cost (subscription-based).
    """

    def __init__(
        self,
        model: str | ModelConfig = "claude-sonnet-4-6",
        *,
        oat_token: str | None = None,
        timeout: float = 600.0,
        max_retries: int = 2,
    ) -> None:
        if isinstance(model, str):
            config = CLAUDE_MAX_MODELS.get(model)
            if config is None:
                config = ModelConfig(
                    name=model,
                    provider="claude-max",
                    context_window=200_000,
                    max_output_tokens=16_000,
                    input_cost_per_million=0.0,
                    output_cost_per_million=0.0,
                    capabilities={
                        ModelCapability.PREFILL,
                        ModelCapability.STREAMING,
                        ModelCapability.FUNCTION_CALLING,
                    },
                )
        else:
            config = model

        super().__init__(config, api_key=None, timeout=timeout, max_retries=max_retries)

        self._token = oat_token or _load_oat_token()
        self._client = anthropic.AsyncAnthropic(
            api_key=None,
            auth_token=self._token,
            timeout=timeout,
            default_headers={
                "anthropic-beta": OAT_BETA_HEADERS,
                "user-agent": f"claude-cli/{CLAUDE_CLI_VERSION}",
                "x-app": "cli",
                "anthropic-dangerous-direct-browser-access": "true",
            },
        )
        logger.info("Claude Max adapter: model=%s (OAT auth)", self.model_name)

    def _build_system(self, system: str | None) -> list[dict[str, str]]:
        """Build system parameter with mandatory Claude Code identity prefix."""
        blocks = [{"type": "text", "text": CLAUDE_CODE_IDENTITY}]
        if system:
            blocks.append({"type": "text", "text": system})
        return blocks

    def _build_messages(
        self,
        prompt: str,
        prefill: str | None,
    ) -> list[dict[str, Any]]:
        # OAT tokens don't support assistant prefill — inject it into user prompt instead
        if prefill:
            prompt = (
                f"{prompt}\n\n"
                f"[IMPORTANT: Begin your response EXACTLY with the following text, "
                f"then continue seamlessly from where it leaves off. "
                f"Do NOT restate or restart.]\n\n{prefill}"
            )
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        return messages

    @staticmethod
    def _translate_error(exc: Exception) -> AdapterError:
        """Convert Anthropic SDK exceptions into DeepForge exceptions."""
        if isinstance(exc, anthropic.RateLimitError):
            return RateLimitError(str(exc))
        if isinstance(exc, anthropic.AuthenticationError):
            return AuthenticationError(str(exc))
        if isinstance(exc, anthropic.NotFoundError):
            return ModelNotFoundError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return APIConnectionError(str(exc))
        if isinstance(exc, anthropic.APITimeoutError):
            return APITimeoutError(str(exc))
        if isinstance(exc, anthropic.APIError):
            return AdapterError(f"Anthropic API error: {exc}")
        return AdapterError(f"Unexpected error: {exc}")

    async def _with_retry(self, coro_factory: Any, attempt: int = 0) -> Any:
        """Retry transient Anthropic failures with exponential backoff."""
        try:
            return await coro_factory()
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        ) as exc:
            if attempt >= self._max_retries:
                raise self._translate_error(exc) from exc
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            self._logger.warning(
                "Transient Claude Max error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                self._max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            return await self._with_retry(coro_factory, attempt + 1)
        except anthropic.APIError as exc:
            raise self._translate_error(exc) from exc

    @staticmethod
    def _content_block_to_dict(block: Any) -> dict[str, Any] | None:
        """Normalise Anthropic SDK content blocks into plain dicts."""
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "text":
                return {"type": "text", "text": str(block.get("text", ""))}
            if block_type == "tool_use":
                return {
                    "type": "tool_use",
                    "id": str(block.get("id", "")),
                    "name": str(block.get("name", "")),
                    "input": dict(block.get("input", {}) or {}),
                }
            return None

        block_type = getattr(block, "type", None)
        if block_type == "text":
            return {"type": "text", "text": getattr(block, "text", "")}
        if block_type == "tool_use":
            return {
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": dict(getattr(block, "input", {}) or {}),
            }
        return None

    def _extract_content_blocks(self, content: Any) -> list[dict[str, Any]]:
        """Convert Anthropic content blocks to plain dicts."""
        blocks: list[dict[str, Any]] = []
        for block in content or []:
            normalized = self._content_block_to_dict(block)
            if normalized is not None:
                blocks.append(normalized)
        return blocks

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> ClaudeToolGenerationResult:
        """
        Generate a response using Anthropic native tool_use/tool_result blocks.

        Parameters mirror :meth:`generate`, except *messages* is a fully formed
        Anthropic conversation history and *tools* is the native tool schema.

        Supports extended thinking via ``thinking`` kwarg::

            await adapter.generate_with_tools(
                messages, tools=tools,
                thinking={"type": "enabled", "budget_tokens": 16000},
            )

        When thinking is enabled, temperature is forced to 1.0 per Anthropic
        API requirements.
        """
        self._reset_cancel()

        t_start = time.monotonic()

        # Extended thinking requires temperature=1 and higher max_tokens
        thinking = kwargs.pop("thinking", None)
        create_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "system": self._build_system(system),
            "messages": messages,
            "tools": tools or [],
            "stream": False,
            **kwargs,
        }

        if thinking and thinking.get("type") == "enabled":
            budget = thinking.get("budget_tokens", 16_000)
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
            # Anthropic requires temperature=1 for thinking
            create_kwargs["temperature"] = 1.0
            # max_tokens must be >= budget + output
            create_kwargs["max_tokens"] = max(max_tokens, budget + 4096)
            self._logger.info(
                "Extended thinking enabled | budget=%d tokens", budget
            )
        else:
            create_kwargs["temperature"] = temperature
            create_kwargs["max_tokens"] = max_tokens

        response = await self._with_retry(
            lambda: self._client.messages.create(**create_kwargs)
        )
        elapsed = time.monotonic() - t_start

        content_blocks = self._extract_content_blocks(response.content)
        text = "".join(block["text"] for block in content_blocks if block.get("type") == "text")
        tool_calls = [
            ClaudeToolCall(
                id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                input=dict(block.get("input", {}) or {}),
            )
            for block in content_blocks
            if block.get("type") == "tool_use"
        ]

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        self._logger.debug(
            "Claude Max generate_with_tools: %.2fs | in=%d out=%d tools=%d",
            elapsed,
            in_tok,
            out_tok,
            len(tool_calls),
        )

        return ClaudeToolGenerationResult(
            text=text,
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            model=self.model_name,
            stop_reason=response.stop_reason or "stop",
            raw=response,
        )

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefill: str | None = None,
        stream: bool = False,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> GenerationResult:
        self._reset_cancel()

        t_start = time.monotonic()
        response = await self._with_retry(
            lambda: self._client.messages.create(
                model=self.model_name,
                system=self._build_system(system),
                messages=self._build_messages(prompt, prefill),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
        )
        elapsed = time.monotonic() - t_start

        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        text = "".join(text_parts)

        if prefill and text.startswith(prefill):
            text = text[len(prefill) :]

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens

        self._logger.debug("Claude Max generate: %.2fs | in=%d out=%d", elapsed, in_tok, out_tok)

        return GenerationResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            model=self.model_name,
            stop_reason=response.stop_reason or "stop",
        )

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        prefill: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        self._reset_cancel()
        accumulated = prefill or ""

        async with self._client.messages.stream(
            model=self.model_name,
            system=self._build_system(system),
            messages=self._build_messages(prompt, prefill),
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                if self.is_cancelled:
                    break
                accumulated += text
                yield StreamChunk(delta=text, accumulated=accumulated)

        msg = await stream.get_final_message()
        yield StreamChunk(
            delta="",
            accumulated=accumulated,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            is_final=True,
            stop_reason=msg.stop_reason or "stop",
        )
