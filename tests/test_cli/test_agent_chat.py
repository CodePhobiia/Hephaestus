from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_cli.test_repl import _console, _make_report, _make_session


def _state_with_current_invention() -> object:
    from hephaestus.cli.repl import InventionEntry

    state = _make_session()
    state.inventions.append(InventionEntry(problem="current problem", report=_make_report()))
    state.current_idx = 0
    return state


class TestAgentChatTools:
    @pytest.mark.asyncio
    async def test_calculate_tool(self) -> None:
        from hephaestus.cli.agent_chat import AgentChat

        agent = AgentChat(_console(), _state_with_current_invention())
        result = await agent._tool_calculate({"expression": "2 * (3 + 4)"})

        payload = json.loads(result.content)
        assert payload["result"] == 14
        assert "evaluated to 14" in result.summary

    @pytest.mark.asyncio
    async def test_save_note_tool(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from hephaestus.cli.agent_chat import AgentChat

        heph_dir = tmp_path / ".hephaestus"
        monkeypatch.setattr("hephaestus.cli.agent_chat.HEPHAESTUS_DIR", heph_dir)
        monkeypatch.setattr("hephaestus.cli.agent_chat.ensure_dirs", lambda: None)

        agent = AgentChat(_console(), _state_with_current_invention())
        result = await agent._tool_save_note({"note": "Remember the pressure threshold."})

        payload = json.loads(result.content)
        note_path = Path(payload["path"])
        assert note_path.exists()
        assert "pressure threshold" in note_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_read_file_restricted_to_hephaestus(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from hephaestus.cli.agent_chat import AgentChat

        heph_dir = tmp_path / ".hephaestus"
        notes_dir = heph_dir / "notes"
        notes_dir.mkdir(parents=True)
        note_path = notes_dir / "saved.md"
        note_path.write_text("saved note", encoding="utf-8")

        monkeypatch.setattr("hephaestus.cli.agent_chat.HEPHAESTUS_DIR", heph_dir)

        agent = AgentChat(_console(), _state_with_current_invention())
        result = await agent._tool_read_file({"path": "notes/saved.md"})
        payload = json.loads(result.content)
        assert payload["content"] == "saved note"

        with pytest.raises(ValueError, match="inside ~/.hephaestus"):
            await agent._tool_read_file({"path": "../outside.txt"})

    @pytest.mark.asyncio
    async def test_compare_inventions_uses_previous_session_invention(self) -> None:
        from hephaestus.cli.agent_chat import AgentChat
        from hephaestus.cli.repl import InventionEntry

        state = _make_session()
        first = _make_report(problem="first problem", name="First Invention", source="Biology")
        second = _make_report(problem="second problem", name="Second Invention", source="Physics")
        state.inventions.append(InventionEntry(problem="first problem", report=first))
        state.inventions.append(InventionEntry(problem="second problem", report=second))
        state.current_idx = 1

        agent = AgentChat(_console(), state)
        result = await agent._tool_compare_inventions({})

        payload = json.loads(result.content)
        assert payload["current"]["name"] == "Second Invention"
        assert payload["other"]["name"] == "First Invention"
        assert payload["source"] == "session"

    @pytest.mark.asyncio
    async def test_export_tool_writes_markdown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from hephaestus.cli.agent_chat import AgentChat

        inventions_dir = tmp_path / "inventions"
        inventions_dir.mkdir(parents=True)
        monkeypatch.setattr("hephaestus.cli.agent_chat.INVENTIONS_DIR", inventions_dir)
        monkeypatch.setattr("hephaestus.cli.agent_chat.ensure_dirs", lambda: None)

        agent = AgentChat(_console(), _state_with_current_invention())
        result = await agent._tool_export({"format": "markdown", "filename": "agent-export"})

        payload = json.loads(result.content)
        export_path = Path(payload["path"])
        assert export_path.exists()
        assert export_path.suffix == ".md"


class TestAgentChatIntegration:
    @pytest.mark.asyncio
    async def test_repl_chat_entrypoint_uses_agent_chat(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import hephaestus.cli.agent_chat as agent_chat_module
        from hephaestus.cli.repl import InventionEntry, _chat_about_invention

        called = {"run": False}

        class DummyAgentChat:
            def __init__(self, console: object, state: object) -> None:
                self.console = console
                self.state = state

            async def run(self) -> None:
                called["run"] = True

        monkeypatch.setattr(agent_chat_module, "AgentChat", DummyAgentChat)

        state = _make_session()
        state.inventions.append(InventionEntry(problem="test", report=_make_report()))
        state.current_idx = 0

        await _chat_about_invention(_console(), state)
        assert called["run"] is True
