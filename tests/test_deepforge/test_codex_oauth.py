"""Tests for native Codex OAuth adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hephaestus.deepforge.adapters.codex_oauth import CodexOAuthAdapter
from hephaestus.deepforge.exceptions import AdapterError, AuthenticationError


class TestCodexOAuthAdapter:
    @pytest.fixture
    def patched_env(self, tmp_path, monkeypatch):
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"access_token": "a", "refresh_token": "r"},
                }
            )
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/node" if name == "node" else None
        )
        bridge = tmp_path / "bridge.mjs"
        bridge.write_text("// bridge")
        return bridge

    def test_instantiation(self, patched_env):
        adapter = CodexOAuthAdapter("gpt-5.4", bridge_script=patched_env)
        assert adapter.model_name == "gpt-5.4"
        assert adapter.config.provider == "openai-codex"

    def test_missing_node_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(AuthenticationError):
            CodexOAuthAdapter("gpt-5.4", bridge_script=tmp_path / "missing.mjs")

    def test_missing_bridge_raises(self, tmp_path, monkeypatch):
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text(
            '{"auth_mode":"chatgpt","tokens":{"access_token":"a","refresh_token":"r"}}'
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
        with pytest.raises(AuthenticationError):
            CodexOAuthAdapter("gpt-5.4", bridge_script=tmp_path / "missing.mjs")

    def test_missing_auth_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node")
        bridge = tmp_path / "bridge.mjs"
        bridge.write_text("// bridge")
        with pytest.raises(AuthenticationError):
            CodexOAuthAdapter("gpt-5.4", bridge_script=bridge)

    @pytest.mark.asyncio
    async def test_generate_success(self, patched_env):
        adapter = CodexOAuthAdapter("gpt-5.4", bridge_script=patched_env)
        with patch.object(
            adapter,
            "_bridge_call",
            new=AsyncMock(
                return_value={
                    "text": "ok",
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.0,
                    "model": "gpt-5.4",
                    "stop_reason": "stop",
                }
            ),
        ):
            result = await adapter.generate("hi")
        assert result.text == "ok"
        assert result.input_tokens == 10

    @pytest.mark.asyncio
    async def test_generate_with_tools_success(self, patched_env):
        adapter = CodexOAuthAdapter("gpt-5.4", bridge_script=patched_env)
        with patch.object(
            adapter,
            "_bridge_call",
            new=AsyncMock(
                return_value={
                    "text": "",
                    "content_blocks": [
                        {"type": "tool_use", "id": "1", "name": "read_file", "input": {"path": "x"}}
                    ],
                    "tool_calls": [{"id": "1", "name": "read_file", "input": {"path": "x"}}],
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cost_usd": 0.0,
                    "model": "gpt-5.4",
                    "stop_reason": "toolUse",
                }
            ),
        ):
            result = await adapter.generate_with_tools(
                [{"role": "user", "content": "read file"}], tools=[]
            )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"

    @pytest.mark.asyncio
    async def test_bridge_failure_no_fallback(self, patched_env):
        adapter = CodexOAuthAdapter("gpt-5.4", bridge_script=patched_env, fallback_to_cli=False)
        with patch.object(adapter, "_bridge_call", new=AsyncMock(side_effect=AdapterError("boom"))):
            with pytest.raises(AdapterError):
                await adapter.generate("hi")

    @pytest.mark.asyncio
    async def test_generate_stream_fallback(self, patched_env):
        adapter = CodexOAuthAdapter("gpt-5.4", bridge_script=patched_env)
        with patch.object(
            adapter,
            "generate",
            new=AsyncMock(
                return_value=type(
                    "R",
                    (),
                    {"text": "hello", "input_tokens": 1, "output_tokens": 1, "stop_reason": "stop"},
                )()
            ),
        ):
            chunks = []
            async for chunk in adapter.generate_stream("hi"):
                chunks.append(chunk)
        assert chunks[-1].is_final
        assert chunks[0].accumulated == "hello"
