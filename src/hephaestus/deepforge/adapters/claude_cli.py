"""
Claude CLI adapter for DeepForge.

Routes API calls through the local ``claude`` CLI (Claude Code), using the
user's Max/Pro subscription via OAuth.  No API keys required — authenticates
through Claude Code's own token refresh mechanism.

Key features:
- Zero API key setup — uses ``claude --print`` with the user's subscription
- Supports system prompts and assistant prefill via prompt construction
- Non-streaming (collects full response from CLI stdout)
- Automatic JSON output parsing when requested
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
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
    AuthenticationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model configs (costs are zero — subscription-based)
# ---------------------------------------------------------------------------

CLAUDE_CLI_MODELS: dict[str, ModelConfig] = {
    "claude-sonnet-4-6": ModelConfig(
        name="claude-sonnet-4-6",
        provider="claude-cli",
        context_window=200_000,
        max_output_tokens=16_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
        },
    ),
    "claude-opus-4-6": ModelConfig(
        name="claude-opus-4-6",
        provider="claude-cli",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
        },
    ),
    "claude-haiku-4-5": ModelConfig(
        name="claude-haiku-4-5",
        provider="claude-cli",
        context_window=200_000,
        max_output_tokens=8192,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.PREFILL,
            ModelCapability.STREAMING,
        },
    ),
}


def _find_claude_cli() -> str:
    """Locate the claude CLI binary."""
    path = shutil.which("claude")
    if not path:
        raise AuthenticationError(
            "Claude CLI (claude) not found on PATH. "
            "Install it from https://claude.ai/claude-code"
        )
    return path


class ClaudeCliAdapter(BaseAdapter):
    """
    Adapter that routes DeepForge calls through ``claude --print``.

    Uses the locally installed Claude Code CLI, which authenticates via
    the user's Claude Max/Pro subscription OAuth token.  This means
    **zero API key configuration** — if ``claude`` works on your machine,
    Hephaestus works too.

    Parameters
    ----------
    model:
        Model name (key into ``CLAUDE_CLI_MODELS``) or a custom
        :class:`ModelConfig`.
    model_flag:
        Explicit ``--model`` flag value passed to the CLI.  If ``None``,
        the CLI's default model is used (usually Sonnet).
    timeout:
        Per-call timeout in seconds (default 120).
    max_retries:
        Retry count on transient failures (default 2).
    """

    def __init__(
        self,
        model: str | ModelConfig = "claude-sonnet-4-6",
        *,
        model_flag: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
    ) -> None:
        if isinstance(model, str):
            config = CLAUDE_CLI_MODELS.get(model)
            if config is None:
                config = ModelConfig(
                    name=model,
                    provider="claude-cli",
                    context_window=200_000,
                    max_output_tokens=16_000,
                    input_cost_per_million=0.0,
                    output_cost_per_million=0.0,
                    capabilities={ModelCapability.PREFILL, ModelCapability.STREAMING},
                )
        else:
            config = model

        super().__init__(config, api_key=None, timeout=timeout, max_retries=max_retries)
        self._model_flag = model_flag
        self._claude_bin = _find_claude_cli()

        logger.info(
            "Claude CLI adapter: model=%s, binary=%s",
            self.model_name,
            self._claude_bin,
        )

    # ------------------------------------------------------------------
    # Core: build prompt and call CLI
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        prompt: str,
        system: str | None,
        prefill: str | None,
    ) -> str:
        """
        Combine system, user prompt, and prefill into a single text block
        that Claude CLI will process.
        """
        parts: list[str] = []

        if system:
            parts.append(f"<system>\n{system}\n</system>\n")

        parts.append(prompt)

        if prefill:
            parts.append(
                f"\n\n[IMPORTANT: Begin your response EXACTLY with the following text, "
                f"then continue seamlessly from where it leaves off. "
                f"Do NOT restate or restart.]\n\n{prefill}"
            )

        return "\n".join(parts)

    async def _call_cli(self, full_prompt: str, max_tokens: int) -> str:
        """Run ``claude --print -p <prompt>`` and return stdout."""
        cmd = [
            self._claude_bin,
            "--print",
            "--permission-mode", "bypassPermissions",
            "-p",
            full_prompt,
        ]
        if self._model_flag:
            cmd.extend(["--model", self._model_flag])

        self._logger.debug("Claude CLI call: %d chars prompt", len(full_prompt))

        t_start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise AdapterError(
                f"Claude CLI timed out after {self._timeout}s"
            )
        except FileNotFoundError:
            raise AuthenticationError(
                f"Claude CLI binary not found at {self._claude_bin}"
            )

        elapsed = time.monotonic() - t_start
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            self._logger.warning(
                "Claude CLI exited %d in %.1fs: %s",
                proc.returncode,
                elapsed,
                stderr[:200],
            )
            raise AdapterError(
                f"Claude CLI failed (exit {proc.returncode}): {stderr[:500]}"
            )

        self._logger.debug(
            "Claude CLI completed in %.2fs, %d chars output",
            elapsed,
            len(stdout),
        )
        return stdout

    # ------------------------------------------------------------------
    # generate()
    # ------------------------------------------------------------------

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
        """Generate via Claude CLI."""
        self._reset_cancel()

        full_prompt = self._build_prompt(prompt, system, prefill)
        text = await self._call_cli(full_prompt, max_tokens)

        # Strip prefill echo if present
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]

        # Rough token estimates (4 chars ≈ 1 token)
        in_tokens = len(full_prompt) // 4
        out_tokens = len(text) // 4

        return GenerationResult(
            text=text,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=0.0,  # subscription-based
            model=self.model_name,
            stop_reason="stop",
        )

    # ------------------------------------------------------------------
    # generate_stream() — fake streaming (collect then yield)
    # ------------------------------------------------------------------

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
        """Fake streaming: run CLI, yield result as single chunk."""
        result = await self.generate(
            prompt,
            system=system,
            prefill=prefill,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        accumulated = (prefill or "") + result.text

        yield StreamChunk(
            delta=result.text,
            accumulated=accumulated,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            is_final=True,
            stop_reason="stop",
        )
