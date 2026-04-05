"""Tests for Codex CLI adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hephaestus.deepforge.adapters.codex_cli import (
    CodexCliAdapter,
    _detect_codex_auth,
)
from hephaestus.deepforge.exceptions import AdapterError, AuthenticationError


class TestCodexAuthDetection:
    def test_detect_false_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _detect_codex_auth() is False

    def test_detect_true_with_chatgpt_tokens(self, tmp_path, monkeypatch):
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"id_token": "abc"},
                }
            )
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _detect_codex_auth() is True


class TestCodexCliAdapter:
    @pytest.fixture
    def patched_env(self, tmp_path, monkeypatch):
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"id_token": "abc"},
                }
            )
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/codex" if name == "codex" else None
        )
        return tmp_path

    def test_instantiation(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        assert adapter.model_name == "gpt-5.4"
        assert adapter.config.provider == "codex-cli"

    def test_unknown_model_becomes_custom(self, patched_env):
        adapter = CodexCliAdapter("gpt-custom")
        assert adapter.model_name == "gpt-custom"

    def test_missing_binary_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(AuthenticationError):
            CodexCliAdapter("gpt-5.4")

    def test_missing_auth_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/codex")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with pytest.raises(AuthenticationError):
            CodexCliAdapter("gpt-5.4")

    @pytest.mark.asyncio
    async def test_generate_success(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        with patch.object(adapter, "_call_cli", new=AsyncMock(return_value="hello world")):
            result = await adapter.generate("say hello")
        assert result.text == "hello world"
        assert result.cost_usd == 0.0
        assert result.model == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_generate_strips_prefill(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        with patch.object(adapter, "_call_cli", new=AsyncMock(return_value="PREFIXrest")):
            result = await adapter.generate("p", prefill="PREFIX")
        assert result.text == "rest"

    @pytest.mark.asyncio
    async def test_generate_stream(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        with patch.object(
            adapter,
            "generate",
            new=AsyncMock(return_value=MagicMock(text="out", stop_reason="end_turn")),
        ):
            chunks = []
            async for chunk in adapter.generate_stream("p"):
                chunks.append(chunk)
        assert chunks[0].accumulated == "out"
        assert chunks[-1].is_final

    @pytest.mark.asyncio
    async def test_call_cli_nonzero_exit(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"boom"))
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            with pytest.raises(AdapterError):
                await adapter._call_cli("prompt", 100)

    @pytest.mark.asyncio
    async def test_call_cli_timeout(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError())
        proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            with pytest.raises(AdapterError):
                await adapter._call_cli("prompt", 100)

    @pytest.mark.asyncio
    async def test_call_cli_parses_transcript(self, patched_env):
        adapter = CodexCliAdapter("gpt-5.4")
        proc = MagicMock()
        proc.returncode = 0
        stdout = b"OpenAI Codex\nuser\nprompt\ncodex\nfinal answer\ntokens used\n123\n"
        proc.communicate = AsyncMock(return_value=(stdout, b""))
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            text = await adapter._call_cli("prompt", 100)
        assert text == "final answer"
