"""Codex CLI adapter for DeepForge.

Routes generation through the local ``codex`` CLI, using the user's Codex/
ChatGPT OAuth session (typically GPT Pro / GPT Plus-backed) from ``~/.codex``.
No API key required.

Key features:
- Zero API key setup — uses local Codex CLI auth/session
- Supports system prompts and structured output via ``--output-schema``
- Non-streaming generation (full stdout collection)
- Subscription-backed / OAuth-backed usage path
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import tempfile
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


CODEX_CLI_MODELS: dict[str, ModelConfig] = {
    "gpt-5.4": ModelConfig(
        name="gpt-5.4",
        provider="codex-cli",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.STREAMING,
        },
    ),
    "gpt-5.4-mini": ModelConfig(
        name="gpt-5.4-mini",
        provider="codex-cli",
        context_window=200_000,
        max_output_tokens=32_000,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        capabilities={
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.STREAMING,
        },
    ),
}


def _find_codex_cli() -> str:
    path = shutil.which("codex")
    if not path:
        raise AuthenticationError(
            "Codex CLI (codex) not found on PATH. Install @openai/codex and login first."
        )
    return path


def _detect_codex_auth() -> bool:
    auth = Path.home() / ".codex" / "auth.json"
    if not auth.exists():
        return False
    try:
        data = json.loads(auth.read_text())
        return data.get("auth_mode") == "chatgpt" and bool(data.get("tokens", {}).get("id_token"))
    except Exception:
        return False


class CodexCliAdapter(BaseAdapter):
    """Adapter that routes DeepForge calls through ``codex exec``.

    Uses the locally installed Codex CLI, which authenticates via the user's
    ChatGPT/Codex OAuth session. This means zero API key configuration if
    ``codex exec`` already works on the machine.
    """

    def __init__(
        self,
        model: str | ModelConfig = "gpt-5.4",
        *,
        timeout: float = 300.0,
        max_retries: int = 2,
    ) -> None:
        if isinstance(model, str):
            config = CODEX_CLI_MODELS.get(model)
            if config is None:
                config = ModelConfig(
                    name=model,
                    provider="codex-cli",
                    context_window=200_000,
                    max_output_tokens=32_000,
                    input_cost_per_million=0.0,
                    output_cost_per_million=0.0,
                    capabilities={ModelCapability.STRUCTURED_OUTPUT, ModelCapability.STREAMING},
                )
        else:
            config = model

        super().__init__(config, api_key=None, timeout=timeout, max_retries=max_retries)
        self._codex_bin = _find_codex_cli()
        if not _detect_codex_auth():
            raise AuthenticationError(
                "Codex auth not found in ~/.codex/auth.json. Run `codex login` or use ChatGPT auth first."
            )

    def _build_prompt(self, prompt: str, system: str | None, prefill: str | None) -> str:
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

    async def _call_cli(
        self,
        full_prompt: str,
        max_tokens: int,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        cmd = [
            self._codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "-m",
            self.model_name,
        ]

        schema_file_name: str | None = None
        if output_schema is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as schema_file:
                json.dump(output_schema, schema_file)
                schema_file_name = schema_file.name
            cmd.extend(["--output-schema", schema_file_name])

        cmd.append(full_prompt)

        t_start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except TimeoutError as err:
            raise AdapterError(f"Codex CLI timed out after {self._timeout}s") from err
        except FileNotFoundError as err:
            raise AuthenticationError(f"Codex CLI binary not found at {self._codex_bin}") from err
        finally:
            if schema_file_name is not None:
                with contextlib.suppress(Exception):
                    Path(schema_file_name).unlink(missing_ok=True)

        elapsed = time.monotonic() - t_start
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise AdapterError(
                f"Codex CLI failed (exit {proc.returncode}) after {elapsed:.1f}s: {stderr[:500]}"
            )

        # Codex prints a transcript and ends with the final answer. For simple exec
        # prompts this is usually just the answer, but trim common scaffolding.
        # Prefer the last non-empty line block after 'codex'.
        if "\ncodex\n" in stdout:
            stdout = stdout.split("\ncodex\n", 1)[-1].strip()
        if "\ntokens used\n" in stdout:
            stdout = stdout.split("\ntokens used\n", 1)[0].strip()
        elif stdout.endswith("tokens used"):
            stdout = stdout.rsplit("tokens used", 1)[0].strip()

        return stdout

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
        full_prompt = self._build_prompt(prompt, system, prefill)
        output_schema = kwargs.get("output_schema")
        text = await self._call_cli(full_prompt, max_tokens, output_schema=output_schema)
        if prefill and text.startswith(prefill):
            text = text[len(prefill) :]
        return GenerationResult(
            text=text,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model=self.model_name,
            stop_reason="end_turn",
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
        # Simple non-streaming fallback
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
            is_final=True,
            input_tokens=0,
            output_tokens=0,
            stop_reason=result.stop_reason,
        )


__all__ = ["CodexCliAdapter", "CODEX_CLI_MODELS"]
