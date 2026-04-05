"""
Claude Agent SDK adapter for DeepForge.

Routes generation calls through the official Claude Agent SDK
(``claude-agent-sdk``), which uses the local Claude Code CLI under the hood.
This lets Hephaestus run entirely on a Claude Code / Claude Max / Claude Pro
subscription — zero API cost, fully legitimate.

Requires:
- ``claude-agent-sdk`` (``pip install claude-agent-sdk``)
- The ``claude`` CLI installed and authenticated (user's subscription)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

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
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model registry — subscription-backed, zero cost
# ---------------------------------------------------------------------------

AGENT_SDK_MODELS: dict[str, ModelConfig] = {
    "claude-sonnet-4-6": ModelConfig(
        name="claude-sonnet-4-6",
        provider="agent-sdk",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
        },
    ),
    "claude-opus-4-6": ModelConfig(
        name="claude-opus-4-6",
        provider="agent-sdk",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
        },
    ),
    "claude-haiku-4-5": ModelConfig(
        name="claude-haiku-4-5",
        provider="agent-sdk",
        context_window=200_000,
        max_output_tokens=8192,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
        },
    ),
}


def _check_sdk_available() -> bool:
    """Return True if the Claude Agent SDK and CLI are usable."""
    try:
        import shutil

        import claude_agent_sdk  # noqa: F401

        return shutil.which("claude") is not None
    except ImportError:
        return False


class AgentSDKAdapter(BaseAdapter):
    """
    Adapter that calls Claude via the official Claude Agent SDK.

    Uses the user's Claude Code subscription — no API key required.
    The SDK spawns the ``claude`` CLI under the hood and communicates
    via its protocol.  Each ``generate()`` / ``generate_stream()`` call
    maps to a ``query()`` invocation with full tool access and
    ``permission_mode="auto"``, making Claude a repo-aware agentic
    harness that can read files, search code, and reason over the
    codebase during invention.

    Notes:
    - No native temperature control (guided via system prompt phrasing).
    - No native assistant prefill (injected as user prompt instruction).
    - Token-level streaming is not available; messages arrive in blocks.
    - ``max_turns`` defaults to 1 (single-shot completion — fast, reliable).
      Pipeline stages provide full context in the prompt so Claude doesn't
      need to read files for most calls.  Pass ``max_turns=3`` via kwargs
      to ``generate()`` when a stage genuinely needs agentic tool access.
    """

    def __init__(
        self,
        model: str | ModelConfig = "claude-sonnet-4-6",
        *,
        timeout: float = 600.0,
        max_retries: int = 2,
        max_turns: int = 1,
        cwd: str | None = None,
    ) -> None:
        if isinstance(model, str):
            config = AGENT_SDK_MODELS.get(model)
            if config is None:
                config = ModelConfig(
                    name=model,
                    provider="agent-sdk",
                    context_window=200_000,
                    max_output_tokens=16_000,
                    input_cost_per_million=0.0,
                    output_cost_per_million=0.0,
                    capabilities={
                        ModelCapability.STREAMING,
                        ModelCapability.FUNCTION_CALLING,
                    },
                )
        else:
            config = model

        super().__init__(config, api_key=None, timeout=timeout, max_retries=max_retries)
        self._cwd = cwd or os.getcwd()
        self._max_turns = max_turns
        logger.info(
            "Agent SDK adapter: model=%s  max_turns=%d (Claude Code subscription)",
            self.model_name, max_turns,
        )

    @staticmethod
    def _build_prompt(prompt: str, prefill: str | None) -> str:
        """Build the full prompt, injecting prefill as an instruction if needed."""
        if prefill:
            return (
                f"{prompt}\n\n"
                f"[IMPORTANT: Begin your response EXACTLY with the following text, "
                f"then continue seamlessly from where it leaves off. "
                f"Do NOT restate or restart.]\n\n{prefill}"
            )
        return prompt

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

        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

        full_prompt = self._build_prompt(prompt, prefill)

        # Callers can override max_turns per-call via kwargs
        turns = kwargs.pop("max_turns", self._max_turns)

        options = ClaudeAgentOptions(
            cwd=self._cwd,
            system_prompt=system,
            model=self.model_name,
            max_turns=turns,
            permission_mode="auto",
        )

        result_text = ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = "end_turn"
        turn_count = 0

        for attempt in range(self._max_retries + 1):
            try:
                async def _run_query() -> None:
                    nonlocal result_text, stop_reason, input_tokens, output_tokens, turn_count
                    async for message in query(prompt=full_prompt, options=options):
                        msg_type = type(message).__name__

                        if isinstance(message, ResultMessage):
                            result_text = message.result or ""
                            stop_reason = message.stop_reason or "end_turn"
                            self._logger.info(
                                "  [agent-sdk] result received (%d chars, stop=%s)",
                                len(result_text), stop_reason,
                            )
                        elif isinstance(message, AssistantMessage):
                            turn_count += 1
                            # Log tool usage if present
                            content_types = []
                            for block in getattr(message, "content", []):
                                block_type = type(block).__name__
                                content_types.append(block_type)
                                if block_type == "ToolUseBlock":
                                    tool_name = getattr(block, "name", "unknown")
                                    self._logger.info(
                                        "  [agent-sdk] turn %d: using tool '%s'",
                                        turn_count, tool_name,
                                    )
                                elif block_type == "TextBlock":
                                    text_len = len(getattr(block, "text", ""))
                                    if text_len > 0:
                                        self._logger.info(
                                            "  [agent-sdk] turn %d: thinking (%d chars)",
                                            turn_count, text_len,
                                        )
                            if message.usage:
                                input_tokens = message.usage.get("input_tokens", 0)
                                output_tokens = message.usage.get("output_tokens", 0)
                        else:
                            self._logger.debug(
                                "  [agent-sdk] message: %s", msg_type,
                            )

                await asyncio.wait_for(_run_query(), timeout=self._timeout)
                break  # success
            except TimeoutError:
                if attempt < self._max_retries:
                    self._logger.warning(
                        "Agent SDK timeout (attempt %d/%d, %.0fs)",
                        attempt + 1, self._max_retries, self._timeout,
                    )
                else:
                    raise APITimeoutError(
                        f"Agent SDK timed out after {self._timeout}s"
                    ) from None
            except Exception as exc:
                # Log the full error with stderr if available
                stderr = getattr(exc, "stderr", None) or getattr(exc, "output", None) or ""
                self._logger.warning(
                    "[agent-sdk] error (attempt %d/%d): %s"
                    "\n  stderr: %s"
                    "\n  prompt: %d chars | system: %d chars",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                    str(stderr)[:500],
                    len(full_prompt),
                    len(system or ""),
                )
                if attempt < self._max_retries:
                    delay = min(2.0**attempt, 8.0)
                    await asyncio.sleep(delay)
                else:
                    raise self._translate_error(exc) from exc

        elapsed = time.monotonic() - t_start

        # Strip prefill echo if the model repeated it
        if prefill and result_text.startswith(prefill):
            result_text = result_text[len(prefill) :]

        self._logger.info(
            "[agent-sdk] done: %.1fs | %d turns | in=%d out=%d | %d chars",
            elapsed, turn_count, input_tokens, output_tokens, len(result_text),
        )

        return GenerationResult(
            text=result_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            model=self.model_name,
            stop_reason=stop_reason,
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
        """
        Stream generation via the Agent SDK.

        The SDK provides message-level streaming (not token-level), so each
        AssistantMessage with text content is yielded as one StreamChunk.
        The final chunk carries token counts.
        """
        self._reset_cancel()

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        full_prompt = self._build_prompt(prompt, prefill)
        accumulated = prefill or ""

        turns = kwargs.pop("max_turns", self._max_turns)

        options = ClaudeAgentOptions(
            cwd=self._cwd,
            system_prompt=system,
            model=self.model_name,
            max_turns=turns,
            permission_mode="auto",
        )

        input_tokens = 0
        output_tokens = 0
        stop_reason = "end_turn"

        async for message in query(prompt=full_prompt, options=options):
            if self.is_cancelled:
                break

            if isinstance(message, AssistantMessage):
                # Extract text from content blocks
                for block in message.content:
                    if isinstance(block, TextBlock):
                        delta = block.text
                        accumulated += delta
                        yield StreamChunk(delta=delta, accumulated=accumulated)

                if message.usage:
                    input_tokens = message.usage.get("input_tokens", 0)
                    output_tokens = message.usage.get("output_tokens", 0)

            elif isinstance(message, ResultMessage):
                stop_reason = message.stop_reason or "end_turn"
                # If result has text we haven't seen via AssistantMessage blocks
                if message.result and message.result not in accumulated:
                    delta = message.result
                    accumulated += delta
                    yield StreamChunk(delta=delta, accumulated=accumulated)

        # Final sentinel chunk with usage
        yield StreamChunk(
            delta="",
            accumulated=accumulated,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_final=True,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _translate_error(exc: Exception) -> AdapterError:
        """Convert Agent SDK exceptions into DeepForge exceptions."""
        exc_str = str(exc)
        if "not found" in exc_str.lower() or "cli" in exc_str.lower():
            return APIConnectionError(
                f"Claude Code CLI error: {exc}. Ensure 'claude' is installed and authenticated."
            )
        if "timeout" in exc_str.lower():
            return APITimeoutError(f"Agent SDK timeout: {exc}")
        return AdapterError(f"Agent SDK error: {exc}")
