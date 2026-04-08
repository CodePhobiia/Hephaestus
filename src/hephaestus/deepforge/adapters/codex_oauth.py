"""Native Codex OAuth adapter for Hephaestus.

This adapter uses a small Node bridge script that calls the same underlying
pi-ai/OpenClaw Codex OAuth transport stack used by OpenClaw's `openai-codex`
provider. Unlike `CodexCliAdapter`, this does NOT shell out to `codex exec`.
It performs native `openai-codex-responses` calls against chatgpt.com/backend-api
using the user's OAuth tokens from ~/.codex/auth.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from hephaestus.deepforge.adapters.base import (
    BaseAdapter,
    GenerationResult,
    ModelCapability,
    ModelConfig,
    StreamChunk,
)
from hephaestus.deepforge.exceptions import AdapterError, AuthenticationError

logger = logging.getLogger(__name__)


CODEX_OAUTH_MODELS: dict[str, ModelConfig] = {
    "gpt-5.4": ModelConfig(
        name="gpt-5.4",
        provider="openai-codex",
        context_window=1_050_000,
        max_output_tokens=128_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
    "gpt-5.4-mini": ModelConfig(
        name="gpt-5.4-mini",
        provider="openai-codex",
        context_window=200_000,
        max_output_tokens=64_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.STREAMING,
            ModelCapability.FUNCTION_CALLING,
            ModelCapability.EXTENDED_THINKING,
        },
    ),
}


class CodexOAuthToolCall:
    def __init__(self, id: str, name: str, input: dict[str, Any]) -> None: # noqa: A002 # noqa: A002
        self.id = id
        self.name = name
        self.input = input


class CodexOAuthToolGenerationResult(GenerationResult):
    def __init__(
        self,
        *,
        text: str,
        content_blocks: list[dict[str, Any]],
        tool_calls: list[CodexOAuthToolCall],
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
        stop_reason: str,
        raw: Any = None,
    ) -> None:
        super().__init__(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=model,
            stop_reason=stop_reason,
            raw=raw,
        )
        self.content_blocks = content_blocks
        self.tool_calls = tool_calls


class CodexOAuthAdapter(BaseAdapter):
    """Native OAuth-backed Codex adapter via bridge script."""

    def __init__(
        self,
        model: str | ModelConfig = "gpt-5.4",
        *,
        timeout: float = 300.0,
        max_retries: int = 2,
        bridge_script: str | Path | None = None,
        fallback_to_cli: bool = False,
        reasoning: str = "xhigh",
        reasoning_effort: str | None = "xhigh",
        reasoning_summary: str | None = "auto",
    ) -> None:
        if isinstance(model, str):
            config = CODEX_OAUTH_MODELS.get(model)
            if config is None:
                config = ModelConfig(
                    name=model,
                    provider="openai-codex",
                    context_window=200_000,
                    max_output_tokens=64_000,
                    input_cost_per_million=0.0,
                    output_cost_per_million=0.0,
                    capabilities={
                        ModelCapability.STRUCTURED_OUTPUT,
                        ModelCapability.STREAMING,
                        ModelCapability.FUNCTION_CALLING,
                        ModelCapability.EXTENDED_THINKING,
                    },
                )
        else:
            config = model

        super().__init__(config, api_key=None, timeout=timeout, max_retries=max_retries)
        self._node_bin = shutil.which("node")
        if not self._node_bin:
            raise AuthenticationError(
                "Node.js is required for Codex OAuth bridge but `node` is not on PATH."
            )
        self._bridge = Path(
            bridge_script
            or Path(__file__).resolve().parents[4] / "scripts" / "codex_oauth_bridge.mjs"
        )
        if not self._bridge.is_file():
            raise AuthenticationError(f"Codex OAuth bridge script not found: {self._bridge}")
        # Strict bridge mode: if OAuth is selected, stay on OAuth.
        # Keep the flag for backwards compatibility, but do not silently
        # fall back to a different transport.
        self._fallback_to_cli = fallback_to_cli
        self._reasoning = reasoning
        self._reasoning_effort = reasoning_effort
        self._reasoning_summary = reasoning_summary
        auth_path = Path.home() / ".codex" / "auth.json"
        if not auth_path.exists():
            raise AuthenticationError(
                "Codex auth not found in ~/.codex/auth.json. Run `codex login` first."
            )

    async def _bridge_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            self._node_bin,
            str(self._bridge),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        data = json.dumps(payload).encode("utf-8")
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(data), timeout=self._timeout
            )
        except TimeoutError as exc:
            proc.kill()
            raise AdapterError(f"Codex OAuth bridge timed out after {self._timeout}s") from exc

        stdout = stdout_b.decode("utf-8", errors="replace").strip()
        stderr = stderr_b.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            # Bridge prints JSON error payload to stdout when it can.
            try:
                parsed = json.loads(stdout) if stdout else {}
                error_text = parsed.get("error") or stderr or f"bridge exit {proc.returncode}"
                stack_text = parsed.get("stack") or ""
                if stack_text:
                    error_text = f"{error_text}\n{stack_text}"
            except Exception:
                error_text = stderr or stdout or f"bridge exit {proc.returncode}"
            raise AdapterError(f"Codex OAuth bridge failed: {error_text}")

        try:
            parsed = json.loads(stdout)
        except Exception as exc:
            raise AdapterError(f"Codex OAuth bridge returned invalid JSON: {stdout[:500]}") from exc

        if not parsed.get("ok"):
            raise AdapterError(parsed.get("error") or "Codex OAuth bridge returned ok=false")
        return parsed["result"]

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        **kwargs: Any,
    ) -> CodexOAuthToolGenerationResult:
        t0 = time.monotonic()
        try:
            result = await self._bridge_call(
                {
                    "kind": "tools",
                    "model": self.model_name,
                    "system": system,
                    "messages": messages,
                    "tools": tools or [],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "reasoning": kwargs.get("reasoning", self._reasoning),
                    "reasoning_effort": kwargs.get("reasoning_effort", self._reasoning_effort),
                    "reasoning_summary": kwargs.get("reasoning_summary", self._reasoning_summary),
                    "session_id": kwargs.get("session_id"),
                }
            )
        except Exception as exc:
            self._logger.exception(
                "Codex OAuth bridge failed during generate_with_tools | model=%s",
                self.model_name,
            )
            raise AdapterError(
                f"Codex OAuth bridge failed during tool-use generation: {exc}"
            ) from exc

        tool_calls = [
            CodexOAuthToolCall(
                id=str(tc.get("id", "")),
                name=str(tc.get("name", "")),
                input=dict(tc.get("input", {}) or {}),
            )
            for tc in result.get("tool_calls", [])
        ]
        content_blocks = list(result.get("content_blocks", []) or [])
        self._logger.debug(
            "Codex OAuth generate_with_tools: %.2fs | in=%d out=%d tools=%d",
            time.monotonic() - t0,
            int(result.get("input_tokens", 0) or 0),
            int(result.get("output_tokens", 0) or 0),
            len(tool_calls),
        )
        return CodexOAuthToolGenerationResult(
            text=str(result.get("text", "")),
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            input_tokens=int(result.get("input_tokens", 0) or 0),
            output_tokens=int(result.get("output_tokens", 0) or 0),
            cost_usd=float(result.get("cost_usd", 0.0) or 0.0),
            model=str(result.get("model", self.model_name)),
            stop_reason=str(result.get("stop_reason", "stop")),
            raw=result,
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
        t0 = time.monotonic()
        try:
            result = await self._bridge_call(
                {
                    "kind": "prompt",
                    "model": self.model_name,
                    "system": system,
                    "prompt": prompt,
                    "prefill": prefill,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "reasoning": kwargs.get("reasoning", self._reasoning),
                    "reasoning_effort": kwargs.get("reasoning_effort", self._reasoning_effort),
                    "reasoning_summary": kwargs.get("reasoning_summary", self._reasoning_summary),
                    "session_id": kwargs.get("session_id"),
                }
            )
        except Exception as exc:
            self._logger.exception(
                "Codex OAuth bridge failed during generate | model=%s",
                self.model_name,
            )
            raise AdapterError(
                f"Codex OAuth bridge failed during prompt generation: {exc}"
            ) from exc

        self._logger.debug(
            "Codex OAuth generate: %.2fs | in=%d out=%d",
            time.monotonic() - t0,
            int(result.get("input_tokens", 0) or 0),
            int(result.get("output_tokens", 0) or 0),
        )
        text = str(result.get("text", ""))
        if prefill and text.startswith(prefill):
            text = text[len(prefill) :]
        return GenerationResult(
            text=text,
            input_tokens=int(result.get("input_tokens", 0) or 0),
            output_tokens=int(result.get("output_tokens", 0) or 0),
            cost_usd=float(result.get("cost_usd", 0.0) or 0.0),
            model=str(result.get("model", self.model_name)),
            stop_reason=str(result.get("stop_reason", "stop")),
            raw=result,
        )

    def _reset_cancel(self):
        """Reset cancellation flag from previous call."""
        self._cancelled = False

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
        proc = await asyncio.create_subprocess_exec(
            self._node_bin,
            str(self._bridge),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        payload = {
            "kind": "prompt_stream",
            "model": self.model_name,
            "system": system,
            "prompt": prompt,
            "prefill": prefill,
            "max_tokens": max_tokens,
            "reasoning": kwargs.get("reasoning", self._reasoning),
            "reasoning_effort": kwargs.get("reasoning_effort", self._reasoning_effort),
            "reasoning_summary": kwargs.get("reasoning_summary", self._reasoning_summary),
            "session_id": kwargs.get("session_id"),
        }
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(payload).encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        accumulated = ""
        final_result: dict[str, Any] | None = None
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if event.get("type") == "delta":
                delta = str(event.get("delta", ""))
                accumulated = str(event.get("accumulated", accumulated + delta))
                yield StreamChunk(delta=delta, accumulated=accumulated)
            elif event.get("type") == "final":
                final_result = dict(event.get("result", {}) or {})

        stderr = ""
        if proc.stderr is not None:
            stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        rc = await proc.wait()
        if rc != 0:
            self._logger.error(
                "Codex OAuth stream bridge failed | model=%s rc=%s stderr=%s",
                self.model_name,
                rc,
                stderr,
            )
            raise AdapterError(f"Codex OAuth stream bridge failed: {stderr or rc}")

        if final_result is None:
            # fallback to non-streaming if bridge emitted nothing useful
            result = await self.generate(
                prompt,
                system=system,
                prefill=prefill,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            yield StreamChunk(delta=result.text, accumulated=result.text)
            yield StreamChunk(
                delta="",
                accumulated=result.text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                is_final=True,
                stop_reason=result.stop_reason,
            )
            return

        final_text = str(final_result.get("text", accumulated))
        if prefill and final_text.startswith(prefill):
            final_text = final_text[len(prefill) :]
        yield StreamChunk(
            delta="",
            accumulated=final_text,
            input_tokens=int(final_result.get("input_tokens", 0) or 0),
            output_tokens=int(final_result.get("output_tokens", 0) or 0),
            is_final=True,
            stop_reason=str(final_result.get("stop_reason", "stop")),
        )


__all__ = [
    "CodexOAuthAdapter",
    "CODEX_OAUTH_MODELS",
    "CodexOAuthToolGenerationResult",
    "CodexOAuthToolCall",
]
